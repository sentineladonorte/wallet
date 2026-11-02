"""Importa o extrato de movimentação da B3 e deriva dele as boletas, o preço médio e os proventos.

O extrato sozinho não reconstrói a posição: encerramentos e trocas de ticker nem sempre têm saída
registrada, e ele não informa vencimentos. Por isso o relatório de posição mais recente acerta o que
restar. As boletas importadas são sempre recriadas a partir de Movement e PositionSnapshot, então
reenviar qualquer arquivo leva ao mesmo resultado.
"""

import hashlib
import re
import unicodedata
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Dict, List

from django.db import transaction
from openpyxl import load_workbook

from wallet.models import Movement, Order, PositionSnapshot

MAX_UNCOMPRESSED_BYTES = 50 * 1024 * 1024
MOVEMENT_SHEET = "movimentacao"
BROKERS = (("NU INVEST", "Nu Invest"), ("EASYNVEST", "Nu Invest"), ("XP", "XP"), ("RICO", "Rico"))
MAX_BROKER_LENGTH = 32
TREASURY_ISSUER = "Tesouro Nacional"
FIXED_INCOME_PREFIXES = ("CDB", "LCA", "LCI")
# O relatório de posição arredonda a quantidade em duas casas.
QUANTITY_TOLERANCE = Decimal("0.011")
PRICE_STEP = Decimal("0.000001")
QUANTITY_STEP = Decimal("0.0001")

REQUIRED_COLUMNS = ("entrada/saida", "data", "movimentacao", "produto", "instituicao", "quantidade")

TRADES = {"transferencia - liquidacao", "compra / venda", "compra", "venda"}
REDEMPTIONS = {"vencimento", "vencimento/resgate saldo em conta", "retirada de custodia"}
TRANSFERS = {"transferencia", "transferencia sem financeiro"}
QUANTITY_EVENTS = {"desdobro", "bonificacao em ativos", "cisao", "incorporacao"}
GROUPING = "grupamento"
BALANCE_UPDATE = "atualizacao"
FRACTION = "fracao em ativos"
REDEMPTION_OR_CASH = "resgate"

INCOME_LABELS = {
    "rendimento": "Rendimentos",
    "dividendo": "Dividendos",
    "dividendo - cancelado": "Dividendos",
    "juros sobre capital proprio": "JCP",
    "pagamento de juros": "Juros de renda fixa",
    "amortizacao": "Amortização",
    "restituicao de capital": "Amortização",
    "leilao de fracao": "Outros",
    "cobranca de taxa semestral": "Taxas",
}
# Sem efeito na carteira: direitos não exercidos e provisões repassadas entre corretoras,
# cujo valor já aparece na linha original do provento.
IGNORED = {
    "direito de subscricao",
    "direitos de subscricao - nao exercido",
    "cessao de direitos",
    "cessao de direitos - solicitada",
    "rendimento - transferido",
    "dividendo - transferido",
    "juros sobre capital proprio - transferido",
}


class MovementFileError(Exception):
    """O arquivo não é um extrato de movimentação válido."""


def _normalize(text):
    decomposed = unicodedata.normalize("NFKD", str(text))
    return " ".join("".join(c for c in decomposed if not unicodedata.combining(c)).lower().split())


def _broker_name(institution):
    upper = institution.upper()
    for prefix, broker in BROKERS:
        if upper.startswith(prefix):
            return broker
    return institution[:MAX_BROKER_LENGTH]


def _decimal(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float, Decimal)):
        return Decimal(str(value))
    text = str(value).strip() if value is not None else ""
    if text in ("", "-"):
        return None
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def _parse_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value).strip(), "%d/%m/%Y").date()
    except ValueError:
        return None


def asset_key(product):
    """CDB - CDBA26 - BANCO X vira CDBA26; Tesouro IPCA+ 2029 fica em maiúsculas; PETR4 - EMPRESA vira PETR4."""
    text = " ".join(str(product).split())
    match = re.match(r"^(?:CDB|LCA|LCI) - ([A-Z0-9]+)", text)
    if match:
        return match.group(1)
    if text.lower().startswith("tesouro"):
        return text.upper()
    return text.split(" - ")[0].strip().upper()


