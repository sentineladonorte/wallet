"""Cotações e cadastros fictícios para os testes de navegador, carregados ao subir o ambiente."""

from datetime import date, timedelta

from django.conf import settings

from app.models import Asset, AssetPrice, IndexRate

# Trava de segurança: este script só pode rodar no banco temporário dos testes.
assert settings.DATABASES["default"]["HOST"] == "e2e-postgres", "Banco inesperado: seed abortado"

ASSETS = {
    "BANK3": ("AC", "Bancos", 20.0),
    "AGUA3": ("AC", "Saneamento", 10.0),
    "LOGI11": ("FII", "Logístico", 100.0),
    "SHOP11": ("FII", "Shopping", 50.0),
    "INDX11": ("ETF", "Ações", 80.0),
    "TECH34": ("BDR", "Tecnologia", 40.0),
    "BOVA11": ("ETF", "Ações", 130.0),
}
CDI_DAILY_PERCENT = 0.05
HISTORY_DAYS = 800

for ticker, (asset_class, category, _) in ASSETS.items():
    Asset.objects.get_or_create(ticker=ticker, defaults={"asset_class": asset_class, "category": category})

today = date.today()
prices = []
for offset in range(HISTORY_DAYS, 0, -1):
    day = today - timedelta(days=offset)
    if day.weekday() >= 5:
        continue
    for ticker, (_, _, base) in ASSETS.items():
        # Sobe devagar até chegar ao preço-base, que é o do relatório de posição.
        prices.append(AssetPrice(ticker=ticker, date=day, close=round(base * (1 - offset * 0.0002), 2)))
AssetPrice.objects.bulk_create(prices, batch_size=2000, ignore_conflicts=True)
cdi_days = {price.date for price in prices}
IndexRate.objects.bulk_create(
    [IndexRate(code="CDI", date=day, daily_percent=CDI_DAILY_PERCENT) for day in cdi_days], ignore_conflicts=True
)
print(f"e2e: {len(prices)} cotações")
