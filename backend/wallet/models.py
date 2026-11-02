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

    # Boletas importadas são derivadas de Movement e PositionSnapshot e recriadas a cada importação.
    SOURCE_MANUAL = "manual"
    SOURCE_POSITION = "position"
    SOURCE_MOVEMENT = "movement"

    KIND_TRADE = "trade"  # compra, venda ou resgate: entra no custo e no lucro realizado
    KIND_EVENT = "event"  # desdobro, grupamento, bonificação: muda a quantidade, não o custo
    KIND_TRANSFER = "transfer"  # troca de corretora: idem
    KIND_FRACTION = "fraction"  # fração vendida em leilão: reduz quantidade e custo
    KIND_SUCCESSION = "succession"  # troca de ticker: o custo passa do antigo para o novo
    KIND_RECONCILIATION = "reconcile"  # acerto com o relatório de posição, sem lucro realizado

    name = models.CharField(max_length=64)
    broker = models.CharField(max_length=32)
    asset_type = models.CharField(max_length=3, choices=ASSET_TYPES)
    order_type = models.IntegerField(choices=ORDER_TYPES)
    date = models.DateField()
    price = models.DecimalField(max_digits=16, decimal_places=6)
    volume = models.DecimalField(max_digits=14, decimal_places=4)
    description = models.TextField(null=True, blank=True)
    interest_rate = models.DecimalField(max_digits=8, decimal_places=5, null=True)
    maturity_date = models.DateField(null=True)
    index = models.CharField(max_length=1, choices=INDEX_CHOICES, null=True)
    fixed_income_type = models.CharField(
        max_length=3, choices=FIXED_INCOME_CHOICES, null=True
    )

    issuer = models.CharField(max_length=64, null=True, blank=True)
    source = models.CharField(max_length=8, default=SOURCE_MANUAL)
    kind = models.CharField(max_length=10, default=KIND_TRADE)
    note = models.CharField(max_length=64, blank=True, default="")
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
    volume = models.DecimalField(max_digits=14, decimal_places=4)
    invested = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.user} - {self.name} - {self.date}"

    class Meta:
        unique_together = ["user", "name", "date"]


class AllocationTarget(models.Model):
    """Meta de alocação: da classe na carteira ou, com `category`, da categoria dentro da classe."""

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    asset_class = models.CharField(max_length=3)
    category = models.CharField(max_length=64, blank=True, default="")
    percent = models.DecimalField(max_digits=5, decimal_places=2)

    def __str__(self):
        return f"{self.user} - {self.asset_class} {self.category} - {self.percent}%"

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "asset_class", "category"],
                name="unique_allocation_target",
            )
        ]


class Movement(models.Model):
    """Linha do extrato de movimentação da B3, guardada como veio para permitir recalcular tudo."""

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    # Identifica a linha entre arquivos; a ocorrência separa operações idênticas e legítimas.
    fingerprint = models.CharField(max_length=64)
    occurrence = models.PositiveIntegerField(default=1)
    date = models.DateField()
    direction = models.SmallIntegerField()
    movement_type = models.CharField(max_length=64)
    name = models.CharField(max_length=64)
    product = models.CharField(max_length=128)
    broker = models.CharField(max_length=32)
    quantity = models.DecimalField(max_digits=14, decimal_places=4)
    unit_price = models.DecimalField(max_digits=16, decimal_places=6, null=True)
    value = models.DecimalField(max_digits=14, decimal_places=2, null=True)

    def __str__(self):
        return f"{self.date} {self.movement_type} {self.name}"

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "fingerprint", "occurrence"], name="unique_movement_line")
        ]
        indexes = [models.Index(fields=["user", "date"])]


class PositionSnapshot(models.Model):
    """Posição oficial numa data, vinda do relatório de posição da B3."""

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    date = models.DateField()
    name = models.CharField(max_length=64)
    broker = models.CharField(max_length=32)
    asset_type = models.CharField(max_length=3)
    quantity = models.DecimalField(max_digits=14, decimal_places=4)
    unit_price = models.DecimalField(max_digits=16, decimal_places=6)
    value = models.DecimalField(max_digits=14, decimal_places=2)
    description = models.TextField(null=True, blank=True)
    maturity_date = models.DateField(null=True)
    index = models.CharField(max_length=1, null=True)
    fixed_income_type = models.CharField(max_length=3, null=True)
    issuer = models.CharField(max_length=64, null=True)

    def __str__(self):
        return f"{self.date} {self.name} {self.quantity}"

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "date", "name", "broker"], name="unique_position_snapshot_line")
        ]
