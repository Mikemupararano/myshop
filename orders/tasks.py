import logging

from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMessage, get_connection
from .models import Order

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 5, "countdown": 60},
    rate_limit="5/m",  # helps avoid Yahoo rate limiting in bursts
)
def order_created(self, order_id):
    """
    Send an e-mail notification when an order is successfully created.
    Retries on transient failures (SMTP disconnects, etc).
    """
    try:
        order = Order.objects.get(id=order_id)
    except Order.DoesNotExist:
        logger.warning("order_created: Order %s not found", order_id)
        return 0

    subject = f"Order nr. {order.id}"
    message = (
        f"Dear {order.first_name},\n\n"
        "You have successfully placed an order.\n"
        f"Your order ID is {order.id}.\n"
    )

    # Use DEFAULT_FROM_EMAIL so it matches EMAIL_HOST_USER/authenticated account
    from_email = settings.DEFAULT_FROM_EMAIL

    # Reuse one SMTP connection per task execution (more stable than send_mail bursts)
    connection = get_connection()

    email = EmailMessage(
        subject=subject,
        body=message,
        from_email=from_email,
        to=[order.email],
        connection=connection,
        reply_to=[from_email],  # optional
    )

    sent = email.send(fail_silently=False)
    logger.info("order_created: sent=%s order_id=%s to=%s", sent, order.id, order.email)
    return sent
