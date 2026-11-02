from decimal import Decimal


def summarize_orders(orders):
    """Retorna (quantidade líquida, custo líquido a preço médio) de uma lista de boletas."""
    quantity = Decimal(0)
    invested = Decimal(0)

    for order in sorted(orders, key=lambda o: (o.date, o.id)):
        if order.order_type == 1:
            quantity += order.volume
            invested += order.price * order.volume
        elif quantity > 0:
            average_price = invested / quantity
            quantity -= order.volume
            invested -= average_price * order.volume
        else:
            quantity -= order.volume

    if quantity <= 0:
        return Decimal(0), Decimal(0)
    return quantity, invested
