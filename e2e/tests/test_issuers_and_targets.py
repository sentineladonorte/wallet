from playwright.sync_api import expect


def test_issuers_show_fgc_usage_without_treasury(page, portfolio):
    page.goto("/issuers")
    main = page.locator("main")

    expect(main).to_contain_text("BANCO ALFA S/A")
    expect(main).to_contain_text("BANCO BETA S/A")
    expect(main).to_contain_text("Dentro do limite")
    expect(main).not_to_contain_text("Tesouro Nacional")
    expect(page.get_by_role("meter")).to_have_count(2)


def set_target(form, label, value):
    form.get_by_label(label, exact=True).fill(str(value))


def test_targets_validate_sum_and_show_gap(page, portfolio):
    page.goto("/targets")
    classes = page.locator("form").first
    expect(classes).to_contain_text("Renda Fixa")

    set_target(classes, "Ações", 60)
    set_target(classes, "FIIs", 50)
    expect(classes).to_contain_text("passou 10,0%")
    expect(classes.locator("button[type=submit]")).to_be_disabled()

    set_target(classes, "Ações", 25)
    set_target(classes, "FIIs", 25)
    set_target(classes, "Renda Fixa", 50)
    # 25% de R$ 4.580,00 é R$ 1.145,00, e as ações valem R$ 300,00.
    expect(classes).to_contain_text("Aportar R$\xa0845,00")
    classes.locator("button[type=submit]").click()
    expect(page.locator("[aria-live=polite]")).to_contain_text("Metas salvas")

    page.reload()
    expect(page.locator("form").first.get_by_label("Renda Fixa", exact=True)).to_have_value("50")


def test_unsaved_targets_survive_saving_another_table(page, portfolio):
    page.goto("/targets")
    stocks = page.locator('details:has-text("Dentro de Ações") form')
    fixed = page.locator('details:has-text("Dentro de Renda Fixa") form')

    set_target(stocks, "Bancos", 20)
    set_target(fixed, "IPCA", 60)
    fixed.locator("button[type=submit]").click()
    expect(page.locator("[aria-live=polite]")).to_contain_text("Metas salvas")

    expect(stocks.get_by_label("Bancos", exact=True)).to_have_value("20")


def test_contribution_calculator_splits_amount_and_dashboard_shows_targets(page, portfolio):
    page.goto("/targets")
    classes = page.locator("form").first
    expect(classes).to_contain_text("Renda Fixa")
    set_target(classes, "Ações", 50)
    set_target(classes, "FIIs", 50)
    set_target(classes, "Renda Fixa", 0)
    classes.locator("button[type=submit]").click()
    expect(page.locator("[aria-live=polite]")).to_contain_text("Metas salvas")

    page.fill("#contribution", "1000")
    # Total depois do aporte: R$ 5.580. Faltam R$ 2.490 em ações e R$ 2.390 em FIIs, divididos na proporção.
    calculator = page.locator('section:has-text("Calculadora de aporte")').first
    expect(calculator).to_contain_text("R$\xa0510,25")
    expect(calculator).to_contain_text("R$\xa0489,75")
    expect(calculator).to_contain_text("Sem aporte")

    page.goto("/")
    expect(page.locator("main")).to_contain_text("Metas por classe")
    page.locator('ul button:has-text("Renda Fixa")').click()
    expect(page.locator("main")).to_contain_text("Metas em Renda Fixa")
