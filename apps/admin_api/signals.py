# apps/admin_api/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from apps.raw.models import Transaction
from apps.admin_api.models import Product
from django.db.models import F

@receiver(post_save, sender=Transaction)
def update_product_sales(sender, instance, created, **kwargs):
    """
    Signal handler to update the sales count of a product when a SHOP_REDEMPTION transaction is created.
    - Listens for post_save on Transaction model.
    - Increments Product.sales if the transaction type is SHOP_REDEMPTION and product_id is provided.
    """
    if created and instance.transaction_type == 'SHOP_REDEMPTION' and instance.product_id:
        try:
            product = Product.objects.get(id=instance.product_id)
            product.sales = F('sales') + 1  # Atomic increment to avoid race conditions
            product.save(update_fields=['sales'])
        except Product.DoesNotExist:
            pass  # Ignore if product_id is invalid (e.g., deleted product)