"""Gera o histórico diário da carteira de cada usuário a partir das boletas e das cotações."""

from bisect import bisect_right
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Max

from app.models import AssetPrice
from wallet.models import AssetConsolidatedValue, Order, PositionSnapshot
from wallet.positions import RunningPosition, summarize_orders

# Um usuário parado há muito tempo não dispara o cálculo de anos de histórico de uma só vez.
MAX_BACKFILL_DAYS = 30
DAYS_IN_YEAR = 365
CENTS = Decimal("0.01")
VOLUME_STEP = Decimal("0.0001")
INSERT_BATCH_SIZE = 5000


def _start_date(user, orders, until):
    last = AssetConsolidatedValue.objects.filter(user=user).aggregate(last=Max("date"))["last"]
    start = last + timedelta(days=1) if last else min(order.date for order in orders)
    return max(start, until - timedelta(days=MAX_BACKFILL_DAYS))


def _session_dates(start, until):
    return list(
        AssetPrice.objects.filter(date__range=(start, until)).order_by("date").values_list("date", flat=True).distinct()
    )


class _MarketPrices:
    """Último fechamento até cada data; o ativo sem negócio no dia mantém o preço anterior."""

    def __init__(self, tickers, start, until):
        self.dates = defaultdict(list)
        self.closes = defaultdict(list)
        for ticker in tickers:
            before = AssetPrice.objects.filter(ticker=ticker, date__lt=start).order_by("date").last()
            if before:
                self.dates[ticker].append(before.date)
                self.closes[ticker].append(before.close)
        rows = AssetPrice.objects.filter(ticker__in=tickers, date__range=(start, until)).order_by("date")
        for ticker, day, close in rows.values_list("ticker", "date", "close"):
            self.dates[ticker].append(day)
            self.closes[ticker].append(close)

    def close_on(self, ticker, day):
        position = bisect_right(self.dates[ticker], day)
        return self.closes[ticker][position - 1] if position else None


class _FixedIncomeValue:
    """Parte do último valor conhecido e só projeta ganho quando a boleta informa a taxa."""

    def __init__(self, user, name, start, orders):
        previous = AssetConsolidatedValue.objects.filter(user=user, name=name, date__lt=start, volume__gt=0)
        last = previous.order_by("date").last()
        self.value = last.value if last else None
        self.volume = last.volume if last else None
        self.date = last.date if last else None
        rates = [order.interest_rate for order in orders if order.interest_rate is not None]
        self.rate = rates[0] if rates else None

    def on(self, day, quantity, invested):
        if self.value is None:
            self.value, self.volume, self.date = invested, quantity, day
        if self.volume and quantity != self.volume:
            self.value = self.value * quantity / self.volume
        if self.rate is not None and day > self.date:
            growth = (1 + float(self.rate) / 100) ** ((day - self.date).days / DAYS_IN_YEAR)
            self.value = self.value * Decimal(str(growth))
        self.volume, self.date = quantity, day
        return self.value


def consolidate_user(user, until):
    orders = list(Order.objects.filter(user=user))
    if not orders:
        return 0

    start = _start_date(user, orders, until)
    days = _session_dates(start, until)
    if not days:
        return 0

    orders_by_name = defaultdict(list)
    for order in orders:
        orders_by_name[order.name].append(order)

    tickers = [name for name, items in orders_by_name.items() if items[0].asset_type != "RF"]
    market = _MarketPrices(tickers, start, until)
    rows = []

    for name, name_orders in orders_by_name.items():
        first = name_orders[0]
        is_fixed_income = first.asset_type == "RF"
        fixed_income = _FixedIncomeValue(user, name, start, name_orders) if is_fixed_income else None

        for day in days:
            quantity, invested = summarize_orders([order for order in name_orders if order.date <= day])
            if quantity <= 0:
                continue
            if is_fixed_income:
                if first.maturity_date and first.maturity_date < day:
                    continue
                value = fixed_income.on(day, quantity, invested)
            else:
                close = market.close_on(name, day)
                if close is None:
                    continue
                value = quantity * Decimal(str(close))
            rows.append(
                AssetConsolidatedValue(
                    user=user,
                    name=name,
                    asset_type=first.asset_type,
                    date=day,
                    value=value.quantize(CENTS),
                    volume=quantity.quantize(VOLUME_STEP),
                    invested=invested.quantize(CENTS),
                )
            )

    AssetConsolidatedValue.objects.bulk_create(
        rows,
        update_conflicts=True,
        unique_fields=["user", "name", "date"],
        update_fields=["asset_type", "value", "volume", "invested"],
    )
    return len(rows)


