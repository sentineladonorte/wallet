import re

from django.db import migrations

IMPORTED_DESCRIPTION = re.compile(r"^(?:CDB|LCA|LCI) - (.+?)(?: \((.+)\))? - venc\. \d{2}/\d{2}/\d{4}$")
TREASURY_ISSUER = "Tesouro Nacional"
MAX_ISSUER_LENGTH = 64


def backfill_issuers(apps, schema_editor):
    """Boletas importadas antes do campo `issuer` têm o emissor apenas na descrição."""
    Order = apps.get_model("wallet", "Order")
    orders = Order.objects.filter(asset_type="RF", issuer__isnull=True)

    orders.filter(fixed_income_type="TD").update(issuer=TREASURY_ISSUER)

    for order in orders.exclude(fixed_income_type="TD").exclude(description__isnull=True):
        match = IMPORTED_DESCRIPTION.match(order.description)
        if match:
            order.issuer = (match.group(2) or match.group(1))[:MAX_ISSUER_LENGTH]
            order.save(update_fields=["issuer"])


class Migration(migrations.Migration):

    dependencies = [
        ("wallet", "0009_order_issuer"),
    ]

    operations = [
        migrations.RunPython(backfill_issuers, migrations.RunPython.noop),
    ]
