import logging

from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection

from orders.models import Order

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 5, "countdown": 60},
    rate_limit="5/m",  # helps avoid Yahoo SMTP throttling
)
def order_created(self, order_id: int) -> int:
    """
    Send an e-mail notification when an order is successfully created.
    Retries automatically on transient failures (SMTP disconnects, etc).
    """
    try:
        order = Order.objects.get(id=order_id)
    except Order.DoesNotExist:
        logger.warning("order_created: Order %s not found", order_id)
        return 0

    subject = f"Order confirmation – Order #{order.id}"
    message = (
        f"Dear {order.first_name},\n\n"
        "Thank you for your order.\n\n"
        f"Your order reference is #{order.id}.\n"
        "We will notify you again once payment is confirmed.\n\n"
        "Kind regards,\n"
        "Su Solutions"
    )

    from_email = settings.DEFAULT_FROM_EMAIL

    # Reuse one SMTP connection per task (more reliable with Yahoo)
    connection = get_connection()

    email = EmailMultiAlternatives(
        subject=subject,
        body=message,
        from_email=from_email,
        to=[order.email],
        reply_to=[from_email],
        connection=connection,
    )

    sent = email.send(fail_silently=False)

    logger.info(
        "order_created: sent=%s order_id=%s to=%s",
        sent,
        order.id,
        order.email,
    )

    return 1 if sent else 0
