"""Importação do relatório de posição exportado pela Área do Investidor da B3.

O relatório é uma foto da posição: não traz data nem preço de compra. Por isso a
importação reconcilia a foto com as boletas (`Order`) do usuário, criando apenas a
diferença de quantidade, e marca os custos como estimados.
"""

import re
import unicodedata
import zipfile
from collections import defaultdict
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import List, Optional

from django.db import transaction
from django.utils import timezone
from openpyxl import load_workbook

from app.models import Asset, AssetPrice
from wallet.models import AssetConsolidatedValue, Order
from wallet.positions import summarize_orders

MAX_UNCOMPRESSED_BYTES = 50 * 1024 * 1024
MAX_VOLUME = Decimal("9999.9999")
MAX_PRICE = Decimal("999999.99")
MAX_NAME_LENGTH = 64
MAX_TICKER_LENGTH = 8
MAX_BROKER_LENGTH = 32
TOTAL_TOLERANCE = Decimal("0.01")
NOMINAL_PRICE_THRESHOLD = Decimal(100)

BUY = 1
SELL = -1

INDEXES = {"IPCA": "I", "PREFIXADO": "P", "SELIC": "S"}
FIXED_INCOME_TYPES = ("CDB", "LCA", "LCI")
BROKERS = (("NU INVESTIMENTOS", "Nu Invest"), ("XP", "XP"), ("RICO", "Rico"))

VARIABLE_INCOME_SHEETS = {"acoes": "AC", "bdr": "BDR", "etf": "ETF", "fundo de investimento": "FII"}
FIXED_INCOME_SHEET = "renda fixa"
TREASURY_SHEET = "tesouro direto"

COL_PRODUCT = "produto"
COL_INSTITUTION = "instituicao"
COL_QUANTITY = "quantidade"
COL_CODE = "codigo de negociacao"
COL_CLOSE = "preco de fechamento"
COL_VALUE = "valor atualizado"
COL_CNPJ_COMPANY = "cnpj da empresa"
COL_CNPJ_FUND = "cnpj do fundo"
COL_RF_CODE = "codigo"
COL_INDEX = "indexador"
COL_ISSUE_DATE = "data de emissao"
COL_MATURITY = "vencimento"
COL_ISSUER = "emissor"
COL_APPLIED = "valor aplicado"
COL_TYPE = "tipo"
TREASURY_ISSUER = "Tesouro Nacional"
# Ordem de preferência das colunas de preço e valor da aba Renda Fixa.
RF_PRICE_COLUMNS = (
    ("preco atualizado curva", "valor atualizado curva"),
    ("preco atualizado mtm", "valor atualizado mtm"),
    ("preco atualizado fechamento", "valor atualizado fechamento"),
)


class ImportFileError(Exception):
    """O arquivo ou os parâmetros enviados não podem ser processados."""


@dataclass
class ParsedPosition:
    sheet: str
    row: int
    name: str
    broker: str
    asset_type: str
    quantity: Decimal
    unit_price: Decimal
    value: Decimal
    description: str
    issue_date: Optional[date] = None
    maturity_date: Optional[date] = None
    index: Optional[str] = None
    fixed_income_type: Optional[str] = None
    applied_value: Optional[Decimal] = None
    cnpj: Optional[str] = None
    company_name: Optional[str] = None
    category: Optional[str] = None
    issuer: Optional[str] = None

    @property
    def is_market_asset(self):
        return self.asset_type != "RF"


@dataclass
class RowError:
    sheet: str
    row: int
    name: Optional[str]
    message: str


@dataclass
class SheetSummary:
    sheet: str
    rows: int = 0
    total: Decimal = Decimal(0)
    footer_total: Optional[Decimal] = None

    @property
    def matches_footer(self):
        if self.footer_total is None:
            return None
        return abs(self.total - self.footer_total) <= TOTAL_TOLERANCE


@dataclass
class ParsedFile:
    positions: List[ParsedPosition] = field(default_factory=list)
    errors: List[RowError] = field(default_factory=list)
    sheets: List[SheetSummary] = field(default_factory=list)
    snapshot_date: Optional[date] = None


@dataclass
class PlannedOrder:
    position: ParsedPosition
    order_type: int
    volume: Decimal
    price: Decimal
    date: date
    current_volume: Decimal


