"""Preenche a categoria de ativos que ainda não têm, sem nunca sobrescrever o que já existe."""

import base64
import html
import json
import re
import time
import unicodedata

import requests

from app.models import Asset

B3_COMPANY_URL = "https://sistemaswebb3-listados.b3.com.br/listedCompaniesProxy/CompanyCall/GetInitialCompanies/{query}"
INVESTIDOR10_FII_URL = "https://investidor10.com.br/fiis/{ticker}/"
INVESTIDOR10_BDR_URL = "https://investidor10.com.br/bdrs/{ticker}/"
REQUEST_TIMEOUT_SECONDS = 20
REQUEST_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; wallet-carteira-pessoal)"}
# Consulta só o que falta, com intervalo entre as páginas, para não sobrecarregar o site.
SECONDS_BETWEEN_PAGES = 1
MAX_LOOKUPS_PER_RUN = 20
MAX_CONSECUTIVE_FAILURES = 2
MAX_CATEGORY_LENGTH = 32

UNCLASSIFIED_B3_SEGMENTS = {"nao classificados", "nao classificado"}
FUND_OF_FUNDS_TYPE = "fundo de fundos"
PAPER_TYPE = "fundo de papel"
FUND_TYPE_PREFIX = "Fundo de "
SECURITIES_SEGMENT = "titulos e valores mobiliarios"

# Nomes que as fontes usam para o que a carteira já chama de outra forma; as metas comparam o texto exato.
CATEGORY_ALIASES = {
    "logistico / industria / galpoes": "Logistico & Industrial",
    "logistica": "Logistico & Industrial",
    "lajes corporativas": "Office",
    "shoppings": "Shopping",
    "shoppings / varejo": "Shopping",
    "fundo de fundos": "FOFs",
    "papeis": "Papel",
    "agua e saneamento": "Saneamento",
}


class LookupFailed(Exception):
    """A fonte não pôde ser consultada, o que é diferente de ela não ter o dado."""


def _normalize(text):
    decomposed = unicodedata.normalize("NFKD", text)
    return " ".join("".join(c for c in decomposed if not unicodedata.combining(c)).lower().split())


def _existing_labels():
    labels = Asset.objects.exclude(category__isnull=True).exclude(category="").values_list("category", flat=True)
    return {_normalize(label): label for label in labels}


def _harmonize(raw, labels):
    """Reaproveita o nome já usado na carteira, para que metas e gráficos não se dividam."""
    normalized = _normalize(raw)
    alias = CATEGORY_ALIASES.get(normalized)
    return (alias or labels.get(normalized) or raw.strip())[:MAX_CATEGORY_LENGTH]


def _get(url):
    try:
        response = requests.get(url, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT_SECONDS)
    except requests.RequestException as error:
        raise LookupFailed(error.__class__.__name__)
    if response.status_code == 404:
        return None
    if response.status_code != 200:
        raise LookupFailed(f"HTTP {response.status_code}")
    return response


def parse_fii_page(page):
    """Extrai (segmento, tipo de fundo) do bloco de dados da página de um FII."""

    def field(label):
        match = re.search(r">\s*" + label + r'\s*</span>\s*<div class="value">\s*<span>\s*([^<]+?)\s*</span>', page)
        return html.unescape(match.group(1)) if match else None

    return field("SEGMENTO"), field("TIPO DE FUNDO")


def _fii_classification(ticker, labels):
    response = _get(INVESTIDOR10_FII_URL.format(ticker=ticker.lower()))
    if response is None:
        return None, None
    segment, fund_type = parse_fii_page(response.text)
    if not segment:
        return None, None

    category = segment
    normalized_type = _normalize(fund_type or "")
    # "Títulos e Valores Mobiliários" reúne fundos de papel e de fundos, que a carteira separa.
    if _normalize(segment) == SECURITIES_SEGMENT:
        if normalized_type == FUND_OF_FUNDS_TYPE:
            category = "Fundo de Fundos"
        elif normalized_type == PAPER_TYPE:
            category = "Papel"

    sub_category = fund_type
    if fund_type and fund_type.startswith(FUND_TYPE_PREFIX):
        sub_category = fund_type[len(FUND_TYPE_PREFIX):]
    return _harmonize(category, labels), sub_category[:MAX_CATEGORY_LENGTH] if sub_category else None