def _issuer(product):
    text = " ".join(str(product).split())
    if text.lower().startswith("tesouro"):
        return TREASURY_ISSUER
    match = re.match(r"^(?:CDB|LCA|LCI) - [A-Z0-9]+ - (.+)$", text)
    return match.group(1)[:64] if match else None


def is_fixed_income(product):
    text = str(product).strip()
    return text.lower().startswith("tesouro") or text[:3] in FIXED_INCOME_PREFIXES


def infer_asset_type(name, product):
    """Classe de um ativo que não está no relatório de posição, deduzida pelo texto do extrato."""
    if is_fixed_income(product):
        return "RF"
    text = _normalize(product)
    if "fundo de indice" in text or " etf " in f" {text} ":
        return "ETF"
    if re.search(r"\bfii\b|imob|fdo inv imob", text):
        return "FII"
    if re.search(r"3[1-9]$", name):
        return "BDR"
    return "AC"


def _fixed_income_type(product):
    text = str(product).strip()
    return "TD" if text.lower().startswith("tesouro") else text[:3]


def _fingerprint(day, movement_type, direction, name, broker, quantity, unit_price, value):
    # O nome do produto fica de fora: a B3 muda o texto do mesmo ativo ao longo do tempo.
    raw = "|".join(
        str(part) for part in (day, _normalize(movement_type), direction, name, broker, quantity, unit_price, value)
    )
    return hashlib.sha256(raw.encode()).hexdigest()


def is_movement_file(file):
    """Diz se o .xlsx é um extrato de movimentação, sem processar as linhas."""
    try:
        file.seek(0)
        workbook = load_workbook(file, read_only=True)
        names = [_normalize(name) for name in workbook.sheetnames]
        workbook.close()
    except Exception:
        return False
    finally:
        file.seek(0)
    return MOVEMENT_SHEET in names


def _read_rows(file):
    try:
        with zipfile.ZipFile(file) as archive:
            if sum(info.file_size for info in archive.infolist()) > MAX_UNCOMPRESSED_BYTES:
                raise MovementFileError("Arquivo muito grande")
        file.seek(0)
        workbook = load_workbook(file, read_only=True, data_only=True)
    except MovementFileError:
        raise
    except Exception:
        raise MovementFileError("Não foi possível ler o arquivo. Envie o .xlsx exportado pela B3.")

    try:
        worksheet = next((ws for ws in workbook.worksheets if _normalize(ws.title) == MOVEMENT_SHEET), None)
        if worksheet is None:
            raise MovementFileError("O arquivo não tem a aba Movimentação.")
        worksheet.reset_dimensions()
        return list(worksheet.iter_rows(values_only=True))
    finally:
        workbook.close()


def parse_movements_file(file):
    """Retorna as linhas únicas do arquivo como Movement ainda não gravados, e as linhas com erro."""
    rows = _read_rows(file)
    if not rows:
        raise MovementFileError("O arquivo está vazio.")

    columns = {_normalize(header): index for index, header in enumerate(rows[0]) if header is not None}
    absent = [column for column in REQUIRED_COLUMNS if column not in columns]
    if absent:
        raise MovementFileError(f"Colunas não encontradas: {', '.join(absent)}")

    def cell(values, column):
        index = columns.get(column)
        return values[index] if index is not None and index < len(values) else None

    movements = []
    errors = []
    copies = Counter()
    for number, values in enumerate(rows[1:], start=2):
        if all(value is None for value in values):
            continue
        product = cell(values, "produto")
        day = _parse_date(cell(values, "data"))
        movement_type = cell(values, "movimentacao")
        direction_text = _normalize(cell(values, "entrada/saida") or "")
        quantity = _decimal(cell(values, "quantidade"))
        institution = cell(values, "instituicao")
        if not (product and day and movement_type and institution) or direction_text not in ("credito", "debito"):
            errors.append({"row": number, "message": "Linha incompleta"})
            continue

        direction = 1 if direction_text == "credito" else -1
        name = asset_key(product)
        broker = _broker_name(str(institution).strip())
        quantity = (quantity or Decimal(0)).quantize(QUANTITY_STEP)
        unit_price = _decimal(cell(values, "preco unitario"))
        value = _decimal(cell(values, "valor da operacao"))
        fingerprint = _fingerprint(day, movement_type, direction, name, broker, quantity, unit_price, value)

        # Texto igual repete a operação; texto diferente para a mesma linha é duplicata da própria B3,
        # que às vezes lista a compra com e sem o emissor.
        copies[(fingerprint, " ".join(str(product).split()))] += 1
        movements.append(
            Movement(
                fingerprint=fingerprint,
                occurrence=copies[(fingerprint, " ".join(str(product).split()))],
                date=day,
                direction=direction,
                movement_type=str(movement_type).strip()[:64],
                name=name[:64],
                product=" ".join(str(product).split())[:128],
                broker=broker,
                quantity=quantity,
                unit_price=unit_price,
                value=value,
            )
        )

    unique = {}
    for movement in movements:
        unique.setdefault((movement.fingerprint, movement.occurrence), movement)
    return list(unique.values()), errors


