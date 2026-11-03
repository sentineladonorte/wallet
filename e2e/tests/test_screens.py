"""Salva capturas das telas em e2e/artifacts/screens para revisão visual: testes não avaliam aparência."""

from pathlib import Path

import pytest

SCREENS = Path("/e2e/artifacts/screens")
PAGES = {
    "carteira": "/",
    "rentabilidade": "/performance",
    "metas": "/targets",
    "proventos": "/income",
    "vencimentos": "/maturities",
    "emissores": "/issuers",
    "boletas": "/orders",
}


@pytest.mark.parametrize("name,path", PAGES.items())
def test_capture(page, portfolio, name, path):
    SCREENS.mkdir(parents=True, exist_ok=True)
    page.goto(path)
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(1200)
    page.screenshot(path=SCREENS / f"{name}.png")

    page.set_viewport_size({"width": 360, "height": 800})
    page.wait_for_timeout(600)
    page.screenshot(path=SCREENS / f"{name}-celular.png")
