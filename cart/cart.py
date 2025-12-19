from decimal import Decimal

from django.conf import settings
from shop.models import Product
from coupons.models import Coupon


class Cart:
    def __init__(self, request):
        self.session = request.session
        cart = self.session.get(settings.CART_SESSION_ID)
        if not cart:
            cart = self.session[settings.CART_SESSION_ID] = {}
        self.cart = cart
        self.coupon_id = self.session.get("coupon_id")

    def __iter__(self):
        product_ids = list(self.cart.keys())
        products = Product.objects.filter(id__in=[int(pid) for pid in product_ids])

        cart = self.cart.copy()
        product_map = {str(p.id): p for p in products}

        # keep session order (better UX)
        for pid in product_ids:
            cart[pid]["product"] = product_map[pid]

        for item in cart.values():
            item["price"] = Decimal(item["price"])
            item["total_price"] = item["price"] * item["quantity"]
            yield item

    def __len__(self):
        return sum(item["quantity"] for item in self.cart.values())

    def add(self, product, quantity=1, override_quantity=False):
        product_id = str(product.id)
        if product_id not in self.cart:
            self.cart[product_id] = {"quantity": 0, "price": str(product.price)}

        if override_quantity:
            self.cart[product_id]["quantity"] = int(quantity)
        else:
            self.cart[product_id]["quantity"] += int(quantity)

        self.save()

    def save(self):
        self.session.modified = True

    def remove(self, product):
        product_id = str(product.id)
        if product_id in self.cart:
            del self.cart[product_id]
            self.save()

    def clear(self):
        self.session.pop(settings.CART_SESSION_ID, None)
        self.session.pop("coupon_id", None)
        self.save()

    def get_total_price(self) -> Decimal:
        return sum(
            Decimal(item["price"]) * item["quantity"] for item in self.cart.values()
        )

    @property
    def coupon(self):
        if not self.coupon_id:
            return None
        try:
            return Coupon.objects.get(id=self.coupon_id)
        except Coupon.DoesNotExist:
            self.session.pop("coupon_id", None)
            self.save()
            return None

    def get_discount(self) -> Decimal:
        coupon = self.coupon
        if coupon:
            return (Decimal(coupon.discount) / Decimal("100")) * self.get_total_price()
        return Decimal("0")

    def get_total_price_after_discount(self) -> Decimal:
        return self.get_total_price() - self.get_discount()
