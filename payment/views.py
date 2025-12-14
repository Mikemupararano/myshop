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
        return redirect("cart:cart_detail")  # update if your cart url name differs

    order = get_object_or_404(Order, id=order_id)

    if request.method == "POST":
        # ✅ Include session_id so the completed page can verify payment with Stripe
        success_url = (
            request.build_absolute_uri(reverse("payment:completed"))
            + "?session_id={CHECKOUT_SESSION_ID}"
        )
        cancel_url = request.build_absolute_uri(reverse("payment:cancelled"))

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
    """
    Payment completed page.
    IMPORTANT: this verifies status with Stripe instead of assuming payment succeeded.
    """
    session_id = request.GET.get("session_id")
    payment_status = None
    order_id = None

    if session_id:
        session = stripe.checkout.Session.retrieve(session_id)
        payment_status = session.get("payment_status")  # 'paid' or 'unpaid'
        metadata = session.get("metadata") or {}
        order_id = metadata.get("order_id") or session.get("client_reference_id")

    # Optional: show the current DB status too (useful for debugging webhook issues)
    order = None
    if order_id:
        try:
            order = Order.objects.get(id=order_id)
        except Order.DoesNotExist:
            order = None

    return render(
        request,
        "payment/completed.html",
        {
            "payment_status": payment_status,
            "order": order,
        },
    )


def payment_cancelled(request):
    return render(request, "payment/cancelled.html")
