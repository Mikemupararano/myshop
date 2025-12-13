from io import BytesIO
import weasyprint
from django.contrib.staticfiles import finders
from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from orders.models import Order
from celery import shared_task

@shared_task
def payment_completed(order_id):
    """
    Task to handle actions after payment completion.
    Generates a PDF invoice and sends it via email to the customer.
    """
    # Retrieve the order
    order = Order.objects.get(id=order_id)

    # Create invoice e-mail
    subject = f'Su Solutions - Invoice no. {order.id}'
    message = (
        'Thank you for your purchase. '
        'Please find attached the invoice for your recent order.'
    )
    email = EmailMessage(subject, message, 'kudath@yahoo.co.uk', [order.email]
                         )
    # Generate PDF invoice
    html = render_to_string('orders/order/pdf.html', {'order': order})
    out = BytesIO()
    stylesheets = [weasyprint.CSS(finders.find('css/pdf.css'))]
    weasyprint.HTML(string=html).write_pdf(out, stylesheets=stylesheets)
    # Attach PDF to e-mail
    email.attach(
        f'order_{order.id}.pdf', out.getvalue(), 'application/pdf'
    )
    # Send e-mail
    email.send()
    
    
        
    