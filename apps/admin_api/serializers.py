# apps/admin_api/serializers.py
from rest_framework import serializers
from apps.users.models import User
from apps.raw.models import Wallet, Transaction
from apps.admin_api.models import Category, Product, Admin
from decimal import Decimal
from django.contrib.auth.password_validation import validate_password
import cloudinary
import cloudinary.uploader
from django.conf import settings

class AdminLoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, data):
        email = data.get('email')
        password = data.get('password')

        if not email or not password:
            raise serializers.ValidationError("Email and password are required.")

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise serializers.ValidationError("User with this email does not exist.")

        if not user.check_password(password):
            raise serializers.ValidationError("Incorrect password.")

        if not user.is_superuser:
            raise serializers.ValidationError("Only superusers can log in via this endpoint.")

        data['user'] = user
        return data

    def generate_otp(self, admin):
        """Generate a 6-digit OTP with a 5-minute expiry using the Admin model."""
        return admin.set_otp(length=6, expiry_minutes=5)  # Use Admin's set_otp method

class AdminOtpVerifySerializer(serializers.Serializer):
    otp = serializers.CharField(max_length=6, required=True)
    login_token = serializers.CharField(required=True)  # Temporary token (user ID)

    def validate(self, data):
        otp = data.get('otp')
        login_token = data.get('login_token')

        try:
            user_id = int(login_token)
            user = User.objects.get(pk=user_id, is_superuser=True)
            admin = user.admin_profile  # Get the related Admin instance
        except (ValueError, User.DoesNotExist, Admin.DoesNotExist):
            raise serializers.ValidationError("Invalid login token.")

        if not admin.verify_otp(otp):
            raise serializers.ValidationError("Invalid or expired OTP code.")
        data['user'] = user
        data['admin'] = admin
        return data

class AdminProfileSerializer(serializers.ModelSerializer):
    join_date = serializers.SerializerMethodField()  # Custom field to handle datetime to date
    profile_picture = serializers.ImageField(required=False, allow_empty_file=True)  # Removed write_only=True
    email = serializers.SerializerMethodField()  # Field for email

    class Meta:
        model = Admin
        fields = ['id', 'user', 'name', 'email', 'phone_number', 'location', 'department', 'join_date', 'bio', 'profile_picture']
        extra_kwargs = {
            'name': {'required': False},
            'phone_number': {'required': False},
            'location': {'required': False},
            'department': {'required': False},
            'bio': {'required': False},
            'user': {'read_only': True},
        }

    def get_join_date(self, obj):
        # Convert datetime to date, preserving timezone awareness
        if obj.user.date_joined:
            return obj.user.date_joined.date().isoformat()
        return None

    def get_email(self, obj):
        # Return the email from the related User model
        return obj.user.email if obj.user else None

    def create(self, validated_data):
        profile_picture = validated_data.pop('profile_picture', None)
        instance = Admin.objects.create(**validated_data)
        if profile_picture:
            result = cloudinary.uploader.upload(profile_picture, folder='admin_profiles')
            instance.profile_picture = result['secure_url']
            instance.save()
        return instance

    def update(self, instance, validated_data):
        profile_picture = validated_data.pop('profile_picture', None)
        instance = super().update(instance, validated_data)
        if profile_picture:
            result = cloudinary.uploader.upload(profile_picture, folder='admin_profiles')
            instance.profile_picture = result['secure_url']
            instance.save()
        return instance

    def to_representation(self, instance):
        # Ensure profile_picture is included as a string (URL) in the response
        ret = super().to_representation(instance)
        if instance.profile_picture:
            ret['profile_picture'] = instance.profile_picture
        return ret

class AdminPasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True, validators=[validate_password])
    confirm_password = serializers.CharField(required=True)

    def validate(self, data):
        if data['new_password'] != data['confirm_password']:
            raise serializers.ValidationError("New passwords do not match.")
        return data

    def validate_current_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError("Current password is incorrect.")
        return value

class GrantCoinsSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()
    amount = serializers.DecimalField(min_value=Decimal('0.01'), max_digits=15, decimal_places=2)

class AllocateCoinsSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()
    amount = serializers.DecimalField(min_value=Decimal('0.01'), max_digits=15, decimal_places=2)
    reason = serializers.CharField(max_length=255)

    def validate_user_id(self, value):
        if not User.objects.filter(id=value, is_staff=False).exists():
            raise serializers.ValidationError("Invalid user ID.")
        return value

