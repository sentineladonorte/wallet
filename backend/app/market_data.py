"""Cotações do arquivo oficial COTAHIST da B3, publicado depois de cada pregão."""

import io
import tempfile
import zipfile
from datetime import date, datetime

import requests

from app.models import AssetPrice

DAILY_URL = "https://bvmf.bmfbovespa.com.br/InstDados/SerHist/COTAHIST_D{day}.ZIP"
YEARLY_URL = "https://bvmf.bmfbovespa.com.br/InstDados/SerHist/COTAHIST_A{year}.ZIP"
REQUEST_TIMEOUT_SECONDS = 60
DOWNLOAD_CHUNK_BYTES = 1024 * 1024
BATCH_SIZE = 5000

QUOTE_RECORD = "01"
SPOT_MARKET = "010"
MAX_TICKER_LENGTH = 8
PRICE_SCALE = 100.0


class MarketDataError(Exception):
    """A B3 não respondeu ou o arquivo veio em formato inesperado."""


def _price(line, start, end, factor):
    return int(line[start:end]) / PRICE_SCALE / factor


def parse_line(line):
    """Interpreta uma linha do COTAHIST; devolve None se não for cotação do mercado à vista."""
    if line[:2] != QUOTE_RECORD or line[24:27] != SPOT_MARKET:
        return None
    ticker = line[12:24].strip()
    if not ticker or len(ticker) > MAX_TICKER_LENGTH:
        return None
    try:
        # Alguns ativos são cotados por lote: o preço vale para FATCOT unidades.
        factor = int(line[210:217]) or 1
        close = _price(line, 108, 121, factor)
        if close <= 0:
            return None
        return AssetPrice(
            ticker=ticker,
            date=datetime.strptime(line[2:10], "%Y%m%d").date(),
            open=_price(line, 56, 69, factor),
            high=_price(line, 69, 82, factor),
            low=_price(line, 82, 95, factor),
            mid=_price(line, 95, 108, factor),
            close=close,
        )
    except ValueError:
        return None


def _save_batch(prices_by_key):
    # O mesmo ticker pode aparecer duas vezes no dia, e o banco recusa duas atualizações da mesma linha.
    AssetPrice.objects.bulk_create(
        list(prices_by_key.values()),
        update_conflicts=True,
        unique_fields=["ticker", "date"],
        update_fields=["open", "high", "low", "mid", "close"],
    )


def _store_archive(archive_file):
    """Grava os preços do ZIP e retorna (quantidade de preços, data do último pregão)."""
    saved = 0
    last_session = None
    batch = {}
    try:
        with zipfile.ZipFile(archive_file) as archive:
            for name in archive.namelist():
                with archive.open(name) as content:
                    for raw in content:
                        price = parse_line(raw.decode("latin-1"))
                        if price is None:
                            continue
                        batch[(price.ticker, price.date)] = price
                        last_session = max(last_session, price.date) if last_session else price.date
                        if len(batch) >= BATCH_SIZE:
                            _save_batch(batch)
                            saved += len(batch)
                            batch = {}
    except zipfile.BadZipFile:
        raise MarketDataError("A B3 devolveu um arquivo inválido")
    if batch:
        _save_batch(batch)
        saved += len(batch)
    return saved, last_session


def _get(url, stream=False):
    try:
        return requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS, stream=stream)
    except requests.RequestException as error:
        raise MarketDataError(f"Não foi possível acessar a B3: {error.__class__.__name__}")


def fetch_session(day):
    """Baixa um pregão. Devolve None quando ele não existe: feriado ou arquivo ainda não publicado."""
    response = _get(DAILY_URL.format(day=day.strftime("%d%m%Y")))
    if response.status_code == 404:
        return None
    if response.status_code != 200:
        raise MarketDataError(f"A B3 respondeu {response.status_code}")
    return _store_archive(io.BytesIO(response.content))


def fetch_year(year):
    """Baixa um ano inteiro, para preencher períodos antigos. O arquivo tem dezenas de megabytes."""
    response = _get(YEARLY_URL.format(year=year), stream=True)
    if response.status_code != 200:
        raise MarketDataError(f"A B3 respondeu {response.status_code} para o ano {year}")
    with tempfile.TemporaryFile() as archive_file:
        for chunk in response.iter_content(chunk_size=DOWNLOAD_CHUNK_BYTES):
            archive_file.write(chunk)
        archive_file.seek(0)
        return _store_archive(archive_file)


def weekdays_between(start, end):
    current = start
    while current <= end:
        if current.weekday() < 5:
            yield current
        current = date.fromordinal(current.toordinal() + 1)
