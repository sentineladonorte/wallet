from django.core.management.base import BaseCommand, CommandError

from app.market_data import MarketDataError, fetch_year
from wallet.market_update import run_update


class Command(BaseCommand):
    help = "Baixa as cotações recentes da B3, preenche categorias e gera o histórico."

    def add_arguments(self, parser):
        parser.add_argument("--year", type=int, nargs="*", default=[], help="Baixa também anos inteiros de cotações")

    def handle(self, *args, **options):
        for year in options["year"]:
            try:
                saved, _ = fetch_year(year)
            except MarketDataError as error:
                raise CommandError(str(error))
            self.stdout.write(f"{year}: {saved} cotação(ões)")

        run = run_update()
        if run is None:
            self.stdout.write("Já existe uma atualização em andamento.")
            return
        self.stdout.write(
            f"{run.status}: {run.prices_saved} cotação(ões), {run.categories_filled} categoria(s), "
            f"{run.history_rows} linha(s) de histórico, último pregão {run.last_session}. {run.message}"
        )
