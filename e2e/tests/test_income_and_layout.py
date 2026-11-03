import pytest
from playwright.sync_api import expect


def test_income_page_totals_and_filters(page, portfolio):
    page.goto("/income")
    main = page.locator("main")

    # Rendimentos 6 + dividendo 10 + JCP 5.
    expect(main).to_contain_text("R$\xa021,00")
    expect(main).to_contain_text("4 pagamento(s)")
    expect(main).to_contain_text("LOGI11")

    page.get_by_role("group", name="Filtrar por classe").get_by_role("button", name="FIIs").click()
    expect(main).to_contain_text("R$\xa06,00")
    expect(page.locator("tbody")).not_to_contain_text("BANK3")


def test_income_chart_groups_by_month_or_year(page, portfolio):
    page.goto("/income")
    chart = page.locator("canvas").first
    expect(chart).to_have_attribute("aria-label", "Proventos recebidos por mês e por tipo")
    expect(page.locator("main")).to_contain_text("Recebido por mês")

    group = page.get_by_role("group", name="Agrupar gráfico por")
    group.get_by_role("button", name="Ano").click()

    expect(group.get_by_role("button", name="Ano")).to_have_attribute("aria-pressed", "true")
    expect(page.locator("canvas").first).to_have_attribute("aria-label", "Proventos recebidos por ano e por tipo")
    expect(page.locator("main")).to_contain_text("Recebido por ano")
    # Agrupar muda o gráfico, não os totais.
    expect(page.locator("main")).to_contain_text("R$\xa021,00")

    group.get_by_role("button", name="Mês").click()
    expect(page.locator("main")).to_contain_text("Recebido por mês")


def test_income_page_without_data_offers_import(page, position_portfolio):
    page.goto("/income")
    expect(page.get_by_text("Nenhum provento registrado")).to_be_visible()


@pytest.mark.parametrize("width", [360, 390])
@pytest.mark.parametrize(
    "path", ["/", "/orders", "/targets", "/income", "/issuers", "/tickers", "/maturities", "/performance"]
)
def test_no_horizontal_overflow_on_phones(page, portfolio, path, width):
    page.set_viewport_size({"width": width, "height": 800})
    page.goto(path)
    page.wait_for_load_state("networkidle")

    scroll_width, inner_width = page.evaluate("[document.documentElement.scrollWidth, window.innerWidth]")
    assert scroll_width <= inner_width


def test_menu_shows_names_on_desktop(page, user):
    page.goto("/")
    menu = page.get_by_role("navigation", name="Principal")
    for label in (
        "Carteira",
        "Rentabilidade",
        "Metas",
        "Proventos",
        "Vencimentos",
        "Boletas",
        "Ativos",
        "Emissores",
        "Perfil",
    ):
        expect(menu.get_by_text(label, exact=True)).to_be_visible()
