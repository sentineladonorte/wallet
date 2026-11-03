import re

from conftest import MOVEMENT_FILENAME, XLSX, upload, upload_movements, upload_position
from playwright.sync_api import expect
from reports import _move, movement_report, movement_rows, position_filename, position_report
from datetime import date


def choose_file(page, name, content):
    page.set_input_files("#b3File", {"name": name, "mimeType": XLSX, "buffer": content})
    page.get_by_role("button", name="Ver prévia").click()


def state(page):
    position = page.request.get("/api/position").json()
    return {
        "assets": len(position["assets"]),
        "value": position["summary"]["value"],
        "invested": position["summary"]["invested"],
        "income": position["summary"]["income_total"],
        "orders": len(page.request.get("/api/orders/").json()),
    }


def test_login_rejects_wrong_password_and_register_opens_empty_portfolio(page):
    page.goto("/")
    page.wait_for_url("**/auth")
    page.fill("#username", "nao-existe")
    page.fill("#password", "errada")
    page.click("button[type=submit]")
    expect(page.get_by_text("Usuário ou senha inválidos.")).to_be_visible()

    page.goto("/auth/register")
    name = "novo" + str(abs(hash(page)) % 10**8)
    page.fill("#username", name)
    page.fill("#email", f"{name}@e.com")
    page.fill("#password", "Senha!12345")
    page.click("button[type=submit]")
    expect(page.get_by_text("Sua carteira está vazia")).to_be_visible()


def test_logout_goes_back_to_login(page, user):
    page.goto("/")
    page.get_by_role("button", name="Sair").click()
    page.wait_for_url("**/auth")


def test_position_import_shows_preview_and_totals(page, user):
    page.goto("/orders?import=1")
    choose_file(page, position_filename(), position_report())

    dialog = page.get_by_role("dialog")
    expect(dialog).to_contain_text("R$\xa04.580,00")
    expect(dialog).to_contain_text("custos são estimados")
    dialog.get_by_role("button", name="Confirmar importação").click()
    expect(page.locator("[aria-live=polite]")).to_contain_text("9 boleta(s) criada(s)")

    page.goto("/")
    expect(page.locator("main")).to_contain_text("R$\xa04.580,00")


def test_invalid_file_shows_error(page, user):
    page.goto("/orders?import=1")
    choose_file(page, "invalido.xlsx", b"nao e um xlsx")

    expect(page.get_by_role("dialog")).to_contain_text("Não foi possível ler o arquivo")


def test_movement_preview_reports_reconciliation(page, position_portfolio):
    page.goto("/orders?import=1")
    choose_file(page, MOVEMENT_FILENAME, movement_report())

    dialog = page.get_by_role("dialog")
    expect(dialog).to_contain_text(re.compile(r"Linhas novas\s*16"))
    expect(dialog).to_contain_text("9 de 9")
    expect(dialog).not_to_contain_text("não reconhecidos")


def test_movements_replace_estimated_costs(page, portfolio):
    position = page.request.get("/api/position").json()
    assets = {asset["name"]: asset for asset in position["assets"]}

    assert position["summary"]["estimated_assets"] == 0
    # 12 cotas a R$ 15,4166 de preço médio, menos 2 vendidas.
    assert round(assets["BANK3"]["cost"] / assets["BANK3"]["volume"], 2) == 15.42
    # O desdobro dobra a quantidade e mantém o custo.
    assert assets["AGUA3"]["volume"] == 10 and assets["AGUA3"]["cost"] == 80
    assert assets["CDBFICT1"]["issuer"] == "BANCO ALFA S/A"
    assert position["summary"]["value"] == 4580
    # Venda de 2 cotas a R$ 18,00 contra o preço médio de R$ 15,4167.
    assert round(position["summary"]["realized_gain"], 2) == 5.17


def test_reimporting_never_duplicates(page, portfolio):
    before = state(page)

    # Arquivo menor, só com as últimas linhas.
    recent = upload(page, "preview", MOVEMENT_FILENAME, movement_report(movement_rows()[-3:]))
    assert (recent["new_rows"], recent["duplicate_rows"]) == (0, 3)
    upload_movements(page, movement_report(movement_rows()[-3:]))
    assert state(page) == before

    # Arquivo completo e relatório de posição de novo.
    upload_movements(page)
    upload_position(page)
    assert state(page) == before


def test_only_new_rows_are_added(page, portfolio):
    before = state(page)
    extra = _move(date.today(), "Rendimento", "LOGI11 - FUNDO LOGI11", 3, 2.0, 6.0)

    result = upload_movements(page, movement_report([*movement_rows()[-2:], extra]))

    after = state(page)
    assert result["new_rows"] == 1
    assert round(after["income"] - before["income"], 2) == 6
    assert after["value"] == before["value"] and after["orders"] == before["orders"]


def test_imported_orders_are_locked_and_events_are_optional(page, portfolio):
    page.goto("/orders")
    expect(page.locator("tbody")).to_contain_text("BANK3")
    expect(page.locator('tbody button[aria-label^="Editar"]')).to_have_count(0)
    expect(page.locator("tbody")).not_to_contain_text("Desdobro")

    page.get_by_label("Mostrar eventos e transferências").check()
    expect(page.locator("tbody")).to_contain_text("Desdobro")


def test_estimated_cost_badge_goes_away_after_editing(page, position_portfolio):
    page.goto("/orders")
    row = page.locator("tbody tr", has_text="TESOURO SELIC 2099")
    expect(row).to_contain_text("estimado")

    row.get_by_role("button", name=re.compile("Editar")).click()
    page.fill("#price", "1500.55")
    page.get_by_role("dialog").locator("button[type=submit]").click()
    expect(page.locator("[aria-live=polite]")).to_contain_text("Boleta atualizada")
    expect(row).not_to_contain_text("estimado")
