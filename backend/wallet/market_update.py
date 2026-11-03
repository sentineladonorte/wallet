"""Executa a atualização de cotações, categorias e histórico, pelo agendador ou pelo botão da tela."""

import threading
from collections import defaultdict
from datetime import timedelta
from zoneinfo import ZoneInfo

from django.contrib.auth.models import User
from django.db import OperationalError, connection, connections
from django.utils import timezone

from app.categories import fill_missing_categories
from app.indices import fetch_cdi
from app.market_data import MarketDataError, fetch_session, weekdays_between
from app.models import MarketDataUpdate
from wallet.consolidation import consolidate_all_users, rebuild_history
from wallet.models import Order
from wallet.positions import summarize_orders

MARKET_TIME_ZONE = ZoneInfo("America/Sao_Paulo")
INITIAL_LOOKBACK_DAYS = 10
# Uma execução interrompida não pode deixar o sistema preso em "atualizando" para sempre.
STALE_AFTER = timedelta(minutes=30)
ADVISORY_LOCK_ID = 748201
HISTORY_LOCK_BASE = 748300
REBUILD_ATTEMPTS = 3


def _try_lock():
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(%s)", [ADVISORY_LOCK_ID])
        return cursor.fetchone()[0]


def _unlock():
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_unlock(%s)", [ADVISORY_LOCK_ID])


def _last_session():
    update = MarketDataUpdate.objects.exclude(last_session__isnull=True).order_by("-last_session").first()
    return update.last_session if update else None


def _fetch_recent_sessions(run, today):
    last = _last_session()
    start = last + timedelta(days=1) if last else today - timedelta(days=INITIAL_LOOKBACK_DAYS)
    for day in weekdays_between(start, today):
        result = fetch_session(day)
        if result is None:
            continue
        saved, session = result
        run.prices_saved += saved
        run.last_session = session or run.last_session


def _held_assets():
    orders_by_name = defaultdict(list)
    for order in Order.objects.exclude(asset_type="RF"):
        orders_by_name[order.name].append(order)
    # Ativos já encerrados não precisam de categoria nem gastam consultas às fontes externas.
    return {
        name: orders[0].asset_type
        for name, orders in orders_by_name.items()
        if summarize_orders(orders)[0] > 0
    }


def run_update():
    """Retorna o registro da execução, ou None se já houver outra em andamento."""
    if not _try_lock():
        return None

    run = MarketDataUpdate.objects.create()
    problems = []
    try:
        today = timezone.now().astimezone(MARKET_TIME_ZONE).date()
        try:
            _fetch_recent_sessions(run, today)
        except MarketDataError as error:
            problems.append(str(error))
        try:
            fetch_cdi(today)
        except MarketDataError as error:
            problems.append(str(error))

        filled, unresolved, failed = fill_missing_categories(_held_assets())
        run.categories_filled = filled
        if failed:
            problems.append("Algumas categorias não puderam ser consultadas")
        run.history_rows = consolidate_all_users()

        run.status = MarketDataUpdate.ERROR if problems else MarketDataUpdate.SUCCESS
        notes = list(problems)
        if unresolved:
            notes.append(f"Sem categoria: {', '.join(unresolved)}")
        run.message = ". ".join(notes)
    except Exception as error:
        run.status = MarketDataUpdate.ERROR
        run.message = f"Falha inesperada: {error.__class__.__name__}"
        raise
    finally:
        run.finished_at = timezone.now()
        run.save()
        _unlock()
    return run


def update_status():
    latest = MarketDataUpdate.objects.order_by("-started_at").first()
    finished = MarketDataUpdate.objects.exclude(finished_at__isnull=True).order_by("-started_at").first()
    running = bool(
        latest and latest.status == MarketDataUpdate.RUNNING and timezone.now() - latest.started_at < STALE_AFTER
    )
    return {
        "running": running,
        "last_session": _last_session(),
        "finished_at": finished.finished_at if finished else None,
        "status": finished.status if finished else None,
        "message": finished.message if finished else "",
        "prices_saved": finished.prices_saved if finished else 0,
        "categories_filled": finished.categories_filled if finished else 0,
    }


def _run_in_thread():
    try:
        run_update()
    finally:
        connections.close_all()


def _rebuild_with_retry(user):
    # Uma importação gravando o histórico ao mesmo tempo pode causar um deadlock passageiro no banco.
    for attempt in range(REBUILD_ATTEMPTS):
        try:
            return rebuild_history(user)
        except OperationalError:
            if attempt == REBUILD_ATTEMPTS - 1:
                raise
    return 0


def _rebuild_in_thread(user_id):
    # Importações seguidas entram em fila: a última lê as boletas mais recentes e define o resultado.
    lock_id = HISTORY_LOCK_BASE + user_id
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_lock(%s)", [lock_id])
        try:
            _rebuild_with_retry(User.objects.get(pk=user_id))
        finally:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_unlock(%s)", [lock_id])
    finally:
        connections.close_all()


def start_history_rebuild(user):
    """O histórico de anos leva alguns segundos; a importação não espera por ele."""
    threading.Thread(target=_rebuild_in_thread, args=(user.pk,), daemon=True).start()


def start_update_in_background():
    threading.Thread(target=_run_in_thread, daemon=True).start()
