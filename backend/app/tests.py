import io
import zipfile
from datetime import date
from unittest import mock

import requests
from django.test import TestCase

from app.categories import fill_missing_categories, parse_bdr_page, parse_fii_page
from app.indices import fetch_cdi
from app.market_data import MarketDataError, fetch_session, fetch_year, parse_line, weekdays_between
from app.models import Asset, AssetPrice, IndexRate


def quote_line(ticker="PETR4", day="20261030", market="010", close=5271, factor=1, record="01"):
    line = record + day + "02" + ticker.ljust(12) + market
    line += "PETROBRAS   PN      N2   R$  "[:29]
    line = line.ljust(56)
    for value in (5245, 5366, 5236, 5288, close):
        line += str(value).zfill(13)
    line = line.ljust(210) + str(factor).zfill(7)
    return line.ljust(245)


def zip_bytes(lines):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("COTAHIST.TXT", ("\r\n".join(lines) + "\r\n").encode("latin-1"))
    return buffer.getvalue()


def response(status=200, content=b""):
    fake = mock.Mock(status_code=status, content=content)
    fake.iter_content = lambda chunk_size: [content]
    return fake


class ParseLineTests(TestCase):
    def test_reads_prices_in_reais(self):
        price = parse_line(quote_line())

        self.assertEqual(price.ticker, "PETR4")
        self.assertEqual(price.date, date(2026, 10, 30))
        self.assertEqual(
            (price.open, price.high, price.low, price.mid, price.close),
            (52.45, 53.66, 52.36, 52.88, 52.71),
        )

    def test_divides_by_quotation_factor(self):
        self.assertEqual(parse_line(quote_line(close=500000, factor=1000)).close, 5.0)

    def test_ignores_other_records_markets_and_invalid_lines(self):
        for line in [
            quote_line(record="00"),
            quote_line(record="99"),
            quote_line(market="020"),
            quote_line(market="070"),
            quote_line(ticker="MUITOLONGO123"),
            quote_line(close=0),
            quote_line(day="20261399"),
            "",
            "01 linha cortada",
        ]:
            self.assertIsNone(parse_line(line), line[:30])


class FetchTests(TestCase):
    @mock.patch("app.market_data.requests.get")
    def test_stores_session_and_updates_on_repeat(self, get):
        AssetPrice.objects.create(ticker="PETR4", date=date(2026, 10, 30), close=1.0)
        lines = [quote_line(), quote_line("VALE3", close=6202), quote_line(record="99")]
        get.return_value = response(content=zip_bytes(lines))

        self.assertEqual(fetch_session(date(2026, 10, 30)), (2, date(2026, 10, 30)))
        self.assertEqual(fetch_session(date(2026, 10, 30)), (2, date(2026, 10, 30)))

        self.assertEqual(AssetPrice.objects.count(), 2)
        self.assertEqual(AssetPrice.objects.get(ticker="PETR4").close, 52.71)
        self.assertIn("COTAHIST_D30102026.ZIP", get.call_args[0][0])

    @mock.patch("app.market_data.requests.get")
    def test_same_ticker_twice_in_file_does_not_fail(self, get):
        get.return_value = response(content=zip_bytes([quote_line(close=100), quote_line(close=200)]))

        fetch_session(date(2026, 10, 30))

        self.assertEqual(AssetPrice.objects.get().close, 2.0)

    @mock.patch("app.market_data.requests.get")
    def test_missing_session_is_not_an_error(self, get):
        get.return_value = response(status=404)

        self.assertIsNone(fetch_session(date(2026, 11, 2)))

    @mock.patch("app.market_data.requests.get")
    def test_failures_raise_market_data_error(self, get):
        for result in (response(status=500), response(content=b"nao e zip")):
            get.return_value = result
            with self.assertRaises(MarketDataError):
                fetch_session(date(2026, 10, 30))
        get.side_effect = requests.ConnectionError()
        with self.assertRaises(MarketDataError):
            fetch_session(date(2026, 10, 30))

    @mock.patch("app.market_data.requests.get")
    def test_fetches_full_year(self, get):
        get.return_value = response(content=zip_bytes([quote_line(day="20250102"), quote_line(day="20251230")]))

        self.assertEqual(fetch_year(2025), (2, date(2025, 12, 30)))
        self.assertIn("COTAHIST_A2025.ZIP", get.call_args[0][0])

    def test_weekdays_skip_weekends(self):
        days = list(weekdays_between(date(2026, 10, 30), date(2026, 11, 2)))

        self.assertEqual(days, [date(2026, 10, 30), date(2026, 11, 2)])


