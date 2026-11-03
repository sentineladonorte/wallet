"""Estima o rendimento da renda fixa entre relatórios de posição.

O relatório da B3 dá o valor de cada título numa data, e o extrato dá o custo e a data de compra. Daí sai
a taxa anual implícita de cada título, usada para projetar o valor até o próximo relatório. É uma
estimativa: títulos IPCA ou Selic não rendem a uma taxa constante, e o relatório seguinte corrige o valor.
"""

from decimal import Decimal

from wallet.models import Order, PositionSnapshot
from wallet.positions import RunningPosition

DAYS_IN_YEAR = 365
# Com pouco tempo de carteira a taxa fica instável; títulos recentes usam a média dos demais.
MIN_DAYS_FOR_RATE = 30
MAX_ANNUAL_RATE = 0.30


def grow(value, annual_rate, days):
    """Valor depois de `days` dias a uma taxa anual; preserva Decimal."""
    if days <= 0 or not annual_rate:
        return value
    return value * Decimal(str((1 + annual_rate) ** (days / DAYS_IN_YEAR)))


def _implied_rate(value, invested, days):
    if invested <= 0 or value <= 0 or days < MIN_DAYS_FOR_RATE:
        return None
    rate = float(value / invested) ** (DAYS_IN_YEAR / days) - 1
    # Tesouro pode estar abaixo do custo pela marcação a mercado: não projeta queda contínua.
    return min(max(rate, 0.0), MAX_ANNUAL_RATE)


class ImpliedRates:
    """Taxas implícitas dos títulos de um usuário, a partir do relatório de posição mais recente."""

    def __init__(self, user):
        self.rates = {}
        self.default = 0.0
        self.last_snapshot_date = (
            PositionSnapshot.objects.filter(user=user, asset_type="RF")
            .order_by("-date")
            .values_list("date", flat=True)
            .first()
        )
        if self.last_snapshot_date is None:
            return

        values = {}
        for row in PositionSnapshot.objects.filter(user=user, asset_type="RF", date=self.last_snapshot_date):
            values[row.name] = values.get(row.name, Decimal(0)) + row.value

        orders_by_name = {}
        for order in Order.objects.filter(user=user, name__in=values, date__lte=self.last_snapshot_date):
            orders_by_name.setdefault(order.name, []).append(order)

        weighted, weights = 0.0, 0.0
        for name, orders in orders_by_name.items():
            if any(order.cost_estimated for order in orders):
                continue
            orders.sort(key=lambda order: (order.date, order.id))
            position = RunningPosition()
            for order in orders:
                position.apply(order)
            days = (self.last_snapshot_date - orders[0].date).days
            rate = _implied_rate(values[name], position.invested, days)
            if rate is not None:
                self.rates[name] = rate
                weighted += rate * float(position.invested)
                weights += float(position.invested)
        if weights:
            self.default = weighted / weights

    def rate_for(self, name, orders):
        """Taxa informada na boleta; senão, a implícita do título; senão, a média da carteira."""
        for order in orders:
            if order.interest_rate is not None and order.source == Order.SOURCE_MANUAL:
                return float(order.interest_rate) / 100
        return self.rates.get(name, self.default)

    def is_estimated(self, name, value_date):
        """O valor só é oficial na data do relatório de posição."""
        return self.last_snapshot_date is None or value_date is None or value_date != self.last_snapshot_date
