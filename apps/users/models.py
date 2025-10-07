# apps/users/models.py
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone
from django.utils.crypto import get_random_string
from datetime import timedelta

class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        """
        Creates and saves a User with the given email and password.
        """
        if not email:
            raise ValueError("Email is required")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        """
        Creates and saves a superuser with the given email and password.
        """
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        if not email:
            raise ValueError("Superuser must have an email")

        return self.create_user(email=email, password=password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    GRADE_CHOICES = [
        ("CM2", "CM2"),
        ("6ème", "6ème"),
        ("5ème", "5ème"),
        ("4ème", "4ème"),
        ("3ème", "3ème"),
        ("2nde", "2nde"),
        ("1ère", "1ère"),
        ("Tle", "Tle"),
    ]
    # Personal info
    full_name = models.CharField(max_length=255)
    username = models.CharField(max_length=50, unique=True)
    date_of_birth = models.DateField(null=True, blank=True)
    grade = models.CharField(max_length=10, choices=GRADE_CHOICES, null=True, blank=True)

    # Login info
    email = models.EmailField(unique=True)
    otp_code = models.CharField(max_length=6, null=True, blank=True)
    otp_expiry = models.DateTimeField(null=True, blank=True)
    # Permissions
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    accepted_terms = models.BooleanField(default=False)
    last_activity = models.DateTimeField(null=True, blank=True)
    date_joined = models.DateTimeField(auto_now_add=True)  # Added field

    # Authentication
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    objects = UserManager()

    def __str__(self):
        return self.email
    
    # -----------------------------
    # OTP Methods
    # -----------------------------
    def set_otp(self, length=4, expiry_minutes=5):
        self.otp_code = get_random_string(length=length, allowed_chars="0123456789")
        self.otp_expiry = timezone.now() + timedelta(minutes=expiry_minutes)
        self.save(update_fields=["otp_code", "otp_expiry"])
        return self.otp_code

    def verify_otp(self, otp):
        if self.otp_code != otp:
            return False
        if self.otp_expiry < timezone.now():
            return False
        return True

    def clear_otp(self):
        self.otp_code = None
        self.otp_expiry = None
        self.save(update_fields=["otp_code", "otp_expiry"])

    def update_last_activity(self):
        self.last_activity = timezone.now()
        self.save(update_fields=["last_activity"])    