import itertools
import time
import uuid

import pytest
from reports import MOVEMENT_FILENAME, movement_report, position_filename, position_report

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_counter = itertools.count()
# O erro de quando o login é propositalmente recusado aparece no console do navegador.
IGNORED_CONSOLE = ("400 (Bad Request)",)


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    return {**browser_context_args, "ignore_https_errors": True, "viewport": {"width": 1440, "height": 1000}}


@pytest.fixture(autouse=True)
def console_is_clean(page):
    errors = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(str(e)))
    yield
    relevant = [e for e in errors if not any(text in e for text in IGNORED_CONSOLE)]
    assert not relevant, relevant


def upload(page, endpoint, name, content, **fields):
    response = page.request.post(
        f"/api/orders/import/{endpoint}",
        multipart={"file": {"name": name, "mimeType": XLSX, "buffer": content}, **fields},
    )
    assert response.ok, response.text()
    return response.json()


def upload_position(page):
    return upload(page, "confirm", position_filename(), position_report())


def upload_movements(page, content=None):
    return upload(page, "confirm", MOVEMENT_FILENAME, content or movement_report())


def wait_for_history(page, timeout=30):
    """O histórico é recalculado em segundo plano depois de importar."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        data = page.request.get("/api/position-history").json()
        if len(data["labels"]) > 100:
            return data
        time.sleep(0.5)
    raise AssertionError("O histórico não foi recalculado a tempo")


@pytest.fixture
def user(page):
    """Usuário novo a cada teste, para um não enxergar os dados do outro."""
    name = f"e2e{next(_counter)}{uuid.uuid4().hex[:8]}"
    response = page.request.post(
        "/api/register", data={"username": name, "email": f"{name}@e.com", "password": "Senha!12345"}
    )
    assert response.ok, response.text()
    return name


@pytest.fixture
def position_portfolio(page, user):
    upload_position(page)
    return user


@pytest.fixture
def portfolio(page, user):
    """Carteira completa: posição e histórico de movimentações."""
    upload_position(page)
    upload_movements(page)
    wait_for_history(page)
    return user