FII_PAGE = """
<span class="name"> SEGMENTO </span> <div class="value"> <span> {segment} </span></div>
<span class="name"> TIPO DE FUNDO </span> <div class="value"> <span> {fund_type} </span></div>
"""


def page(segment, fund_type):
    return mock.Mock(status_code=200, text=FII_PAGE.format(segment=segment, fund_type=fund_type))


def company(root, segment):
    fake = mock.Mock(status_code=200)
    fake.json.return_value = {"results": [{"issuingCompany": root, "segment": segment}]}
    return fake


@mock.patch("app.categories.time.sleep")
@mock.patch("app.categories.requests.get")
class FillCategoriesTests(TestCase):
    def test_parses_fii_page(self, get, sleep):
        self.assertEqual(
            parse_fii_page(FII_PAGE.format(segment="H&iacute;brido", fund_type="Fundo de Papel")),
            ("Híbrido", "Fundo de Papel"),
        )
        self.assertEqual(parse_fii_page("<html></html>"), (None, None))

    def test_fii_uses_portfolio_names(self, get, sleep):
        Asset.objects.create(ticker="OLDA11", asset_class="FII", category="Hibrido")
        cases = [
            ("BTHF11", "Híbrido", "Fundo de Papel", "Hibrido", "Papel"),
            ("XPLG11", "Logístico / Indústria / Galpões", "Fundo de Tijolo", "Logistico & Industrial", "Tijolo"),
            ("RBRX11", "Títulos e Valores Mobiliários", "Fundo de Fundos", "FOFs", "Fundos"),
            ("MXRF11", "Títulos e Valores Mobiliários", "Fundo de Papel", "Papel", "Papel"),
            ("NOVO11", "Agências de Bancos", "Fundo de Tijolo", "Agências de Bancos", "Tijolo"),
        ]
        for ticker, segment, fund_type, category, sub_category in cases:
            get.return_value = page(segment, fund_type)

            fill_missing_categories({ticker: "FII"})

            asset = Asset.objects.get(ticker=ticker)
            self.assertEqual((asset.category, asset.sub_category), (category, sub_category))

    def test_stock_prefers_sibling_over_b3(self, get, sleep):
        Asset.objects.create(ticker="CYRE3", asset_class="AC", category="Outros")

        filled, unresolved, failed = fill_missing_categories({"CYRE4": "AC"})

        self.assertEqual((filled, unresolved, failed), (1, [], False))
        self.assertEqual(Asset.objects.get(ticker="CYRE4").category, "Outros")
        get.assert_not_called()

    def test_stock_uses_b3_segment_and_alias(self, get, sleep):
        get.return_value = company("SBSP", "Água e Saneamento")

        fill_missing_categories({"SBSP3": "AC"})

        self.assertEqual(Asset.objects.get(ticker="SBSP3").category, "Saneamento")

    def test_unclassified_b3_segment_stays_empty(self, get, sleep):
        get.return_value = company("XPTO", "Não Classificados")

        filled, unresolved, _ = fill_missing_categories({"XPTO3": "AC"})

        self.assertEqual((filled, unresolved), (0, ["XPTO3"]))
        self.assertIsNone(Asset.objects.get(ticker="XPTO3").category)

    def test_b3_ignores_other_companies_in_search_results(self, get, sleep):
        get.return_value = company("IAME", "Bancos")

        _, unresolved, _ = fill_missing_categories({"COCA3": "AC"})

        self.assertEqual(unresolved, ["COCA3"])

    def test_parses_bdr_page(self, get, sleep):
        snippet = (
            "listada no setor de Financeiro e categorizada na ind&uacute;stria de\n"
            '<a href="x"> Bancos </a> . Nos meses'
        )

        self.assertEqual(parse_bdr_page(snippet), "Bancos")
        description = (
            "atua na indústria de bebidas não alcoólicas, criada por John. "
            "É categorizada na indústria de <a>Bebidas</a>."
        )
        self.assertEqual(parse_bdr_page(description), "Bebidas")
        self.assertIsNone(parse_bdr_page("atua na indústria de bebidas não alcoólicas, criada por John."))
        self.assertIsNone(parse_bdr_page("categorizada na indústria de bebidas, criada por John."))
        self.assertIsNone(parse_bdr_page("<html></html>"))

    def test_bdr_uses_investidor10_industry(self, get, sleep):
        get.return_value = mock.Mock(status_code=200, text="categorizada na indústria de <a>Bancos</a>. Fim")

        filled, _, _ = fill_missing_categories({"ROXO34": "BDR"})

        self.assertEqual(filled, 1)
        self.assertEqual(Asset.objects.get(ticker="ROXO34").category, "Bancos")
        self.assertIn("/bdrs/roxo34/", get.call_args[0][0])

    def test_bdr_prefers_sibling_category(self, get, sleep):
        Asset.objects.create(ticker="AMZO32", category="Tech")

        fill_missing_categories({"AMZO34": "BDR"})

        self.assertEqual(Asset.objects.get(ticker="AMZO34").category, "Tech")
        get.assert_not_called()

    def test_etf_has_no_source_and_makes_no_request(self, get, sleep):
        _, unresolved, _ = fill_missing_categories({"BOVA11": "ETF"})

        self.assertEqual(unresolved, ["BOVA11"])
        get.assert_not_called()

    def test_never_overwrites_existing_category(self, get, sleep):
        Asset.objects.create(ticker="HGLG11", asset_class="FII", category="Minha categoria")

        filled, _, _ = fill_missing_categories({"HGLG11": "FII"})

        self.assertEqual(filled, 0)
        self.assertEqual(Asset.objects.get(ticker="HGLG11").category, "Minha categoria")
        get.assert_not_called()

    def test_stops_after_repeated_failures(self, get, sleep):
        get.side_effect = requests.ConnectionError()

        _, unresolved, failed = fill_missing_categories({f"AAA{i}11": "FII" for i in range(5)})

        self.assertTrue(failed)
        self.assertEqual(len(unresolved), 5)
        self.assertEqual(get.call_count, 2)

    def test_limits_lookups_per_run(self, get, sleep):
        get.return_value = page("Shoppings", "Fundo de Tijolo")

        filled, unresolved, _ = fill_missing_categories({f"T{i:03}11": "FII" for i in range(25)})

        self.assertEqual((filled, len(unresolved)), (20, 5))
        self.assertEqual(get.call_count, 20)


