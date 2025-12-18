# payment/webhooks.py
import logging

import stripe
from django.conf import settings
from django.db import transaction
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt

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

    event_type = event["type"]
    obj = event["data"]["object"]

    logger.info("Stripe webhook received: %s", event_type)

    order_id = None
    payment_intent_id = None

    # 1) Primary path: Checkout Session completed + paid
    if event_type == "checkout.session.completed":
        if obj.get("payment_status") != "paid":
            logger.info(
                "Checkout session not paid (status=%s)", obj.get("payment_status")
            )
            return HttpResponse(status=200)

        order_id = (obj.get("metadata") or {}).get("order_id") or obj.get(
            "client_reference_id"
        )
        payment_intent_id = obj.get("payment_intent")

    # 2) Fallback path: PaymentIntent succeeded
    elif event_type == "payment_intent.succeeded":
        payment_intent_id = obj.get("id")
        order_id = (obj.get("metadata") or {}).get("order_id")

    else:
        return HttpResponse(status=200)

    if not order_id:
        logger.warning("No order_id found in Stripe event (type=%s)", event_type)
        return HttpResponse(status=200)

    # ✅ atomic + idempotent
    with transaction.atomic():
        try:
            order = Order.objects.select_for_update().get(id=order_id)
        except Order.DoesNotExist:
            logger.warning("Order %s not found", order_id)
            return HttpResponse(status=200)

        if order.paid:
            logger.info("Order %s already marked as paid", order.id)
            return HttpResponse(status=200)

        order.paid = True

        if payment_intent_id:
            if hasattr(order, "stripe_id"):
                order.stripe_id = payment_intent_id
            elif hasattr(order, "stripe_payment"):
                order.stripe_payment = payment_intent_id

        order.save()

        # save items bought for product recommendations
        product_ids = order.items.values_list("product_id")
        products = Product.objects.filter(id__in=product_ids)
        r = Recommender()
        r.products_bought(products)

        transaction.on_commit(lambda: payment_completed.delay(order.id))

    logger.info("Order %s marked as PAID (pi=%s)", order_id, payment_intent_id)
    return HttpResponse(status=200)
