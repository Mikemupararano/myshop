"""
URL configuration for myshop project.
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("cart/", include(("cart.urls", "cart"), namespace="cart")),
    path("orders/", include(("orders.urls", "orders"), namespace="orders")),
    # ✅ FIX: namespace must match payment/urls.py -> app_name = "payment"
    path("payment/", include(("payment.urls", "payment"), namespace="payment")),
    path("coupons/", include(("coupons.urls", "coupons"), namespace="coupons")),
    path('rosetta/', include('rosetta.urls')),
    path("", include(("shop.urls", "shop"), namespace="shop")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
