"""Rentabilidade da carteira, sem a distorção de aportes e resgates, comparada a CDI e Ibovespa.

Usa o retorno ponderado pelo tempo: mede o ganho de cada período sobre o capital daquele período e encadeia
os resultados, como faz a cota de um fundo. Assim, aportar muito não altera o percentual.
"""

from collections import defaultdict

from app.indices import CDI
from app.models import AssetPrice, IndexRate
from wallet.models import AssetConsolidatedValue, Movement, Order
from wallet.movements import income_label, income_value

# O Ibovespa não vem no arquivo da B3; o BOVA11 é o ETF que replica o índice.
IBOV_PROXY = "BOVA11"
# No começo da carteira, poucos reais fariam qualquer variação parecer enorme.
MIN_CAPITAL = 1000.0
# Variação maior que essa em um dia, sem boleta explicando, é desdobramento na cotação sem ajuste.
MAX_DAILY_MOVE = 0.40
FEES = "Taxas"
NEUTRAL_KINDS = {Order.KIND_EVENT, Order.KIND_FRACTION, Order.KIND_SUCCESSION, Order.KIND_RECONCILIATION}


def _flows_by_day(orders, days):
    """Por pregão e ativo: dinheiro aplicado ou retirado, e se houve evento que torna o dia incomparável."""
    flows = defaultdict(lambda: defaultdict(float))
    neutral = defaultdict(set)
    position = 0
    for order in sorted(orders, key=lambda o: o.date):
        while position < len(days) and days[position] < order.date:
            position += 1
        if position == len(days):
            break
        day = days[position]
        if order.kind == Order.KIND_TRADE:
            flows[day][order.name] += float(order.price * order.volume) * order.order_type
        elif order.kind in NEUTRAL_KINDS:
            neutral[day].add(order.name)
    return flows, neutral


def _income_by_day(movements, days):
    income = defaultdict(lambda: defaultdict(float))
    position = 0
    for movement in sorted(movements, key=lambda m: m.date):
        label = income_label(movement)
        if not label or label == FEES:
            continue
        while position < len(days) and days[position] < movement.date:
            position += 1
        if position == len(days):
            break
        income[days[position]][movement.name] += float(income_value(movement))
    return income


def _portfolio_returns(values_by_day, days, flows, neutral, income):
    """Retorno de cada pregão. Retorna {dia: retorno} e quantos ativos-dia foram desconsiderados."""
    returns = {}
    ignored = 0
    for previous, day in zip(days, days[1:]):
        before = values_by_day[previous]
        after = values_by_day[day]
        gain, capital = 0.0, 0.0
        for name in set(before) | set(after):
            value_before = before.get(name, 0.0)
            value_after = after.get(name, 0.0)
            flow = flows[day].get(name, 0.0)
            capital += value_before + max(flow, 0.0)
            if name in neutral[day]:
                continue
            base = value_before + max(flow, 0.0)
            change = value_after - value_before - flow
            if base > 0 and abs(change) / base > MAX_DAILY_MOVE:
                ignored += 1
                continue
            gain += change + income[day].get(name, 0.0)
        if capital >= MIN_CAPITAL:
            returns[day] = gain / capital
    return returns, ignored


def _chain(days, daily):
    """Acumula retornos diários em um índice que começa em 1."""
    index, series = 1.0, []
    for day in days:
        index *= 1 + daily.get(day, 0.0)
        series.append(index)
    return series


def _cdi_series(days):
    rates = IndexRate.objects.filter(code=CDI, date__gte=days[0], date__lte=days[-1]).order_by("date")
    entries = list(rates.values_list("date", "daily_percent"))
    if not entries:
        return [None] * len(days)
    index, series, position = 1.0, [], 0
    for day in days:
        while position < len(entries) and entries[position][0] <= day:
            if entries[position][0] > days[0]:
                index *= 1 + entries[position][1] / 100
            position += 1
        series.append(index)
    return series


def _ibov_series(days):
    prices = list(
        AssetPrice.objects.filter(ticker=IBOV_PROXY, date__lte=days[-1]).order_by("date").values_list("date", "close")
    )
    if not prices:
        return [None] * len(days)
    index, series, position, previous = 1.0, [], 0, None
    for day in days:
        while position < len(prices) and prices[position][0] <= day:
            close = prices[position][1]
            if prices[position][0] > days[0] and previous:
                move = close / previous - 1
                # O preço não tem ajuste de desdobramento; um salto assim não é rentabilidade.
                if abs(move) <= MAX_DAILY_MOVE:
                    index *= 1 + move
            previous = close
            position += 1
        series.append(index)
    return series


def performance_series(user, asset_class=None):
    rows = AssetConsolidatedValue.objects.filter(user=user).exclude(name="profit")
    orders = Order.objects.filter(user=user)
    if asset_class:
        rows = rows.filter(asset_type=asset_class.upper())
        orders = orders.filter(asset_type=asset_class.upper())

    values_by_day = defaultdict(dict)
    for day, name, value in rows.values_list("date", "name", "value"):
        values_by_day[day][name] = float(value)
    days = sorted(values_by_day)
    empty = {"dates": [], "portfolio": [], "cdi": [], "ibov": [], "ignored_days": 0}
    if len(days) < 2:
        return empty

    names = {name for day_values in values_by_day.values() for name in day_values}
    flows, neutral = _flows_by_day(list(orders), days)
    income = _income_by_day(list(Movement.objects.filter(user=user, name__in=names)), days)
    returns, ignored = _portfolio_returns(values_by_day, days, flows, neutral, income)
    if not returns:
        return empty

    first_return_day = min(returns)
    start = days.index(first_return_day) - 1
    window = days[start:]
    return {
        "dates": window,
        "portfolio": _chain(window, returns),
        "cdi": _cdi_series(window),
        "ibov": _ibov_series(window),
        "ignored_days": ignored,
    }
