# apps/admin_api/models.py
from django.db import models
from apps.users.models import User
from django.utils import timezone
import cloudinary.uploader
import random
import string

class Category(models.Model):
    """
    Model to manage categories in the marketplace.
    - name: Unique name of the category.
    - paused: Boolean to hide category and its items from the app's shop.
    - item_count: Auto-calculated number of active products in the category.
    """
    name = models.CharField(max_length=100, unique=True)
    paused = models.BooleanField(default=False)
    item_count = models.PositiveIntegerField(default=0)  # Updated dynamically via Product model

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        # Recalculate item_count if needed (handled by Product signals in practice)
        if not self.pk:  # New category
            self.item_count = 0
        super().save(*args, **kwargs)

class Product(models.Model):
    """
    Model to manage products in the marketplace.
    - name: Name of the product.
    - description: Detailed description of the product.
    - price: Coin price for purchase.
    - category: Foreign key to the Category model.
    - thumbnail_url: URL to the product thumbnail image (stored in Cloudinary).
    - file_url: URL to an optional PDF file (stored in Cloudinary, downloadable after purchase).
    - paused: Boolean to hide the product from the app's shop (independent of category pause).
    - sales: Number of times the product was purchased, updated via Transaction signals.
    - date_submitted: Creation date, editable during updates.
    """
    name = models.CharField(max_length=200)
    description = models.TextField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='products')
    thumbnail_url = models.URLField(max_length=500, null=True, blank=True)
    file_url = models.URLField(max_length=500, null=True, blank=True)
    paused = models.BooleanField(default=False)
    sales = models.PositiveIntegerField(default=0)
    date_submitted = models.DateTimeField(default=timezone.now)  # Editable, defaults to creation time

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        # Update category item_count if this is a new product or category changes
        is_new = not self.pk
        old_category_id = None
        if not is_new:
            old_category_id = Product.objects.get(pk=self.pk).category_id
        super().save(*args, **kwargs)
        if is_new or (old_category_id and old_category_id != self.category_id):
            if is_new:
                self.category.item_count += 1
            elif old_category_id != self.category_id:
                Category.objects.filter(id=old_category_id).update(item_count=models.F('item_count') - 1)
                self.category.item_count += 1
            self.category.save(update_fields=['item_count'])

class Admin(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, limit_choices_to={'is_superuser': True}, related_name='admin_profile')
    name = models.CharField(max_length=100, blank=True, null=True)  # Added name field
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    location = models.CharField(max_length=100, blank=True, null=True)
    department = models.CharField(max_length=100, blank=True, null=True)
    bio = models.TextField(blank=True, null=True)
    profile_picture = models.TextField(blank=True, null=True)  # Stores Cloudinary URL
    otp_code = models.CharField(max_length=6, null=True, blank=True)  # Store the OTP
    otp_expiry = models.DateTimeField(null=True, blank=True)  # Store the OTP expiry time

    def __str__(self):
        return f"{self.name or self.user.username}'s Admin Profile"

    @property
    def join_date(self):
        return self.user.date_joined

    def set_otp(self, length=6, expiry_minutes=5):
        """Generate a 6-digit OTP and set its expiry time (default 5 minutes)."""
        self.otp_code = ''.join(random.choices(string.digits, k=length))
        self.otp_expiry = timezone.now() + timezone.timedelta(minutes=expiry_minutes)
        self.save(update_fields=['otp_code', 'otp_expiry'])
        return self.otp_code

    def verify_otp(self, otp):
        """Verify if the provided OTP is valid and not expired."""
        if self.otp_code == otp and self.otp_expiry and self.otp_expiry > timezone.now():
            return True
        return False

    def clear_otp(self):
        """Clear the OTP and its expiry after successful verification."""
        self.otp_code = None
        self.otp_expiry = None
        self.save(update_fields=['otp_code', 'otp_expiry'])

    def save(self, *args, **kwargs):
        # Handle profile picture upload to Cloudinary if provided in kwargs
        if 'profile_picture' in kwargs and kwargs['profile_picture']:
            result = cloudinary.uploader.upload(kwargs['profile_picture'], folder='admin_profiles')
            self.profile_picture = result['secure_url']
        super().save(*args, **kwargs)