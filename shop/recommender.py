import redis
from redis.exceptions import RedisError
from django.conf import settings
from .models import Product


def get_redis():
    """
    Create a Redis client on-demand so the app can recover
    if Redis restarts or is temporarily unavailable.
    """
    return redis.Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        db=settings.REDIS_DB,
        decode_responses=True,
    )


class Recommender:
    def get_product_key(self, id):
        return f"product:{id}:purchased_with"

    def products_bought(self, products):
        product_ids = [p.id for p in products]
        if len(product_ids) < 2:
            return

        r = get_redis()
        try:
            for product_id in product_ids:
                for with_id in product_ids:
                    if product_id != with_id:
                        r.zincrby(self.get_product_key(product_id), 1, with_id)
        except RedisError:
            # Redis down -> skip recording rather than crashing checkout/webhooks
            return

    def suggest_products_for(self, products, max_results=6):
        product_ids = [p.id for p in products]
        if not product_ids:
            return []

        r = get_redis()
        try:
            if len(product_ids) == 1:
                suggestions = r.zrange(
                    self.get_product_key(product_ids[0]), 0, -1, desc=True
                )[:max_results]
            else:
                flat_ids = "_".join(map(str, product_ids))
                tmp_key = f"tmp_{flat_ids}"

                keys = [self.get_product_key(pid) for pid in product_ids]
                r.zunionstore(tmp_key, keys)
                r.zrem(tmp_key, *product_ids)

                suggestions = r.zrange(tmp_key, 0, -1, desc=True)[:max_results]
                r.delete(tmp_key)

            suggested_products_ids = [int(x) for x in suggestions]

        except RedisError:
            return []

        suggested_products = list(Product.objects.filter(id__in=suggested_products_ids))
        suggested_products.sort(key=lambda x: suggested_products_ids.index(x.id))
        return suggested_products

    def clear_purchases(self):
        r = get_redis()
        try:
            for id in Product.objects.values_list("id", flat=True):
                r.delete(self.get_product_key(id))
        except RedisError:
            return
