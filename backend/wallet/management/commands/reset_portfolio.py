from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError

from wallet.models import AssetConsolidatedValue, Order


class Command(BaseCommand):
    help = "Apaga as boletas e o histórico consolidado de um usuário. Sem --yes, só mostra o que seria apagado."

    def add_arguments(self, parser):
        parser.add_argument("--username", required=True)
        parser.add_argument("--yes", action="store_true", help="Confirma a remoção")

    def handle(self, *args, **options):
        user = User.objects.filter(username=options["username"]).first()
        if user is None:
            raise CommandError(f"Usuário não encontrado: {options['username']}")

        orders = Order.objects.filter(user=user)
        consolidated = AssetConsolidatedValue.objects.filter(user=user)
        summary = f"{orders.count()} boleta(s) e {consolidated.count()} linha(s) consolidada(s) de {user.username}"

        if not options["yes"]:
            self.stdout.write(f"Seriam apagadas {summary}. Repita com --yes para confirmar.")
            return

        orders.delete()
        consolidated.delete()
        self.stdout.write(self.style.SUCCESS(f"Apagadas {summary}."))