class TransactionHistorySerializer(serializers.ModelSerializer):
    type = serializers.SerializerMethodField()
    from_user = serializers.SerializerMethodField()
    to_user = serializers.SerializerMethodField()
    amount = serializers.DecimalField(max_digits=15, decimal_places=2, read_only=True)
    status = serializers.CharField(read_only=True)
    date = serializers.DateTimeField(source='created_at', format="%d %b, %Y", read_only=True)

    class Meta:
        model = Transaction
        fields = ['type', 'from_user', 'to_user', 'amount', 'status', 'date']

    def get_type(self, obj):
        if obj.transaction_type in ['TRANSFER_SEND', 'TRANSFER_RECEIVE']:
            return 'P2P'
        return 'Purchase'

    def get_from_user(self, obj):
        if obj.transaction_type == 'SHOP_REDEMPTION':
            return obj.wallet.user.username
        return obj.wallet.user.username

    def get_to_user(self, obj):
        if obj.transaction_type == 'SHOP_REDEMPTION':
            return 'Shop'
        if obj.recipient_wallet:
            return obj.recipient_wallet.user.username
        # Handle failed transactions based on description
        if 'Failed transfer to Boiya ID' in obj.description and 'invalid recipient' in obj.description:
            return obj.description.split('Failed transfer to Boiya ID ')[1].split(' (invalid recipient')[0]
        if 'Failed transfer to' in obj.description and 'insufficient balance' in obj.description:
            return obj.description.split('Failed transfer to ')[1].split(' (insufficient balance')[0]
        return None

class AllocationHistorySerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='wallet.user.username', read_only=True)
    amount = serializers.DecimalField(max_digits=15, decimal_places=2, read_only=True)
    reason = serializers.CharField(source='description', read_only=True)
    date = serializers.DateTimeField(source='created_at', format="%d %b, %Y", read_only=True)

    class Meta:
        model = Transaction
        fields = ['username', 'amount', 'reason', 'date']

class CurrencyStatsSerializer(serializers.Serializer):
    total_coins_issued = serializers.DecimalField(max_digits=15, decimal_places=2, read_only=True)
    coins_redeemed = serializers.DecimalField(max_digits=15, decimal_places=2, read_only=True)
    active_balance = serializers.DecimalField(max_digits=15, decimal_places=2, read_only=True)

class StudentManagementSerializer(serializers.ModelSerializer):
    balance = serializers.DecimalField(max_digits=15, decimal_places=2, source='wallet.balance', read_only=True)
    boiya_id = serializers.CharField(source='wallet.boiya_id', read_only=True)
    transactions = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'date_joined', 'is_active', 'balance', 'boiya_id', 'transactions']

    def get_transactions(self, obj):
        return Transaction.objects.filter(
            wallet__user=obj,
            transaction_type__in=['TRANSFER_SEND', 'TRANSFER_RECEIVE']
        ).count()

class ExportStudentSerializer(serializers.ModelSerializer):
    balance = serializers.DecimalField(max_digits=15, decimal_places=2, source='wallet.balance', read_only=True)
    boiya_id = serializers.CharField(source='wallet.boiya_id', read_only=True)
    transactions = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['username', 'email', 'date_joined', 'is_active', 'balance', 'boiya_id', 'transactions']

    def get_transactions(self, obj):
        return Transaction.objects.filter(
            wallet__user=obj,
            transaction_type__in=['TRANSFER_SEND', 'TRANSFER_RECEIVE']
        ).count()

class CategorySerializer(serializers.ModelSerializer):
    """
    Serializer for Category model.
    - Handles creation and listing of categories.
    """
    class Meta:
        model = Category
        fields = ['id', 'name', 'paused', 'item_count']

class ProductSerializer(serializers.ModelSerializer):
    """
    Serializer for Product model.
    - Handles creation, update, and listing of products.
    - Manages Cloudinary uploads for thumbnail and file.
    - Filters category dropdown to non-paused categories.
    """
    category = serializers.PrimaryKeyRelatedField(queryset=Category.objects.filter(paused=False))

    class Meta:
        model = Product
        fields = ['id', 'name', 'description', 'price', 'category', 'thumbnail_url', 'file_url', 'paused', 'sales', 'date_submitted']

    def create(self, validated_data):
        """
        Create a new product with optional thumbnail and file uploads.
        """
        request = self.context.get('request')
        thumbnail = request.FILES.get('thumbnail') if request else None
        file = request.FILES.get('file') if request else None

        if thumbnail:
            result = cloudinary.uploader.upload(thumbnail, folder="product_thumbnails")
            validated_data['thumbnail_url'] = result['secure_url']

        if file:
            result = cloudinary.uploader.upload(file, folder="product_files", resource_type="raw")
            validated_data['file_url'] = result['secure_url']

        product = Product.objects.create(**validated_data)
        return product

    def update(self, instance, validated_data):
        """
        Update an existing product with optional thumbnail and file uploads.
        Allows editing date_submitted and category.
        """
        request = self.context.get('request')
        instance.name = validated_data.get('name', instance.name)
        instance.description = validated_data.get('description', instance.description)
        instance.price = validated_data.get('price', instance.price)
        instance.category = validated_data.get('category', instance.category)
        instance.date_submitted = validated_data.get('date_submitted', instance.date_submitted)
        instance.paused = validated_data.get('paused', instance.paused)

        thumbnail = request.FILES.get('thumbnail') if request else None
        if thumbnail:
            result = cloudinary.uploader.upload(thumbnail, folder="product_thumbnails")
            instance.thumbnail_url = result['secure_url']

        file = request.FILES.get('file') if request else None
        if file:
            result = cloudinary.uploader.upload(file, folder="product_files", resource_type="raw")
            instance.file_url = result['secure_url']

        instance.save()
        return instance