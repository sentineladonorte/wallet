from django.core.management.base import BaseCommand

from wallet.consolidation import consolidate_all_users


class Command(BaseCommand):
    help = "Gera o histórico de todos os usuários até o último preço disponível."

    def handle(self, *args, **options):
        rows = consolidate_all_users()
        self.stdout.write(self.style.SUCCESS(f"{rows} linha(s) de histórico gravada(s)."))
