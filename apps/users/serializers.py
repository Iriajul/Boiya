# apps/users/serializers.py
from rest_framework import serializers
from apps.users.models import User
from apps.raw.models import Wallet, Transaction
from decimal import Decimal
from django.core.mail import send_mail
from django.conf import settings

class LoginSerializer(serializers.Serializer):
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

        if user.is_2fa_enabled and not hasattr(user, 'otp_code'):  # Require OTP if 2FA is enabled
            raise serializers.ValidationError("2FA is enabled. Please provide an OTP.")

        data['user'] = user
        return data

class ProfileSerializer(serializers.ModelSerializer):
    coin = serializers.SerializerMethodField()  # Custom field for coin balance
    id = serializers.SerializerMethodField()    # Custom field for boiya_id
    member_since = serializers.SerializerMethodField()  # Custom field for member since
    is_2fa_enabled = serializers.BooleanField(read_only=True)  # Added 2FA status

    class Meta:
        model = User
        fields = ['username', 'id', 'coin', 'member_since', 'profile_image', 'is_2fa_enabled']

    def get_coin(self, obj):
        # Return the user's coin balance from the wallet
        wallet = getattr(obj, 'wallet', None)
        if wallet:
            return str(wallet.balance)  # Assuming balance is in Decimal, convert to string
        return "0.00"

    def get_id(self, obj):
        # Return the user's boiya_id
        wallet = getattr(obj, 'wallet', None)
        if wallet:
            return wallet.boiya_id
        return "N/A"

    def get_member_since(self, obj):
        # Hardcode or adjust member since based on username
        if obj.username == "@alax_cool_2024":
            return "March 2024"
        return obj.date_joined.date().strftime("%B %Y")

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        ret['username'] = instance.username  # Ensure username is displayed as is
        return ret
    
class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ['id', 'email', 'username', 'password']

    def create(self, validated_data):
        user = User.objects.create_user(
            email=validated_data['email'],
            username=validated_data['username'],
            password=validated_data['password']
        )
        return user

class ForgotPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()

class VerifyOtpSerializer(serializers.Serializer):
    otp = serializers.CharField(max_length=6)
    otp_token = serializers.CharField()

class ResetPasswordSerializer(serializers.Serializer):
    new_password = serializers.CharField()
    otp_token = serializers.CharField()

class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()

class TransferSerializer(serializers.Serializer):
    recipient_boiya_id = serializers.CharField(max_length=20)
    amount = serializers.DecimalField(min_value=Decimal('0.01'), max_digits=15, decimal_places=2)

    def validate(self, data):
        user = self.context['request'].user
        recipient_boiya_id = data.get('recipient_boiya_id')

        sender_wallet = getattr(user, 'wallet', None)
        if not sender_wallet:
            raise serializers.ValidationError("Sender does not have a wallet.")

        data['sender_wallet'] = sender_wallet
        return data

class ReceiveSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['wallet__boiya_id']

    def to_representation(self, instance):
        return {"boiya_id": instance.wallet.boiya_id}
    
class GradeListSerializer(serializers.Serializer):
    code = serializers.CharField()
    label = serializers.CharField()

class CurrentBalanceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Wallet
        fields = ['balance']

    def to_representation(self, instance):
        return {"current_amount": str(instance.balance)}

# New 2FA Serializers
class TwoFactorAuthSetupSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)

    def validate_email(self, value):
        user = self.context['request'].user
        if value != user.email:
            raise serializers.ValidationError("The email must match your registered email.")
        return value

    def save(self, **kwargs):
        user = self.context['request'].user
        otp = user.set_otp(length=6, expiry_minutes=1)  # Use existing set_otp method
        send_mail(
            subject='Your 2FA OTP Code',
            message=f'Your 6-digit OTP code is {otp}. It will expire in 1 minute.',
            from_email=settings.EMAIL_HOST_USER,
            recipient_list=[user.email],
            fail_silently=False,
        )
        return user

