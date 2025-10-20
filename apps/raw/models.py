# apps/raw/models.py
from django.db import models
from django.utils.crypto import get_random_string
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from apps.users.models import User
from decimal import Decimal

class Wallet(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='wallet')
    balance = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    boiya_id = models.CharField(max_length=20, unique=True, editable=False)
    last_login_bonus = models.DateField(null=True, blank=True)

    def __str__(self):
        return f"{self.user.username}'s Wallet: {self.balance} Booya Coins"

    def add_coins(self, amount):
        if amount > 0:
            self.balance += Decimal(amount)
            self.save()

    def remove_coins(self, amount):
        if amount > 0 and self.balance >= Decimal(amount):
            self.balance -= Decimal(amount)
            self.save()
            return True
        return False

class Transaction(models.Model):
    TRANSACTION_TYPES = [
        ('ADMIN_GRANT', 'Admin Grant'),
        ('TASK_REWARD', 'Task Reward'),
        ('TRANSFER_SEND', 'Transfer Send'),
        ('TRANSFER_RECEIVE', 'Transfer Receive'),
        ('SIGNUP_BONUS', 'Signup Bonus'),
        ('DAILY_LOGIN', 'Daily Login'),
        ('SHOP_REDEMPTION', 'Shop Redemption'),  # Added for purchases
    ]
    
    STATUS_CHOICES = [
        ('COMPLETED', 'Completed'),
        ('FAILED', 'Failed'),
    ]

    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name='transactions')
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    recipient_wallet = models.ForeignKey('Wallet', on_delete=models.SET_NULL, null=True, blank=True, related_name='received_transactions')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='COMPLETED')
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    product_id = models.PositiveIntegerField(null=True, blank=True)  # New field to link to Product

    def __str__(self):
        return f"{self.transaction_type} of {self.amount} for {self.wallet.user.username} - {self.status}"

class Task(models.Model):
    title = models.CharField(max_length=255)
    description = models.TextField()
    reward_coins = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.title

class UserTaskCompletion(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    task = models.ForeignKey(Task, on_delete=models.CASCADE)
    completed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'task')

# Signal for signup bonus
@receiver(post_save, sender=User)
def create_wallet(sender, instance, created, **kwargs):
    if created:
        boiya_id = get_random_string(length=12, allowed_chars='ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789')
        wallet = Wallet.objects.create(user=instance, boiya_id=boiya_id)
        wallet.add_coins(Decimal('50.00'))
        Transaction.objects.create(
            wallet=wallet,
            amount=Decimal('50.00'),
            transaction_type='SIGNUP_BONUS',
            status='COMPLETED',
            description='Signup bonus'
        )