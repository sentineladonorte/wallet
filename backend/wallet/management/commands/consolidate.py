from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from wallet.models import Order
from wallet.models import AssetConsolidatedValue
from app.models import AssetPrice
from datetime import timedelta, datetime
from decimal import Decimal


class Command(BaseCommand):

  help = 'Consolida a carteira'

  def add_arguments(self, parser):
    parser.add_argument('--tickers', nargs="*", default=None, help='Tickers to consolidate')

  def handle(self, *args, **options):

    for user in User.objects.filter(order__isnull=False).distinct():
      self.consolidate_user(user, options['tickers'])

  def consolidate_user(self, user, tickers):
    assets = Order.objects.filter(user=user).values('name', 'asset_type').exclude(asset_type="RF").distinct()

    if tickers:
      assets = Order.objects.filter(user=user, name__in=tickers).values('name', 'asset_type').distinct()

    for asset in assets:
      asset_name = asset['name']
      asset_type = asset['asset_type']

      first_purchase_date = Order.objects.filter(name=asset_name, user=user, order_type=1).earliest('date').date

      current_date = datetime.today().date()
      invested = 0
      consolidated_value = 0
      realized_value = 0
      volume = 0

      current = first_purchase_date
      while current < current_date:
        assetPrice = AssetPrice.objects.filter(ticker=asset_name, date__lte=current).latest('date')
        daily_purchases = Order.objects.filter(name=asset_name, user=user, date=current)

        if daily_purchases:
          for purchase in daily_purchases:
            if purchase.order_type == 1:
              volume += purchase.volume
              invested += purchase.price * purchase.volume
            else:
              average_price = (invested/volume)
              volume -= purchase.volume
              invested -= average_price * purchase.volume
              realized_value += purchase.volume * Decimal(str(purchase.price - average_price))

        consolidated_value = (volume * Decimal(str(assetPrice.close))) + realized_value

        asset_consolidated_value, created = AssetConsolidatedValue.objects.get_or_create(
          user=user,
          name=asset_name,
          date=current,
          defaults={'value': consolidated_value, 'volume': volume, 'invested': invested, 'asset_type': asset_type}
        )

        if not created:
          asset_consolidated_value.value = consolidated_value
          asset_consolidated_value.volume = volume
          asset_consolidated_value.invested = invested
          asset_consolidated_value.asset_type = asset_type
          asset_consolidated_value.save()

        print(asset_name, current, volume, consolidated_value)

        current += timedelta(days=1)