@dataclass
class MissingPosition:
    name: str
    broker: str
    asset_type: str
    volume: Decimal
    price: Optional[Decimal]
    description: Optional[str]
    possible_duplicate: bool

    @property
    def key(self):
        return f"{self.name}|{self.broker}"


@dataclass
class ImportPlan:
    snapshot_date: date
    positions: List[ParsedPosition]
    new: List[PlannedOrder]
    adjustments: List[PlannedOrder]
    unchanged: List[ParsedPosition]
    missing: List[MissingPosition]
    errors: List[RowError]
    sheets: List[SheetSummary]


def _normalize(text):
    decomposed = unicodedata.normalize("NFKD", str(text))
    without_accents = "".join(c for c in decomposed if not unicodedata.combining(c))
    return " ".join(without_accents.lower().split())


def _text(value):
    if value is None:
        return None
    text = str(value).strip()
    return None if text in ("", "-") else text


def _decimal(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float, Decimal)):
        return Decimal(str(value))
    text = _text(value)
    if text is None:
        return None
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def _date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = _text(value)
    if text is None:
        return None
    try:
        return datetime.strptime(text, "%d/%m/%Y").date()
    except ValueError:
        return None


def _money(value):
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _volume(value):
    return value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def _broker(institution):
    upper = institution.upper()
    for prefix, broker in BROKERS:
        if upper.startswith(prefix):
            return broker
    return institution[:MAX_BROKER_LENGTH]


def _format_cnpj(cnpj):
    if not cnpj:
        return None
    digits = re.sub(r"\D", "", cnpj).zfill(14)
    return f"{digits[:2]}.{digits[2:5]}.{digits[5:8]}/{digits[8:12]}-{digits[12:]}"


def _company_name(product, code):
    prefix = f"{code} - "
    return product[len(prefix):] if product.startswith(prefix) else product


def _snapshot_date_from(filename, workbook):
    match = re.search(r"posicao-(\d{4}-\d{2}-\d{2})", filename or "")
    if match:
        try:
            return datetime.strptime(match.group(1), "%Y-%m-%d").date()
        except ValueError:
            pass
    created = workbook.properties.created
    return created.date() if created else timezone.localdate()


class _Row:
    def __init__(self, columns, values):
        self.columns = columns
        self.values = values

    def get(self, column):
        index = self.columns.get(column)
        if index is None or index >= len(self.values):
            return None
        return self.values[index]


def _parse_common(row):
    """Retorna (produto, corretora, quantidade), lançando ValueError se forem inválidos."""
    product = _text(row.get(COL_PRODUCT))
    if not product:
        raise ValueError("Produto não informado")
    quantity = _decimal(row.get(COL_QUANTITY))
    if quantity is None or quantity <= 0:
        raise ValueError("Quantidade inválida")
    quantity = _volume(quantity)
    if quantity > MAX_VOLUME:
        raise ValueError(f"Quantidade acima do limite de {MAX_VOLUME}")
    return product, _broker(_text(row.get(COL_INSTITUTION))), quantity


def _unit_price(unit_price, value, quantity):
    price = unit_price if unit_price is not None else value / quantity
    if price > MAX_PRICE:
        raise ValueError(f"Preço acima do limite de {MAX_PRICE}")
    return price


def _parse_variable_income(row, sheet, number, asset_type):
    product, broker, quantity = _parse_common(row)
    code = _text(row.get(COL_CODE))
    if not code:
        raise ValueError("Código de Negociação não informado")
    code = code.upper()
    if len(code) > MAX_TICKER_LENGTH:
        raise ValueError(f"Código de Negociação com mais de {MAX_TICKER_LENGTH} caracteres")

    close = _decimal(row.get(COL_CLOSE))
    value = _decimal(row.get(COL_VALUE))
    if value is None and close is not None:
        value = _money(close * quantity)
    if value is None:
        raise ValueError("Preço e valor não informados")

    return ParsedPosition(
        sheet=sheet,
        row=number,
        name=code,
        broker=broker,
        asset_type=asset_type,
        quantity=quantity,
        unit_price=_unit_price(close, value, quantity),
        value=value,
        description=product,
        cnpj=_format_cnpj(_text(row.get(COL_CNPJ_COMPANY)) or _text(row.get(COL_CNPJ_FUND))),
        company_name=_company_name(product, code),
        # Em ETFs, "Tipo" diz o que o fundo replica (Ações, Internacional...); nas demais abas é ON, PN, Cotas.
        category=_text(row.get(COL_TYPE)) if asset_type == "ETF" else None,
    )


