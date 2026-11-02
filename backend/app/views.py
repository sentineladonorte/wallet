import json
from datetime import datetime, time, timezone

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from .models import Asset, AssetPrice

MAX_CLASSIFICATION_LENGTH = 32


def asset(request):
    return JsonResponse(list(Asset.objects.all().values()), safe=False)


def asset_prices(request, ticker):
    prices = AssetPrice.objects.filter(ticker=ticker.upper()).order_by("date")
    return JsonResponse(
        [
            [int(datetime.combine(price.date, time(), timezone.utc).timestamp()) * 1000, price.close]
            for price in prices
        ],
        safe=False,
    )


@csrf_exempt
def asset_classification(request, ticker):
    if not request.user.is_authenticated:
        return JsonResponse({"message": "Usuário não autenticado"}, status=401)
    if request.method != "PATCH":
        return JsonResponse({"message": "Método não permitido"}, status=400)

    try:
        data = json.loads(request.body.decode("utf-8"))
    except ValueError:
        return JsonResponse({"message": "Dados inválidos"}, status=400)

    target = Asset.objects.filter(ticker=ticker.upper()).first()
    if target is None:
        return JsonResponse({"message": "Ativo não encontrado"}, status=404)

    for field in ("category", "sub_category"):
        if field not in data:
            continue
        value = (data[field] or "").strip() or None
        if value and len(value) > MAX_CLASSIFICATION_LENGTH:
            return JsonResponse(
                {"message": f"Use no máximo {MAX_CLASSIFICATION_LENGTH} caracteres"},
                status=400,
            )
        setattr(target, field, value)
    target.save(update_fields=["category", "sub_category"])

    return JsonResponse(
        {"ticker": target.ticker, "category": target.category, "sub_category": target.sub_category}
    )
