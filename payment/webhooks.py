# payment/webhooks.py
import logging

import stripe
from django.conf import settings
from django.db import transaction
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from redis.exceptions import RedisError

from orders.models import Order
from payment.tasks import payment_completed
from shop.models import Product
from shop.recommender import Recommender

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

    event_type = event.get("type")
    obj = (event.get("data") or {}).get("object") or {}

    logger.info("Stripe webhook received: %s", event_type)

    order_id = None
    payment_intent_id = None

    # Handle the events we care about
    if event_type == "checkout.session.completed":
        # For cards this is usually "paid". For async methods it may not be.
        if obj.get("payment_status") != "paid":
            logger.info(
                "Checkout session not paid yet (status=%s)", obj.get("payment_status")
            )
            return HttpResponse(status=200)

        order_id = (obj.get("metadata") or {}).get("order_id") or obj.get(
            "client_reference_id"
        )
        payment_intent_id = obj.get("payment_intent")

    elif event_type == "checkout.session.async_payment_succeeded":
        order_id = (obj.get("metadata") or {}).get("order_id") or obj.get(
            "client_reference_id"
        )
        payment_intent_id = obj.get("payment_intent")

    elif event_type == "payment_intent.succeeded":
        payment_intent_id = obj.get("id")
        order_id = (obj.get("metadata") or {}).get("order_id")

    else:
        return HttpResponse(status=200)

    if not order_id:
        logger.warning("No order_id found in Stripe event (type=%s)", event_type)
        return HttpResponse(status=200)

    try:
        order_id_int = int(order_id)
    except (TypeError, ValueError):
        logger.warning("Invalid order_id value: %r", order_id)
        return HttpResponse(status=200)

    # ✅ atomic + idempotent update
    with transaction.atomic():
        try:
            order = Order.objects.select_for_update().get(id=order_id_int)
        except Order.DoesNotExist:
            logger.warning("Order %s not found", order_id_int)
            return HttpResponse(status=200)

        if order.paid:
            logger.info("Order %s already marked as paid", order.id)
            return HttpResponse(status=200)

        # Mark as paid and store Stripe reference if available
        order.paid = True
        if payment_intent_id:
            if hasattr(order, "stripe_id"):
                order.stripe_id = payment_intent_id
            elif hasattr(order, "stripe_payment"):
                order.stripe_payment = payment_intent_id

        order.save(
            update_fields=["paid"]
            + (["stripe_id"] if hasattr(order, "stripe_id") else [])
            + (["stripe_payment"] if hasattr(order, "stripe_payment") else [])
        )

        # Save items bought for product recommendations
        product_ids = order.items.values_list("product_id", flat=True)
        products = Product.objects.filter(id__in=product_ids)

        try:
            Recommender().products_bought(products)
        except RedisError:
            # Don't fail the webhook if Redis is down
            logger.warning("Redis unavailable; skipping recommendation update")

        transaction.on_commit(lambda: payment_completed.delay(order.id))

    logger.info("Order %s marked as PAID (pi=%s)", order_id_int, payment_intent_id)
    return HttpResponse(status=200)