def _parse_index(row):
    raw = _text(row.get(COL_INDEX))
    index = INDEXES.get((raw or "").upper())
    if index is None:
        raise ValueError(f"Indexador não suportado: {raw or 'não informado'}")
    return index


def _parse_maturity(row):
    maturity = _date(row.get(COL_MATURITY))
    if maturity is None:
        raise ValueError("Vencimento inválido")
    return maturity


def _parse_fixed_income(row, sheet, number):
    product, broker, quantity = _parse_common(row)
    code = _text(row.get(COL_RF_CODE))
    if not code:
        raise ValueError("Código não informado")
    code = code.upper()

    prefix = product.split(" ")[0].upper()
    if prefix not in FIXED_INCOME_TYPES:
        raise ValueError(f"Tipo de renda fixa não suportado: {prefix}")

    unit_price = value = None
    for price_column, value_column in RF_PRICE_COLUMNS:
        value = _decimal(row.get(value_column))
        if value is not None:
            unit_price = _decimal(row.get(price_column))
            break
    if value is None:
        raise ValueError("Valor atualizado não informado")

    maturity = _parse_maturity(row)
    issuer = _text(row.get(COL_ISSUER))
    description = product if not issuer or issuer in product else f"{product} ({issuer})"

    return ParsedPosition(
        sheet=sheet,
        row=number,
        name=code,
        broker=broker,
        asset_type="RF",
        quantity=quantity,
        unit_price=_unit_price(unit_price, value, quantity),
        value=value,
        description=f"{description} - venc. {maturity.strftime('%d/%m/%Y')}",
        issue_date=_date(row.get(COL_ISSUE_DATE)),
        maturity_date=maturity,
        index=_parse_index(row),
        fixed_income_type=prefix,
        issuer=issuer[:MAX_NAME_LENGTH] if issuer else None,
    )


def _parse_treasury(row, sheet, number):
    product, broker, quantity = _parse_common(row)
    name = product.upper()
    if len(name) > MAX_NAME_LENGTH:
        raise ValueError(f"Produto com mais de {MAX_NAME_LENGTH} caracteres")

    value = _decimal(row.get(COL_VALUE))
    if value is None:
        raise ValueError("Valor Atualizado não informado")

    return ParsedPosition(
        sheet=sheet,
        row=number,
        name=name,
        broker=broker,
        asset_type="RF",
        quantity=quantity,
        unit_price=_unit_price(None, value, quantity),
        value=value,
        description=product,
        maturity_date=_parse_maturity(row),
        index=_parse_index(row),
        fixed_income_type="TD",
        applied_value=_decimal(row.get(COL_APPLIED)),
        issuer=TREASURY_ISSUER,
    )


def _row_parser(normalized_sheet):
    if normalized_sheet in VARIABLE_INCOME_SHEETS:
        asset_type = VARIABLE_INCOME_SHEETS[normalized_sheet]
        return (
            lambda row, sheet, number: _parse_variable_income(row, sheet, number, asset_type),
            (COL_CODE, COL_CLOSE, COL_VALUE),
        )
    if normalized_sheet == FIXED_INCOME_SHEET:
        return _parse_fixed_income, (COL_RF_CODE, COL_INDEX, COL_MATURITY)
    if normalized_sheet == TREASURY_SHEET:
        return _parse_treasury, (COL_INDEX, COL_MATURITY, COL_VALUE)
    return None, ()


def _footer_total(row_values, next_values):
    for index, value in enumerate(row_values):
        if isinstance(value, str) and _normalize(value) == "total":
            return _decimal(next_values[index]) if index < len(next_values) else None
    return None


