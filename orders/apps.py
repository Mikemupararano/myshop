from django.apps import AppConfig


class OrdersConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'orders'

class Order(models.Model):
    stripe_id = models.name = models.CharField(max_length=250, blank=True)