@dataclass
class OrderSpec:
    name: str
    broker: str
    order_type: int
    kind: str
    volume: Decimal
    price: Decimal
    date: object
    product: str
    note: str = ""
    cost_estimated: bool = False


@dataclass
class Difference:
    name: str
    ledger: Decimal
    snapshot: Decimal
    action: str


@dataclass
class Ledger:
    orders: List[OrderSpec] = field(default_factory=list)
    differences: List[Difference] = field(default_factory=list)
    matched: int = 0
    unknown_types: Dict[str, int] = field(default_factory=dict)
    successions: List[tuple] = field(default_factory=list)


class _LedgerBuilder:
    def __init__(self, movements, snapshot_rows):
        self.movements = sorted(movements, key=lambda m: (m.date, m.id or 0))
        self.snapshot_rows = snapshot_rows
        self.snapshot_date = snapshot_rows[0].date if snapshot_rows else None
        self.snapshot_names = {row.name for row in snapshot_rows}
        self.quantity = defaultdict(Decimal)
        self.cost = defaultdict(Decimal)
        self.products = {}
        self.ledger = Ledger()
        self.unknown = Counter()
        self.reconciled = False
        self.updates_by_day = defaultdict(list)
        self.last_activity = {}
        self.last_seen = {}
        for movement in self.movements:
            kind = _normalize(movement.movement_type)
            if not self.snapshot_date or movement.date <= self.snapshot_date:
                self.last_seen[movement.name] = movement.date
            # Provento pago depois da troca de ticker não indica que o ativo antigo continuou na carteira.
            is_cash_redemption = kind == REDEMPTION_OR_CASH and movement.direction == 1
            if kind not in INCOME_LABELS and kind not in IGNORED and not is_cash_redemption:
                self.last_activity[movement.name] = movement.date
            if kind == BALANCE_UPDATE:
                self.updates_by_day[movement.date].append(movement)

    def _total(self, name):
        return sum((q for (n, _), q in self.quantity.items() if n == name), Decimal(0))

    def _emit(
        self, movement_or_none, name, broker, order_type, kind, volume, price, day, note="", cost_estimated=False
    ):
        self.ledger.orders.append(
            OrderSpec(
                name=name,
                broker=broker,
                order_type=order_type,
                kind=kind,
                volume=volume.quantize(QUANTITY_STEP),
                price=price.quantize(PRICE_STEP),
                date=day,
                product=self.products.get(name, name),
                note=note[:64],
                cost_estimated=cost_estimated,
            )
        )

    def _remove_with_cost(self, name, broker, volume):
        total = self._total(name)
        removed = self.cost[name] * volume / total if total > 0 else Decimal(0)
        self.cost[name] -= min(removed, self.cost[name])
        self.quantity[(name, broker)] -= volume
        return removed

    def _apply_trade(self, movement):
        volume, value = movement.quantity, movement.value
        unit = movement.unit_price or Decimal(0)
        if volume <= 0:
            return
        price = value / volume if value is not None else unit
        if movement.direction == 1:
            self.quantity[(movement.name, movement.broker)] += volume
            self.cost[movement.name] += price * volume
            self._emit(
                movement,
                movement.name,
                movement.broker,
                1,
                Order.KIND_TRADE,
                volume,
                price,
                movement.date,
                movement.movement_type,
            )
            return
        total = self._total(movement.name)
        average = self.cost[movement.name] / total if total > 0 else Decimal(0)
        self._remove_with_cost(movement.name, movement.broker, volume)
        # Vencimento com valor zero: o dinheiro aparece em outra linha do extrato. Não é prejuízo.
        kind = Order.KIND_TRADE if price > 0 else Order.KIND_RECONCILIATION
        self._emit(
            movement,
            movement.name,
            movement.broker,
            -1,
            kind,
            volume,
            price if price > 0 else average,
            movement.date,
            movement.movement_type,
        )

    def _apply_quantity_only(self, movement, kind):
        if movement.quantity <= 0:
            return
        self.quantity[(movement.name, movement.broker)] += movement.quantity * movement.direction
        self._emit(
            movement,
            movement.name,
            movement.broker,
            movement.direction,
            kind,
            movement.quantity,
            Decimal(0),
            movement.date,
            movement.movement_type,
        )

    def _apply_grouping(self, movement):
        # O grupamento informa o saldo final na corretora, não a variação.
        key = (movement.name, movement.broker)
        difference = movement.quantity - self.quantity[key]
        if difference == 0:
            return
        self.quantity[key] = movement.quantity
        order_type = 1 if difference > 0 else -1
        self._emit(
            movement,
            movement.name,
            movement.broker,
            order_type,
            Order.KIND_EVENT,
            abs(difference),
            Decimal(0),
            movement.date,
            movement.movement_type,
        )

    def _old_ticker_for(self, movement):
        """Procura o ticker que deu origem ao novo. Ele saiu da carteira sem baixa no extrato: não está
        na posição atual, tem saldo na mesma corretora e nunca mais teve movimentação depois dessa data."""
        if not self.snapshot_names:
            return None
        day_updates = self.updates_by_day[movement.date]
        same_day, same_quantity = [], []
        for (name, broker), held in self.quantity.items():
            if name == movement.name or broker != movement.broker or held <= 0 or name in self.snapshot_names:
                continue
            if is_fixed_income(self.products.get(name, name)) or self.last_activity[name] > movement.date:
                continue
            if any(
                update.name == name and update.broker == broker and abs(update.quantity - held) < QUANTITY_TOLERANCE
                for update in day_updates
            ):
                same_day.append(name)
            if abs(held - movement.quantity) < QUANTITY_TOLERANCE:
                same_quantity.append(name)
        candidates = same_day or same_quantity
        return candidates[0] if len(candidates) == 1 else None

    def _apply_balance_update(self, movement):
        # "Atualização" repete o saldo quando nada mudou e, quando difere, soma a quantidade informada.
        key = (movement.name, movement.broker)
        if movement.quantity <= 0 or abs(self.quantity[key] - movement.quantity) < QUANTITY_TOLERANCE:
            return
        old = self._old_ticker_for(movement) if self.quantity[key] == 0 else None
        if old is None:
            self.quantity[key] += movement.quantity
            self._emit(
                movement,
                movement.name,
                movement.broker,
                1,
                Order.KIND_EVENT,
                movement.quantity,
                Decimal(0),
                movement.date,
                movement.movement_type,
            )
            return

        held = self.quantity[(old, movement.broker)]
        moved = self._remove_with_cost(old, movement.broker, held)
        average = moved / held if held else Decimal(0)
        self._emit(
            movement,
            old,
            movement.broker,
            -1,
            Order.KIND_SUCCESSION,
            held,
            average,
            movement.date,
            f"Trocado por {movement.name}",
        )
        self.quantity[key] += movement.quantity
        self.cost[movement.name] += moved
        self._emit(
            movement,
            movement.name,
            movement.broker,
            1,
            Order.KIND_SUCCESSION,
            movement.quantity,
            moved / movement.quantity,
            movement.date,
            f"Trocado de {old}",
        )
        self.ledger.successions.append((old, movement.name))

    def _apply(self, movement):
        self.products[movement.name] = movement.product
        kind = _normalize(movement.movement_type)
        if kind in TRADES or kind in REDEMPTIONS or (kind == REDEMPTION_OR_CASH and movement.direction == -1):
            self._apply_trade(movement)
        elif kind in TRANSFERS:
            self._apply_quantity_only(movement, Order.KIND_TRANSFER)
        elif kind in QUANTITY_EVENTS:
            self._apply_quantity_only(movement, Order.KIND_EVENT)
        elif kind == GROUPING:
            self._apply_grouping(movement)
        elif kind == BALANCE_UPDATE:
            self._apply_balance_update(movement)
        elif kind == FRACTION:
            if movement.quantity > 0:
                self._remove_with_cost(movement.name, movement.broker, movement.quantity)
                self._emit(
                    movement,
                    movement.name,
                    movement.broker,
                    -1,
                    Order.KIND_FRACTION,
                    movement.quantity,
                    Decimal(0),
                    movement.date,
                    movement.movement_type,
                )
        elif kind == REDEMPTION_OR_CASH or kind in INCOME_LABELS or kind in IGNORED:
            return
        else:
            self.unknown[movement.movement_type] += 1

    def _reconcile(self):
        """Acerta o saldo com a posição oficial: o relatório é a referência da quantidade."""
        self.reconciled = True
        day = self.snapshot_date
        rows_by_key = {(row.name, row.broker): row for row in self.snapshot_rows}
        names = {name for (name, _), held in self.quantity.items() if held != 0} | self.snapshot_names

        for name in sorted(names):
            brokers = {b for (n, b) in self.quantity if n == name} | {b for (n, b) in rows_by_key if n == name}
            target = {b: (rows_by_key[(name, b)].quantity if (name, b) in rows_by_key else Decimal(0)) for b in brokers}
            held_total = self._total(name)
            target_total = sum(target.values(), Decimal(0))
            excess = {b: self.quantity[(name, b)] - target[b] for b in brokers}
            excess = {b: amount for b, amount in excess.items() if amount != 0}

            if abs(held_total - target_total) < QUANTITY_TOLERANCE:
                if name in self.snapshot_names:
                    self.ledger.matched += 1
                # Mesmo saldo total: o que muda é só em qual corretora ele está, ou o arredondamento.
                for broker, amount in excess.items():
                    self.quantity[(name, broker)] -= amount
                    self._emit(
                        None,
                        name,
                        broker,
                        -1 if amount > 0 else 1,
                        Order.KIND_TRANSFER,
                        abs(amount),
                        Decimal(0),
                        day,
                        "Acerto com a posição da B3",
                    )
                continue

            # Saldo negativo vindo de uma fração é só resíduo, não uma compra sem registro.
            action = "estimated_buy" if target_total > held_total and target_total > 0 else "closed"
            self.ledger.differences.append(Difference(name, held_total, target_total, action))
            if target_total > held_total:
                self._add_missing(name, excess, target_total - held_total, rows_by_key, day)
            else:
                # Sem data de saída no extrato, a última atividade é a melhor estimativa: encerrar na data
                # do relatório criaria no histórico uma queda brusca que nunca aconteceu.
                exit_day = day if target_total > 0 else self.last_seen.get(name, day)
                self._remove_excess(name, excess, held_total - target_total, exit_day)

    def _add_missing(self, name, excess, missing, rows_by_key, day):
        for broker, amount in sorted(excess.items(), key=lambda item: item[1]):
            if amount >= 0 or missing <= 0:
                if amount > 0:
                    self.quantity[(name, broker)] -= amount
                    self._emit(
                        None,
                        name,
                        broker,
                        -1,
                        Order.KIND_TRANSFER,
                        amount,
                        Decimal(0),
                        day,
                        "Acerto com a posição da B3",
                    )
                continue
            needed = -amount
            bought = min(needed, missing)
            row = rows_by_key.get((name, broker))
            price = row.unit_price if row else Decimal(0)
            self.quantity[(name, broker)] += bought
            self.cost[name] += price * bought
            missing -= bought
            self._emit(
                None,
                name,
                broker,
                1,
                Order.KIND_RECONCILIATION,
                bought,
                price,
                day,
                "Sem registro de compra no extrato",
                True,
            )
            if needed > bought:
                self.quantity[(name, broker)] += needed - bought
                self._emit(
                    None,
                    name,
                    broker,
                    1,
                    Order.KIND_TRANSFER,
                    needed - bought,
                    Decimal(0),
                    day,
                    "Acerto com a posição da B3",
                )

    def _remove_excess(self, name, excess, surplus, day):
        for broker, amount in sorted(excess.items(), key=lambda item: -item[1]):
            if amount <= 0:
                if amount < 0:
                    self.quantity[(name, broker)] -= amount
                    self._emit(
                        None,
                        name,
                        broker,
                        1,
                        Order.KIND_TRANSFER,
                        -amount,
                        Decimal(0),
                        day,
                        "Acerto com a posição da B3",
                    )
                continue
            removed = min(amount, surplus)
            total = self._total(name)
            average = self.cost[name] / total if total > 0 else Decimal(0)
            self._remove_with_cost(name, broker, removed)
            surplus -= removed
            self._emit(
                None,
                name,
                broker,
                -1,
                Order.KIND_RECONCILIATION,
                removed,
                average,
                day,
                "Encerrado sem baixa no extrato",
            )
            if amount > removed:
                self.quantity[(name, broker)] -= amount - removed
                self._emit(
                    None,
                    name,
                    broker,
                    -1,
                    Order.KIND_TRANSFER,
                    amount - removed,
                    Decimal(0),
                    day,
                    "Acerto com a posição da B3",
                )

    def build(self):
        for movement in self.movements:
            if self.snapshot_date and not self.reconciled and movement.date > self.snapshot_date:
                self._reconcile()
            self._apply(movement)
        if self.snapshot_date and not self.reconciled:
            self._reconcile()
        self.ledger.unknown_types = dict(self.unknown)
        self.ledger.products = self.products
        return self.ledger