def _snapshot_values(user):
    """{nome: [(data, valor, quantidade)]} das posições oficiais, em ordem de data."""
    totals = defaultdict(lambda: [Decimal(0), Decimal(0)])
    for row in PositionSnapshot.objects.filter(user=user):
        totals[(row.name, row.date)][0] += row.value
        totals[(row.name, row.date)][1] += row.quantity
    values = defaultdict(list)
    for (name, day), (value, quantity) in sorted(totals.items(), key=lambda item: item[0][1]):
        values[name].append((day, value, quantity))
    return values


def _official_growth(known_values, name_orders):
    """Fator entre o custo e o primeiro valor oficial, para estimar o caminho até ele."""
    if not known_values:
        return None
    first_day, first_value, _ = known_values[0]
    position = RunningPosition()
    for order in name_orders:
        if order.date <= first_day:
            position.apply(order)
    if position.invested <= 0 or first_value <= 0:
        return None
    return float(first_value / position.invested), first_day


def _fixed_income_value(day, position, known_values, rate, first_date, official_growth):
    """Último valor oficial. Antes dele não há preço conhecido: o custo cresce até esse valor a uma
    taxa constante, ou pela taxa da boleta. Sem isso, todo o ganho apareceria de uma vez no gráfico."""
    known = [item for item in known_values if item[0] <= day]
    if known:
        _, value, quantity = known[-1]
        return value * position.quantity / quantity if quantity else value
    if official_growth:
        factor, target_day = official_growth
        total_days = (target_day - first_date).days
        if total_days > 0:
            return position.invested * Decimal(str(factor ** ((day - first_date).days / total_days)))
    if rate is not None:
        growth = (1 + float(rate) / 100) ** ((day - first_date).days / DAYS_IN_YEAR)
        return position.invested * Decimal(str(growth))
    return position.invested


def rebuild_history(user):
    """Refaz todo o histórico do usuário a partir das boletas. Usado quando o passado muda."""
    orders = sorted(Order.objects.filter(user=user), key=lambda order: (order.date, order.id))
    until = AssetPrice.objects.aggregate(last=Max("date"))["last"]
    if not orders or until is None:
        return 0

    snapshots = _snapshot_values(user)
    snapshot_days = set(PositionSnapshot.objects.filter(user=user).values_list("date", flat=True))
    days = sorted(set(_session_dates(orders[0].date, until)) | snapshot_days)

    orders_by_name = defaultdict(list)
    for order in orders:
        orders_by_name[order.name].append(order)
    tickers = [name for name, items in orders_by_name.items() if items[0].asset_type != "RF"]
    market = _MarketPrices(tickers, orders[0].date, until)

    rows = []
    for name, name_orders in orders_by_name.items():
        first = name_orders[0]
        is_rf = first.asset_type == "RF"
        rate = next((order.interest_rate for order in name_orders if order.interest_rate is not None), None)
        known = snapshots.get(name, [])
        exact = {day: value for day, value, _ in known}
        official_growth = _official_growth(known, name_orders) if is_rf else None
        position = RunningPosition()
        next_order = 0

        for day in days:
            while next_order < len(name_orders) and name_orders[next_order].date <= day:
                position.apply(name_orders[next_order])
                next_order += 1
            if position.quantity <= 0:
                continue
            if is_rf:
                if first.maturity_date and first.maturity_date < day:
                    continue
                value = _fixed_income_value(day, position, known, rate, first.date, official_growth)
            elif day in exact:
                value = exact[day]
            else:
                close = market.close_on(name, day)
                if close is None:
                    continue
                value = position.quantity * Decimal(str(close))
            rows.append(
                AssetConsolidatedValue(
                    user=user,
                    name=name,
                    asset_type=first.asset_type,
                    date=day,
                    value=value.quantize(CENTS),
                    volume=position.quantity.quantize(VOLUME_STEP),
                    invested=position.invested.quantize(CENTS),
                )
            )

    with transaction.atomic():
        AssetConsolidatedValue.objects.filter(user=user).delete()
        AssetConsolidatedValue.objects.bulk_create(rows, batch_size=INSERT_BATCH_SIZE)
    return len(rows)


def consolidate_all_users():
    until = AssetPrice.objects.aggregate(last=Max("date"))["last"]
    if until is None:
        return 0
    return sum(consolidate_user(user, until) for user in User.objects.filter(order__isnull=False).distinct())
