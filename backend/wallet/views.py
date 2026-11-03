from collections import defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation
from django.http import JsonResponse
from app.models import AssetPrice, Asset
from wallet.b3_import import (
    ImportFileError,
    apply_plan,
    build_plan,
    parse_position_file,
    plan_to_dict,
)
from wallet.fixed_income import ImpliedRates, grow
from wallet.performance import performance_series
from wallet.market_update import start_history_rebuild, start_update_in_background, update_status
from wallet.models import AllocationTarget, AssetConsolidatedValue, Movement, Order
from wallet.movements import (
    MovementFileError,
    import_movements,
    income_by_name,
    income_rows,
    infer_asset_type,
    is_movement_file,
    parse_movements_file,
    preview_movements,
)
from wallet.positions import realized_gain, summarize_orders
from django.views.decorators.csrf import csrf_exempt
import json
from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone


INDEX_NAMES = {"P": "Prefixado", "S": "Selic", "I": "IPCA"}
FIXED_INCOME_NAMES = {
    "CDB": "CDB",
    "LCA": "LCA",
    "LCI": "LCI",
    "TD": "Tesouro Direto",
}
NOT_AUTHENTICATED = {"message": "Usuário não autenticado"}
IMPORTED_ORDER_MESSAGE = (
    "Esta boleta vem do extrato de movimentação da B3 e seria recriada na próxima importação."
)

MAX_IMPORT_FILE_BYTES = 1024 * 1024
# INT é a classe das boletas antigas, anterior a BDR e ETF.
TARGET_CLASSES = {code for code, _ in Order.ASSET_TYPES} | {"INT"}
MAX_TARGET_CATEGORY_LENGTH = 64


def _variable_income_details(name):
    latest_price = AssetPrice.objects.filter(ticker=name).order_by("date").last()
    asset = Asset.objects.filter(ticker=name).first()
    return {
        "category": asset.category if asset else None,
        "sub_category": asset.sub_category if asset else None,
        "price": latest_price.close if latest_price else None,
    }


def _fixed_income_details(user, name, orders, quantity, invested, rates):
    order = _with_maturity(orders)
    latest_value = (
        AssetConsolidatedValue.objects.filter(user=user, name=name, volume__gt=0)
        .order_by("date")
        .last()
    )
    # Título comprado depois do último cálculo do histórico ainda não tem linha: vale o custo.
    value = float(latest_value.value) if latest_value else invested
    as_of = latest_value.date if latest_value else None
    rate = rates.rate_for(name, orders)
    days_to_maturity = (order.maturity_date - timezone.now().date()).days if order.maturity_date else None
    return {
        "category": INDEX_NAMES.get(order.index, order.index),
        "sub_category": FIXED_INCOME_NAMES.get(
            order.fixed_income_type, order.fixed_income_type
        ),
        "price": value / quantity if quantity else None,
        "estimated_rate": rate * 100,
        "maturity_value": float(grow(Decimal(str(value)), rate, max(days_to_maturity, 0)))
        if days_to_maturity is not None
        else None,
        "value_estimated": rates.is_estimated(name, as_of),
    }


def _with_maturity(orders):
    """Boletas de um mesmo título podem não trazer os dados dele; usa a mais completa."""
    return next((order for order in orders if order.maturity_date), orders[0])


def _broker_volumes(orders):
    volumes = {}
    for order in orders:
        volumes[order.broker] = volumes.get(order.broker, Decimal(0)) + (
            order.volume * order.order_type
        )
    return [
        {"broker": broker, "volume": float(volume)}
        for broker, volume in sorted(volumes.items())
        if volume > 0
    ]


