from decimal import Decimal

from wallet.models import Order

COST_KEEPING_KINDS = {Order.KIND_EVENT, Order.KIND_TRANSFER}


class RunningPosition:
    """Quantidade, custo e lucro realizado de um ativo, aplicando as boletas em ordem cronológica."""

    def __init__(self):
        self.quantity = Decimal(0)
        self.invested = Decimal(0)
        self.realized = Decimal(0)

    def apply(self, order):
        if order.kind in COST_KEEPING_KINDS:
            # Numa troca de corretora a saída pode vir antes da entrada: o saldo passa por zero, mas o custo fica.
            self.quantity += order.volume * order.order_type
            return
        if order.order_type == 1:
            self.quantity += order.volume
            self.invested += order.price * order.volume
            return
        if self.quantity > 0:
            average_price = self.invested / self.quantity
            sold = min(order.volume, self.quantity)
            if order.kind == Order.KIND_TRADE:
                self.realized += (order.price - average_price) * sold
            self.invested -= average_price * sold
        self.quantity -= order.volume
        self._clear_if_closed()

    def _clear_if_closed(self):
        if self.quantity <= 0:
            self.invested = Decimal(0)


def _chronological(orders):
    return sorted(orders, key=lambda order: (order.date, order.id or 0))


def _run(orders):
    position = RunningPosition()
    for order in _chronological(orders):
        position.apply(order)
    return position


def summarize_orders(orders):
    """Retorna (quantidade líquida, custo líquido a preço médio) de uma lista de boletas."""
    position = _run(orders)
    if position.quantity <= 0:
        return Decimal(0), Decimal(0)
    return position.quantity, position.invested


def realized_gain(orders):
    """Lucro ou prejuízo das vendas e resgates, contra o preço médio de cada momento."""
    return _run(orders).realized
