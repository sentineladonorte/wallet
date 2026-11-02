import io
import importlib
from datetime import date, timedelta
from decimal import Decimal
from unittest import mock

from django.apps import apps
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from openpyxl import Workbook

from app.models import Asset, AssetPrice
from app.market_data import MarketDataError
from app.models import MarketDataUpdate
from wallet.b3_import import ImportFileError, apply_plan, build_plan, parse_position_file
from wallet.consolidation import MAX_BACKFILL_DAYS, consolidate_all_users, rebuild_history
from wallet.market_update import run_update, update_status
from wallet.models import AllocationTarget, AssetConsolidatedValue, Movement, Order, PositionSnapshot
from wallet.movements import (
    MovementFileError,
    asset_key,
    build_ledger,
    import_movements,
    infer_asset_type,
    is_movement_file,
    parse_movements_file,
    rebuild_orders,
)
from wallet.positions import realized_gain, summarize_orders

NU = "NU INVESTIMENTOS S.A. - CTVM"
SNAPSHOT = date(2026, 11, 2)
PREVIEW_URL = "/api/orders/import/preview"
CONFIRM_URL = "/api/orders/import/confirm"

STOCK_HEADER = [
    "Produto",
    "Instituição",
    "Conta",
    "Código de Negociação",
    "CNPJ da Empresa",
    "Código ISIN / Distribuição",
    "Tipo",
    "Escriturador",
    "Quantidade",
    "Quantidade Disponível",
    "Quantidade Indisponível",
    "Motivo",
    "Preço de Fechamento",
    "Valor Atualizado",
]
BDR_HEADER = [
    "Produto",
    "Instituição",
    "Conta",
    "Código de Negociação",
    "Código ISIN / Distribuição",
    "Tipo",
    "Escriturador",
    "Quantidade",
    "Quantidade Disponível",
    "Quantidade Indisponível",
    "Motivo",
    "Preço de Fechamento",
    "Valor Atualizado",
]
RF_HEADER = [
    "Produto",
    "Instituição",
    "Emissor",
    "Código",
    "Indexador",
    "Tipo de regime",
    "Data de Emissão",
    "Vencimento",
    "Quantidade",
    "Quantidade Disponível",
    "Quantidade Indisponível",
    "Motivo",
    "Contraparte",
    "Preço Atualizado MTM",
    "Valor Atualizado MTM",
    "Preço Atualizado CURVA",
    "Valor Atualizado CURVA",
    "Preço Atualizado FECHAMENTO",
    "Valor Atualizado FECHAMENTO",
]
TD_HEADER = [
    "Produto",
    "Instituição",
    "Código ISIN",
    "Indexador",
    "Vencimento",
    "Quantidade",
    "Quantidade Disponível",
    "Quantidade Indisponível",
    "Motivo",
    "Valor Aplicado",
    "Valor bruto",
    "Valor líquido",
    "Valor Atualizado",
]


def stock(code="TEST3", quantity=10, close=5.5, institution=NU):
    return [
        f"{code} - EMPRESA TESTE S.A.",
        institution,
        "1",
        code,
        "00000000000191",
        "BRTESTACNOR0 - 1",
        "ON",
        "BANCO",
        quantity,
        quantity,
        "-",
        "-",
        close,
        round(quantity * close, 2),
    ]


def bdr(code="TEST34", quantity=2, close=10.0):
    return [
        f"{code} - EMPRESA INC",
        NU,
        "1",
        code,
        "BRTESTBDR000 - 1",
        "BDR",
        "BANCO",
        quantity,
        quantity,
        "-",
        "-",
        close,
        round(quantity * close, 2),
    ]


def fixed_income(code="CDBTEST1", index="PREFIXADO", quantity=1000, price=1.05, product="CDB - BANCO TESTE S/A"):
    return [
        product,
        NU,
        "BANCO TESTE S/A",
        code,
        index,
        "DEPOSITADO",
        "10/02/2026",
        "10/02/2099",
        quantity,
        quantity,
        "-",
        "-",
        "-",
        "-",
        "-",
        price,
        round(quantity * price, 2),
        "-",
        "-",
    ]


def treasury(product="Tesouro IPCA+ 2099", quantity=0.69, applied=2161.03, value=2722.74):
    return [product, NU, "BRSTNTEST000", "IPCA", "15/05/2099", quantity, quantity, 0, "-", applied, value, value, value]


def footer(header, total):
    blank = [None] * len(header)
    labels = list(blank)
    values = list(blank)
    column = header.index("Valor Atualizado CURVA") if "Valor Atualizado CURVA" in header else len(header) - 1
    labels[column] = "Total"
    values[column] = total
    return [blank, labels, values]


def workbook_bytes(sheets):
    workbook = Workbook()
    workbook.remove(workbook.active)
    for title, rows in sheets.items():
        worksheet = workbook.create_sheet(title)
        for row in rows:
            worksheet.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    return buffer


def parse(sheets, filename="posicao-2026-11-02-13-17-19.xlsx"):
    return parse_position_file(workbook_bytes(sheets), filename)


class ParserTests(TestCase):
    def test_reads_columns_by_header_in_each_sheet(self):
        parsed = parse({"Acoes": [STOCK_HEADER, stock()], "BDR": [BDR_HEADER, bdr()]})

        by_name = {position.name: position for position in parsed.positions}
        self.assertEqual(by_name["TEST3"].asset_type, "AC")
        self.assertEqual(by_name["TEST3"].quantity, Decimal(10))
        self.assertEqual(by_name["TEST3"].unit_price, Decimal("5.5"))
        self.assertEqual(by_name["TEST3"].broker, "Nu Invest")
        self.assertEqual(by_name["TEST3"].cnpj, "00.000.000/0001-91")
        self.assertEqual(by_name["TEST34"].asset_type, "BDR")
        self.assertEqual(by_name["TEST34"].unit_price, Decimal("10.0"))

    def test_ignores_footer_and_compares_total(self):
        parsed = parse({"Acoes": [STOCK_HEADER, stock(), *footer(STOCK_HEADER, 55)]})

        self.assertEqual(len(parsed.positions), 1)
        self.assertEqual(parsed.sheets[0].footer_total, Decimal(55))
        self.assertTrue(parsed.sheets[0].matches_footer)

    def test_flags_total_different_from_footer(self):
        parsed = parse({"Acoes": [STOCK_HEADER, stock(), *footer(STOCK_HEADER, 99)]})

        self.assertFalse(parsed.sheets[0].matches_footer)

    def test_fixed_income_uses_curve_when_mtm_is_dash(self):
        parsed = parse({"Renda Fixa": [RF_HEADER, fixed_income(), *footer(RF_HEADER, 1050)]})

        position = parsed.positions[0]
        self.assertEqual(position.name, "CDBTEST1")
        self.assertEqual(position.value, Decimal("1050.0"))
        self.assertEqual(position.issue_date, date(2026, 2, 10))
        self.assertEqual(position.maturity_date, date(2099, 2, 10))
        self.assertEqual(position.index, "P")
        self.assertEqual(position.fixed_income_type, "CDB")
        self.assertTrue(parsed.sheets[0].matches_footer)

    def test_treasury_index_is_case_insensitive_and_keeps_fraction(self):
        row = treasury("Tesouro Prefixado 2099")
        row[3] = "prefixado"
        parsed = parse({"Tesouro Direto": [TD_HEADER, row]})

        position = parsed.positions[0]
        self.assertEqual(position.name, "TESOURO PREFIXADO 2099")
        self.assertEqual(position.quantity, Decimal("0.69"))
        self.assertEqual(position.index, "P")
        self.assertEqual(position.fixed_income_type, "TD")

    def test_unknown_index_and_type_become_row_errors(self):
        parsed = parse(
            {
                "Renda Fixa": [
                    RF_HEADER,
                    fixed_income("CDBCDI", index="CDI"),
                    fixed_income("CRI1", product="CRI - SECURITIZADORA"),
                    fixed_income("CDBOK"),
                ]
            }
        )

        self.assertEqual([p.name for p in parsed.positions], ["CDBOK"])
        self.assertEqual({e.name for e in parsed.errors}, {"CDBCDI", "CRI1"})
        self.assertIn("CDI", [e.message for e in parsed.errors if e.name == "CDBCDI"][0])

    def test_volume_over_model_limit_becomes_row_error(self):
        parsed = parse({"Acoes": [STOCK_HEADER, stock(quantity=10000)]})

        self.assertEqual(parsed.positions, [])
        self.assertEqual(parsed.errors[0].name, "TEST3")

    def test_missing_column_reports_error_for_sheet(self):
        header = [column for column in STOCK_HEADER if column != "Valor Atualizado"]
        parsed = parse({"Acoes": [header, stock()[:-1]]})

        self.assertEqual(parsed.positions, [])
        self.assertIn("valor atualizado", parsed.errors[0].message)

    def test_absent_sheets_are_accepted(self):
        self.assertEqual(len(parse({"ETF": [BDR_HEADER, bdr()]}).positions), 1)

    def test_no_known_sheet_is_rejected(self):
        with self.assertRaises(ImportFileError):
            parse({"Planilha1": [["a"]]})

    def test_invalid_file_is_rejected(self):
        with self.assertRaises(ImportFileError):
            parse_position_file(io.BytesIO(b"isto nao e um xlsx"), "a.xlsx")

    def test_snapshot_date_comes_from_filename(self):
        self.assertEqual(parse({"Acoes": [STOCK_HEADER]}).snapshot_date, SNAPSHOT)

    def test_snapshot_date_falls_back_to_file_metadata(self):
        workbook_file = workbook_bytes({"Acoes": [STOCK_HEADER]})
        self.assertIsNotNone(parse_position_file(workbook_file, "relatorio.xlsx").snapshot_date)


class ReconciliationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("investidor", password="senha")

    def run_import(self, sheets, close_missing=(), snapshot=SNAPSHOT):
        plan = build_plan(self.user, parse(sheets), snapshot)
        apply_plan(self.user, plan, close_missing)
        return plan

    def test_estimated_cost_rules(self):
        self.run_import(
            {
                "Acoes": [STOCK_HEADER, stock()],
                "Renda Fixa": [
                    RF_HEADER,
                    fixed_income("CDBPU1", quantity=1000, price=1.05),
                    fixed_income("CDBPU1000", quantity=2, price=1814.87),
                ],
                "Tesouro Direto": [TD_HEADER, treasury()],
            }
        )

        orders = {order.name: order for order in Order.objects.filter(user=self.user)}
        self.assertTrue(all(order.cost_estimated for order in orders.values()))

        self.assertEqual(orders["TEST3"].price, Decimal("5.50"))
        self.assertEqual(orders["TEST3"].date, SNAPSHOT)

        self.assertEqual(orders["CDBPU1"].price, Decimal("1.00"))
        self.assertEqual(orders["CDBPU1"].date, date(2026, 2, 10))
        self.assertEqual(orders["CDBPU1000"].price, Decimal("1000.00"))
        self.assertIsNone(orders["CDBPU1"].interest_rate)
        self.assertIn("BANCO TESTE S/A", orders["CDBPU1"].description)

        treasury_order = orders["TESOURO IPCA+ 2099"]
        self.assertEqual(treasury_order.price, Decimal("3131.93"))
        self.assertEqual(treasury_order.volume, Decimal("0.6900"))
        self.assertEqual(treasury_order.date, SNAPSHOT)
        self.assertEqual(treasury_order.fixed_income_type, "TD")

    def test_fixed_income_keeps_issuer_and_etf_gets_category(self):
        etf = bdr("BOVA11")
        etf[5] = "Ações"
        self.run_import(
            {
                "ETF": [BDR_HEADER, etf],
                "Renda Fixa": [RF_HEADER, fixed_income()],
                "Tesouro Direto": [TD_HEADER, treasury()],
            }
        )

        self.assertEqual(Asset.objects.get(ticker="BOVA11").category, "Ações")
        self.assertEqual(Order.objects.get(name="CDBTEST1").issuer, "BANCO TESTE S/A")
        self.assertEqual(Order.objects.get(name="TESOURO IPCA+ 2099").issuer, "Tesouro Nacional")

    def test_reimport_fills_issuer_of_orders_saved_without_it(self):
        sheets = {"Renda Fixa": [RF_HEADER, fixed_income()], "Tesouro Direto": [TD_HEADER, treasury()]}
        self.run_import(sheets)
        Order.objects.filter(user=self.user).update(issuer=None)

        plan = self.run_import(sheets)

        self.assertEqual(plan.new + plan.adjustments, [])
        self.assertEqual(Order.objects.get(name="CDBTEST1").issuer, "BANCO TESTE S/A")
        self.assertEqual(Order.objects.get(name="TESOURO IPCA+ 2099").issuer, "Tesouro Nacional")

    def test_reimport_keeps_issuer_already_set(self):
        sheets = {"Renda Fixa": [RF_HEADER, fixed_income()]}
        self.run_import(sheets)
        Order.objects.filter(user=self.user).update(issuer="EDITADO PELO USUARIO")

        self.run_import(sheets)

        self.assertEqual(Order.objects.get(name="CDBTEST1").issuer, "EDITADO PELO USUARIO")

    def test_first_import_creates_market_data_and_consolidated_value(self):
        self.run_import({"Acoes": [STOCK_HEADER, stock()], "Renda Fixa": [RF_HEADER, fixed_income()]})

        asset = Asset.objects.get(ticker="TEST3")
        self.assertEqual(asset.asset_class, "AC")
        self.assertEqual(asset.company_name, "EMPRESA TESTE S.A.")
        self.assertEqual(AssetPrice.objects.get(ticker="TEST3", date=SNAPSHOT).close, 5.5)
        self.assertFalse(Asset.objects.filter(ticker="CDBTEST1").exists())

        consolidated = AssetConsolidatedValue.objects.get(user=self.user, name="CDBTEST1", date=SNAPSHOT)
        self.assertEqual(consolidated.value, Decimal("1050.00"))
        self.assertEqual(consolidated.invested, Decimal("1000.00"))
        self.assertEqual(consolidated.volume, Decimal("1000"))
        self.assertEqual(consolidated.asset_type, "RF")

    def test_import_does_not_override_existing_market_data(self):
        Asset.objects.create(ticker="TEST3", asset_class="OUTRA", trading_name="NOME ORIGINAL")
        AssetPrice.objects.create(ticker="TEST3", date=SNAPSHOT, close=7.0)

        self.run_import({"Acoes": [STOCK_HEADER, stock()]})

        asset = Asset.objects.get(ticker="TEST3")
        self.assertEqual(asset.asset_class, "OUTRA")
        self.assertEqual(asset.trading_name, "NOME ORIGINAL")
        self.assertEqual(asset.company_name, "EMPRESA TESTE S.A.")
        self.assertEqual(AssetPrice.objects.get(ticker="TEST3", date=SNAPSHOT).close, 7.0)

    def test_reimport_of_same_file_creates_nothing(self):
        sheets = {
            "Acoes": [STOCK_HEADER, stock()],
            "Renda Fixa": [RF_HEADER, fixed_income()],
            "Tesouro Direto": [TD_HEADER, treasury()],
        }
        self.run_import(sheets)
        orders = Order.objects.count()
        consolidated = AssetConsolidatedValue.objects.count()

        plan = self.run_import(sheets)

        self.assertEqual(len(plan.new) + len(plan.adjustments), 0)
        self.assertEqual(len(plan.unchanged), 3)
        self.assertEqual(Order.objects.count(), orders)
        self.assertEqual(AssetConsolidatedValue.objects.count(), consolidated)

    def test_larger_quantity_creates_buy_adjustment(self):
        self.run_import({"Acoes": [STOCK_HEADER, stock(quantity=10)]})
        self.run_import({"Acoes": [STOCK_HEADER, stock(quantity=15, close=6.0)]}, snapshot=date(2026, 11, 3))

        adjustment = Order.objects.filter(user=self.user).order_by("id").last()
        self.assertEqual(adjustment.order_type, 1)
        self.assertEqual(adjustment.volume, Decimal(5))
        self.assertEqual(adjustment.price, Decimal("6.00"))
        self.assertEqual(adjustment.date, date(2026, 11, 3))
        self.assertTrue(adjustment.cost_estimated)

    def test_smaller_quantity_creates_sell_adjustment(self):
        self.run_import({"Acoes": [STOCK_HEADER, stock(quantity=10)]})
        self.run_import({"Acoes": [STOCK_HEADER, stock(quantity=4, close=6.0)]}, snapshot=date(2026, 11, 3))

        adjustment = Order.objects.filter(user=self.user).order_by("id").last()
        self.assertEqual(adjustment.order_type, -1)
        self.assertEqual(adjustment.volume, Decimal(6))

        consolidated = AssetConsolidatedValue.objects.get(user=self.user, name="TEST3", date=date(2026, 11, 3))
        self.assertEqual(consolidated.volume, Decimal(4))
        self.assertEqual(consolidated.value, Decimal("24.00"))
        self.assertEqual(consolidated.invested, Decimal("22.00"))

    def test_adjustment_keeps_asset_type_of_existing_orders(self):
        Order.objects.create(
            user=self.user,
            name="TEST34",
            broker="Nu Invest",
            asset_type="INT",
            order_type=1,
            date=date(2023, 1, 1),
            price=Decimal(8),
            volume=Decimal(1),
        )

        self.run_import({"BDR": [BDR_HEADER, bdr(quantity=2)]})

        self.assertEqual(set(Order.objects.filter(name="TEST34").values_list("asset_type", flat=True)), {"INT"})
        self.assertEqual(AssetConsolidatedValue.objects.get(name="TEST34").asset_type, "INT")

    def test_same_asset_on_other_broker_is_reconciled_separately(self):
        other_broker = stock(quantity=5, institution="XP INVESTIMENTOS")
        self.run_import({"Acoes": [STOCK_HEADER, stock(quantity=10), other_broker]})

        brokers = {order.broker: order.volume for order in Order.objects.filter(user=self.user)}
        self.assertEqual(brokers, {"Nu Invest": Decimal(10), "XP": Decimal(5)})
        consolidated = AssetConsolidatedValue.objects.get(user=self.user, name="TEST3")
        self.assertEqual(consolidated.volume, Decimal(15))

    def test_repeated_rows_of_same_broker_are_summed(self):
        plan = self.run_import({"Acoes": [STOCK_HEADER, stock(quantity=10), stock(quantity=5)]})

        self.assertEqual(len(plan.new), 1)
        self.assertEqual(Order.objects.get(user=self.user).volume, Decimal(15))

    def test_missing_position_is_only_closed_when_selected(self):
        self.run_import({"Acoes": [STOCK_HEADER, stock("OLD3"), stock("KEEP3")]})

        plan = self.run_import({"Acoes": [STOCK_HEADER, stock("KEEP3")]}, snapshot=date(2026, 11, 3))
        self.assertEqual([missing.name for missing in plan.missing], ["OLD3"])
        self.assertEqual(Order.objects.filter(user=self.user, order_type=-1).count(), 0)

        plan = self.run_import(
            {"Acoes": [STOCK_HEADER, stock("KEEP3")]}, close_missing=["OLD3|Nu Invest"], snapshot=date(2026, 11, 4)
        )
        sale = Order.objects.get(user=self.user, order_type=-1)
        self.assertEqual((sale.name, sale.volume, sale.price), ("OLD3", Decimal(10), Decimal("5.50")))
        consolidated = AssetConsolidatedValue.objects.get(user=self.user, name="OLD3", date=date(2026, 11, 4))
        self.assertEqual(consolidated.value, Decimal(0))
        self.assertEqual(consolidated.volume, Decimal(0))

        plan = build_plan(self.user, parse({"Acoes": [STOCK_HEADER, stock("KEEP3")]}), date(2026, 11, 5))
        self.assertEqual(plan.missing, [])

    def test_unknown_position_to_close_is_rejected(self):
        plan = build_plan(self.user, parse({"Acoes": [STOCK_HEADER, stock()]}), SNAPSHOT)

        with self.assertRaises(ImportFileError):
            apply_plan(self.user, plan, ["NAO3|Nu Invest"])
        self.assertEqual(Order.objects.count(), 0)

    def test_manual_fixed_income_is_flagged_as_possible_duplicate(self):
        Order.objects.create(
            user=self.user,
            name="CDB TESTE 2099-02-10",
            broker="Nu Invest",
            asset_type="RF",
            order_type=1,
            date=date(2026, 1, 1),
            price=Decimal(1000),
            volume=Decimal(1),
            maturity_date=date(2099, 2, 10),
            interest_rate=Decimal(10),
            index="P",
            fixed_income_type="CDB",
        )

        plan = build_plan(self.user, parse({"Renda Fixa": [RF_HEADER, fixed_income()]}), SNAPSHOT)

        self.assertTrue(plan.missing[0].possible_duplicate)

    def test_matured_fixed_income_is_not_listed_as_missing(self):
        Order.objects.create(
            user=self.user,
            name="CDB VENCIDO",
            broker="Nu Invest",
            asset_type="RF",
            order_type=1,
            date=date(2020, 1, 1),
            price=Decimal(1000),
            volume=Decimal(1),
            maturity_date=date(2021, 1, 1),
            index="P",
            fixed_income_type="CDB",
        )

        plan = build_plan(self.user, parse({"Acoes": [STOCK_HEADER, stock()]}), SNAPSHOT)

        self.assertEqual(plan.missing, [])

    def test_position_with_row_error_is_not_listed_as_missing(self):
        self.run_import({"Renda Fixa": [RF_HEADER, fixed_income("CDBX")]})

        plan = build_plan(
            self.user,
            parse({"Renda Fixa": [RF_HEADER, fixed_income("CDBX", index="CDI"), fixed_income("CDBY")]}),
            SNAPSHOT,
        )

        self.assertEqual(plan.missing, [])

    def test_consolidate_fixed_income_keeps_imported_value(self):
        self.run_import({"Renda Fixa": [RF_HEADER, fixed_income()]})

        call_command("consolidate_fixed_income")

        consolidated = AssetConsolidatedValue.objects.get(user=self.user, name="CDBTEST1", date=SNAPSHOT)
        self.assertEqual(consolidated.value, Decimal("1050.00"))


class PositionViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("investidor", password="senha")
        self.client.force_login(self.user)

    def create_order(self, user=None, **overrides):
        fields = {
            "user": user or self.user,
            "name": "TEST3",
            "broker": "Nu Invest",
            "asset_type": "AC",
            "order_type": 1,
            "date": date(2026, 1, 1),
            "price": Decimal(10),
            "volume": Decimal(10),
        }
        fields.update(overrides)
        return Order.objects.create(**fields)

    def fixed_income_order(self, **overrides):
        fields = {
            "name": "CDB1",
            "asset_type": "RF",
            "price": Decimal(1),
            "volume": Decimal(1000),
            "maturity_date": date.today() + timedelta(days=365),
            "index": "P",
            "fixed_income_type": "CDB",
        }
        fields.update(overrides)
        return self.create_order(**fields)

    def position(self, query=""):
        response = self.client.get(f"/api/position{query}")
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_fractional_quantity_keeps_value(self):
        self.fixed_income_order(name="TD", price=Decimal("3131.93"), volume=Decimal("0.69"), fixed_income_type="TD")
        AssetConsolidatedValue.objects.create(
            user=self.user,
            name="TD",
            asset_type="RF",
            date=SNAPSHOT,
            value=Decimal("2722.74"),
            volume=Decimal("0.69"),
            invested=Decimal("2161.03"),
        )

        row = self.position()["assets"][0]

        self.assertEqual(row["volume"], 0.69)
        self.assertAlmostEqual(row["value"], 2722.74, places=2)
        self.assertEqual(row["sub_category"], "Tesouro Direto")
        self.assertEqual(row["category"], "Prefixado")

    def test_sale_reduces_quantity_and_cost(self):
        AssetPrice.objects.create(ticker="TEST3", date=SNAPSHOT, close=20.0)
        self.create_order()
        self.create_order(order_type=-1, volume=Decimal(4), price=Decimal(15), date=date(2026, 2, 1))

        row = self.position()["assets"][0]

        self.assertEqual(row["volume"], 6.0)
        self.assertEqual(row["cost"], 60.0)
        self.assertEqual(row["value"], 120.0)
        self.assertEqual(row["profit"], 60.0)
        self.assertEqual(row["profit_pct"], 100.0)

    def test_closed_position_is_not_listed(self):
        AssetPrice.objects.create(ticker="TEST3", date=SNAPSHOT, close=20.0)
        self.create_order()
        self.create_order(order_type=-1, date=date(2026, 2, 1))

        self.assertEqual(self.position()["assets"], [])

    def test_summary_totals_only_priced_assets(self):
        AssetPrice.objects.create(ticker="TEST3", date=SNAPSHOT, close=20.0)
        self.create_order(cost_estimated=True)
        self.create_order(name="SEMPRECO3")
        self.fixed_income_order()
        AssetConsolidatedValue.objects.create(
            user=self.user,
            name="CDB1",
            asset_type="RF",
            date=SNAPSHOT,
            value=Decimal(1050),
            volume=Decimal(1000),
            invested=Decimal(1000),
        )

        summary = self.position()["summary"]

        self.assertAlmostEqual(summary["value"], 1250, places=2)
        self.assertEqual(summary["invested"], 1100)
        self.assertAlmostEqual(summary["profit"], 150, places=2)
        self.assertEqual(summary["assets"], 3)
        self.assertEqual(summary["assets_without_price"], 1)
        self.assertEqual(summary["estimated_assets"], 1)

    def test_empty_portfolio_has_zeroed_summary(self):
        body = self.position()

        self.assertEqual(body["assets"], [])
        self.assertEqual(body["summary"]["value"], 0)
        self.assertIsNone(body["summary"]["profit_pct"])

    def test_fixed_income_value_is_isolated_per_user_and_uses_latest_date(self):
        other = User.objects.create_user("outro", password="senha")
        self.fixed_income_order()
        AssetConsolidatedValue.objects.create(
            user=self.user,
            name="CDB1",
            asset_type="RF",
            date=SNAPSHOT,
            value=Decimal(1100),
            volume=Decimal(1000),
            invested=Decimal(1000),
        )
        AssetConsolidatedValue.objects.create(
            user=self.user,
            name="CDB1",
            asset_type="RF",
            date=SNAPSHOT - timedelta(days=1),
            value=Decimal(1000),
            volume=Decimal(1000),
            invested=Decimal(1000),
        )
        AssetConsolidatedValue.objects.create(
            user=other,
            name="CDB1",
            asset_type="RF",
            date=SNAPSHOT + timedelta(days=1),
            value=Decimal(9999),
            volume=Decimal(1000),
            invested=Decimal(1000),
        )

        self.assertAlmostEqual(self.position()["assets"][0]["value"], 1100, places=2)

    def test_latest_market_price_is_by_date(self):
        self.create_order()
        AssetPrice.objects.create(ticker="TEST3", date=SNAPSHOT, close=20.0)
        AssetPrice.objects.create(ticker="TEST3", date=SNAPSHOT - timedelta(days=1), close=1.0)

        self.assertEqual(self.position()["assets"][0]["price"], 20.0)

    def test_missing_asset_and_price_do_not_break_view(self):
        self.create_order()
        self.fixed_income_order()

        rows = {row["name"]: row for row in self.position()["assets"]}

        self.assertIsNone(rows["TEST3"]["price"])
        self.assertIsNone(rows["CDB1"]["value"])

    def test_class_comes_from_order_even_if_asset_differs(self):
        Asset.objects.create(ticker="TEST34", asset_class="AC", category="Tech", sub_category="Software")
        AssetPrice.objects.create(ticker="TEST34", date=SNAPSHOT, close=10.0)
        self.create_order(name="TEST34", asset_type="BDR")

        row = self.position()["assets"][0]

        self.assertEqual(row["asset_class"], "BDR")
        self.assertEqual(row["category"], "Tech")
        self.assertEqual(row["sub_category"], "Software")

    def test_lists_volume_per_broker_and_sorts_by_value(self):
        AssetPrice.objects.create(ticker="TEST3", date=SNAPSHOT, close=20.0)
        AssetPrice.objects.create(ticker="BIG3", date=SNAPSHOT, close=100.0)
        self.create_order()
        self.create_order(broker="XP", volume=Decimal(5))
        self.create_order(name="BIG3")

        rows = self.position()["assets"]

        self.assertEqual([row["name"] for row in rows], ["BIG3", "TEST3"])
        self.assertEqual(rows[1]["brokers"], [{"broker": "Nu Invest", "volume": 10.0}, {"broker": "XP", "volume": 5.0}])

    def test_issuer_ignores_orders_without_it(self):
        self.fixed_income_order(date=date(2026, 1, 1))
        self.fixed_income_order(date=date(2026, 2, 1), issuer="BANCO TESTE", volume=Decimal(1))

        self.assertEqual(self.position()["assets"][0]["issuer"], "BANCO TESTE")

    def test_class_filter_works_for_new_classes(self):
        AssetPrice.objects.create(ticker="TEST34", date=SNAPSHOT, close=10.0)
        self.create_order(name="TEST34", asset_type="BDR")
        self.create_order()

        self.assertEqual([row["name"] for row in self.position("?class=BDR")["assets"]], ["TEST34"])

    def test_position_history_without_data_returns_empty(self):
        response = self.client.get("/api/position-history?class=ETF")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"labels": [], "values": [], "invested": []})

    def test_position_history_finds_name_with_hyphen(self):
        AssetConsolidatedValue.objects.create(
            user=self.user,
            name="CDB X 2030-01-01",
            asset_type="RF",
            date=SNAPSHOT,
            value=Decimal(10),
            volume=Decimal(1),
            invested=Decimal(10),
        )

        response = self.client.get("/api/position-history", {"ticker": "cdb x 2030-01-01"})

        self.assertEqual(response.json()["values"], [10.0])


class OrdersViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("investidor", password="senha")
        self.client.force_login(self.user)
        self.order = Order.objects.create(
            user=self.user,
            name="TEST3",
            broker="Nu Invest",
            asset_type="AC",
            order_type=1,
            date=SNAPSHOT,
            price=Decimal("3131.93"),
            volume=Decimal("0.69"),
            cost_estimated=True,
        )

    def test_returns_named_fields_newest_first(self):
        older = Order.objects.create(
            user=self.user,
            name="OLD3",
            broker="XP",
            asset_type="AC",
            order_type=-1,
            date=date(2020, 1, 1),
            price=Decimal(1),
            volume=Decimal(1),
        )

        rows = self.client.get("/api/orders/").json()

        self.assertEqual([row["id"] for row in rows], [self.order.id, older.id])
        self.assertEqual(rows[0]["price"], 3131.93)
        self.assertEqual(rows[0]["volume"], 0.69)
        self.assertEqual(rows[0]["date"], "2026-11-02")
        self.assertIs(rows[0]["cost_estimated"], True)

    def test_ticker_filter_without_matches_returns_empty(self):
        self.assertEqual(self.client.get("/api/orders/?ticker=NAOTEM3").json(), [])

    def test_get_order_is_scoped_to_user(self):
        other = User.objects.create_user("outro", password="senha")
        foreign = Order.objects.create(
            user=other,
            name="X",
            broker="XP",
            asset_type="AC",
            order_type=1,
            date=SNAPSHOT,
            price=Decimal(1),
            volume=Decimal(1),
        )

        self.assertEqual(self.client.get(f"/api/order/{self.order.id}").json()["name"], "TEST3")
        self.assertEqual(self.client.get(f"/api/order/{foreign.id}").status_code, 404)

    def patch(self, **data):
        response = self.client.patch(f"/api/order/{self.order.id}", data=data, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.order.refresh_from_db()

    def test_editing_price_clears_estimated_flag(self):
        self.patch(price=3000.5, date=str(SNAPSHOT))

        self.assertFalse(self.order.cost_estimated)
        self.assertEqual(self.order.price, Decimal("3000.50"))

    def test_editing_date_clears_estimated_flag(self):
        self.patch(price=3131.93, date="2020-01-01")

        self.assertFalse(self.order.cost_estimated)

    def test_editing_other_fields_keeps_estimated_flag(self):
        self.patch(price=3131.93, date=str(SNAPSHOT), broker="XP")

        self.assertTrue(self.order.cost_estimated)
        self.assertEqual(self.order.broker, "XP")


class BackfillIssuerMigrationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("investidor", password="senha")

    def create_order(self, name, description, fixed_income_type="CDB", issuer=None):
        return Order.objects.create(
            user=self.user,
            name=name,
            broker="Nu Invest",
            asset_type="RF",
            order_type=1,
            date=SNAPSHOT,
            price=Decimal(1),
            volume=Decimal(1),
            description=description,
            fixed_income_type=fixed_income_type,
            issuer=issuer,
        )

    def backfill(self):
        migration = importlib.import_module("wallet.migrations.0010_backfill_order_issuer")
        migration.backfill_issuers(apps, None)

    def issuer_of(self, name):
        return Order.objects.get(name=name).issuer

    def test_reads_issuer_from_imported_description(self):
        self.create_order("A", "CDB - BANCO BMG S/A - venc. 10/02/2028")
        self.create_order("B", "CDB - PICPAY BANK - BANCO MULTIPLO S.A - venc. 14/02/2029")
        self.create_order("C", "LCA - BANCO X (EMISSOR REAL) - venc. 14/02/2029", "LCA")
        self.create_order("D", "Tesouro IPCA+ 2029", "TD")

        self.backfill()

        self.assertEqual(self.issuer_of("A"), "BANCO BMG S/A")
        self.assertEqual(self.issuer_of("B"), "PICPAY BANK - BANCO MULTIPLO S.A")
        self.assertEqual(self.issuer_of("C"), "EMISSOR REAL")
        self.assertEqual(self.issuer_of("D"), "Tesouro Nacional")

    def test_leaves_manual_and_filled_orders_untouched(self):
        self.create_order("MANUAL", "comprado no banco")
        self.create_order("VAZIA", None)
        self.create_order("PREENCHIDA", "CDB - BANCO BMG S/A - venc. 10/02/2028", issuer="OUTRO")

        self.backfill()

        self.assertIsNone(self.issuer_of("MANUAL"))
        self.assertIsNone(self.issuer_of("VAZIA"))
        self.assertEqual(self.issuer_of("PREENCHIDA"), "OUTRO")


class ResetPortfolioTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("investidor", password="senha")
        self.other = User.objects.create_user("outro", password="senha")
        for user in (self.user, self.other):
            Order.objects.create(
                user=user,
                name="TEST3",
                broker="XP",
                asset_type="AC",
                order_type=1,
                date=SNAPSHOT,
                price=Decimal(1),
                volume=Decimal(1),
            )
            AssetConsolidatedValue.objects.create(
                user=user,
                name="TEST3",
                asset_type="AC",
                date=SNAPSHOT,
                value=Decimal(1),
                volume=Decimal(1),
                invested=Decimal(1),
            )

    def test_without_yes_only_reports(self):
        call_command("reset_portfolio", "--username", "investidor", stdout=io.StringIO())

        self.assertEqual(Order.objects.count(), 2)

    def test_with_yes_deletes_only_that_user(self):
        call_command("reset_portfolio", "--username", "investidor", "--yes", stdout=io.StringIO())

        self.assertEqual(Order.objects.filter(user=self.user).count(), 0)
        self.assertEqual(AssetConsolidatedValue.objects.filter(user=self.user).count(), 0)
        self.assertEqual(Order.objects.filter(user=self.other).count(), 1)
        self.assertEqual(AssetConsolidatedValue.objects.filter(user=self.other).count(), 1)


class AssetClassificationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("investidor", password="senha")
        Asset.objects.create(ticker="TEST3", category="Antiga", sub_category="Velha")

    def patch(self, ticker="test3", **data):
        return self.client.patch(f"/api/asset/{ticker}/classification", data=data, content_type="application/json")

    def test_requires_authentication(self):
        self.assertEqual(self.patch(category="Nova").status_code, 401)

    def test_updates_and_clears_fields(self):
        self.client.force_login(self.user)

        response = self.patch(category=" Bancos ", sub_category="")

        self.assertEqual(response.status_code, 200)
        asset = Asset.objects.get(ticker="TEST3")
        self.assertEqual(asset.category, "Bancos")
        self.assertIsNone(asset.sub_category)

    def test_rejects_unknown_asset_and_long_value(self):
        self.client.force_login(self.user)

        self.assertEqual(self.patch(ticker="NAO3", category="x").status_code, 404)
        self.assertEqual(self.patch(category="x" * 33).status_code, 400)


class ImportEndpointsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("investidor", password="senha")

    def upload(self, sheets=None, name="posicao-2026-11-02-13-17-19.xlsx"):
        sheets = sheets or {"Acoes": [STOCK_HEADER, stock()]}
        return SimpleUploadedFile(name, workbook_bytes(sheets).read())

    def test_requires_authentication(self):
        for url in (PREVIEW_URL, CONFIRM_URL):
            self.assertEqual(self.client.post(url, {"file": self.upload()}).status_code, 401)
        self.assertEqual(Order.objects.count(), 0)

    def test_preview_returns_plan_without_writing(self):
        self.client.force_login(self.user)

        response = self.client.post(PREVIEW_URL, {"file": self.upload()})

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["snapshot_date"], "2026-11-02")
        self.assertEqual(body["positions"], 1)
        self.assertEqual(body["new"][0]["name"], "TEST3")
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(Asset.objects.count(), 0)
        self.assertEqual(AssetPrice.objects.count(), 0)
        self.assertEqual(AssetConsolidatedValue.objects.count(), 0)

    def test_confirm_applies_plan_with_informed_date_and_is_idempotent(self):
        self.client.force_login(self.user)

        response = self.client.post(CONFIRM_URL, {"file": self.upload(), "snapshot_date": "2026-10-30"})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["created_orders"], 1)
        self.assertEqual(Order.objects.get().date, date(2026, 10, 30))

        response = self.client.post(CONFIRM_URL, {"file": self.upload(), "snapshot_date": "2026-10-30"})
        self.assertEqual(response.json()["created_orders"], 0)

    def test_confirm_closes_selected_missing_position(self):
        self.client.force_login(self.user)
        self.client.post(CONFIRM_URL, {"file": self.upload({"Acoes": [STOCK_HEADER, stock("OLD3"), stock("KEEP3")]})})

        response = self.client.post(
            CONFIRM_URL,
            {"file": self.upload({"Acoes": [STOCK_HEADER, stock("KEEP3")]}), "close_missing": ["OLD3|Nu Invest"]},
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(Order.objects.get(order_type=-1).name, "OLD3")

    def test_each_user_reconciles_own_orders(self):
        other = User.objects.create_user("outro", password="senha")
        self.client.force_login(other)
        self.client.post(CONFIRM_URL, {"file": self.upload()})

        self.client.force_login(self.user)
        body = self.client.post(PREVIEW_URL, {"file": self.upload()}).json()

        self.assertEqual(len(body["new"]), 1)
        self.assertEqual(body["missing"], [])

    def test_rejects_invalid_uploads(self):
        self.client.force_login(self.user)
        oversize = SimpleUploadedFile("a.xlsx", b"0" * (1024 * 1024 + 1))
        cases = [
            {},
            {"file": SimpleUploadedFile("a.csv", b"a,b")},
            {"file": SimpleUploadedFile("a.xlsx", b"nao e xlsx")},
            {"file": oversize},
            {"file": self.upload(), "snapshot_date": "02/11/2026"},
            {"file": self.upload(), "snapshot_date": "2999-01-01"},
        ]
        for data in cases:
            response = self.client.post(PREVIEW_URL, data)
            self.assertEqual(response.status_code, 400, data)
            self.assertIn("message", response.json())

    def test_rejects_get(self):
        self.client.force_login(self.user)

        self.assertEqual(self.client.get(PREVIEW_URL).status_code, 400)


class AllocationTargetsTests(TestCase):
    URL = "/api/targets"

    def setUp(self):
        self.user = User.objects.create_user("investidor", password="senha")
        self.client.force_login(self.user)

    def put(self, asset_class=None, **targets):
        return self.put_raw(
            {
                "asset_class": asset_class,
                "targets": [{"key": key, "percent": percent} for key, percent in targets.items()],
            }
        )

    def put_raw(self, data):
        return self.client.put(self.URL, data=data, content_type="application/json")

    def test_requires_authentication(self):
        self.client.logout()

        self.assertEqual(self.client.get(self.URL).status_code, 401)
        self.assertEqual(self.put(AC=10).status_code, 401)

    def test_starts_empty(self):
        self.assertEqual(self.client.get(self.URL).json(), {"classes": {}, "categories": {}})

    def test_saves_class_and_category_levels_separately(self):
        self.assertEqual(self.put(AC=25, FII=25, RF=50).status_code, 200)
        response = self.put("AC", Bancos=20, Saneamento=20.5)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "classes": {"AC": 25.0, "FII": 25.0, "RF": 50.0},
                "categories": {"AC": {"Bancos": 20.0, "Saneamento": 20.5}},
            },
        )

    def test_saving_a_level_replaces_only_that_level(self):
        self.put(AC=25, FII=25)
        self.put("AC", Bancos=20, Saneamento=20)
        self.put("RF", IPCA=50)

        self.put(AC=40)
        body = self.put("AC", Bancos=30).json()

        self.assertEqual(body["classes"], {"AC": 40.0})
        self.assertEqual(body["categories"], {"AC": {"Bancos": 30.0}, "RF": {"IPCA": 50.0}})

    def test_empty_list_clears_level(self):
        self.put("AC", Bancos=20)

        self.assertEqual(self.put("AC").json()["categories"], {})

    def test_zero_is_a_valid_target(self):
        self.assertEqual(self.put(BDR=0).json()["classes"], {"BDR": 0.0})

    def test_targets_are_per_user(self):
        self.put(AC=25)
        other = User.objects.create_user("outro", password="senha")
        self.client.force_login(other)

        self.assertEqual(self.client.get(self.URL).json()["classes"], {})
        self.put(AC=70)
        self.assertEqual(AllocationTarget.objects.get(user=self.user).percent, Decimal("25.00"))

    def test_sum_can_be_exactly_100_but_not_more(self):
        self.assertEqual(self.put(AC=33.33, FII=33.33, RF=33.34).status_code, 200)
        self.assertEqual(self.put(AC=60, FII=40.01).status_code, 400)
        self.assertEqual(self.client.get(self.URL).json()["classes"]["AC"], 33.33)

    def test_rejects_invalid_data_without_changing_saved_targets(self):
        self.put(AC=25)
        invalid = [
            {},
            {"targets": "x"},
            ["x"],
            {"targets": ["x"]},
            {"asset_class": "XX", "targets": []},
            {"targets": [{"key": "XX", "percent": 10}]},
            {"targets": [{"key": "AC", "percent": -1}]},
            {"targets": [{"key": "AC", "percent": 101}]},
            {"targets": [{"key": "AC", "percent": "NaN"}]},
            {"targets": [{"key": "AC", "percent": "abc"}]},
            {"targets": [{"key": "AC", "percent": True}]},
            {"targets": [{"key": "AC", "percent": None}]},
            {"targets": [{"key": "AC", "percent": 1}, {"key": "AC", "percent": 2}]},
            {"asset_class": "AC", "targets": [{"key": "  ", "percent": 1}]},
            {"asset_class": "AC", "targets": [{"key": "x" * 65, "percent": 1}]},
        ]
        for data in invalid:
            response = self.put_raw(data)
            self.assertEqual(response.status_code, 400, data)
            self.assertIn("message", response.json())

        self.assertEqual(self.client.get(self.URL).json()["classes"], {"AC": 25.0})

    def test_rejects_malformed_json_and_other_methods(self):
        response = self.client.put(self.URL, data="{", content_type="application/json")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.post(self.URL).status_code, 400)


class ConsolidationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("investidor", password="senha")

    def order(self, name="TEST3", asset_type="AC", user=None, **overrides):
        fields = {
            "user": user or self.user,
            "name": name,
            "broker": "XP",
            "asset_type": asset_type,
            "order_type": 1,
            "date": date(2026, 10, 1),
            "price": Decimal(10),
            "volume": Decimal(10),
        }
        fields.update(overrides)
        return Order.objects.create(**fields)

    def price(self, day, close=20.0, ticker="TEST3"):
        return AssetPrice.objects.create(ticker=ticker, date=day, close=close)

    def snapshot(self, name="TEST3", day=date(2026, 10, 1), value=100, volume=10, asset_type="AC"):
        return AssetConsolidatedValue.objects.create(
            user=self.user,
            name=name,
            asset_type=asset_type,
            date=day,
            value=Decimal(value),
            volume=Decimal(volume),
            invested=Decimal(value),
        )

    def row(self, day, name="TEST3", user=None):
        return AssetConsolidatedValue.objects.get(user=user or self.user, name=name, date=day)

    def test_values_market_asset_by_close_of_the_day(self):
        self.order()
        self.snapshot()
        self.price(date(2026, 10, 2), 20.0)
        self.price(date(2026, 10, 5), 25.0)

        self.assertEqual(consolidate_all_users(), 2)

        self.assertEqual(self.row(date(2026, 10, 2)).value, Decimal(200))
        self.assertEqual(self.row(date(2026, 10, 5)).value, Decimal(250))
        self.assertEqual(self.row(date(2026, 10, 5)).invested, Decimal(100))

    def test_does_not_overwrite_rows_before_the_last_one(self):
        self.order()
        self.snapshot(day=date(2026, 10, 2), value=999)
        self.price(date(2026, 10, 2), 20.0)
        self.price(date(2026, 10, 5), 25.0)

        consolidate_all_users()

        self.assertEqual(self.row(date(2026, 10, 2)).value, Decimal(999))

    def test_is_idempotent(self):
        self.order()
        self.snapshot()
        self.price(date(2026, 10, 2))

        consolidate_all_users()

        self.assertEqual(consolidate_all_users(), 0)

    def test_asset_without_trade_keeps_previous_close(self):
        self.order()
        self.order(name="OTHER3")
        self.snapshot()
        self.snapshot(name="OTHER3")
        self.price(date(2026, 10, 1), 30.0)
        self.price(date(2026, 10, 2), 40.0, ticker="OTHER3")

        consolidate_all_users()

        self.assertEqual(self.row(date(2026, 10, 2)).value, Decimal(300))

    def test_sale_reduces_position_from_its_date(self):
        self.order()
        self.order(order_type=-1, volume=Decimal(4), date=date(2026, 10, 5))
        self.snapshot()
        self.price(date(2026, 10, 2))
        self.price(date(2026, 10, 5))

        consolidate_all_users()

        self.assertEqual(self.row(date(2026, 10, 2)).volume, Decimal(10))
        self.assertEqual(self.row(date(2026, 10, 5)).volume, Decimal(6))
        self.assertEqual(self.row(date(2026, 10, 5)).value, Decimal(120))

    def test_position_opened_later_starts_on_its_date(self):
        self.order(date=date(2026, 10, 5))
        self.price(date(2026, 10, 2))
        self.price(date(2026, 10, 5))

        consolidate_all_users()

        self.assertEqual(AssetConsolidatedValue.objects.count(), 1)
        self.assertEqual(self.row(date(2026, 10, 5)).value, Decimal(200))

    def test_fixed_income_without_rate_keeps_last_known_value(self):
        self.order(name="CDB1", asset_type="RF", maturity_date=date(2030, 1, 1))
        self.snapshot(name="CDB1", value=1234, asset_type="RF")
        self.price(date(2026, 10, 2))

        consolidate_all_users()

        self.assertEqual(self.row(date(2026, 10, 2), "CDB1").value, Decimal(1234))

    def test_fixed_income_with_rate_grows_by_elapsed_days(self):
        self.order(name="CDB1", asset_type="RF", maturity_date=date(2030, 1, 1), interest_rate=Decimal(10))
        self.snapshot(name="CDB1", value=1000, asset_type="RF")
        self.price(date(2026, 10, 1) + timedelta(days=30))

        consolidate_all_users()

        expected = Decimal(str(1000 * 1.1 ** (30 / 365))).quantize(Decimal("0.01"))
        self.assertEqual(self.row(date(2026, 10, 31), "CDB1").value, expected)

    def test_matured_fixed_income_stops(self):
        self.order(name="CDB1", asset_type="RF", maturity_date=date(2026, 10, 3))
        self.snapshot(name="CDB1", value=1000, asset_type="RF")
        self.price(date(2026, 10, 2))
        self.price(date(2026, 10, 5))

        consolidate_all_users()

        self.assertEqual(self.row(date(2026, 10, 2), "CDB1").value, Decimal(1000))
        self.assertFalse(AssetConsolidatedValue.objects.filter(name="CDB1", date=date(2026, 10, 5)).exists())

    def test_handles_each_user_separately(self):
        other = User.objects.create_user("outro", password="senha")
        self.order()
        self.order(user=other, volume=Decimal(1))
        self.price(date(2026, 10, 2))

        consolidate_all_users()

        self.assertEqual(self.row(date(2026, 10, 2)).value, Decimal(200))
        self.assertEqual(self.row(date(2026, 10, 2), user=other).value, Decimal(20))

    def test_old_gap_is_limited(self):
        self.order(date=date(2020, 1, 1))
        self.snapshot(day=date(2020, 1, 1))
        self.price(date(2026, 1, 1))
        self.price(date(2026, 10, 30))

        consolidate_all_users()

        first = AssetConsolidatedValue.objects.exclude(date=date(2020, 1, 1)).order_by("date").first()
        self.assertEqual(first.date, date(2026, 10, 30))
        self.assertLessEqual((date(2026, 10, 30) - first.date).days, MAX_BACKFILL_DAYS)

    def test_no_prices_means_no_history(self):
        self.order()

        self.assertEqual(consolidate_all_users(), 0)

    def test_old_commands_work_with_many_users(self):
        other = User.objects.create_user("outro", password="senha")
        self.order(date=date(2026, 10, 1))
        self.order(user=other, date=date(2026, 10, 1))
        self.order(
            name="CDB1",
            asset_type="RF",
            maturity_date=date(2030, 1, 1),
            interest_rate=Decimal(10),
            date=date(2026, 10, 25),
        )
        self.price(date(2026, 9, 30))

        call_command("consolidate")
        call_command("consolidate_fixed_income")

        self.assertTrue(AssetConsolidatedValue.objects.filter(user=other, name="TEST3").exists())
        self.assertTrue(AssetConsolidatedValue.objects.filter(user=self.user, name="CDB1").exists())


@mock.patch("wallet.market_update.fill_missing_categories", return_value=(0, [], False))
@mock.patch("wallet.market_update.fetch_session")
class MarketUpdateTests(TestCase):
    def test_downloads_only_sessions_after_the_last_one(self, fetch, categories):
        MarketDataUpdate.objects.create(status="success", last_session=date.today() - timedelta(days=1))
        fetch.return_value = None

        run_update()

        self.assertLessEqual(fetch.call_count, 2)
        for call in fetch.call_args_list:
            self.assertGreaterEqual(call[0][0], date.today() - timedelta(days=1))

    def test_records_success_and_last_session(self, fetch, categories):
        fetch.side_effect = lambda day: (3, day)

        run = run_update()

        self.assertEqual(run.status, "success")
        self.assertIsNotNone(run.finished_at)
        self.assertIsNotNone(run.last_session)
        self.assertGreater(run.prices_saved, 0)
        self.assertFalse(update_status()["running"])

    def test_missing_files_keep_previous_last_session(self, fetch, categories):
        MarketDataUpdate.objects.create(status="success", last_session=date(2026, 10, 30))
        fetch.return_value = None

        run = run_update()

        self.assertEqual(run.status, "success")
        self.assertEqual(update_status()["last_session"], date(2026, 10, 30))

    def test_download_failure_is_recorded_and_history_still_runs(self, fetch, categories):
        fetch.side_effect = MarketDataError("B3 fora do ar")

        with mock.patch("wallet.market_update.consolidate_all_users", return_value=7) as consolidate:
            run = run_update()

        consolidate.assert_called_once()
        self.assertEqual(run.status, "error")
        self.assertIn("B3 fora do ar", run.message)

    def test_unresolved_categories_are_reported_without_failing(self, fetch, categories):
        fetch.return_value = None
        categories.return_value = (0, ["BOVA11"], False)

        run = run_update()

        self.assertEqual(run.status, "success")
        self.assertIn("BOVA11", run.message)

    def test_sends_only_market_assets_for_categories(self, fetch, categories):
        fetch.return_value = None
        user = User.objects.create_user("investidor", password="senha")
        for name, asset_type in (("TEST3", "AC"), ("CDB1", "RF")):
            Order.objects.create(
                user=user,
                name=name,
                broker="XP",
                asset_type=asset_type,
                order_type=1,
                date=SNAPSHOT,
                price=Decimal(1),
                volume=Decimal(1),
            )

        run_update()

        categories.assert_called_once_with({"TEST3": "AC"})

    def test_second_run_is_skipped_while_one_holds_the_lock(self, fetch, categories):
        with mock.patch("wallet.market_update._try_lock", return_value=False):
            self.assertIsNone(run_update())
        self.assertEqual(MarketDataUpdate.objects.count(), 0)


class MarketDataEndpointTests(TestCase):
    URL = "/api/market-data"

    def setUp(self):
        self.user = User.objects.create_user("investidor", password="senha")

    def test_requires_authentication(self):
        self.assertEqual(self.client.get(self.URL).status_code, 401)
        self.assertEqual(self.client.post(self.URL).status_code, 401)

    def test_status_before_any_update(self):
        self.client.force_login(self.user)

        body = self.client.get(self.URL).json()

        self.assertFalse(body["running"])
        self.assertIsNone(body["last_session"])

    def test_reports_last_finished_update(self):
        self.client.force_login(self.user)
        finished = timezone.now()
        MarketDataUpdate.objects.create(
            status="success",
            last_session=date(2026, 10, 30),
            finished_at=finished,
            message="ok",
        )

        body = self.client.get(self.URL).json()

        self.assertEqual(body["last_session"], "2026-10-30")
        self.assertEqual(body["status"], "success")
        self.assertEqual(body["message"], "ok")

    @mock.patch("wallet.views.start_update_in_background")
    def test_post_starts_update(self, start):
        self.client.force_login(self.user)

        response = self.client.post(self.URL)

        self.assertEqual(response.status_code, 202)
        self.assertTrue(response.json()["running"])
        start.assert_called_once()

    @mock.patch("wallet.views.start_update_in_background")
    def test_post_does_not_start_second_update(self, start):
        self.client.force_login(self.user)
        MarketDataUpdate.objects.create()

        self.assertTrue(self.client.get(self.URL).json()["running"])
        self.assertEqual(self.client.post(self.URL).status_code, 202)
        start.assert_not_called()

    def test_abandoned_run_stops_counting_as_running(self):
        self.client.force_login(self.user)
        stale = MarketDataUpdate.objects.create()
        MarketDataUpdate.objects.filter(pk=stale.pk).update(started_at=timezone.now() - timedelta(hours=2))

        self.assertFalse(self.client.get(self.URL).json()["running"])


MOVEMENT_HEADER = [
    "Entrada/Saída",
    "Data",
    "Movimentação",
    "Produto",
    "Instituição",
    "Quantidade",
    "Preço unitário",
    "Valor da Operação",
]
NU = "NU INVEST CORRETORA DE VALORES S.A."
XP = "XP INVESTIMENTOS CCTVM S/A"


