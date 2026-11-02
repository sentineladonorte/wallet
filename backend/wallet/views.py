from datetime import datetime
from decimal import Decimal
from django.http import JsonResponse
from app.models import AssetPrice, Asset
from wallet.b3_import import (
    ImportFileError,
    apply_plan,
    build_plan,
    parse_position_file,
    plan_to_dict,
)
from wallet.models import AssetConsolidatedValue, Order
from wallet.positions import summarize_orders
import pandas as pd
from django.views.decorators.csrf import csrf_exempt
import json
from django.db.models import Q
from django.utils import timezone


INDEX_NAMES = {"P": "Prefixado", "S": "Selic", "I": "IPCA"}
FIXED_INCOME_NAMES = {
    "CDB": "CDB",
    "LCA": "LCA",
    "LCI": "LCI",
    "TD": "Tesouro Direto",
}
NOT_AUTHENTICATED = {"message": "Usuário não autenticado"}

MAX_IMPORT_FILE_BYTES = 1024 * 1024


def _variable_income_details(name):
    latest_price = AssetPrice.objects.filter(ticker=name).order_by("date").last()
    asset = Asset.objects.filter(ticker=name).first()
    return {
        "category": asset.category if asset else None,
        "sub_category": asset.sub_category if asset else None,
        "price": latest_price.close if latest_price else None,
    }


def _fixed_income_details(user, name, order, quantity):
    latest_value = (
        AssetConsolidatedValue.objects.filter(user=user, name=name)
        .order_by("date")
        .last()
    )
    return {
        "category": INDEX_NAMES.get(order.index, order.index),
        "sub_category": FIXED_INCOME_NAMES.get(
            order.fixed_income_type, order.fixed_income_type
        ),
        "price": float(latest_value.value) / quantity if latest_value else None,
    }


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


def _build_position(user, name, orders):
    quantity, invested = summarize_orders(orders)
    if quantity <= 0:
        return None

    quantity = float(quantity)
    invested = float(invested)
    order = orders[0]
    if order.asset_type == "RF":
        details = _fixed_income_details(user, name, order, quantity)
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
        "description": order.description,
        "issuer": next((o.issuer for o in orders if o.issuer), None),
        "index": INDEX_NAMES.get(order.index, order.index),
        "maturity_date": order.maturity_date,
        "brokers": _broker_volumes(orders),
        "cost_estimated": any(o.cost_estimated for o in orders),
    }


def _summarize_positions(assets):
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
    }


def position(request):
    user = request.user
    if not user.is_authenticated:
        return JsonResponse(NOT_AUTHENTICATED, status=401)
    asset_type = request.GET.get("class")

    orders = Order.objects.filter(
        Q(user=user)
        & (Q(asset_type="RF", maturity_date__gte=timezone.now()) | ~Q(asset_type="RF"))
    )

    if asset_type:
        orders = orders.filter(asset_type=asset_type.upper())

    orders_by_name = {}
    for order in orders:
        orders_by_name.setdefault(order.name, []).append(order)

    assets = [
        _build_position(user, name, asset_orders)
        for name, asset_orders in orders_by_name.items()
    ]
    assets = [asset for asset in assets if asset]
    assets.sort(key=lambda asset: asset["value"] or 0, reverse=True)

    return JsonResponse({"assets": assets, "summary": _summarize_positions(assets)})


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

    if not asset_consolidated_values.exists():
        return JsonResponse({"labels": [], "values": [], "invested": []})

    df = pd.DataFrame(asset_consolidated_values.values())
    df = df[["date", "value", "invested", "volume"]]
    df["date"] = pd.to_datetime(df["date"])

    grouped = df.groupby("date").agg({"value": "sum", "invested": "sum"}).reset_index()

    grouped["date"] = grouped["date"].dt.strftime("%d/%m/%Y")
    grouped["value"] = grouped["value"].astype(float)
    grouped["invested"] = grouped["invested"].astype(float)

    return JsonResponse(
        {
            "labels": grouped["date"].values.tolist(),
            "values": grouped["value"].values.tolist(),
            "invested": grouped["invested"].values.tolist(),
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


def _read_import_request(request):
    """Retorna (arquivo já lido, data informada ou None), lançando ImportFileError se inválidos."""
    file = request.FILES.get("file")
    if not file:
        raise ImportFileError("Envie o arquivo .xlsx exportado pela B3.")
    if not file.name.lower().endswith(".xlsx"):
        raise ImportFileError("O arquivo precisa ter a extensão .xlsx.")
    if file.size > MAX_IMPORT_FILE_BYTES:
        raise ImportFileError("O arquivo precisa ter no máximo 1 MB.")

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
        parsed, snapshot_date = _read_import_request(request)
    except ImportFileError as error:
        return JsonResponse({"message": str(error)}, status=400)

    return JsonResponse(plan_to_dict(build_plan(user, parsed, snapshot_date)))


@csrf_exempt
def import_confirm(request):
    user = request.user
    if not user.is_authenticated:
        return JsonResponse(NOT_AUTHENTICATED, status=401)
    if request.method != "POST":
        return JsonResponse({"message": "Método não permitido"}, status=400)

    try:
        parsed, snapshot_date = _read_import_request(request)
        plan = build_plan(user, parsed, snapshot_date)
        created = apply_plan(user, plan, request.POST.getlist("close_missing"))
    except ImportFileError as error:
        return JsonResponse({"message": str(error)}, status=400)

    return JsonResponse({"created_orders": created}, status=201)


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