def _parse_sheet(worksheet, parse_row, required, result):
    summary = SheetSummary(sheet=worksheet.title)
    result.sheets.append(summary)

    worksheet.reset_dimensions()
    rows = list(worksheet.iter_rows(values_only=True))
    if not rows:
        return

    columns = {}
    for index, header in enumerate(rows[0]):
        if header is not None:
            columns.setdefault(_normalize(header), index)

    absent = [c for c in (COL_PRODUCT, COL_INSTITUTION, COL_QUANTITY) + tuple(required) if c not in columns]
    if absent:
        result.errors.append(
            RowError(worksheet.title, 1, None, f"Colunas não encontradas: {', '.join(absent)}")
        )
        return

    for offset, values in enumerate(rows[1:], start=1):
        row = _Row(columns, values)
        if _text(row.get(COL_INSTITUTION)) is None:
            footer = rows[offset + 1] if offset + 1 < len(rows) else ()
            total = _footer_total(values, footer)
            if total is not None:
                summary.footer_total = total
            continue

        number = offset + 1
        try:
            position = parse_row(row, worksheet.title, number)
        except ValueError as error:
            name = _text(row.get(COL_CODE)) or _text(row.get(COL_RF_CODE)) or _text(row.get(COL_PRODUCT))
            result.errors.append(RowError(worksheet.title, number, name.upper() if name else None, str(error)))
            continue

        result.positions.append(position)
        summary.rows += 1
        summary.total += position.value


def parse_position_file(file, filename=None):
    """Lê o relatório de posição, sem acessar o banco de dados."""
    try:
        with zipfile.ZipFile(file) as archive:
            uncompressed = sum(info.file_size for info in archive.infolist())
        if uncompressed > MAX_UNCOMPRESSED_BYTES:
            raise ImportFileError("Arquivo muito grande")
        file.seek(0)
        workbook = load_workbook(file, read_only=True, data_only=True)
    except ImportFileError:
        raise
    except Exception:
        raise ImportFileError("Não foi possível ler o arquivo. Envie o .xlsx exportado pela B3.")

    try:
        result = ParsedFile(snapshot_date=_snapshot_date_from(filename, workbook))
        for worksheet in workbook.worksheets:
            parse_row, required = _row_parser(_normalize(worksheet.title))
            if parse_row:
                _parse_sheet(worksheet, parse_row, required, result)
    finally:
        workbook.close()

    if not result.sheets:
        raise ImportFileError("O arquivo não tem nenhuma aba de posição da B3.")
    return result


def _merge_by_key(positions):
    """Soma linhas do mesmo ativo na mesma corretora (ex.: duas contas na mesma instituição)."""
    merged = {}
    for position in positions:
        key = (position.name, position.broker)
        current = merged.get(key)
        if current is None:
            merged[key] = position
            continue
        applied = None
        if current.applied_value is not None and position.applied_value is not None:
            applied = current.applied_value + position.applied_value
        merged[key] = replace(
            current,
            quantity=current.quantity + position.quantity,
            value=current.value + position.value,
            applied_value=applied,
        )
    return list(merged.values())


def _initial_price(position):
    if position.fixed_income_type == "TD":
        if position.applied_value is not None:
            return _money(position.applied_value / position.quantity)
        return _money(position.unit_price)
    if position.asset_type == "RF":
        # O PU de emissão não vem no arquivo; CDB/LCI/LCA costumam ser emitidos a R$ 1 ou R$ 1.000.
        return Decimal(1000) if position.unit_price >= NOMINAL_PRICE_THRESHOLD else Decimal(1)
    return _money(position.unit_price)


def _initial_date(position, snapshot_date):
    if position.asset_type == "RF" and position.fixed_income_type != "TD" and position.issue_date:
        return position.issue_date
    return snapshot_date


def _last_known_price(user, order):
    if order.asset_type == "RF":
        consolidated = (
            AssetConsolidatedValue.objects.filter(user=user, name=order.name, volume__gt=0)
            .order_by("date")
            .last()
        )
        if consolidated:
            return _money(consolidated.value / consolidated.volume)
    else:
        price = AssetPrice.objects.filter(ticker=order.name).order_by("date").last()
        if price:
            return _money(Decimal(str(price.close)))
    return order.price


def _reject_over_limit(positions, errors):
    """Rejeita ativos cuja quantidade somada entre corretoras não cabe em AssetConsolidatedValue."""
    totals = defaultdict(Decimal)
    for position in positions:
        totals[position.name] += position.quantity
    accepted = []
    for position in positions:
        if totals[position.name] > MAX_VOLUME:
            errors.append(
                RowError(position.sheet, position.row, position.name, f"Quantidade acima do limite de {MAX_VOLUME}")
            )
        else:
            accepted.append(position)
    return accepted


