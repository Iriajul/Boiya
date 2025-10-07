# apps/raw/models.py
from django.db import models
from django.utils.crypto import get_random_string
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from apps.users.models import User

class Wallet(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='wallet')
    balance = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    boiya_id = models.CharField(max_length=20, unique=True, editable=False)
    last_login_bonus = models.DateField(null=True, blank=True)

    def __str__(self):
        return f"{self.user.username}'s Wallet: {self.balance} Booya Coins"

    def add_coins(self, amount):
        self.balance += amount
        self.save()

    def subtract_coins(self, amount):
        if self.balance < amount:
            raise ValueError("Insufficient balance")
        self.balance -= amount
        self.save()

class Transaction(models.Model):
    TRANSACTION_TYPES = [
        ('ADMIN_GRANT', 'Admin Grant'),
        ('TASK_REWARD', 'Task Reward'),
        ('TRANSFER_SEND', 'Transfer Send'),
        ('TRANSFER_RECEIVE', 'Transfer Receive'),
        ('SIGNUP_BONUS', 'Signup Bonus'),
        ('DAILY_LOGIN', 'Daily Login'),
    ]
    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name='transactions')
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    recipient_wallet = models.ForeignKey('Wallet', on_delete=models.SET_NULL, null=True, blank=True, related_name='received_transactions')
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.transaction_type} of {self.amount} for {self.wallet.user.username}"

class Task(models.Model):
    title = models.CharField(max_length=255)
    description = models.TextField()
    reward_coins = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
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
        wallet.add_coins(50)
        Transaction.objects.create(
            wallet=wallet,
            amount=50,
            transaction_type='SIGNUP_BONUS',
            description='Signup bonus'
        )