def build_ledger(movements, snapshot_rows):
    """Função pura: transforma movimentações e a foto de posição em boletas, sem gravar nada."""
    return _LedgerBuilder(movements, snapshot_rows).build()


def latest_snapshot(user):
    latest = PositionSnapshot.objects.filter(user=user).order_by("-date").values_list("date", flat=True).first()
    return list(PositionSnapshot.objects.filter(user=user, date=latest)) if latest else []


def _order_from_spec(user, spec, rows_by_name, known_types, issuers):
    row = rows_by_name.get(spec.name)
    asset_type = known_types.get(spec.name) or (row.asset_type if row else infer_asset_type(spec.name, spec.product))
    is_rf = asset_type == "RF"
    return Order(
        user=user,
        name=spec.name,
        broker=spec.broker,
        asset_type=asset_type,
        order_type=spec.order_type,
        date=spec.date,
        price=spec.price,
        volume=spec.volume,
        description=row.description if row and row.description else spec.product,
        maturity_date=row.maturity_date if row else None,
        index=row.index if row else None,
        fixed_income_type=(row.fixed_income_type if row else _fixed_income_type(spec.product)) if is_rf else None,
        issuer=(row.issuer if row and row.issuer else issuers.get(spec.name)) if is_rf else None,
        cost_estimated=spec.cost_estimated,
        source=Order.SOURCE_MOVEMENT,
        kind=spec.kind,
        note=spec.note,
    )


