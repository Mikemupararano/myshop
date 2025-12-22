"""
URL configuration for myshop project.
"""

from django.contrib import admin
from django.urls import include, path
from django.conf import settings
from django.conf.urls.static import static
from django.conf.urls.i18n import i18n_patterns
from django.utils.translation import gettext_lazy as _

from payment import webhooks

urlpatterns = [
    # Needed for {% url 'set_language' %} and Django language switching
    path("i18n/", include("django.conf.urls.i18n")),
    # Keep webhooks OUTSIDE i18n so Stripe hits a stable URL
    path("payment/webhook/", webhooks.stripe_webhook, name="payment-webhook"),
]

urlpatterns += i18n_patterns(
    path("admin/", admin.site.urls),
    path(_("cart/"), include(("cart.urls", "cart"), namespace="cart")),
    path(_("orders/"), include(("orders.urls", "orders"), namespace="orders")),
    path(_("payment/"), include(("payment.urls", "payment"), namespace="payment")),
    path(_("coupons/"), include(("coupons.urls", "coupons"), namespace="coupons")),
    path(_("rosetta/"), include("rosetta.urls")),
    path("", include(("shop.urls", "shop"), namespace="shop")),
)

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
