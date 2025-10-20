# apps/shop/models.py
from django.db import models
from django.utils import timezone
from apps.users.models import User
from apps.admin_api.models import Product

class UserPurchase(models.Model):
    """
    Tracks purchases made by users.
    - user: The user who made the purchase.
    - product: The product purchased.
    - purchase_date: Timestamp of the purchase.
    - transaction_id: Reference to the Transaction model for coin deduction.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='purchases')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    purchase_date = models.DateTimeField(default=timezone.now)
    transaction_id = models.ForeignKey('raw.Transaction', on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return f"{self.user.username} bought {self.product.name}"