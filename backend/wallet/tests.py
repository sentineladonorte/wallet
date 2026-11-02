import io
import importlib
from datetime import date, timedelta
from decimal import Decimal

from django.apps import apps
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase
from openpyxl import Workbook

from app.models import Asset, AssetPrice
from wallet.b3_import import ImportFileError, apply_plan, build_plan, parse_position_file
from wallet.models import AssetConsolidatedValue, Order

NU = "NU INVESTIMENTOS S.A. - CTVM"
SNAPSHOT = date(2026, 11, 2)
PREVIEW_URL = "/api/orders/import/preview"
CONFIRM_URL = "/api/orders/import/confirm"

STOCK_HEADER = [
    "Produto", "Instituição", "Conta", "Código de Negociação", "CNPJ da Empresa", "Código ISIN / Distribuição",
    "Tipo", "Escriturador", "Quantidade", "Quantidade Disponível", "Quantidade Indisponível", "Motivo",
    "Preço de Fechamento", "Valor Atualizado",
]
BDR_HEADER = [
    "Produto", "Instituição", "Conta", "Código de Negociação", "Código ISIN / Distribuição", "Tipo", "Escriturador",
    "Quantidade", "Quantidade Disponível", "Quantidade Indisponível", "Motivo", "Preço de Fechamento",
    "Valor Atualizado",
]
RF_HEADER = [
    "Produto", "Instituição", "Emissor", "Código", "Indexador", "Tipo de regime", "Data de Emissão", "Vencimento",
    "Quantidade", "Quantidade Disponível", "Quantidade Indisponível", "Motivo", "Contraparte",
    "Preço Atualizado MTM", "Valor Atualizado MTM", "Preço Atualizado CURVA", "Valor Atualizado CURVA",
    "Preço Atualizado FECHAMENTO", "Valor Atualizado FECHAMENTO",
]
TD_HEADER = [
    "Produto", "Instituição", "Código ISIN", "Indexador", "Vencimento", "Quantidade", "Quantidade Disponível",
    "Quantidade Indisponível", "Motivo", "Valor Aplicado", "Valor bruto", "Valor líquido", "Valor Atualizado",
]


def stock(code="TEST3", quantity=10, close=5.5, institution=NU):
    return [
        f"{code} - EMPRESA TESTE S.A.", institution, "1", code, "00000000000191", "BRTESTACNOR0 - 1", "ON", "BANCO",
        quantity, quantity, "-", "-", close, round(quantity * close, 2),
    ]


def bdr(code="TEST34", quantity=2, close=10.0):
    return [
        f"{code} - EMPRESA INC", NU, "1", code, "BRTESTBDR000 - 1", "BDR", "BANCO",
        quantity, quantity, "-", "-", close, round(quantity * close, 2),
    ]