def _build_position(user, name, orders, rates, income=0.0):
    quantity, invested = summarize_orders(orders)
    if quantity <= 0:
        return None

    quantity = float(quantity)
    invested = float(invested)
    order = _with_maturity(orders)
    if order.asset_type == "RF":
        details = _fixed_income_details(user, name, orders, quantity, invested, rates)
    else:
        details = _variable_income_details(name)

    price = details["price"]
    value = quantity * price if price else None
    profit = value - invested if value is not None else None

    return {
        "name": name,
        "asset_class": order.asset_type,
        "category": details["category"],
        "sub_category": details["sub_category"],
        "volume": quantity,
        "cost": invested,
        "price": price,
        "value": value,
        "profit": profit,
        "profit_pct": profit / invested * 100 if profit is not None and invested else None,
        "income": income,
        "total_return": profit + income if profit is not None else None,
        "total_return_pct": (profit + income) / invested * 100 if profit is not None and invested else None,
        "description": order.description,
        "issuer": next((o.issuer for o in orders if o.issuer), None),
        "index": INDEX_NAMES.get(order.index, order.index),
        "maturity_date": order.maturity_date,
        "brokers": _broker_volumes(orders),
        "estimated_rate": details.get("estimated_rate"),
        "maturity_value": details.get("maturity_value"),
        "value_estimated": details.get("value_estimated", False),
        "cost_estimated": any(o.cost_estimated for o in orders),
    }


def _summarize_positions(assets, income_total, realized, fixed_income_as_of):
    priced = [asset for asset in assets if asset["value"] is not None]
    value = sum(asset["value"] for asset in priced)
    invested = sum(asset["cost"] for asset in priced)
    return {
        "value": value,
        "invested": invested,
        "profit": value - invested,
        "profit_pct": (value - invested) / invested * 100 if invested else None,
        "assets": len(assets),
        "assets_without_price": len(assets) - len(priced),
        "estimated_assets": sum(1 for asset in assets if asset["cost_estimated"]),
        "income_total": income_total,
        "realized_gain": realized,
        "fixed_income_as_of": fixed_income_as_of,
    }


def position(request):
    user = request.user
    if not user.is_authenticated:
        return JsonResponse(NOT_AUTHENTICATED, status=401)
    asset_type = request.GET.get("class")

    orders = Order.objects.filter(
        Q(user=user)
        # Título sem vencimento conhecido foi comprado depois do último relatório de posição.
        & (
            Q(asset_type="RF", maturity_date__gte=timezone.now())
            | Q(asset_type="RF", maturity_date__isnull=True)
            | ~Q(asset_type="RF")
        )
    )

    if asset_type:
        orders = orders.filter(asset_type=asset_type.upper())

    orders_by_name = {}
    for order in orders:
        orders_by_name.setdefault(order.name, []).append(order)

    income = income_by_name(user)
    rates = ImpliedRates(user)
    assets = [
        _build_position(user, name, asset_orders, rates, float(income.get(name, 0)))
        for name, asset_orders in orders_by_name.items()
    ]
    assets = [asset for asset in assets if asset]
    assets.sort(key=lambda asset: asset["value"] or 0, reverse=True)

    # O lucro realizado e os proventos incluem ativos que já saíram da carteira.
    all_orders = defaultdict(list)
    for order in Order.objects.filter(user=user):
        all_orders[order.name].append(order)
    realized = sum((realized_gain(items) for items in all_orders.values()), Decimal(0))
    income_total = float(sum(income.values(), Decimal(0)))

    return JsonResponse(
        {
            "assets": assets,
            "summary": _summarize_positions(assets, income_total, float(realized), rates.last_snapshot_date),
        }
    )


def _changes_estimated_cost(order, data):
    if "date" in data and str(data["date"]) != str(order.date):
        return True
    if data.get("price") is None:
        return False
    return Decimal(str(data["price"])) != order.price


def position_history(request):

    ticker = request.GET.get("ticker")
    asset_type = request.GET.get("class")
    user = request.user
    if not user.is_authenticated:
        return JsonResponse(NOT_AUTHENTICATED, status=401)
    asset_consolidated_values = AssetConsolidatedValue.objects.filter(
        user=user
    ).exclude(name="profit")

    if ticker:
        asset_consolidated_values = asset_consolidated_values.filter(
            name=ticker.upper()
        )
    elif asset_type:
        asset_consolidated_values = asset_consolidated_values.filter(
            asset_type=asset_type.upper()
        )

    # Agregado no banco: o histórico completo de uma carteira passa de 100 mil linhas.
    grouped = (
        asset_consolidated_values.values("date")
        .annotate(total_value=Sum("value"), total_invested=Sum("invested"))
        .order_by("date")
    )

    return JsonResponse(
        {
            "labels": [row["date"].strftime("%d/%m/%Y") for row in grouped],
            "values": [float(row["total_value"]) for row in grouped],
            "invested": [float(row["total_invested"]) for row in grouped],
        },
        safe=False,
    )


