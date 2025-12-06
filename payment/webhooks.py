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

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except (ValueError, stripe.error.SignatureVerificationError):
        return HttpResponse(status=400)

    # Handle ONLY the event type we care about
    if event.type == "checkout.session.completed":
        session = event.data.object

        if session.mode == "payment" and session.payment_status == "paid":
            order_id = session.client_reference_id

            if order_id is not None:
                try:
                    order = Order.objects.get(id=order_id)
                    order.paid = True
                    # Store Stripe payment ID
                    order.stripe_id = session.payment_intent
                    order.save()
                except Order.DoesNotExist:
                    # Do not crash – just acknowledge
                    return HttpResponse(status=200)

    # Always return 200 so Stripe stops retrying
    return HttpResponse(status=200)
