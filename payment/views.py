from decimal import Decimal, ROUND_HALF_UP

import stripe
from django.conf import settings
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from orders.models import Order

stripe.api_key = settings.STRIPE_SECRET_KEY
stripe.api_version = settings.STRIPE_API_VERSION


def _to_pence(amount: Decimal) -> int:
    """
    Convert a Decimal amount in GBP to pence (int), safely rounded.
    """
    return int((amount * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def payment_process(request):
    order_id = request.session.get("order_id")
    if not order_id:
        return redirect("cart:cart_detail")  # update if your cart url name differs

    order = get_object_or_404(Order, id=order_id)

    if request.method == "POST":
        success_url = request.build_absolute_uri(reverse("payment:completed"))
        cancel_url = request.build_absolute_uri(
            reverse("payment:cancelled")
        )  # must match urls.py

        line_items = []
        for item in order.items.all():
            line_items.append(
                {
                    "price_data": {
                        "currency": "gbp",
                        "product_data": {"name": item.product.name},
                        "unit_amount": _to_pence(item.price),
                    },
                    "quantity": int(item.quantity),
                }
            )

        if not line_items:
            return render(
                request,
                "payment/process.html",
                {"order": order, "error": "Your order has no items to pay for."},
                status=400,
            )

        session = stripe.checkout.Session.create(
            mode="payment",
            client_reference_id=str(order.id),
            success_url=success_url,
            cancel_url=cancel_url,
            line_items=line_items,
            customer_email=order.email,
            metadata={"order_id": str(order.id)},
        )

        return redirect(session.url, code=303)

    return render(request, "payment/process.html", {"order": order})


def payment_completed(request):
    return render(request, "payment/completed.html")


def payment_cancelled(request):
    return render(request, "payment/cancelled.html")