def _order_to_dict(order):
    return {
        "id": order.id,
        "name": order.name,
        "broker": order.broker,
        "asset_type": order.asset_type,
        "order_type": order.order_type,
        "date": order.date,
        "price": float(order.price),
        "volume": float(order.volume),
        "total": float(order.price * order.volume),
        "description": order.description,
        "interest_rate": float(order.interest_rate) if order.interest_rate is not None else None,
        "maturity_date": order.maturity_date,
        "index": order.index,
        "fixed_income_type": order.fixed_income_type,
        "issuer": order.issuer,
        "cost_estimated": order.cost_estimated,
        "source": order.source,
        "kind": order.kind,
        "note": order.note,
    }


def orders(request):
    user = request.user
    if not user.is_authenticated:
        return JsonResponse(NOT_AUTHENTICATED, status=401)

    user_orders = Order.objects.filter(user=user).order_by("-date", "-id")
    ticker = request.GET.get("ticker")
    if ticker:
        user_orders = user_orders.filter(name=ticker.upper())

    return JsonResponse([_order_to_dict(order) for order in user_orders], safe=False)


def _targets_to_dict(user):
    result = {"classes": {}, "categories": {}}
    for target in AllocationTarget.objects.filter(user=user).order_by("asset_class", "category"):
        percent = float(target.percent)
        if target.category:
            result["categories"].setdefault(target.asset_class, {})[target.category] = percent
        else:
            result["classes"][target.asset_class] = percent
    return result


def _parse_target_percent(raw):
    if isinstance(raw, bool) or not isinstance(raw, (int, float, str)):
        raise ValueError("Informe a meta em percentual")
    try:
        percent = Decimal(str(raw))
    except InvalidOperation:
        raise ValueError("Informe a meta em percentual")
    if not percent.is_finite() or percent < 0 or percent > 100:
        raise ValueError("Cada meta precisa ficar entre 0% e 100%")
    return percent.quantize(Decimal("0.01"))


def _parse_target_key(raw, asset_class):
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("Informe o nome da meta")
    key = raw.strip()
    if asset_class is None and key not in TARGET_CLASSES:
        raise ValueError(f"Classe desconhecida: {key}")
    if len(key) > MAX_TARGET_CATEGORY_LENGTH:
        raise ValueError(f"Use no máximo {MAX_TARGET_CATEGORY_LENGTH} caracteres")
    return key


def _parse_targets(data):
    """Retorna (classe ou None para o nível da carteira, {chave: percentual})."""
    if not isinstance(data, dict) or not isinstance(data.get("targets"), list):
        raise ValueError("Dados inválidos")

    asset_class = data.get("asset_class")
    if asset_class is not None and asset_class not in TARGET_CLASSES:
        raise ValueError(f"Classe desconhecida: {asset_class}")

    parsed = {}
    for entry in data["targets"]:
        if not isinstance(entry, dict):
            raise ValueError("Dados inválidos")
        key = _parse_target_key(entry.get("key"), asset_class)
        if key in parsed:
            raise ValueError(f"Meta repetida: {key}")
        parsed[key] = _parse_target_percent(entry.get("percent"))

    if sum(parsed.values(), Decimal(0)) > 100:
        raise ValueError("A soma das metas não pode passar de 100%")
    return asset_class, parsed


def _replace_targets(user, asset_class, parsed):
    if asset_class is None:
        scope = AllocationTarget.objects.filter(user=user, category="")
        rows = [AllocationTarget(user=user, asset_class=key, percent=percent) for key, percent in parsed.items()]
    else:
        scope = AllocationTarget.objects.filter(user=user, asset_class=asset_class).exclude(category="")
        rows = [
            AllocationTarget(user=user, asset_class=asset_class, category=key, percent=percent)
            for key, percent in parsed.items()
        ]
    with transaction.atomic():
        scope.delete()
        AllocationTarget.objects.bulk_create(rows)


@csrf_exempt
def targets(request):
    user = request.user
    if not user.is_authenticated:
        return JsonResponse(NOT_AUTHENTICATED, status=401)
    if request.method == "GET":
        return JsonResponse(_targets_to_dict(user))
    if request.method != "PUT":
        return JsonResponse({"message": "Método não permitido"}, status=400)

    try:
        asset_class, parsed = _parse_targets(json.loads(request.body.decode("utf-8")))
    except ValueError as error:
        message = str(error) if not isinstance(error, json.JSONDecodeError) else "Dados inválidos"
        return JsonResponse({"message": message}, status=400)

    _replace_targets(user, asset_class, parsed)
    return JsonResponse(_targets_to_dict(user))


