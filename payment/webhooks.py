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

    if event.type == "checkout.session.completed":
        session = event.data.object
        # Fulfill the purchase...
        if session.mode == "payment" and session.payment_status == "paid":
            try:
                order = Order.objects.get(id=session.client_reference_id)
            except Order.DoesNotExist:
                return HttpResponse(status=404)
            # Mark the order as paid
            order.paid = True
            order.save()
    else:
        order = None
        order.paid = True
        order.save()

    # Return HTTP 200 so Stripe knows the webhook was received
    return HttpResponse(status=200)