def parse_bdr_page(page):
    """Extrai a indústria da frase "categorizada na indústria de <a>Bancos</a>." da página de um BDR."""
    text = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", page)))
    # A descrição da empresa pode citar "na indústria de ..." antes, por isso a frase completa.
    match = re.search(r"categorizada na indústria de\s+([^.,]{1,%d}?)\s*\." % MAX_CATEGORY_LENGTH, text)
    return match.group(1) if match else None


def _bdr_industry(ticker, labels):
    response = _get(INVESTIDOR10_BDR_URL.format(ticker=ticker.lower()))
    if response is None:
        return None
    industry = parse_bdr_page(response.text)
    return _harmonize(industry, labels) if industry else None


def _b3_segment(ticker, labels):
    root = ticker[:4]
    payload = {"language": "pt-br", "pageNumber": 1, "pageSize": 20, "company": root}
    query = base64.b64encode(json.dumps(payload).encode()).decode()
    response = _get(B3_COMPANY_URL.format(query=query))
    if response is None:
        return None
    try:
        results = response.json().get("results") or []
    except ValueError:
        raise LookupFailed("resposta inválida")
    for company in results:
        segment = (company.get("segment") or "").strip()
        if company.get("issuingCompany") == root and segment and _normalize(segment) not in UNCLASSIFIED_B3_SEGMENTS:
            return _harmonize(segment, labels)
    return None


def _sibling_category(ticker):
    """Outro papel da mesma empresa, como CYRE3 para CYRE4, já traz a categoria escolhida na carteira."""
    sibling = (
        Asset.objects.filter(ticker__startswith=ticker[:4])
        .exclude(ticker=ticker)
        .exclude(category__isnull=True)
        .exclude(category="")
        .order_by("ticker")
        .first()
    )
    return sibling.category if sibling else None


def fill_missing_categories(asset_classes):
    """Recebe {ticker: classe} e retorna (preenchidos, tickers sem categoria, fontes com falha)."""
    labels = _existing_labels()
    filled = 0
    lookups = 0
    consecutive_failures = 0
    unresolved = []
    failed = False

    for ticker in sorted(asset_classes):
        asset_class = asset_classes[ticker]
        asset, _ = Asset.objects.get_or_create(ticker=ticker, defaults={"asset_class": asset_class})
        if asset.category:
            continue

        category = None
        sub_category = None
        is_company = asset_class in ("AC", "BDR", "INT")
        if is_company:
            category = _sibling_category(ticker)

        can_look_up = lookups < MAX_LOOKUPS_PER_RUN and consecutive_failures < MAX_CONSECUTIVE_FAILURES
        if not category and can_look_up and (is_company or asset_class == "FII"):
            lookups += 1
            try:
                if asset_class == "FII":
                    category, sub_category = _fii_classification(ticker, labels)
                    time.sleep(SECONDS_BETWEEN_PAGES)
                elif asset_class == "AC":
                    category = _b3_segment(ticker, labels)
                else:
                    category = _bdr_industry(ticker, labels)
                    time.sleep(SECONDS_BETWEEN_PAGES)
                consecutive_failures = 0
            except LookupFailed:
                consecutive_failures += 1
                failed = True

        if not category:
            unresolved.append(ticker)
            continue

        asset.category = category
        if sub_category and not asset.sub_category:
            asset.sub_category = sub_category
        asset.save(update_fields=["category", "sub_category"])
        labels[_normalize(category)] = category
        filled += 1

    return filled, unresolved, failed