@csrf_exempt
def market_data(request):
    if not request.user.is_authenticated:
        return JsonResponse(NOT_AUTHENTICATED, status=401)
    if request.method == "GET":
        return JsonResponse(update_status())
    if request.method != "POST":
        return JsonResponse({"message": "Método não permitido"}, status=400)

    if not update_status()["running"]:
        start_update_in_background()
    return JsonResponse({**update_status(), "running": True}, status=202)


def _uploaded_file(request):
    file = request.FILES.get("file")
    if not file:
        raise ImportFileError("Envie o arquivo .xlsx exportado pela B3.")
    if not file.name.lower().endswith(".xlsx"):
        raise ImportFileError("O arquivo precisa ter a extensão .xlsx.")
    if file.size > MAX_IMPORT_FILE_BYTES:
        raise ImportFileError("O arquivo precisa ter no máximo 1 MB.")
    return file


def _read_position_request(request, file):
    """Retorna (arquivo já lido, data informada ou None), lançando ImportFileError se inválidos."""
    snapshot_date = None
    raw_date = request.POST.get("snapshot_date")
    if raw_date:
        try:
            snapshot_date = datetime.strptime(raw_date, "%Y-%m-%d").date()
        except ValueError:
            raise ImportFileError("Data da posição inválida.")
        if snapshot_date > timezone.localdate():
            raise ImportFileError("A data da posição não pode estar no futuro.")

    return parse_position_file(file, file.name), snapshot_date


@csrf_exempt
def import_preview(request):
    user = request.user
    if not user.is_authenticated:
        return JsonResponse(NOT_AUTHENTICATED, status=401)
    if request.method != "POST":
        return JsonResponse({"message": "Método não permitido"}, status=400)

    try:
        file = _uploaded_file(request)
        if is_movement_file(file):
            parsed, errors = parse_movements_file(file)
            return JsonResponse(preview_movements(user, parsed, errors))
        parsed, snapshot_date = _read_position_request(request, file)
    except (ImportFileError, MovementFileError) as error:
        return JsonResponse({"message": str(error)}, status=400)

    return JsonResponse({"file_type": "position", **plan_to_dict(build_plan(user, parsed, snapshot_date))})


@csrf_exempt
def import_confirm(request):
    user = request.user
    if not user.is_authenticated:
        return JsonResponse(NOT_AUTHENTICATED, status=401)
    if request.method != "POST":
        return JsonResponse({"message": "Método não permitido"}, status=400)

    try:
        file = _uploaded_file(request)
        if is_movement_file(file):
            parsed, _ = parse_movements_file(file)
            new_rows, created = import_movements(user, parsed, request.POST.get("replace_manual") == "true")
            start_history_rebuild(user)
            return JsonResponse({"file_type": "movements", "new_rows": new_rows, "created_orders": created}, status=201)

        parsed, snapshot_date = _read_position_request(request, file)
        plan = build_plan(user, parsed, snapshot_date)
        created = apply_plan(user, plan, request.POST.getlist("close_missing"))
        if Movement.objects.filter(user=user).exists():
            start_history_rebuild(user)
    except (ImportFileError, MovementFileError) as error:
        return JsonResponse({"message": str(error)}, status=400)

    return JsonResponse({"file_type": "position", "created_orders": created}, status=201)


def performance(request):
    user = request.user
    if not user.is_authenticated:
        return JsonResponse(NOT_AUTHENTICATED, status=401)
    return JsonResponse(performance_series(user, request.GET.get("class")))


def income(request):
    user = request.user
    if not user.is_authenticated:
        return JsonResponse(NOT_AUTHENTICATED, status=401)

    classes = dict(Order.objects.filter(user=user).values_list("name", "asset_type"))
    costs = {}
    orders_by_name = defaultdict(list)
    for order in Order.objects.filter(user=user):
        orders_by_name[order.name].append(order)
    for name, name_orders in orders_by_name.items():
        costs[name] = float(summarize_orders(name_orders)[1])

    return JsonResponse(
        {
            "rows": [
                {
                    "date": movement.date,
                    "name": movement.name,
                    "description": movement.product,
                    "asset_class": classes.get(movement.name) or infer_asset_type(movement.name, movement.product),
                    "type": label,
                    "value": float(value),
                }
                for movement, label, value in income_rows(user)
            ],
            "costs": costs,
        }
    )