def rebuild_orders(user):
    """Recria as boletas importadas do usuário. Boletas manuais não são tocadas."""
    movements = list(Movement.objects.filter(user=user).order_by("date", "id"))
    rows = latest_snapshot(user)
    ledger = build_ledger(movements, rows)

    rows_by_name = {row.name: row for row in rows}
    issuers = {}
    for movement in movements:
        issuer = _issuer(movement.product)
        if issuer:
            issuers[movement.name] = issuer
    # Um ativo mantém a classe das boletas manuais, para o filtro por classe não o dividir.
    known_types = dict(
        Order.objects.filter(user=user, source=Order.SOURCE_MANUAL).order_by("-date").values_list("name", "asset_type")
    )

    Order.objects.filter(user=user, source__in=[Order.SOURCE_POSITION, Order.SOURCE_MOVEMENT]).delete()
    orders = [_order_from_spec(user, spec, rows_by_name, known_types, issuers) for spec in ledger.orders]
    Order.objects.bulk_create(orders)
    return orders


def _manual_conflicts(user, names):
    rows = Order.objects.filter(user=user, source=Order.SOURCE_MANUAL, name__in=names).values_list("name", flat=True)
    return sorted(Counter(rows).items())


def preview_movements(user, parsed, errors):
    """Calcula o efeito da importação sem gravar nada."""
    existing = list(Movement.objects.filter(user=user).order_by("date", "id"))
    existing_keys = {(m.fingerprint, m.occurrence) for m in existing}
    new = [m for m in parsed if (m.fingerprint, m.occurrence) not in existing_keys]
    rows = latest_snapshot(user)
    ledger = build_ledger(existing + new, rows)
    dates = [m.date for m in parsed]
    names = {spec.name for spec in ledger.orders}

    return {
        "file_type": "movements",
        "total_rows": len(parsed),
        "new_rows": len(new),
        "duplicate_rows": len(parsed) - len(new),
        "first_date": min(dates) if dates else None,
        "last_date": max(dates) if dates else None,
        "errors": errors,
        "unknown_types": ledger.unknown_types,
        "snapshot_date": rows[0].date if rows else None,
        "positions_in_snapshot": len({row.name for row in rows}),
        "positions_matched": ledger.matched,
        "differences": [
            {"name": d.name, "ledger": float(d.ledger), "snapshot": float(d.snapshot), "action": d.action}
            for d in ledger.differences
        ],
        "successions": [{"old": old, "new": new_name} for old, new_name in ledger.successions],
        "orders_replaced": Order.objects.filter(
            user=user, source__in=[Order.SOURCE_POSITION, Order.SOURCE_MOVEMENT]
        ).count(),
        "orders_after": len(ledger.orders),
        "manual_conflicts": [{"name": name, "count": count} for name, count in _manual_conflicts(user, names)],
    }