@mock.patch("app.indices.requests.get")
class FetchCdiTests(TestCase):
    TODAY = date(2026, 10, 30)

    def api(self, rows, status=200):
        fake = mock.Mock(status_code=status)
        fake.json.return_value = rows
        return fake

    def test_stores_daily_rates(self, get):
        get.return_value = self.api(
            [{"data": "29/10/2026", "valor": "0.050788"}, {"data": "30/10/2026", "valor": "0.05"}]
        )

        self.assertEqual(fetch_cdi(self.TODAY), 2)

        self.assertEqual(IndexRate.objects.get(date=date(2026, 10, 29)).daily_percent, 0.050788)
        self.assertEqual(get.call_args[1]["params"]["dataInicial"], "01/01/2020")

    def test_downloads_only_what_is_missing(self, get):
        IndexRate.objects.create(code="CDI", date=date(2026, 10, 28), daily_percent=0.05)
        get.return_value = self.api([])

        fetch_cdi(self.TODAY)

        self.assertEqual(get.call_args[1]["params"]["dataInicial"], "29/10/2026")

    def test_nothing_to_do_when_up_to_date(self, get):
        IndexRate.objects.create(code="CDI", date=self.TODAY, daily_percent=0.05)

        self.assertEqual(fetch_cdi(self.TODAY), 0)
        get.assert_not_called()

    def test_respects_ten_year_limit_of_api(self, get):
        get.return_value = self.api([])

        fetch_cdi(date(2035, 1, 1))

        self.assertEqual(get.call_args[1]["params"]["dataFinal"], "29/12/2029")

    def test_no_rate_in_period_is_not_an_error(self, get):
        get.return_value = self.api([], status=404)

        self.assertEqual(fetch_cdi(self.TODAY), 0)

    def test_ignores_malformed_rows(self, get):
        get.return_value = self.api(
            [{"data": "x", "valor": "1"}, {"data": "30/10/2026"}, {"data": "29/10/2026", "valor": "0.05"}]
        )

        self.assertEqual(fetch_cdi(self.TODAY), 1)

    def test_failures_raise_market_data_error(self, get):
        get.return_value = self.api([], status=500)
        with self.assertRaises(MarketDataError):
            fetch_cdi(self.TODAY)
        get.side_effect = requests.ConnectionError()
        with self.assertRaises(MarketDataError):
            fetch_cdi(self.TODAY)
