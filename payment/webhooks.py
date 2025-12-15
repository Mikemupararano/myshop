# payment/webhooks.py
import logging

import stripe
from django.conf import settings
from django.db import transaction
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt

from orders.models import Order
from payment.tasks import payment_completed

logger = logging.getLogger(__name__)

stripe.api_key = settings.STRIPE_SECRET_KEY
stripe.api_version = getattr(settings, "STRIPE_API_VERSION", None)


@csrf_exempt
def stripe_webhook(request):
    payload = request.body
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE")

    if not sig_header:
        logger.warning("Stripe webhook missing signature header")
        return HttpResponse(status=400)

    try:
        event = stripe.Webhook.construct_event(
            payload=payload,
            sig_header=sig_header,
            secret=settings.STRIPE_WEBHOOK_SECRET,
        )
    except ValueError:
        logger.exception("Invalid Stripe webhook payload")
        return HttpResponse(status=400)
    except stripe.error.SignatureVerificationError:
        logger.exception("Invalid Stripe webhook signature")
        return HttpResponse(status=400)

    event_type = event["type"]
    session = event["data"]["object"]

    logger.info("Stripe webhook received: %s", event_type)

    # ✅ Only handle successful Checkout payments
    if event_type != "checkout.session.completed":
        return HttpResponse(status=200)

    if session.get("payment_status") != "paid":
        logger.info(
            "Checkout session not paid (status=%s)",
            session.get("payment_status"),
        )
        return HttpResponse(status=200)

    # Order ID from metadata or client_reference_id
    order_id = (session.get("metadata") or {}).get("order_id") or session.get(
        "client_reference_id"
    )

    if not order_id:
        logger.warning("No order_id found in Stripe session")
        return HttpResponse(status=200)

    try:
        order = Order.objects.select_for_update().get(id=order_id)
    except Order.DoesNotExist:
        logger.warning("Order %s not found", order_id)
        return HttpResponse(status=200)

    # ✅ Idempotency: Stripe may retry webhooks
    if order.paid:
        logger.info("Order %s already marked as paid", order.id)
        return HttpResponse(status=200)

    payment_intent = session.get("payment_intent")

    # 🔒 Atomic update
    with transaction.atomic():
        order.paid = True

        if payment_intent:
            # Save Stripe ID for admin link
            if hasattr(order, "stripe_id"):
                order.stripe_id = payment_intent
            elif hasattr(order, "stripe_payment"):
                order.stripe_payment = payment_intent

        order.save()

        # ✅ Send invoice AFTER commit
        transaction.on_commit(lambda: payment_completed.delay(order.id))

    logger.info(
        "Order %s marked as PAID (payment_intent=%s)",
        order.id,
        payment_intent,
    )

    return HttpResponse(status=200)