def fixed_income(code="CDBTEST1", index="PREFIXADO", quantity=1000, price=1.05, product="CDB - BANCO TESTE S/A"):
    return [
        product, NU, "BANCO TESTE S/A", code, index, "DEPOSITADO", "10/02/2026", "10/02/2099", quantity, quantity,
        "-", "-", "-", "-", "-", price, round(quantity * price, 2), "-", "-",
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
        parsed = parse({
            "Renda Fixa": [
                RF_HEADER,
                fixed_income("CDBCDI", index="CDI"),
                fixed_income("CRI1", product="CRI - SECURITIZADORA"),
                fixed_income("CDBOK"),
            ]
        })

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
        self.run_import({
            "Acoes": [STOCK_HEADER, stock()],
            "Renda Fixa": [
                RF_HEADER,
                fixed_income("CDBPU1", quantity=1000, price=1.05),
                fixed_income("CDBPU1000", quantity=2, price=1814.87),
            ],
            "Tesouro Direto": [TD_HEADER, treasury()],
        })

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
        self.run_import({
            "ETF": [BDR_HEADER, etf],
            "Renda Fixa": [RF_HEADER, fixed_income()],
            "Tesouro Direto": [TD_HEADER, treasury()],
        })

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
            user=self.user, name="TEST34", broker="Nu Invest", asset_type="INT", order_type=1,
            date=date(2023, 1, 1), price=Decimal(8), volume=Decimal(1),
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
            user=self.user, name="CDB TESTE 2099-02-10", broker="Nu Invest", asset_type="RF", order_type=1,
            date=date(2026, 1, 1), price=Decimal(1000), volume=Decimal(1), maturity_date=date(2099, 2, 10),
            interest_rate=Decimal(10), index="P", fixed_income_type="CDB",
        )

        plan = build_plan(self.user, parse({"Renda Fixa": [RF_HEADER, fixed_income()]}), SNAPSHOT)

        self.assertTrue(plan.missing[0].possible_duplicate)

    def test_matured_fixed_income_is_not_listed_as_missing(self):
        Order.objects.create(
            user=self.user, name="CDB VENCIDO", broker="Nu Invest", asset_type="RF", order_type=1,
            date=date(2020, 1, 1), price=Decimal(1000), volume=Decimal(1), maturity_date=date(2021, 1, 1),
            index="P", fixed_income_type="CDB",
        )

        plan = build_plan(self.user, parse({"Acoes": [STOCK_HEADER, stock()]}), SNAPSHOT)

        self.assertEqual(plan.missing, [])

    def test_position_with_row_error_is_not_listed_as_missing(self):
        self.run_import({"Renda Fixa": [RF_HEADER, fixed_income("CDBX")]})

        plan = build_plan(
            self.user, parse({"Renda Fixa": [RF_HEADER, fixed_income("CDBX", index="CDI"), fixed_income("CDBY")]}),
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
            "user": user or self.user, "name": "TEST3", "broker": "Nu Invest", "asset_type": "AC", "order_type": 1,
            "date": date(2026, 1, 1), "price": Decimal(10), "volume": Decimal(10),
        }
        fields.update(overrides)
        return Order.objects.create(**fields)

    def fixed_income_order(self, **overrides):
        fields = {
            "name": "CDB1", "asset_type": "RF", "price": Decimal(1), "volume": Decimal(1000),
            "maturity_date": date.today() + timedelta(days=365), "index": "P", "fixed_income_type": "CDB",
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
            user=self.user, name="TD", asset_type="RF", date=SNAPSHOT, value=Decimal("2722.74"),
            volume=Decimal("0.69"), invested=Decimal("2161.03"),
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
            user=self.user, name="CDB1", asset_type="RF", date=SNAPSHOT, value=Decimal(1050),
            volume=Decimal(1000), invested=Decimal(1000),
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
            user=self.user, name="CDB1", asset_type="RF", date=SNAPSHOT, value=Decimal(1100),
            volume=Decimal(1000), invested=Decimal(1000),
        )
        AssetConsolidatedValue.objects.create(
            user=self.user, name="CDB1", asset_type="RF", date=SNAPSHOT - timedelta(days=1), value=Decimal(1000),
            volume=Decimal(1000), invested=Decimal(1000),
        )
        AssetConsolidatedValue.objects.create(
            user=other, name="CDB1", asset_type="RF", date=SNAPSHOT + timedelta(days=1), value=Decimal(9999),
            volume=Decimal(1000), invested=Decimal(1000),
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
        self.assertEqual(
            rows[1]["brokers"], [{"broker": "Nu Invest", "volume": 10.0}, {"broker": "XP", "volume": 5.0}]
        )

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
            user=self.user, name="CDB X 2030-01-01", asset_type="RF", date=SNAPSHOT, value=Decimal(10),
            volume=Decimal(1), invested=Decimal(10),
        )

        response = self.client.get("/api/position-history", {"ticker": "cdb x 2030-01-01"})

        self.assertEqual(response.json()["values"], [10.0])


class OrdersViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("investidor", password="senha")
        self.client.force_login(self.user)
        self.order = Order.objects.create(
            user=self.user, name="TEST3", broker="Nu Invest", asset_type="AC", order_type=1, date=SNAPSHOT,
            price=Decimal("3131.93"), volume=Decimal("0.69"), cost_estimated=True,
        )

    def test_returns_named_fields_newest_first(self):
        older = Order.objects.create(
            user=self.user, name="OLD3", broker="XP", asset_type="AC", order_type=-1, date=date(2020, 1, 1),
            price=Decimal(1), volume=Decimal(1),
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
            user=other, name="X", broker="XP", asset_type="AC", order_type=1, date=SNAPSHOT,
            price=Decimal(1), volume=Decimal(1),
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
            user=self.user, name=name, broker="Nu Invest", asset_type="RF", order_type=1, date=SNAPSHOT,
            price=Decimal(1), volume=Decimal(1), description=description, fixed_income_type=fixed_income_type,
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
                user=user, name="TEST3", broker="XP", asset_type="AC", order_type=1, date=SNAPSHOT,
                price=Decimal(1), volume=Decimal(1),
            )
            AssetConsolidatedValue.objects.create(
                user=user, name="TEST3", asset_type="AC", date=SNAPSHOT, value=Decimal(1),
                volume=Decimal(1), invested=Decimal(1),
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
        return self.client.patch(
            f"/api/asset/{ticker}/classification", data=data, content_type="application/json"
        )

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
