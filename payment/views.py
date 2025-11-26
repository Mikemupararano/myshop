frm decimal import Decimal
from django.shortcuts import get_object_or_404, redirect, render
import stripe
from django.conf import settings
from django.urls import reverse
from orders.models import Order

# Create your views here.
# Create the Stripe instance
stripe.api_key = settings.STRIPE_SECRET_KEY
stripe.api_version = settings.STRIPE_API_VERSION
def payment_page(request):
    order_id = request.session.get('order_id')
    order = get_object_or_404(Order, id=order_id)
    if request.method == 'POST':
        suceed_url = request.build_absolute_uri(
            reverse('payment:completed')
            )
        cancel_url = request.build_absolute_uri(
            reverse('payment:cancelled')
            )
        # Create a new Stripe checkout data
        session_data = {
            'mode': 'payment',
            'client_reference_id': order.id,
            'success_url': success_url,
            'cancel_url': cancel_url,
            'line_items': []
        }
        # Create Stripe checkout session
        session = stripe.checkout.Session.create(**session_data)
        # Redirect to Stripe payment form
        return redirect(session.url, code=303)
    else: 
        return render (request, 'payment/process.html', locals())