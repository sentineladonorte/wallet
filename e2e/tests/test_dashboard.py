import re

from playwright.sync_api import expect

LEAK = re.compile(r"R\$\s*[\d.]+,\d\d")
FGC_LIMIT = "250.000,00"


def rows(page):
    return page.locator("tbody tr")


def visible_money(text):
    return [value for value in LEAK.findall(text) if FGC_LIMIT not in value]


def test_pie_drills_down_and_table_follows(page, portfolio):
    page.goto("/")
    expect(rows(page)).to_have_count(9)

    page.locator('ul button:has-text("FIIs")').click()
    expect(rows(page)).to_have_count(2)
    expect(page.locator("main")).to_contain_text("Evolução: FIIs")

    page.locator('ul button:has-text("Logístico")').click()
    expect(rows(page)).to_have_count(1)

    page.get_by_role("navigation", name="Nível da distribuição").get_by_role("button", name="Carteira").click()
    expect(rows(page)).to_have_count(9)


def test_clicking_a_slice_filters(page, portfolio):
    page.goto("/")
    expect(page.locator("canvas").first).to_be_visible()
    page.wait_for_timeout(800)
    box = page.locator("canvas").first.bounding_box()

    page.mouse.click(box["x"] + box["width"] * 0.85, box["y"] + box["height"] * 0.5)

    expect(page.get_by_role("navigation", name="Nível da distribuição")).to_contain_text("Renda Fixa")
    expect(rows(page)).to_have_count(3)


def test_other_groupings_are_available(page, portfolio):
    page.goto("/")
    for tab, expected in (("Corretora", "Nu Invest"), ("Emissor", "BANCO ALFA S/A"), ("Indexador", "IPCA")):
        page.get_by_role("tab", name=tab, exact=True).click()
        expect(page.locator("ul").first).to_contain_text(expected)


def test_tooltip_is_drawn_above_center_total(page, portfolio):
    page.goto("/")
    canvas = page.locator("canvas").first
    expect(canvas).to_be_visible()

    z_index = canvas.evaluate("element => getComputedStyle(element).zIndex")
    center = canvas.locator("xpath=preceding-sibling::div[1]")
    assert int(z_index) > int(center.evaluate("element => getComputedStyle(element).zIndex"))


def test_class_filter_on_positions_table(page, portfolio):
    page.goto("/")
    chips = page.get_by_role("group", name="Filtrar por classe")

    chips.get_by_role("button", name=re.compile("Ações")).click()
    expect(rows(page)).to_have_count(2)
    expect(page.locator("tbody")).not_to_contain_text("LOGI11")

    chips.get_by_role("button", name=re.compile("Todas")).click()
    expect(rows(page)).to_have_count(9)


def test_investidor10_links_by_class(page, portfolio):
    page.goto("/")
    expected = {
        "BANK3": "https://investidor10.com.br/acoes/bank3/",
        "LOGI11": "https://investidor10.com.br/fiis/logi11/",
        "TECH34": "https://investidor10.com.br/bdrs/tech34/",
        "INDX11": "https://investidor10.com.br/etfs/indx11/",
    }
    for name, url in expected.items():
        expect(page.locator(f'tbody a:has-text("{name}")').first).to_have_attribute("href", url)
    expect(page.locator('tbody a:has-text("CDBFICT1")')).to_have_count(0)


def test_table_search_sort_and_csv(page, portfolio):
    page.goto("/")
    page.get_by_label("Buscar ativo").fill("tesouro")
    expect(rows(page)).to_have_count(1)
    page.get_by_label("Buscar ativo").fill("")

    page.locator('th button:has-text("Ativo")').click()
    expect(rows(page).first).to_contain_text("AGUA3")

    with page.expect_download() as download:
        page.get_by_role("button", name="Exportar CSV").click()
    assert download.value.suggested_filename == "carteira.csv"


def test_classification_can_be_edited(page, portfolio):
    page.goto("/")
    # A categoria é global: edita um ativo que nenhum outro teste usa pela categoria.
    page.get_by_role("button", name="Editar classificação de TECH34").click()
    page.fill("#category", "Plataformas")
    page.get_by_role("dialog").locator("button[type=submit]").click()

    expect(page.locator("[aria-live=polite]")).to_contain_text("Classificação de TECH34 atualizada")
    expect(page.locator("tbody")).to_contain_text("Plataformas")


def test_hide_values_masks_everything_and_persists(page, portfolio):
    page.goto("/")
    expect(rows(page)).to_have_count(9)
    assert visible_money(page.inner_text("main"))

    page.get_by_role("button", name="Ocultar valores").click()
    for path in ("/", "/orders", "/issuers", "/targets", "/income", "/maturities"):
        page.goto(path)
        expect(page.locator("main")).to_contain_text("••••")
        assert not visible_money(page.inner_text("main")), path

    page.get_by_role("button", name="Mostrar valores").click()
    page.goto("/")
    expect(page.locator("main")).to_contain_text("R$\xa04.580,00")


def test_asset_detail_page(page, portfolio):
    page.goto("/tickers/BANK3")
    expect(page.get_by_text("Abrir no Investidor10")).to_have_attribute(
        "href", "https://investidor10.com.br/acoes/bank3/"
    )
    expect(page.locator(".highcharts-container")).to_be_visible()
    expect(page.locator("main")).to_contain_text("Proventos")

    page.goto("/tickers/CDBFICT1")
    expect(page.get_by_text("Sem cotações")).to_be_visible()