def line(day, kind, product, quantity, price="-", value="-", direction="Credito", institution=NU):
    return [direction, day, kind, product, institution, quantity, price, value]


def buy(day, product, quantity, price, institution=NU):
    return line(
        day, "Transferência - Liquidação", product, quantity, price, round(quantity * price, 2), institution=institution
    )


def sell(day, product, quantity, price, institution=NU):
    return line(
        day, "Transferência - Liquidação", product, quantity, price, round(quantity * price, 2), "Debito", institution
    )


def movement_file(*rows):
    return workbook_bytes({"Movimentação": [MOVEMENT_HEADER, *rows]})


def snapshot_row(name, quantity, unit_price=10, broker="Nu Invest", day=date(2026, 11, 2), asset_type="AC", **extra):
    return PositionSnapshot(
        date=day,
        name=name,
        broker=broker,
        asset_type=asset_type,
        quantity=Decimal(str(quantity)),
        unit_price=Decimal(str(unit_price)),
        value=Decimal(str(quantity)) * Decimal(str(unit_price)),
        **extra,
    )


def ledger_for(*rows, snapshot=()):
    movements, errors = parse_movements_file(movement_file(*rows))
    assert not errors, errors
    return build_ledger(movements, list(snapshot))


def totals(ledger, name):
    position = _ledger_position(ledger, name)
    return position.quantity, position.invested


def _ledger_position(ledger, name):
    from types import SimpleNamespace

    from wallet.positions import RunningPosition

    position = RunningPosition()
    for spec in ledger.orders:
        if spec.name == name:
            position.apply(
                SimpleNamespace(kind=spec.kind, order_type=spec.order_type, volume=spec.volume, price=spec.price)
            )
    return position


class MovementParsingTests(TestCase):
    def test_asset_key_forms(self):
        self.assertEqual(asset_key("PETR4 - PETROBRAS"), "PETR4")
        self.assertEqual(asset_key("CDB - CDBFICT03"), "CDBFICT03")
        self.assertEqual(asset_key("CDB - CDBFICT02 - BANCO TESTE S/A"), "CDBFICT02")
        self.assertEqual(asset_key("LCA - CDBFICT00 - BANCO TESTE S/A"), "CDBFICT00")
        self.assertEqual(asset_key("Tesouro IPCA+ 2032"), "TESOURO IPCA+ 2032")

    def test_infers_asset_type_from_text(self):
        self.assertEqual(infer_asset_type("BOVA11", "BOVA11 - ISHARES IBOVESPA FUNDO DE INDICE"), "ETF")
        self.assertEqual(infer_asset_type("VINO11", "VINO11 - VINCI OFFICES FUNDO DE INVESTIMENTO IMOBILIARIO"), "FII")
        self.assertEqual(infer_asset_type("FBOK34", "FBOK34 - FACEBOOK"), "BDR")
        self.assertEqual(infer_asset_type("CARD3", "CARD3 - CSU"), "AC")
        self.assertEqual(infer_asset_type("X", "CDB - X - BANCO"), "RF")

    def test_detects_file_type(self):
        self.assertTrue(is_movement_file(movement_file()))
        self.assertFalse(is_movement_file(workbook_bytes({"Acoes": [STOCK_HEADER]})))
        self.assertFalse(is_movement_file(io.BytesIO(b"nao e xlsx")))

    def test_identical_rows_are_separate_operations(self):
        row = buy("06/04/2021", "PETR4 - PETROBRAS", 1, 10.0)

        movements, _ = parse_movements_file(movement_file(row, list(row)))

        self.assertEqual(sorted(m.occurrence for m in movements), [1, 2])

    def test_same_row_with_and_without_issuer_is_b3_duplicate(self):
        rows = [
            line("18/02/2026", "COMPRA / VENDA", "CDB - CDBFICT01", 1000, 1, 1000),
            line("18/02/2026", "COMPRA / VENDA", "CDB - CDBFICT01 - BANCO TESTE S/A", 1000, 1, 1000),
        ]

        movements, _ = parse_movements_file(movement_file(*rows))

        self.assertEqual(len(movements), 1)

    def test_name_change_does_not_change_fingerprint(self):
        first, _ = parse_movements_file(movement_file(buy("01/02/2024", "ITSA4 - ITAUSA S.A.", 1, 10.0)))
        second, _ = parse_movements_file(movement_file(buy("01/02/2024", "ITSA4 - ITAUSA S/A", 1, 10.0)))

        self.assertEqual(first[0].fingerprint, second[0].fingerprint)

    def test_old_and_new_nu_names_are_same_broker(self):
        names = ["NU INVEST CORRETORA DE VALORES S.A.", "NU INVESTIMENTOS S.A. - CTVM", "EASYNVEST - TITULO CV S/A"]
        movements, _ = parse_movements_file(
            movement_file(*[buy("01/02/2024", "ITSA4 - X", 1, 10.0, name) for name in names])
        )

        self.assertEqual({m.broker for m in movements}, {"Nu Invest"})

    def test_reads_dash_as_empty_and_flags_bad_lines(self):
        rows = [
            line("01/02/2024", "Desdobro", "BBAS3 - BB", 8),
            ["Outro", "01/02/2024", "Compra", "X", NU, 1, 1, 1],
            ["Credito", "sem data", "Compra", "X", NU, 1, 1, 1],
        ]
        movements, errors = parse_movements_file(movement_file(*rows))

        self.assertIsNone(movements[0].value)
        self.assertEqual([error["row"] for error in errors], [3, 4])

    def test_missing_column_is_rejected(self):
        with self.assertRaises(MovementFileError):
            parse_movements_file(workbook_bytes({"Movimentação": [["Data", "Produto"]]}))


class LedgerTests(TestCase):
    def test_average_price_and_sale(self):
        ledger = ledger_for(
            buy("01/02/2024", "PETR4 - X", 10, 10.0),
            buy("02/02/2024", "PETR4 - X", 10, 20.0),
            sell("03/02/2024", "PETR4 - X", 5, 30.0),
        )

        quantity, invested = totals(ledger, "PETR4")

        self.assertEqual((quantity, invested), (Decimal(15), Decimal(225)))
        self.assertEqual(_ledger_position(ledger, "PETR4").realized, Decimal(75))

    def test_split_and_bonus_keep_total_cost(self):
        ledger = ledger_for(
            buy("01/02/2024", "BBAS3 - X", 8, 34.0),
            line("17/04/2024", "Desdobro", "BBAS3 - X", 8),
            line("18/04/2024", "Bonificação em Ativos", "BBAS3 - X", 1),
        )

        self.assertEqual(totals(ledger, "BBAS3"), (Decimal(17), Decimal(272)))

    def test_grouping_informs_final_balance_per_broker(self):
        ledger = ledger_for(
            buy("01/02/2024", "GOGL34 - X", 60, 10.0),
            line("30/08/2022", "Desdobro", "OTHER3 - X", 1),
            line("02/02/2024", "Grupamento", "GOGL34 - X", 4.8),
        )

        self.assertEqual(totals(ledger, "GOGL34"), (Decimal("4.8"), Decimal(600)))

    def test_balance_update_equal_to_balance_changes_nothing(self):
        ledger = ledger_for(
            buy("01/02/2024", "BOVA11 - X", 3, 10.0), line("02/02/2024", "Atualização", "BOVA11 - X", 3)
        )

        self.assertEqual(totals(ledger, "BOVA11"), (Decimal(3), Decimal(30)))

    def test_balance_update_different_from_balance_adds(self):
        ledger = ledger_for(
            buy("01/02/2024", "HGLG11 - X", 3, 100.0), line("02/02/2024", "Atualização", "HGLG11 - X", 1.17)
        )

        self.assertEqual(totals(ledger, "HGLG11"), (Decimal("4.17"), Decimal(300)))

    def test_fraction_reduces_quantity_and_proportional_cost(self):
        ledger = ledger_for(
            buy("01/02/2024", "HGLG11 - X", 4, 100.0),
            line("02/02/2024", "Fração em Ativos", "HGLG11 - X", 1, direction="Debito"),
        )

        self.assertEqual(totals(ledger, "HGLG11"), (Decimal(3), Decimal(300)))

    def test_transfer_keeps_cost_even_when_outgoing_comes_first(self):
        ledger = ledger_for(
            buy("01/02/2024", "HGLG11 - X", 3, 100.0, XP),
            line("02/02/2024", "Transferência", "HGLG11 - X", 3, direction="Debito", institution=XP),
            line("02/02/2024", "Transferência", "HGLG11 - X", 3),
        )

        self.assertEqual(totals(ledger, "HGLG11"), (Decimal(3), Decimal(300)))

    def test_maturity_with_zero_value_is_not_a_loss(self):
        ledger = ledger_for(
            line("01/02/2024", "COMPRA / VENDA", "CDB - CDB1", 1, 1000, 1000),
            line("01/02/2025", "VENCIMENTO", "CDB - CDB1", 1, 0, 0, "Debito"),
        )

        self.assertEqual(_ledger_position(ledger, "CDB1").realized, Decimal(0))
        self.assertEqual(totals(ledger, "CDB1")[0], Decimal(0))

    def test_maturity_with_value_realizes_gain(self):
        ledger = ledger_for(
            line("01/02/2024", "COMPRA / VENDA", "CDB - CDB1", 1, 1000, 1000),
            line("01/02/2025", "VENCIMENTO", "CDB - CDB1", 1, 1191.38, 1191.38, "Debito"),
        )

        self.assertEqual(_ledger_position(ledger, "CDB1").realized, Decimal("191.38"))

    def test_ticker_change_on_same_day_moves_cost(self):
        ledger = ledger_for(
            buy("01/02/2024", "BCFF11 - X", 40, 10.0),
            line("13/12/2024", "Atualização", "BCFF11 - X", 40),
            line("13/12/2024", "Atualização", "BTHF11 - X", 32),
            line("19/12/2024", "Resgate", "BCFF11 - X", 40, 0.01, 0.4),
            snapshot=[snapshot_row("BTHF11", 32)],
        )

        self.assertEqual(ledger.successions, [("BCFF11", "BTHF11")])
        self.assertEqual(totals(ledger, "BTHF11"), (Decimal(32), Decimal(400)))
        self.assertEqual(totals(ledger, "BCFF11")[0], Decimal(0))
        self.assertEqual(_ledger_position(ledger, "BCFF11").realized, Decimal(0))

    def test_ticker_change_by_same_quantity_moves_cost(self):
        ledger = ledger_for(
            buy("01/02/2022", "CARD3 - X", 4, 10.0),
            line("16/09/2022", "Atualização", "CSUD3 - X", 4),
            line("20/09/2022", "Rendimento", "CARD3 - X", 4, 0.1, 0.4),
            snapshot=[snapshot_row("CSUD3", 4)],
        )

        self.assertEqual(ledger.successions, [("CARD3", "CSUD3")])
        self.assertEqual(totals(ledger, "CSUD3"), (Decimal(4), Decimal(40)))

    def test_old_ticker_with_later_operations_is_not_a_ticker_change(self):
        ledger = ledger_for(
            buy("01/02/2024", "AERI3 - X", 6, 10.0),
            line("16/04/2024", "Atualização", "CNES11 - X", 6),
            line("15/05/2024", "Grupamento", "AERI3 - X", 1),
            snapshot=[snapshot_row("OUTRO3", 1)],
        )

        self.assertEqual(ledger.successions, [])

    def test_fixed_income_is_never_treated_as_ticker_change(self):
        ledger = ledger_for(
            line("01/02/2024", "Compra", "Tesouro Prefixado 2025", 1, 100, 100),
            line("02/02/2024", "Atualização", "EVTC31 - X", 1),
            snapshot=[snapshot_row("OUTRO3", 1)],
        )

        self.assertEqual(ledger.successions, [])

    def test_ambiguous_ticker_change_keeps_no_link(self):
        ledger = ledger_for(
            buy("01/02/2024", "AAAA3 - X", 2, 10.0),
            buy("01/02/2024", "BBBB3 - X", 2, 10.0),
            line("02/02/2024", "Atualização", "CCCC3 - X", 2),
            snapshot=[snapshot_row("CCCC3", 2)],
        )

        self.assertEqual(ledger.successions, [])

    def test_snapshot_closes_positions_without_exit_record(self):
        ledger = ledger_for(buy("01/02/2024", "SARE11 - X", 70, 10.0), snapshot=[snapshot_row("OUTRO3", 1)])

        self.assertEqual(totals(ledger, "SARE11"), (Decimal(0), Decimal(0)))
        self.assertEqual(_ledger_position(ledger, "SARE11").realized, Decimal(0))
        self.assertEqual([d.action for d in ledger.differences if d.name == "SARE11"], ["closed"])

    def test_position_closed_without_record_exits_on_last_activity(self):
        ledger = ledger_for(
            buy("01/02/2022", "SARE11 - X", 70, 10.0),
            line("15/03/2023", "Rendimento", "SARE11 - X", 70, 0.1, 7),
            snapshot=[snapshot_row("OUTRO3", 1)],
        )

        closing = [spec for spec in ledger.orders if spec.name == "SARE11" and spec.kind == Order.KIND_RECONCILIATION]
        self.assertEqual([spec.date for spec in closing], [date(2023, 3, 15)])

    def test_trim_of_position_still_held_stays_on_snapshot_date(self):
        ledger = ledger_for(buy("01/02/2022", "PETR4 - X", 4, 10.0), snapshot=[snapshot_row("PETR4", 1)])

        closing = [spec for spec in ledger.orders if spec.kind == Order.KIND_RECONCILIATION]
        self.assertEqual([spec.date for spec in closing], [date(2026, 11, 2)])

    def test_snapshot_adds_missing_quantity_at_estimated_price(self):
        ledger = ledger_for(buy("01/02/2024", "PETR4 - X", 1, 10.0), snapshot=[snapshot_row("PETR4", 3, 50)])

        self.assertEqual(totals(ledger, "PETR4"), (Decimal(3), Decimal(110)))
        estimated = [spec for spec in ledger.orders if spec.cost_estimated]
        self.assertEqual([(s.volume, s.price) for s in estimated], [(Decimal(2), Decimal(50))])

    def test_snapshot_trims_excess_quantity_keeping_average_price(self):
        ledger = ledger_for(buy("01/02/2024", "PETR4 - X", 4, 10.0), snapshot=[snapshot_row("PETR4", 1)])

        self.assertEqual(totals(ledger, "PETR4"), (Decimal(1), Decimal(10)))

    def test_snapshot_fixes_broker_without_changing_cost(self):
        ledger = ledger_for(buy("01/02/2024", "PETR4 - X", 2, 10.0, XP), snapshot=[snapshot_row("PETR4", 2)])

        self.assertEqual(ledger.matched, 1)
        self.assertEqual(ledger.differences, [])
        self.assertEqual(totals(ledger, "PETR4"), (Decimal(2), Decimal(20)))

    def test_movement_after_snapshot_applies_on_top_of_it(self):
        ledger = ledger_for(
            buy("01/02/2024", "PETR4 - X", 1, 10.0),
            buy("05/11/2026", "PETR4 - X", 1, 20.0),
            snapshot=[snapshot_row("PETR4", 1)],
        )

        self.assertEqual(totals(ledger, "PETR4"), (Decimal(2), Decimal(30)))

    def test_rights_and_transferred_income_change_nothing(self):
        ledger = ledger_for(
            line("01/02/2024", "Direito de Subscrição", "BTLG12 - X", 3),
            line("01/02/2024", "Cessão de Direitos", "BBDC2 - X", 1),
            line("01/02/2024", "Dividendo - Transferido", "PETR4 - X", 1, 1, 1),
        )

        self.assertEqual(ledger.orders, [])
        self.assertEqual(ledger.unknown_types, {})

    def test_unknown_type_is_reported(self):
        self.assertEqual(ledger_for(line("01/02/2024", "Tipo Novo", "PETR4 - X", 1)).unknown_types, {"Tipo Novo": 1})


class MovementImportTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("investidor", password="senha")

    def run_import(self, *rows, replace_manual=False):
        parsed, _ = parse_movements_file(movement_file(*rows))
        return import_movements(self.user, parsed, replace_manual)

    def quantity(self, name):
        return summarize_orders(list(Order.objects.filter(user=self.user, name=name)))[0]

    def test_full_file_then_overlapping_smaller_file_adds_only_new_rows(self):
        old = buy("01/02/2024", "PETR4 - X", 1, 10.0)
        repeated = buy("02/02/2024", "PETR4 - X", 1, 11.0)
        self.run_import(old, repeated, list(repeated))
        self.assertEqual(self.quantity("PETR4"), Decimal(3))

        new_rows, _ = self.run_import(repeated, buy("03/02/2024", "PETR4 - X", 1, 12.0))

        self.assertEqual(new_rows, 1)
        self.assertEqual(Movement.objects.count(), 4)
        self.assertEqual(self.quantity("PETR4"), Decimal(4))

    def test_reimporting_same_file_changes_nothing(self):
        rows = [buy("01/02/2024", "PETR4 - X", 1, 10.0), line("03/02/2024", "Dividendo", "PETR4 - X", 1, 1, 1)]
        self.run_import(*rows)
        first = list(Order.objects.values_list("name", "volume", "price"))

        new_rows, _ = self.run_import(*rows)

        self.assertEqual(new_rows, 0)
        self.assertEqual(list(Order.objects.values_list("name", "volume", "price")), first)

    def test_new_file_with_more_copies_adds_the_difference(self):
        row = buy("01/02/2024", "PETR4 - X", 1, 10.0)
        self.run_import(row)

        new_rows, _ = self.run_import(row, list(row))

        self.assertEqual(new_rows, 1)
        self.assertEqual(self.quantity("PETR4"), Decimal(2))

    def test_files_in_any_order_give_same_result(self):
        first = buy("01/02/2024", "PETR4 - X", 10, 10.0)
        second = sell("02/02/2024", "PETR4 - X", 4, 20.0)
        self.run_import(second)
        self.run_import(first)

        self.assertEqual(self.quantity("PETR4"), Decimal(6))
        self.assertEqual(realized_gain(list(Order.objects.filter(user=self.user))), Decimal(40))

    def test_replaces_estimated_orders_from_position_report(self):
        plan = build_plan(self.user, parse({"Acoes": [STOCK_HEADER, stock("PETR4", quantity=2, close=50.0)]}), SNAPSHOT)
        apply_plan(self.user, plan)
        self.assertTrue(Order.objects.get(name="PETR4").cost_estimated)

        self.run_import(buy("01/02/2024", "PETR4 - X", 2, 30.0))

        order = Order.objects.get(name="PETR4", kind=Order.KIND_TRADE)
        self.assertFalse(order.cost_estimated)
        self.assertEqual(order.price, Decimal(30))
        self.assertEqual(Order.objects.filter(source=Order.SOURCE_POSITION).count(), 0)

    def test_uses_report_metadata_for_fixed_income(self):
        apply_plan(self.user, build_plan(self.user, parse({"Renda Fixa": [RF_HEADER, fixed_income("CDB1")]}), SNAPSHOT))

        self.run_import(line("01/02/2024", "COMPRA / VENDA", "CDB - CDB1 - BANCO TESTE S/A", 1000, 1, 1000))

        order = Order.objects.get(name="CDB1", kind=Order.KIND_TRADE)
        self.assertEqual(order.maturity_date, date(2099, 2, 10))
        self.assertEqual(order.index, "P")
        self.assertEqual(order.issuer, "BANCO TESTE S/A")

    def test_position_report_after_movements_recalculates_instead_of_estimating(self):
        self.run_import(buy("01/02/2024", "PETR4 - X", 2, 30.0), buy("02/02/2024", "SAIU3 - X", 5, 10.0))

        apply_plan(
            self.user,
            build_plan(self.user, parse({"Acoes": [STOCK_HEADER, stock("PETR4", quantity=2, close=50.0)]}), SNAPSHOT),
        )

        self.assertEqual(self.quantity("PETR4"), Decimal(2))
        self.assertEqual(self.quantity("SAIU3"), Decimal(0))
        self.assertFalse(Order.objects.filter(cost_estimated=True).exists())
        self.assertEqual(summarize_orders(list(Order.objects.filter(name="PETR4")))[1], Decimal(60))

    def test_keeps_manual_orders_unless_asked(self):
        manual = Order.objects.create(
            user=self.user,
            name="PETR4",
            broker="XP",
            asset_type="AC",
            order_type=1,
            date=SNAPSHOT,
            price=Decimal(1),
            volume=Decimal(1),
        )
        other = Order.objects.create(
            user=self.user,
            name="MANUAL3",
            broker="XP",
            asset_type="AC",
            order_type=1,
            date=SNAPSHOT,
            price=Decimal(1),
            volume=Decimal(1),
        )
        rows = [buy("01/02/2024", "PETR4 - X", 2, 30.0)]

        self.run_import(*rows)
        self.assertTrue(Order.objects.filter(pk=manual.pk).exists())

        self.run_import(*rows, replace_manual=True)
        self.assertFalse(Order.objects.filter(pk=manual.pk).exists())
        self.assertTrue(Order.objects.filter(pk=other.pk).exists())

    def test_each_user_has_own_movements(self):
        row = buy("01/02/2024", "PETR4 - X", 1, 10.0)
        other = User.objects.create_user("outro", password="senha")
        parsed, _ = parse_movements_file(movement_file(row))
        import_movements(other, parsed)

        new_rows, _ = self.run_import(row)

        self.assertEqual(new_rows, 1)
        self.assertEqual(Movement.objects.filter(user=other).count(), 1)

    def test_rebuild_orders_is_idempotent(self):
        self.run_import(buy("01/02/2024", "PETR4 - X", 2, 30.0))
        before = Order.objects.count()

        rebuild_orders(self.user)

        self.assertEqual(Order.objects.count(), before)


