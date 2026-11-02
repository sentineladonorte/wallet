from django.db import models
from django.contrib.auth.models import User


class Order(models.Model):
    ASSET_TYPES = [
        ("AC", "Ações"),
        ("RF", "Renda Fixa"),
        ("FII", "Fundos de Investimento Imobiliário"),
        ("BDR", "Brazilian Depositary Receipts"),
        ("ETF", "Fundos de Índice"),
    ]

    ORDER_TYPES = [
        (1, "buy"),
        (-1, "sell"),
    ]

    INDEX_CHOICES = [
        ("P", "Prefixed"),
        ("S", "Selic"),
        ("I", "IPCA"),
    ]

    FIXED_INCOME_CHOICES = [
        ("CDB", "Certificado de Depósito Bancário"),
        ("LCA", "Letra de Crédito do Agronegócio"),
        ("LCI", "Letra de Crédito Imobiliário"),
        ("TD", "Tesouro Direto"),
    ]

    name = models.CharField(max_length=64)
    broker = models.CharField(max_length=32)
    asset_type = models.CharField(max_length=3, choices=ASSET_TYPES)
    order_type = models.IntegerField(choices=ORDER_TYPES)
    date = models.DateField()
    price = models.DecimalField(max_digits=8, decimal_places=2)
    volume = models.DecimalField(max_digits=8, decimal_places=4)
    description = models.TextField(null=True, blank=True)
    interest_rate = models.DecimalField(max_digits=8, decimal_places=5, null=True)
    maturity_date = models.DateField(null=True)
    index = models.CharField(max_length=1, choices=INDEX_CHOICES, null=True)
    fixed_income_type = models.CharField(
        max_length=3, choices=FIXED_INCOME_CHOICES, null=True
    )

    issuer = models.CharField(max_length=64, null=True, blank=True)
    # Preço/data vieram de uma estimativa (ex.: importação da posição da B3)
    # e ainda não foram confirmados pelo usuário.
    cost_estimated = models.BooleanField(default=False)

    user = models.ForeignKey(User, on_delete=models.CASCADE)

    def __str__(self):
        return self.name


class AssetConsolidatedValue(models.Model):
    ASSET_TYPES = [
        ("AC", "Ações"),
        ("RF", "Renda Fixa"),
        ("FII", "Fundos de Investimento Imobiliário"),
        ("BDR", "Brazilian Depositary Receipts"),
        ("ETF", "Fundos de Índice"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=64)
    asset_type = models.CharField(max_length=3, choices=ASSET_TYPES)
    date = models.DateField()
    value = models.DecimalField(max_digits=10, decimal_places=2)
    volume = models.DecimalField(max_digits=8, decimal_places=4)
    invested = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.user} - {self.name} - {self.date}"

    class Meta:
        unique_together = ["user", "name", "date"]
