from collections import defaultdict
from decimal import Decimal

from django.db import migrations


def forwards(apps, schema_editor):
    """Boletas estimadas vieram do relatório de posição, que passa a ser guardado em PositionSnapshot."""
    Order = apps.get_model("wallet", "Order")
    Snapshot = apps.get_model("wallet", "PositionSnapshot")
    Consolidated = apps.get_model("wallet", "AssetConsolidatedValue")

    Order.objects.filter(cost_estimated=True).update(source="position")

    orders_by_user = defaultdict(list)
    for order in Order.objects.filter(source="position").order_by("date", "id"):
        orders_by_user[order.user_id].append(order)

    for user_id, orders in orders_by_user.items():
        day = max(order.date for order in orders)
        net = defaultdict(Decimal)
        last = {}
        for order in orders:
            net[(order.name, order.broker)] += order.volume * order.order_type
            last[(order.name, order.broker)] = order
        values = {
            row.name: row for row in Consolidated.objects.filter(user_id=user_id, date=day)
        }
        rows = []
        for (name, broker), quantity in net.items():
            if quantity <= 0:
                continue
            order = last[(name, broker)]
            consolidated = values.get(name)
            value = consolidated.value if consolidated else order.price * quantity
            rows.append(
                Snapshot(
                    user_id=user_id, date=day, name=name, broker=broker, asset_type=order.asset_type,
                    quantity=quantity, unit_price=value / quantity, value=value, description=order.description,
                    maturity_date=order.maturity_date, index=order.index,
                    fixed_income_type=order.fixed_income_type, issuer=order.issuer,
                )
            )
        Snapshot.objects.bulk_create(rows)


class Migration(migrations.Migration):

    dependencies = [
        ("wallet", "0012_movements_and_snapshots"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
