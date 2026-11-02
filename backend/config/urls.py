"""
URL configuration for wallet project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.urls import path
from app import views as asset_views
from wallet import views as wallet_views
from user import views as user_views

urlpatterns = [
    path("api/admin/", admin.site.urls),
    path("api/assets", asset_views.asset, name="asset"),
    path("api/asset/<str:ticker>/", asset_views.asset_prices, name="prices"),
    path("api/orders/", wallet_views.orders, name="orders"),
    path(
        "api/orders/import/preview", wallet_views.import_preview, name="import_preview"
    ),
    path(
        "api/orders/import/confirm", wallet_views.import_confirm, name="import_confirm"
    ),
    path("api/order/<str:id>", wallet_views.order, name="order"),
    path("api/order", wallet_views.order, name="create_order"),
    path("api/position", wallet_views.position, name="position"),
    path(
        "api/position-history", wallet_views.position_history, name="position_history"
    ),
    path("api/login", user_views.login_view, name="login"),
    path("api/logout", user_views.logout_view, name="logout"),
    path("api/register", user_views.register, name="register"),
    path("api/user", user_views.user, name="user"),
]
