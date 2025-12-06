from django.urls import path
from . import views, webhooks
from django.views.decorators.csrf import csrf_exempt


app_name = "payment"
urlpatterns = [
    path("process/", views.payment_process, name="process"),
    path("completed/", views.payment_completed, name="completed"),
    path("cancelled/", views.payment_cancelled, name="cancelled"),
    path("webhooks/", csrf_exempt(webhooks.stripe_webhook), name="stripe-webhook"),
]
