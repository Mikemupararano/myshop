import logging

import stripe
from django.conf import settings
from django.db import transaction
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt

from orders.models import Order
from .tasks import payment_completed

logger = logging.getLogger(__name__)

stripe.api_key = settings.STRIPE_SECRET_KEY
stripe.api_version = getattr(settings, "STRIPE_API_VERSION", None)


@csrf_exempt
def stripe_webhook(request):
    payload = request.body
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE")

    if not sig_header:
        return HttpResponse(status=400)

    try:
        event = stripe.Webhook.construct_event(
            payload=payload,
            sig_header=sig_header,
            secret=settings.STRIPE_WEBHOOK_SECRET,
        )
    except (ValueError, stripe.error.SignatureVerificationError):
        return HttpResponse(status=400)

    event_type = event.get("type")
    session = (event.get("data") or {}).get("object") or {}

    logger.info("Stripe event received: %s", event_type)

    # Some payment methods complete asynchronously; this event is also a valid "paid" signal.
    paid_events = {
        "checkout.session.completed",
        "checkout.session.async_payment_succeeded",
    }

    if event_type not in paid_events:
        return HttpResponse(status=200)

    mode = session.get("mode")
    payment_status = session.get("payment_status")

    # For checkout.session.completed, payment_status should be 'paid' for one-time card payments.
    # For async_payment_succeeded, it's already succeeded, but we keep this guard anyway.
    if mode != "payment" or payment_status != "paid":
        logger.info(
            "Ignoring %s (mode=%s payment_status=%s)",
            event_type,
            mode,
            payment_status,
        )
        return HttpResponse(status=200)

    metadata = session.get("metadata") or {}
    order_id = metadata.get("order_id") or session.get("client_reference_id")

    if not order_id:
        logger.warning(
            "%s missing order id (client_ref=%s metadata=%s)",
            event_type,
            session.get("client_reference_id"),
            metadata,
        )
        return HttpResponse(status=200)

    try:
        order = Order.objects.get(id=order_id)
    except Order.DoesNotExist:
        logger.warning("Order not found for order_id=%s", order_id)
        return HttpResponse(status=200)

    # Idempotency: Stripe can retry events
    if getattr(order, "paid", False):
        logger.info("Order %s already paid; skipping", order.id)
        return HttpResponse(status=200)

    payment_intent = session.get("payment_intent")

    # OPTIONAL: prefer Stripe's email if you want (helps if order email was blank/wrong)
    stripe_email = (session.get("customer_details") or {}).get("email") or session.get(
        "customer_email"
    )

    order.paid = True
    update_fields = ["paid"]

    if stripe_email and stripe_email != order.email:
        order.email = stripe_email
        update_fields.append("email")

    if payment_intent:
        if hasattr(order, "stripe_payment"):
            order.stripe_payment = payment_intent
            update_fields.append("stripe_payment")
        elif hasattr(order, "stripe_id"):
            order.stripe_id = payment_intent
            update_fields.append("stripe_id")

    order.save(update_fields=update_fields)

    # ✅ Queue invoice task only after DB commit is complete (ensures task sees paid=True)
    transaction.on_commit(lambda: payment_completed.delay(order.id))

    logger.info(
        "Marked order %s paid (payment_intent=%s) and queued invoice task",
        order.id,
        payment_intent,
    )

    return HttpResponse(status=200)
