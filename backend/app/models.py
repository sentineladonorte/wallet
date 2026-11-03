from django.db import models

class Asset(models.Model):
  ticker = models.CharField(max_length=8, primary_key=True)
  company_name = models.CharField(max_length=64, null=True)
  trading_name = models.CharField(max_length=32, null=True)
  cvm_code = models.CharField(max_length=8, null=True)
  cnpj = models.CharField(max_length=18, null=True)
  asset_class = models.CharField(max_length=32, null=True)
  category = models.CharField(max_length=32, null=True)
  sub_category = models.CharField(max_length=32, null=True)
  ipo_date = models.DateField(null=True)

class AssetPrice(models.Model):
  ticker = models.CharField(max_length=8)
  date = models.DateField()
  open = models.FloatField(null=True)
  low = models.FloatField(null=True)
  high = models.FloatField(null=True)
  mid = models.FloatField(null=True)
  close = models.FloatField()
  oscillation = models.FloatField(null=True)
  class Meta:
    constraints = [
        models.UniqueConstraint(fields=['ticker', 'date'], name='unique_ticker_date')
    ]


class MarketDataUpdate(models.Model):
    """Registro de cada atualização de cotações, categorias e histórico."""

    RUNNING = "running"
    SUCCESS = "success"
    ERROR = "error"

    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=8, default=RUNNING)
    # Último pregão baixado da B3. Não vem de AssetPrice, que também recebe preços das importações.
    last_session = models.DateField(null=True, blank=True)
    prices_saved = models.IntegerField(default=0)
    categories_filled = models.IntegerField(default=0)
    history_rows = models.IntegerField(default=0)
    message = models.TextField(blank=True, default="")


class IndexRate(models.Model):
    """Taxa diária de um índice de referência, em percentual ao dia (ex.: CDI)."""

    code = models.CharField(max_length=8)
    date = models.DateField()
    daily_percent = models.FloatField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=["code", "date"], name="unique_index_rate")]
