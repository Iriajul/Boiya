# apps/admin_api/serializers.py
from rest_framework import serializers
from apps.users.models import User
from apps.raw.models import Wallet, Transaction
from decimal import Decimal

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

class GrantCoinsSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()
    amount = serializers.DecimalField(min_value=Decimal('0.01'), max_digits=15, decimal_places=2)

class StudentManagementSerializer(serializers.ModelSerializer):
    balance = serializers.DecimalField(max_digits=15, decimal_places=2, source='wallet.balance', read_only=True)
    boiya_id = serializers.CharField(source='wallet.boiya_id', read_only=True)
    transaction_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'date_joined', 'is_active', 'balance', 'boiya_id', 'transaction_count']

    def get_transaction_count(self, obj):
        return Transaction.objects.filter(wallet__user=obj).count()