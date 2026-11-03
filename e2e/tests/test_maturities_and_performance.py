from datetime import date, timedelta

from conftest import upload_movements
from playwright.sync_api import expect
from reports import _move, movement_report, movement_rows


def test_calendar_shows_upcoming_maturities_with_estimated_value(page, portfolio):
    page.goto("/maturities")
    main = page.locator("main")

    expect(main).to_contain_text("Vencimentos e caixa")
    # Um título vence em 20 dias, e o outro passa de um ano.
    expect(main).to_contain_text("Próximos 30 dias")
    expect(main.locator("section", has_text="Próximos 30 dias")).to_contain_text("1 título(s)")
    expect(main.locator("section", has_text="Próximos 12 meses")).to_contain_text("1 título(s)")
    expect(main).to_contain_text("Por mês")
    expect(main).not_to_contain_text("sem vencimento conhecido")

    position = page.request.get("/api/position").json()
    title = next(asset for asset in position["assets"] if asset["name"] == "CDBFICT1")
    # 10% em um ano: a taxa implícita projeta um valor um pouco maior no vencimento.
    assert round(title["estimated_rate"], 0) == 10
    assert 1100 < title["maturity_value"] < 1110


def test_reinvestment_simulation_uses_targets_and_removes_maturing_title(page, portfolio):
    response = page.request.put(
        "/api/targets",
        data={"asset_class": None, "targets": [{"key": "AC", "percent": 50}, {"key": "RF", "percent": 50}]},
    )
    assert response.ok

    page.goto("/maturities")
    page.locator("summary", has_text="título(s)").first.click()
    page.get_by_role("button", name="Simular reinvestimento").first.click()

    simulator = page.locator("section", has_text="Reinvestir em")
    expect(simulator).to_contain_text("do aporte")
    expect(simulator).to_contain_text("Renda Fixa")
    assert float(simulator.locator("#contribution").input_value()) > 1100


def test_reinvestment_without_targets_points_to_targets_page(page, portfolio):
    page.goto("/maturities")
    page.locator("summary", has_text="título(s)").first.click()
    page.get_by_role("button", name="Simular reinvestimento").first.click()

    expect(page.locator("section", has_text="Reinvestir em").get_by_role("link", name="Metas")).to_be_visible()


def test_title_bought_after_last_report_is_listed_without_maturity(page, portfolio):
    purchase = _move(
        date.today() + timedelta(days=1), "COMPRA / VENDA", "CDB - CDBNOVO9 - BANCO GAMA S/A", 1, 1000.0, 1000.0
    )
    upload_movements(page, movement_report([*movement_rows(), purchase]))

    page.goto("/maturities")
    expect(page.locator("section", has_text="sem vencimento conhecido")).to_contain_text("CDBNOVO9")

    page.goto("/")
    expect(page.locator("tbody")).to_contain_text("CDBNOVO9")


def test_maturities_empty_state(page, user):
    page.goto("/maturities")
    expect(page.get_by_text("Nenhum título com vencimento")).to_be_visible()


def test_performance_compares_with_benchmarks(page, portfolio):
    page.goto("/performance")
    main = page.locator("main")

    expect(main).to_contain_text("Aportes e resgates não alteram o percentual")
    expect(page.locator("canvas").first).to_have_attribute(
        "aria-label", "Rentabilidade acumulada da carteira comparada ao CDI e ao Ibovespa"
    )
    table = page.locator("table")
    expect(table).to_contain_text("12 meses")
    expect(table).to_contain_text("p.p.")
    expect(main).to_contain_text("BOVA11")

    series = page.request.get("/api/performance").json()
    # CDI fictício de 0,05% ao dia e BOVA11 subindo devagar: os dois precisam ter acumulado alta.
    assert series["cdi"][-1] > 1 and series["ibov"][-1] > 1 and series["portfolio"][-1] > 1
    assert len(series["dates"]) == len(series["portfolio"]) == len(series["cdi"]) == len(series["ibov"])


def test_performance_periods_and_class_filter(page, portfolio):
    page.goto("/performance")
    periods = page.get_by_role("group", name="Período")
    expect(page.locator("canvas").first).to_be_visible()

    periods.get_by_role("button", name="Tudo").click()
    expect(periods.get_by_role("button", name="Tudo")).to_have_attribute("aria-pressed", "true")
    expect(page.locator("canvas").first).to_be_visible()

    page.get_by_role("group", name="Filtrar por classe").get_by_role("button", name="Renda Fixa").click()
    expect(
        page.get_by_role("group", name="Filtrar por classe").get_by_role("button", name="Renda Fixa")
    ).to_have_attribute("aria-pressed", "true")
    expect(page.locator("table")).to_contain_text("12 meses")


def test_period_longer_than_history_shows_no_number(page, portfolio):
    page.goto("/performance")
    longer = page.locator("tbody tr", has_text="24 meses")
    # O histórico fictício tem um ano: 24 meses não pode repetir o acumulado total.
    expect(longer.locator("td").nth(1)).to_have_text("-")

    page.get_by_role("group", name="Período").get_by_role("button", name="24 meses").click()
    expect(page.get_by_text("Sem dados suficientes neste período.")).to_be_visible()


def test_performance_empty_without_history(page, position_portfolio):
    page.goto("/performance")
    expect(page.get_by_text("Ainda sem histórico suficiente")).to_be_visible()