def build_plan(user, parsed, snapshot_date=None):
    """Compara o arquivo com as boletas do usuário, sem gravar nada."""
    snapshot_date = snapshot_date or parsed.snapshot_date
    errors = list(parsed.errors)
    positions = _reject_over_limit(_merge_by_key(parsed.positions), errors)

    orders_by_key = defaultdict(list)
    asset_type_by_name = {}
    for order in Order.objects.filter(user=user).order_by("date", "id"):
        orders_by_key[(order.name, order.broker)].append(order)
        asset_type_by_name.setdefault(order.name, order.asset_type)

    # O mesmo ativo não pode ter duas classes: as boletas existentes definem a dele
    # (ex.: um BDR registrado antes como INT), senão o filtro por classe o dividiria.
    positions = [
        replace(position, asset_type=asset_type_by_name.get(position.name, position.asset_type))
        for position in positions
    ]

    new, adjustments, unchanged = [], [], []
    for position in positions:
        orders = orders_by_key.get((position.name, position.broker), [])
        balance = sum((o.volume * o.order_type for o in orders), Decimal(0))
        difference = position.quantity - balance

        if difference == 0:
            unchanged.append(position)
        elif balance == 0:
            new.append(
                PlannedOrder(
                    position=position,
                    order_type=BUY,
                    volume=position.quantity,
                    price=_initial_price(position),
                    date=_initial_date(position, snapshot_date),
                    current_volume=balance,
                )
            )
        else:
            adjustments.append(
                PlannedOrder(
                    position=position,
                    order_type=BUY if difference > 0 else SELL,
                    volume=abs(difference),
                    price=_money(position.unit_price),
                    date=snapshot_date,
                    current_volume=balance,
                )
            )

    in_file = {(p.name, p.broker) for p in positions}
    # Linha com erro não permite concluir que a posição deixou de existir.
    with_error = {e.name for e in errors if e.name}
    missing = []
    for (name, broker), orders in orders_by_key.items():
        balance = sum((o.volume * o.order_type for o in orders), Decimal(0))
        if balance <= 0 or (name, broker) in in_file or name in with_error:
            continue
        last_order = max(orders, key=lambda o: (o.date, o.id))
        if last_order.maturity_date and last_order.maturity_date < timezone.localdate():
            continue
        missing.append(
            MissingPosition(
                name=name,
                broker=broker,
                asset_type=last_order.asset_type,
                volume=balance,
                price=_last_known_price(user, last_order),
                description=last_order.description,
                possible_duplicate=last_order.asset_type == "RF",
            )
        )

    return ImportPlan(
        snapshot_date=snapshot_date,
        positions=positions,
        new=new,
        adjustments=adjustments,
        unchanged=unchanged,
        missing=sorted(missing, key=lambda m: m.key),
        errors=errors,
        sheets=parsed.sheets,
    )


def _build_order(user, planned):
    position = planned.position
    return Order(
        user=user,
        name=position.name,
        broker=position.broker,
        asset_type=position.asset_type,
        order_type=planned.order_type,
        date=planned.date,
        price=planned.price,
        volume=planned.volume,
        description=position.description,
        maturity_date=position.maturity_date,
        index=position.index,
        fixed_income_type=position.fixed_income_type,
        issuer=position.issuer,
        cost_estimated=True,
    )


def _sync_asset(position):
    asset, _ = Asset.objects.get_or_create(ticker=position.name)
    updates = {
        "asset_class": position.asset_type,
        "trading_name": (position.company_name or "")[:32] or None,
        "company_name": (position.company_name or "")[:64] or None,
        "cnpj": position.cnpj,
        "category": (position.category or "")[:32] or None,
    }
    changed = [name for name, value in updates.items() if value and not getattr(asset, name)]
    for name in changed:
        setattr(asset, name, updates[name])
    if changed:
        asset.save(update_fields=changed)


def _sync_market_data(positions, snapshot_date):
    for position in positions:
        if not position.is_market_asset:
            continue
        _sync_asset(position)
        AssetPrice.objects.get_or_create(
            ticker=position.name,
            date=snapshot_date,
            defaults={"close": float(position.unit_price)},
        )


