"""Índices de referência para comparar a rentabilidade da carteira."""

from datetime import date, datetime, timedelta

import requests

from app.market_data import MarketDataError
from app.models import IndexRate

CDI = "CDI"
# Série 12 do Sistema Gerenciador de Séries do Banco Central: CDI diário, em % ao dia.
CDI_URL = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.12/dados"
FIRST_DATE = date(2020, 1, 1)
REQUEST_TIMEOUT_SECONDS = 60
# A API limita cada consulta a dez anos.
MAX_RANGE_DAYS = 3650
BATCH_SIZE = 2000


def _store_cdi(rows):
    rates = []
    for row in rows:
        try:
            rates.append(
                IndexRate(
                    code=CDI,
                    date=datetime.strptime(row["data"], "%d/%m/%Y").date(),
                    daily_percent=float(row["valor"]),
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    IndexRate.objects.bulk_create(rates, ignore_conflicts=True, batch_size=BATCH_SIZE)
    return len(rates)


def fetch_cdi(today):
    """Baixa só os dias que faltam. Retorna quantas taxas vieram."""
    last = IndexRate.objects.filter(code=CDI).order_by("-date").values_list("date", flat=True).first()
    start = last + timedelta(days=1) if last else FIRST_DATE
    if start > today:
        return 0
    end = min(today, start + timedelta(days=MAX_RANGE_DAYS))
    params = {"formato": "json", "dataInicial": start.strftime("%d/%m/%Y"), "dataFinal": end.strftime("%d/%m/%Y")}
    try:
        response = requests.get(CDI_URL, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
    except requests.RequestException as error:
        raise MarketDataError(f"Não foi possível acessar o Banco Central: {error.__class__.__name__}")
    # A API responde 404 quando ainda não há taxa no período, o que é normal em fim de semana e feriado.
    if response.status_code == 404:
        return 0
    if response.status_code != 200:
        raise MarketDataError(f"O Banco Central respondeu {response.status_code}")
    try:
        rows = response.json()
    except ValueError:
        raise MarketDataError("O Banco Central devolveu dados inválidos")
    return _store_cdi(rows) if isinstance(rows, list) else 0