def import_movements(user, parsed, replace_manual=False):
    """Grava as linhas novas e recalcula as boletas. Retorna (linhas novas, boletas criadas)."""
    existing_keys = set(Movement.objects.filter(user=user).values_list("fingerprint", "occurrence"))
    new = [m for m in parsed if (m.fingerprint, m.occurrence) not in existing_keys]
    for movement in new:
        movement.user = user

    with transaction.atomic():
        Movement.objects.bulk_create(new)
        names = set(Movement.objects.filter(user=user).values_list("name", flat=True))
        if replace_manual:
            Order.objects.filter(user=user, source=Order.SOURCE_MANUAL, name__in=names).delete()
        orders = rebuild_orders(user)
    return len(new), len(orders)


def income_label(movement):
    kind = _normalize(movement.movement_type)
    # Resgate a crédito é o dinheiro de um ativo extinto; a débito é a venda do título, tratada como boleta.
    if kind == REDEMPTION_OR_CASH:
        return "Outros" if movement.direction == 1 else None
    return INCOME_LABELS.get(kind)


def income_value(movement):
    """Valor com sinal; algumas linhas trazem só quantidade e preço unitário."""
    value = movement.value
    if value is None and movement.unit_price is not None:
        value = movement.quantity * movement.unit_price
    return (value or Decimal(0)) * movement.direction


def income_rows(user):
    rows = []
    for movement in Movement.objects.filter(user=user).order_by("-date", "-id"):
        label = income_label(movement)
        if label:
            rows.append((movement, label, income_value(movement)))
    return rows


def income_by_name(user) -> Dict[str, Decimal]:
    totals: Dict[str, Decimal] = defaultdict(Decimal)
    for movement, label, value in income_rows(user):
        if label != "Taxas":
            totals[movement.name] += value
    return totals