def _sync_consolidated_values(user, plan, closed_names):
    file_totals = {}
    for position in plan.positions:
        value, quantity, _ = file_totals.get(position.name, (Decimal(0), Decimal(0), ""))
        file_totals[position.name] = (value + position.value, quantity + position.quantity, position.asset_type)

    for name in set(file_totals) | set(closed_names):
        orders = list(Order.objects.filter(user=user, name=name))
        quantity, invested = summarize_orders(orders)
        if name in file_totals:
            file_value, file_quantity, asset_type = file_totals[name]
            # A diferença só existe se houver saldo em corretora ausente do arquivo e não zerada.
            value = file_value * quantity / file_quantity
        else:
            value = Decimal(0)
            asset_type = orders[0].asset_type
        AssetConsolidatedValue.objects.update_or_create(
            user=user,
            name=name,
            date=plan.snapshot_date,
            defaults={
                "asset_type": asset_type,
                "value": _money(value),
                "volume": quantity,
                "invested": _money(invested),
            },
        )


def _close_order(user, missing, snapshot_date):
    last_order = (
        Order.objects.filter(user=user, name=missing.name, broker=missing.broker).order_by("date", "id").last()
    )
    return Order(
        user=user,
        name=missing.name,
        broker=missing.broker,
        asset_type=missing.asset_type,
        order_type=SELL,
        date=snapshot_date,
        price=missing.price,
        volume=missing.volume,
        description=missing.description,
        maturity_date=last_order.maturity_date,
        index=last_order.index,
        fixed_income_type=last_order.fixed_income_type,
        issuer=last_order.issuer,
        cost_estimated=True,
    )


def _backfill_issuers(user, positions):
    """Completa o emissor de boletas gravadas sem ele; a reconciliação só olha a quantidade."""
    for position in positions:
        if position.issuer:
            Order.objects.filter(
                user=user, name=position.name, broker=position.broker, issuer__isnull=True
            ).update(issuer=position.issuer)


def apply_plan(user, plan, close_missing=()):
    """Grava o plano de forma atômica. `close_missing` lista as chaves de `MissingPosition` a zerar."""
    if not plan.positions:
        raise ImportFileError("O arquivo não tem nenhuma posição válida para importar.")

    missing_by_key = {missing.key: missing for missing in plan.missing}
    unknown = [key for key in close_missing if key not in missing_by_key]
    if unknown:
        raise ImportFileError(f"Posições a zerar não encontradas: {', '.join(unknown)}")
    to_close = [missing_by_key[key] for key in close_missing]

    with transaction.atomic():
        orders = [_build_order(user, planned) for planned in plan.new + plan.adjustments]
        orders += [_close_order(user, missing, plan.snapshot_date) for missing in to_close]
        Order.objects.bulk_create(orders)
        _backfill_issuers(user, plan.positions)
        _sync_market_data(plan.positions, plan.snapshot_date)
        _sync_consolidated_values(user, plan, {missing.name for missing in to_close})

    return len(orders)


def _planned_to_dict(planned):
    position = planned.position
    return {
        "name": position.name,
        "broker": position.broker,
        "asset_type": position.asset_type,
        "description": position.description,
        "order_type": planned.order_type,
        "date": planned.date,
        "price": float(planned.price),
        "volume": float(planned.volume),
        "current_volume": float(planned.current_volume),
        "file_volume": float(position.quantity),
    }


def plan_to_dict(plan):
    total = sum((p.value for p in plan.positions), Decimal(0))
    return {
        "snapshot_date": plan.snapshot_date,
        "total_value": float(total),
        "positions": len(plan.positions),
        "new": [_planned_to_dict(planned) for planned in plan.new],
        "adjustments": [_planned_to_dict(planned) for planned in plan.adjustments],
        "unchanged": [
            {
                "name": position.name,
                "broker": position.broker,
                "asset_type": position.asset_type,
                "description": position.description,
                "volume": float(position.quantity),
            }
            for position in plan.unchanged
        ],
        "missing": [
            {
                "key": missing.key,
                "name": missing.name,
                "broker": missing.broker,
                "asset_type": missing.asset_type,
                "description": missing.description,
                "volume": float(missing.volume),
                "price": float(missing.price) if missing.price is not None else None,
                "possible_duplicate": missing.possible_duplicate,
            }
            for missing in plan.missing
        ],
        "errors": [
            {"sheet": error.sheet, "row": error.row, "name": error.name, "message": error.message}
            for error in plan.errors
        ],
        "sheets": [
            {
                "sheet": sheet.sheet,
                "rows": sheet.rows,
                "total": float(sheet.total),
                "footer_total": float(sheet.footer_total) if sheet.footer_total is not None else None,
                "matches_footer": sheet.matches_footer,
            }
            for sheet in plan.sheets
        ],
    }
