import logging
from io import BytesIO

import weasyprint
from celery import shared_task
from django.conf import settings
from django.contrib.staticfiles import finders
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

from orders.models import Order  # ✅ correct import

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 60},
)
def payment_completed(self, order_id: int) -> int:
    """
    Send invoice email with attached PDF after successful payment.
    Returns 1 if email sent, 0 if skipped.
    """
    try:
        order = Order.objects.get(id=order_id)
    except Order.DoesNotExist:
        logger.warning("payment_completed: Order %s not found", order_id)
        return 0

    order.refresh_from_db()

    if not order.paid:
        logger.info("payment_completed: Order %s not paid; skipping invoice", order.id)
        return 0

    subject = f"Su Solutions Shop – Invoice no. {order.id}"
    message = "Please find attached the invoice for your recent purchase."

    email = EmailMultiAlternatives(
        subject=subject,
        body=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[order.email],
    )

    # Render invoice HTML (NO logo context)
    html = render_to_string("orders/order/pdf.html", {"order": order})

    out = BytesIO()

    css_path = finders.find("css/pdf.css")
    stylesheets = [weasyprint.CSS(css_path)] if css_path else []

    if not css_path:
        logger.warning(
            "payment_completed: css/pdf.css not found; generating PDF without CSS"
        )

    # base_url helps WeasyPrint resolve relative paths
    weasyprint.HTML(string=html, base_url=str(settings.BASE_DIR)).write_pdf(
        out, stylesheets=stylesheets
    )

    pdf_bytes = out.getvalue()
    if not pdf_bytes:
        raise RuntimeError(
            f"payment_completed: Generated PDF is empty for order {order.id}"
        )

    email.attach(f"order_{order.id}.pdf", pdf_bytes, "application/pdf")
    sent = email.send(fail_silently=False)

    logger.info(
        "payment_completed: sent=%s order_id=%s to=%s pdf_bytes=%s",
        sent,
        order.id,
        order.email,
        len(pdf_bytes),
    )
    return 1 if sent else 0
