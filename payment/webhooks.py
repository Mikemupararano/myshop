import stripe
from django.conf import settings
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt

from orders.models import Order

stripe.api_key = settings.STRIPE_SECRET_KEY


@csrf_exempt
def stripe_webhook(request):
    payload = request.body
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE")

    # If Stripe signature header is missing, reject (usually means it's not Stripe)
    if not sig_header:
        return HttpResponse(status=400)

    try:
        event = stripe.Webhook.construct_event(
            payload=payload,
            sig_header=sig_header,
            secret=settings.STRIPE_WEBHOOK_SECRET,
        )
    except ValueError:
        return HttpResponse(status=400)
    except stripe.error.SignatureVerificationError:
        return HttpResponse(status=400)

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]

        # We only care about one-time payments via Checkout
        if session.get("mode") == "payment" and session.get("payment_status") == "paid":
            # Prefer metadata (most robust), fall back to client_reference_id
            order_id = None
            metadata = session.get("metadata") or {}
            order_id = metadata.get("order_id") or session.get("client_reference_id")

            if order_id:
                try:
                    order = Order.objects.get(id=order_id)
                except Order.DoesNotExist:
                    return HttpResponse(status=200)

                order.paid = True

                payment_intent = session.get("payment_intent")

                # Save into whichever field your model actually has
                if hasattr(order, "stripe_payment"):
                    order.stripe_payment = payment_intent
                    order.save(update_fields=["paid", "stripe_payment"])
                elif hasattr(order, "stripe_id"):
                    order.stripe_id = payment_intent
                    order.save(update_fields=["paid", "stripe_id"])
                else:
                    order.save(update_fields=["paid"])

    return HttpResponse(status=200)
