import time
import traceback

from django.core.management.base import BaseCommand
from django.db import close_old_connections

from wallet.market_update import run_update

DEFAULT_INTERVAL_HOURS = 3
SECONDS_PER_HOUR = 3600


class Command(BaseCommand):
    help = "Mantém as cotações atualizadas, repetindo a atualização em intervalos."

    def add_arguments(self, parser):
        parser.add_argument("--interval-hours", type=float, default=DEFAULT_INTERVAL_HOURS)

    def handle(self, *args, **options):
        while True:
            close_old_connections()
            try:
                run = run_update()
                if run:
                    self.stdout.write(f"{run.status}: último pregão {run.last_session}. {run.message}", ending="\n")
            except Exception:
                # Uma falha pontual não pode parar as atualizações seguintes.
                self.stderr.write(traceback.format_exc())
            self.stdout.flush()
            time.sleep(options["interval_hours"] * SECONDS_PER_HOUR)