class TwoFactorAuthValidateSerializer(serializers.Serializer):
    otp = serializers.CharField(max_length=6, required=True)

    def validate_otp(self, value):
        user = self.context['request'].user
        if not user.verify_otp(value):
            raise serializers.ValidationError("Invalid or expired OTP code.")
        return value

    def save(self, **kwargs):
        user = self.context['request'].user
        user.enable_2fa()
        return user
    
class LoginOtpVerifySerializer(serializers.Serializer):
    otp = serializers.CharField(max_length=6, required=True)
    login_token = serializers.CharField(required=True)  # Temporary token from login response

    def validate(self, data):
        otp = data.get('otp')
        login_token = data.get('login_token')

        try:
            user_id = int(login_token)  # Assuming login_token is the user ID for simplicity
            user = User.objects.get(pk=user_id)
        except (ValueError, User.DoesNotExist):
            raise serializers.ValidationError("Invalid login token.")

        if not user.verify_otp(otp):
            raise serializers.ValidationError("Invalid or expired OTP code.")
        data['user'] = user
        return data


class TransactionHistorySerializer(serializers.ModelSerializer):
    username = serializers.SerializerMethodField()  # Source/Destination username
    time_ago = serializers.SerializerMethodField()  # Relative timestamp

    class Meta:
        model = Transaction
        fields = ['transaction_type', 'amount', 'username', 'time_ago']

    def get_username(self, obj):
        # Determine the username based on transaction type
        if obj.transaction_type == 'ADMIN_GRANT':
            return "Admin"
        elif obj.transaction_type == 'SHOP_REDEMPTION':
            return "Shop"
        elif obj.transaction_type in ['SIGNUP_BONUS', 'DAILY_LOGIN']:
            return "System"
        elif obj.transaction_type == 'TRANSFER_RECEIVE':
            return obj.recipient_wallet.user.username if obj.recipient_wallet else "Unknown"
        elif obj.transaction_type == 'TRANSFER_SEND':
            return obj.wallet.user.username if obj.wallet else "Unknown"
        return "Unknown"

    def get_time_ago(self, obj):
        from django.utils import timezone
        time_difference = timezone.now() - obj.created_at
        total_seconds = time_difference.total_seconds()

        if total_seconds < 3600:  # Less than 1 hour
            minutes = int(total_seconds // 60)
            return f"{minutes} mins ago" if minutes > 0 else "just now"
        elif total_seconds < 86400:  # Less than 1 day
            hours = int(total_seconds // 3600)
            return f"{hours} hour{'s' if hours > 1 else ''} ago"
        else:  # 1 day or more
            days = int(total_seconds // 86400)
            return f"{days} day{'s' if days > 1 else ''} ago"

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        # Add sign to amount based on transaction type
        if instance.transaction_type in ['SIGNUP_BONUS', 'DAILY_LOGIN', 'TRANSFER_RECEIVE', 'ADMIN_GRANT']:
            ret['amount'] = f"+{instance.amount}"
        else:
            ret['amount'] = f"-{instance.amount}"
        # Format transaction_type without underscores and capitalize
        transaction_mapping = {
            'SIGNUP_BONUS': 'Signup Bonus',
            'TRANSFER_RECEIVE': 'Transfer Receive',
            'TRANSFER_SEND': 'Transfer Send',
            'ADMIN_GRANT': 'Admin Grant',
            'SHOP_REDEMPTION': 'Shop Redemption',
            'DAILY_LOGIN': 'Daily Login'
        }
        ret['transaction_type'] = transaction_mapping.get(instance.transaction_type, instance.transaction_type)
        # Only truncate description for SHOP_REDEMPTION if description is detailed and long
        if instance.transaction_type == 'SHOP_REDEMPTION':
            if instance.description and len(instance.description.strip()) > 10 and "Shop Redemption" in instance.description.lower():
                ret['transaction_type'] = f"{instance.description.strip()[:10]}..."
        return ret