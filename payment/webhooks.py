import stripe
from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from orders.models import Order

stripe.api_key = settings.STRIPE_SECRET_KEY


@csrf_exempt
def stripe_webhook(request):
    payload = request.body
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE")
    event = None

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except ValueError:
        # Invalid payload
        return HttpResponse(status=400)
    except stripe.error.SignatureVerificationError:
        # Invalid signature
        return HttpResponse(status=400)

    # ---------------------------
    # HANDLE EVENTS HERE
    # ---------------------------
    event_type = event["type"]
    data = event["data"]["object"]

    if event_type == "checkout.session.completed":
        session = data
        order_id = session.get("client_reference_id")

        if order_id:
            try:
                order = Order.objects.get(id=order_id)
                order.paid = True
                order.save()
            except Order.DoesNotExist:
                pass

    elif event_type == "payment_intent.succeeded":
        payment_intent = data
        # handle payment success logic here
        pass

    # Add additional event handlers if needed...

    # Return HTTP 200 so Stripe knows the webhook was received
    return HttpResponse(status=200)