class MovementEndpointTests(TestCase):
    PREVIEW = "/api/orders/import/preview"
    CONFIRM = "/api/orders/import/confirm"

    def setUp(self):
        self.user = User.objects.create_user("investidor", password="senha")
        self.client.force_login(self.user)

    def upload(self, *rows):
        return SimpleUploadedFile("movimentacao-2026-11-02.xlsx", movement_file(*rows).read())

    def test_preview_reports_duplicates_without_writing(self):
        rows = [buy("01/02/2024", "PETR4 - X", 1, 10.0), line("03/02/2024", "Tipo Novo", "PETR4 - X", 1)]

        body = self.client.post(self.PREVIEW, {"file": self.upload(*rows)}).json()

        self.assertEqual(body["file_type"], "movements")
        self.assertEqual((body["total_rows"], body["new_rows"], body["duplicate_rows"]), (2, 2, 0))
        self.assertEqual(body["unknown_types"], {"Tipo Novo": 1})
        self.assertEqual(Movement.objects.count(), 0)
        self.assertEqual(Order.objects.count(), 0)

    @mock.patch("wallet.views.start_history_rebuild")
    def test_confirm_then_preview_shows_everything_as_duplicate(self, rebuild):
        rows = [buy("01/02/2024", "PETR4 - X", 1, 10.0)]

        response = self.client.post(self.CONFIRM, {"file": self.upload(*rows)})

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["new_rows"], 1)
        rebuild.assert_called_once()
        body = self.client.post(self.PREVIEW, {"file": self.upload(*rows)}).json()
        self.assertEqual((body["new_rows"], body["duplicate_rows"]), (0, 1))

    @mock.patch("wallet.views.start_history_rebuild")
    def test_confirm_can_replace_manual_orders(self, rebuild):
        Order.objects.create(
            user=self.user,
            name="PETR4",
            broker="XP",
            asset_type="AC",
            order_type=1,
            date=SNAPSHOT,
            price=Decimal(1),
            volume=Decimal(1),
        )
        upload = self.upload(buy("01/02/2024", "PETR4 - X", 1, 10.0))
        body = self.client.post(self.PREVIEW, {"file": upload}).json()
        self.assertEqual(body["manual_conflicts"], [{"name": "PETR4", "count": 1}])

        self.client.post(
            self.CONFIRM, {"file": self.upload(buy("01/02/2024", "PETR4 - X", 1, 10.0)), "replace_manual": "true"}
        )

        self.assertFalse(Order.objects.filter(source=Order.SOURCE_MANUAL).exists())

    def test_invalid_movement_file_is_rejected(self):
        file = SimpleUploadedFile("m.xlsx", workbook_bytes({"Movimentação": [["Data"]]}).read())

        self.assertEqual(self.client.post(self.PREVIEW, {"file": file}).status_code, 400)

    @mock.patch("wallet.views.start_history_rebuild")
    def test_imported_orders_cannot_be_edited_or_deleted(self, rebuild):
        self.client.post(self.CONFIRM, {"file": self.upload(buy("01/02/2024", "PETR4 - X", 1, 10.0))})
        order = Order.objects.get()

        patch = self.client.patch(f"/api/order/{order.id}", data={"price": 1}, content_type="application/json")
        delete = self.client.delete(f"/api/order/{order.id}")

        self.assertEqual((patch.status_code, delete.status_code), (400, 400))
        self.assertTrue(Order.objects.filter(pk=order.pk).exists())

    @mock.patch("wallet.views.start_history_rebuild")
    def test_income_endpoint_and_position_fields(self, rebuild):
        AssetPrice.objects.create(ticker="PETR4", date=SNAPSHOT, close=20.0)
        rows = [
            buy("01/02/2024", "PETR4 - X", 10, 10.0),
            line("03/02/2024", "Dividendo", "PETR4 - X", 10, 1, 10),
            line("04/02/2024", "Juros Sobre Capital Próprio", "PETR4 - X", 10, 0.5, 5),
            line("05/02/2024", "Dividendo - Cancelado", "PETR4 - X", 10, 0.1, 1, "Debito"),
            line("06/02/2024", "Dividendo - Transferido", "PETR4 - X", 10, 9, 90),
            line("07/02/2024", "Cobrança de Taxa Semestral", "Tesouro IPCA+ 2026", 0, "-", 2, "Debito"),
            line("08/02/2024", "Resgate", "VELHO3 - X", 1, 3, 3),
            sell("09/02/2024", "PETR4 - X", 5, 30.0),
        ]
        self.client.post(self.CONFIRM, {"file": self.upload(*rows)})

        body = self.client.get("/api/income").json()
        labels = sorted((row["type"], row["value"]) for row in body["rows"])
        self.assertEqual(
            labels, [("Dividendos", -1.0), ("Dividendos", 10.0), ("JCP", 5.0), ("Outros", 3.0), ("Taxas", -2.0)]
        )
        self.assertEqual(body["rows"][0]["asset_class"], "AC")
        self.assertEqual(body["costs"]["PETR4"], 50.0)

        position = self.client.get("/api/position").json()
        asset = position["assets"][0]
        self.assertEqual((asset["income"], asset["cost"], asset["profit"]), (14.0, 50.0, 50.0))
        self.assertEqual(asset["total_return"], 64.0)
        self.assertEqual(position["summary"]["realized_gain"], 100.0)
        self.assertEqual(position["summary"]["income_total"], 17.0)

    def test_income_requires_login(self):
        self.client.logout()

        self.assertEqual(self.client.get("/api/income").status_code, 401)


class RebuildHistoryTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("investidor", password="senha")

    def order(self, name="PETR4", asset_type="AC", **overrides):
        fields = {
            "user": self.user,
            "name": name,
            "broker": "XP",
            "asset_type": asset_type,
            "order_type": 1,
            "date": date(2024, 1, 2),
            "price": Decimal(10),
            "volume": Decimal(10),
        }
        fields.update(overrides)
        return Order.objects.create(**fields)

    def price(self, day, close, ticker="PETR4"):
        AssetPrice.objects.create(ticker=ticker, date=day, close=close)

    def row(self, day, name="PETR4"):
        return AssetConsolidatedValue.objects.get(user=self.user, name=name, date=day)

    def test_values_each_day_with_quantity_of_that_day(self):
        self.order()
        self.order(kind=Order.KIND_EVENT, volume=Decimal(10), price=Decimal(0), date=date(2024, 1, 4))
        self.price(date(2024, 1, 3), 10.0)
        self.price(date(2024, 1, 4), 5.0)

        rebuild_history(self.user)

        self.assertEqual(self.row(date(2024, 1, 3)).value, Decimal(100))
        self.assertEqual(self.row(date(2024, 1, 4)).value, Decimal(100))
        self.assertEqual(self.row(date(2024, 1, 4)).invested, Decimal(100))

    def test_replaces_previous_history_and_is_repeatable(self):
        self.order()
        self.price(date(2024, 1, 3), 10.0)
        AssetConsolidatedValue.objects.create(
            user=self.user,
            name="ANTIGO3",
            asset_type="AC",
            date=date(2023, 1, 1),
            value=1,
            volume=1,
            invested=1,
        )

        first = rebuild_history(self.user)

        self.assertEqual(rebuild_history(self.user), first)
        self.assertFalse(AssetConsolidatedValue.objects.filter(name="ANTIGO3").exists())

    def test_snapshot_gives_exact_value_and_carries_fixed_income(self):
        self.order()
        self.order(name="CDB1", asset_type="RF", price=Decimal(1), volume=Decimal(1000), maturity_date=date(2030, 1, 1))
        snapshot_day = date(2024, 1, 5)
        PositionSnapshot.objects.bulk_create(
            [
                snapshot_row("PETR4", 10, 11, day=snapshot_day, user=self.user),
                snapshot_row("CDB1", 1000, 1.2, day=snapshot_day, asset_type="RF", user=self.user),
            ]
        )
        for day, close in ((date(2024, 1, 3), 10.0), (date(2024, 1, 8), 12.0)):
            self.price(day, close)

        rebuild_history(self.user)

        before_snapshot = self.row(date(2024, 1, 3), "CDB1").value
        self.assertGreater(before_snapshot, Decimal(1000))
        self.assertLess(before_snapshot, Decimal(1200))
        self.assertEqual(self.row(snapshot_day, "CDB1").value, Decimal(1200))
        self.assertEqual(self.row(snapshot_day).value, Decimal(110))
        self.assertEqual(self.row(date(2024, 1, 8), "CDB1").value, Decimal(1200))
        self.assertEqual(self.row(date(2024, 1, 8)).value, Decimal(120))

    def test_fixed_income_grows_smoothly_up_to_official_value(self):
        self.order(name="CDB1", asset_type="RF", price=Decimal(1), volume=Decimal(1000), maturity_date=date(2030, 1, 1))
        self.price(date(2024, 1, 2), 1.0, ticker="OUTRO3")
        self.price(date(2024, 7, 2), 1.0, ticker="OUTRO3")
        PositionSnapshot.objects.bulk_create(
            [
                snapshot_row("CDB1", 1000, 1.21, day=date(2025, 12, 31), asset_type="RF", user=self.user),
            ]
        )

        rebuild_history(self.user)

        self.assertEqual(self.row(date(2024, 1, 2), "CDB1").value, Decimal(1000))
        middle = self.row(date(2024, 7, 2), "CDB1").value
        self.assertGreater(middle, Decimal(1000))
        self.assertLess(middle, Decimal(1210))
        self.assertEqual(self.row(date(2025, 12, 31), "CDB1").value, Decimal(1210))

    def test_position_history_aggregates_by_date(self):
        for name, value in (("A", 10), ("B", 5), ("profit", 100)):
            AssetConsolidatedValue.objects.create(
                user=self.user,
                name=name,
                asset_type="AC",
                date=date(2024, 1, 3),
                value=value,
                volume=1,
                invested=2,
            )
        self.client.force_login(self.user)

        self.assertEqual(
            self.client.get("/api/position-history").json(),
            {"labels": ["03/01/2024"], "values": [15.0], "invested": [4.0]},
        )

    def test_does_not_touch_other_users(self):
        other = User.objects.create_user("outro", password="senha")
        AssetConsolidatedValue.objects.create(
            user=other,
            name="X",
            asset_type="AC",
            date=date(2023, 1, 1),
            value=1,
            volume=1,
            invested=1,
        )
        self.order()
        self.price(date(2024, 1, 3), 10.0)

        rebuild_history(self.user)

        self.assertTrue(AssetConsolidatedValue.objects.filter(user=other).exists())


class SnapshotMigrationTests(TestCase):
    def test_creates_snapshot_from_estimated_orders(self):
        user = User.objects.create_user("investidor", password="senha")
        apply_plan(
            user, build_plan(user, parse({"Acoes": [STOCK_HEADER, stock("PETR4", quantity=2, close=50.0)]}), SNAPSHOT)
        )
        PositionSnapshot.objects.all().delete()
        Order.objects.update(source=Order.SOURCE_MANUAL)
        Order.objects.create(
            user=user,
            name="MANUAL3",
            broker="XP",
            asset_type="AC",
            order_type=1,
            date=SNAPSHOT,
            price=Decimal(1),
            volume=Decimal(1),
        )

        importlib.import_module("wallet.migrations.0013_mark_position_orders_and_snapshots").forwards(apps, None)

        row = PositionSnapshot.objects.get()
        self.assertEqual((row.name, row.quantity, row.value, row.date), ("PETR4", Decimal(2), Decimal(100), SNAPSHOT))
        self.assertEqual(Order.objects.get(name="PETR4").source, Order.SOURCE_POSITION)
        self.assertEqual(Order.objects.get(name="MANUAL3").source, Order.SOURCE_MANUAL)
