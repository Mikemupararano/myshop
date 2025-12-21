"""
URL configuration for myshop project.
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.conf.urls.i18n import i18n_patterns
from django.utils.translation import gettext_lazy as _
from payment import webhooks

urlpatterns = i18n_patterns(
    path("admin/", admin.site.urls),
    path(_("cart/"), include(("cart.urls", "cart"), namespace="cart")),
    path(_("orders/"), include(("orders.urls", "orders"), namespace="orders")),
    # ✅ FIX: namespace must match payment/urls.py -> app_name = "payment"
    path(_("payment/"), include(("payment.urls", "payment"), namespace="payment")),
    path(_("coupons/"), include(("coupons.urls", "coupons"), namespace="coupons")),
    path(_("rosetta/"), include("rosetta.urls")),
    path("", include(("shop.urls", "shop"), namespace="shop")),
)

urlpatterns += [
    path("payment/webhook/", webhooks.stripe_webhook, name="payment-webhook"),
]


if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
