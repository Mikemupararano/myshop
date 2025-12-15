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


def _get_order_id_from_session(session: dict) -> str | None:
    metadata = session.get("metadata") or {}
    return metadata.get("order_id") or session.get("client_reference_id")


def _get_email_from_session(session: dict) -> str | None:
    return (session.get("customer_details") or {}).get("email") or session.get(
        "customer_email"
    )


def _set_payment_ref(order: Order, payment_intent_id: str | None) -> list[str]:
    """
    Save Stripe payment reference into whichever field exists on Order.
    Your admin shows STRIPE PAYMENT, so this will typically be `stripe_payment`.
    Returns update_fields list additions.
    """
    update_fields: list[str] = []
    if not payment_intent_id:
        return update_fields

    if hasattr(order, "stripe_payment"):
        # only set if blank OR to backfill missing value
        if getattr(order, "stripe_payment", "") != payment_intent_id:
            order.stripe_payment = payment_intent_id
            update_fields.append("stripe_payment")
    elif hasattr(order, "stripe_id"):
        if getattr(order, "stripe_id", "") != payment_intent_id:
            order.stripe_id = payment_intent_id
            update_fields.append("stripe_id")

    return update_fields


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
    obj = (event.get("data") or {}).get("object") or {}

    logger.info("Stripe event received: %s", event_type)

    # ---- 1) Checkout events (best: already contain metadata + client_reference_id) ----
    if event_type in {
        "checkout.session.completed",
        "checkout.session.async_payment_succeeded",
    }:
        session = obj

        # Only handle one-time payments and only when paid
        if session.get("mode") != "payment":
            return HttpResponse(status=200)

        if session.get("payment_status") != "paid":
            logger.info(
                "Ignoring %s because payment_status=%s",
                event_type,
                session.get("payment_status"),
            )
            return HttpResponse(status=200)

        order_id = _get_order_id_from_session(session)
        if not order_id:
            logger.warning(
                "%s missing order_id (metadata/client_reference_id)", event_type
            )
            return HttpResponse(status=200)

        payment_intent_id = session.get("payment_intent")
        stripe_email = _get_email_from_session(session)

        # Lock row to avoid races / duplicate processing
        with transaction.atomic():
            try:
                order = Order.objects.select_for_update().get(id=order_id)
            except Order.DoesNotExist:
                logger.warning("Order not found for order_id=%s", order_id)
                return HttpResponse(status=200)

            update_fields = []

            # mark paid (idempotent)
            if not getattr(order, "paid", False):
                order.paid = True
                update_fields.append("paid")

            # optional: keep email in sync with Stripe checkout email
            if stripe_email and stripe_email != order.email:
                order.email = stripe_email
                update_fields.append("email")

            update_fields += _set_payment_ref(order, payment_intent_id)

            if update_fields:
                order.save(update_fields=list(dict.fromkeys(update_fields)))

            # send invoice only after commit
            transaction.on_commit(lambda: payment_completed.delay(order.id))

        logger.info(
            "Order %s marked paid via %s (pi=%s)",
            order_id,
            event_type,
            payment_intent_id,
        )
        return HttpResponse(status=200)

    # ---- 2) Fallback: PaymentIntent succeeded (needs payment_intent.metadata.order_id) ----
    if event_type == "payment_intent.succeeded":
        pi = obj
        metadata = pi.get("metadata") or {}
        order_id = metadata.get("order_id")
        payment_intent_id = pi.get("id")

        if not order_id:
            # If you don't set payment_intent_data.metadata in Checkout Session creation,
            # this event cannot be mapped to an Order.
            logger.warning(
                "payment_intent.succeeded missing metadata.order_id (pi=%s). "
                "Add payment_intent_data={'metadata': {'order_id': str(order.id)}} to Checkout Session create.",
                payment_intent_id,
            )
            return HttpResponse(status=200)

        with transaction.atomic():
            try:
                order = Order.objects.select_for_update().get(id=order_id)
            except Order.DoesNotExist:
                logger.warning(
                    "Order not found for order_id=%s (pi=%s)",
                    order_id,
                    payment_intent_id,
                )
                return HttpResponse(status=200)

            update_fields = []

            if not getattr(order, "paid", False):
                order.paid = True
                update_fields.append("paid")

            update_fields += _set_payment_ref(order, payment_intent_id)

            if update_fields:
                order.save(update_fields=list(dict.fromkeys(update_fields)))

            transaction.on_commit(lambda: payment_completed.delay(order.id))

        logger.info(
            "Order %s marked paid via payment_intent.succeeded (pi=%s)",
            order_id,
            payment_intent_id,
        )
        return HttpResponse(status=200)

    # Ignore everything else
    return HttpResponse(status=200)
