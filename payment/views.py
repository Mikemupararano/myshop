from decimal import Decimal, ROUND_HALF_UP

import stripe
from django.conf import settings
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from orders.models import Order

stripe.api_key = settings.STRIPE_SECRET_KEY
stripe.api_version = settings.STRIPE_API_VERSION


def _to_pence(amount: Decimal) -> int:
    """Convert a Decimal amount in GBP to pence (int), safely rounded."""
    return int((amount * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def payment_process(request):
    order_id = request.session.get("order_id")
    if not order_id:
        return redirect("cart:cart_detail")  # adjust if your cart url name differs

    order = get_object_or_404(Order, id=order_id)

    if request.method == "POST":
        # ✅ include session_id for Stripe verification on completed page
        success_url = (
            request.build_absolute_uri(reverse("payment:completed"))
            + "?session_id={CHECKOUT_SESSION_ID}"
        )
        cancel_url = request.build_absolute_uri(reverse("payment:cancelled"))

        session_data = {
            "mode": "payment",
            "client_reference_id": str(order.id),
            "success_url": success_url,
            "cancel_url": cancel_url,
            "customer_email": order.email,
            # ✅ critical for webhook fallback mapping
            "metadata": {"order_id": str(order.id)},
            "payment_intent_data": {"metadata": {"order_id": str(order.id)}},
            "line_items": [],
        }

        for item in order.items.all():
            session_data["line_items"].append(
                {
                    "price_data": {
                        "currency": "gbp",
                        "product_data": {"name": item.product.name},
                        "unit_amount": _to_pence(item.price),
                    },
                    "quantity": int(item.quantity),
                }
            )

        # Stripe coupon (see note below)
        if getattr(order, "coupon", None):
            stripe_coupon = stripe.Coupon.create(
                name=order.coupon.code,
                percent_off=order.discount,  # make sure this is a number 0-100
                duration="once",
            )
            session_data["discounts"] = [{"coupon": stripe_coupon.id}]

        session = stripe.checkout.Session.create(**session_data)
        return redirect(session.url, code=303)

    return render(request, "payment/process.html", {"order": order})


def payment_completed(request):
    # (Optional) verify session_id here like you did before
    return render(request, "payment/completed.html")


def payment_cancelled(request):
    return render(request, "payment/cancelled.html")