@csrf_exempt  # Use this decorator to disable CSRF protection for demonstration purposes.
def order(request, id=None):
    user = request.user
    if not user.is_authenticated:
        return JsonResponse(NOT_AUTHENTICATED, status=401)
    if request.method == "POST":
        try:

            data = json.loads(request.body.decode("utf-8"))

            if data.get("assetType") == "RF":
                order = Order(
                    name=data.get("name") + " " + str(data.get("maturity")),
                    broker=data.get("broker"),
                    asset_type=data.get("assetType"),
                    order_type=data.get("orderType"),
                    date=data.get("date"),
                    price=data.get("price"),
                    volume=data.get("volume"),
                    description=data.get("description"),
                    interest_rate=data.get("interestRate"),
                    maturity_date=data.get("maturity"),
                    index=data.get("index"),
                    fixed_income_type=data.get("fixedIncomeType"),
                    issuer=data.get("issuer") or None,
                    user=user,
                )
            else:
                order = Order(
                    name=data.get("name"),
                    broker=data.get("broker"),
                    asset_type=data.get("assetType"),
                    order_type=data.get("orderType"),
                    date=data.get("date"),
                    price=data.get("price"),
                    volume=data.get("volume"),
                    description=data.get("description"),
                    user=user,
                )

            order.save()
            return JsonResponse({"message": "Boleta criada"}, status=201)

        except Exception as e:
            print("Erro ao criar boleta")
            print(e)
            return JsonResponse({"message": str(e)}, status=500)

    elif request.method == "DELETE":
        try:
            order = Order.objects.get(user=user, id=id)
            if order.source == Order.SOURCE_MOVEMENT:
                return JsonResponse({"message": IMPORTED_ORDER_MESSAGE}, status=400)

            order.delete()
            return JsonResponse({"message": "Boleta deletada"}, status=204)

        except Exception as e:
            print("Erro ao deletar boleta")
            print(e)
            return JsonResponse({"message": str(e)}, status=500)

    elif request.method == "GET":
        try:
            order = Order.objects.get(user=user, id=id)
            return JsonResponse(_order_to_dict(order), status=200)

        except Order.DoesNotExist:
            return JsonResponse({"message": "Boleta não encontrada"}, status=404)
        except Exception as e:
            print("Erro ao buscar boleta")
            print(e)
            return JsonResponse({"message": str(e)}, status=500)

    elif request.method == "PATCH" and id:
        try:
            data = json.loads(request.body.decode("utf-8"))
            order = Order.objects.get(user=user, id=id)
            if order.source == Order.SOURCE_MOVEMENT:
                return JsonResponse({"message": IMPORTED_ORDER_MESSAGE}, status=400)

            if _changes_estimated_cost(order, data):
                order.cost_estimated = False

            if "name" in data:
                order.name = data["name"]
            if "broker" in data:
                order.broker = data["broker"]
            if "assetType" in data:
                order.asset_type = data["assetType"]
            if "orderType" in data:
                order.order_type = data["orderType"]
            if "date" in data:
                order.date = data["date"]
            if "price" in data:
                order.price = data["price"]
            if "volume" in data:
                order.volume = data["volume"]
            if "description" in data:
                order.description = data["description"]
            if "interestRate" in data:
                order.interest_rate = data["interestRate"]
            if "maturity" in data:
                order.maturity_date = data["maturity"]
            if "index" in data:
                order.index = data["index"]
            if "issuer" in data:
                order.issuer = data["issuer"] or None
            if "fixedIncomeType" in data:
                order.fixed_income_type = data["fixedIncomeType"]

            order.save()

            return JsonResponse({"message": "Boleta atualizada com sucesso"})
        except Order.DoesNotExist:
            return JsonResponse({"message": "Boleta não encontrada"}, status=404)
        except Exception as e:
            return JsonResponse({"message": str(e)}, status=500)

    else:
        return JsonResponse(
            {"message": "Esta rota não suporta este tipo de solicitação"}, status=400
        )
