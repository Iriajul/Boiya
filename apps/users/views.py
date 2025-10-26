from rest_framework import generics, status, permissions
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from .serializers import LoginSerializer, RegisterSerializer, LoginOtpVerifySerializer, ForgotPasswordSerializer, TransactionHistorySerializer, VerifyOtpSerializer, ResetPasswordSerializer, LogoutSerializer, TransferSerializer, ReceiveSerializer, CurrentBalanceSerializer, GradeListSerializer, ProfileSerializer, TwoFactorAuthSetupSerializer, TwoFactorAuthValidateSerializer, ResendForgotPasswordOtpSerializer, ResendTwoFactorAuthOtpSerializer, DisableTwoFactorAuthSerializer, RecentActivitySerializer
from .models import User
from django.db.models import Q
import logging
from django.core.mail import send_mail
from django.conf import settings
from apps.raw.models import Wallet, Transaction
from django.utils import timezone
from decimal import Decimal
import cloudinary
import cloudinary.uploader
from environ import Env  # Updated to use environ from settings.py

# Load environment variables (assuming settings.py uses environ)
env = Env()
cloudinary.config(
    cloud_name=env('CLOUDINARY_CLOUD_NAME'),
    api_key=env('CLOUDINARY_API_KEY'),
    api_secret=env('CLOUDINARY_API_SECRET')
)

logger = logging.getLogger(__name__)

# ---------------------------
# Register (Signup) View
# ---------------------------
class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        return Response({
            "message": "Account created successfully",
            "user": {
                "id": user.id,
                "email": user.email,
                "username": user.username
            },
        }, status=status.HTTP_201_CREATED)

# ---------------------------
# Login View
# ---------------------------
class LoginView(generics.GenericAPIView):
    serializer_class = LoginSerializer
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        wallet = getattr(user, 'wallet', None)

        if not wallet:
            wallet = Wallet.objects.create(user=user, boiya_id=f"BOIYA{user.id:06d}")
            wallet.add_coins(Decimal('50.00'))
            Transaction.objects.create(
                wallet=wallet,
                amount=Decimal('50.00'),
                transaction_type='SIGNUP_BONUS',
                status='COMPLETED',
                description='Welcome bonus'
            )
            wallet.last_login_bonus = timezone.now().date()

        today = timezone.now().date()
        is_first_login = wallet.last_login_bonus is None or wallet.last_login_bonus == timezone.now().date()
        if wallet.last_login_bonus != today and not is_first_login:
            wallet.add_coins(Decimal('50.00'))
            wallet.last_login_bonus = today
            wallet.save()
            Transaction.objects.create(
                wallet=wallet,
                amount=Decimal('50.00'),
                transaction_type='DAILY_LOGIN',
                status='COMPLETED',
                description='Daily login bonus'
            )

        refresh = RefreshToken.for_user(user)

        response_data = {
            "refresh": str(refresh),
            "access": str(refresh.access_token),
            "user": {
                "id": user.id,
                "email": user.email,
                "username": user.username,
                "balance": str(wallet.balance)
            }
        }

        if is_first_login:
            response_data.update({
                "welcome_message": "Welcome to Boyia!",
                "bonus_notification": {
                    "message": "You just earned 50 coins",
                    "type": "Welcome Bonus",
                    "amount": "+50",
                    "details": "Coins added to your wallet",
                    "status": "Getting your wallet ready..."
                }
            })

        # If 2FA is enabled, send OTP and return temporary response
        if user.is_2fa_enabled:
            otp = user.set_otp(length=6, expiry_minutes=5)  # Updated to 5 minutes
            send_mail(
                subject='Your Login OTP Code',
                message=f'Your 6-digit OTP code is {otp}. It will expire in 5 minutes.',
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=False,
            )
            response_data = {
                "detail": "2FA is enabled. Please verify OTP to complete login.",
                "login_token": str(user.id)  # Temporary token (using user ID for simplicity)
            }
            return Response(response_data, status=status.HTTP_200_OK)

        return Response(response_data, status=status.HTTP_200_OK)

# ---------------------------
# Verify OTP for Login View
# ---------------------------
class VerifyOtpLoginView(generics.GenericAPIView):
    """
    Verify OTP to complete login when 2FA is enabled.
    - POST: Requires otp and login_token.
    """
    permission_classes = [AllowAny]
    serializer_class = LoginOtpVerifySerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        user.clear_otp()  # Clear OTP after successful validation

        # Generate new tokens after OTP verification
        refresh = RefreshToken.for_user(user)
        wallet = getattr(user, 'wallet', None) if hasattr(user, 'wallet') else None

        response_data = {
            "refresh": str(refresh),
            "access": str(refresh.access_token),
            "user": {
                "id": user.id,
                "email": user.email,
                "username": user.username,
                "balance": str(wallet.balance) if wallet else "0.00"
            }
        }

        return Response(response_data, status=status.HTTP_200_OK)

# -----------------------------
# OTP Flow Views
# -----------------------------
class ForgotPasswordView(generics.GenericAPIView):
    serializer_class = ForgotPasswordSerializer
    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response({"detail": "Email not found."}, status=status.HTTP_404_NOT_FOUND)

        otp = user.set_otp(length=6, expiry_minutes=5)  # Consistent 5 minutes

        send_mail(
            subject="Your OTP for Password Reset",
            message=f"Your OTP code is {otp}. It is valid for 5 minutes.",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
            fail_silently=False,
        )

        return Response({"detail": "OTP sent to your email.", "otp_token": str(user.pk)}, status=status.HTTP_200_OK)

class VerifyOtpView(generics.GenericAPIView):
    serializer_class = VerifyOtpSerializer
    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        otp = serializer.validated_data["otp"]
        otp_token = serializer.validated_data.get("otp_token")

        if not otp_token:
            return Response({"detail": "OTP token missing."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = User.objects.get(pk=otp_token)
        except User.DoesNotExist:
            return Response({"detail": "Invalid OTP token."}, status=status.HTTP_400_BAD_REQUEST)

        if not user.verify_otp(otp):
            return Response({"detail": "Invalid or expired OTP."}, status=status.HTTP_400_BAD_REQUEST)

        return Response({"detail": "OTP verified successfully."}, status=status.HTTP_200_OK)

class ResetPasswordView(generics.GenericAPIView):
    serializer_class = ResetPasswordSerializer
    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        otp_token = serializer.validated_data.get("otp_token")

        if not otp_token:
            return Response({"detail": "OTP token missing."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = User.objects.get(pk=otp_token)
        except User.DoesNotExist:
            return Response({"detail": "Invalid OTP token."}, status=status.HTTP_400_BAD_REQUEST)

        user.set_password(serializer.validated_data["new_password"])
        user.clear_otp()
        user.save()

        return Response({"detail": "Password reset successfully."}, status=status.HTTP_200_OK)

# -----------------------------
# Logout View
# -----------------------------
class LogoutView(generics.GenericAPIView):
    serializer_class = LogoutSerializer
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        refresh_token = serializer.validated_data["refresh"]

        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
        except Exception:
            return Response({"detail": "Invalid token."}, status=status.HTTP_400_BAD_REQUEST)

        request.user.update_last_activity()

        return Response({"detail": "Logged out successfully."}, status=status.HTTP_200_OK)  # Changed to 200 with body

# ---------------------------
# Send Coins View
# ---------------------------
class SendView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = TransferSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=False)

        if not serializer.is_valid():
            # Log failed transaction for validation errors
            sender_wallet = getattr(request.user, 'wallet', None)
            if sender_wallet:
                amount = serializer.initial_data.get('amount', Decimal('0.00'))
                recipient_boiya_id = serializer.initial_data.get('recipient_boiya_id', '')
                Transaction.objects.create(
                    wallet=sender_wallet,
                    amount=amount,
                    transaction_type='TRANSFER_SEND',
                    status='FAILED',
                    description=f'Validation failed for Boiya ID {recipient_boiya_id}: {str(serializer.errors)}'
                )
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        sender_wallet = serializer.validated_data['sender_wallet']
        amount = serializer.validated_data['amount']
        recipient_boiya_id = serializer.initial_data['recipient_boiya_id']

        try:
            recipient_wallet = Wallet.objects.get(boiya_id=recipient_boiya_id)
            if sender_wallet == recipient_wallet:
                Transaction.objects.create(
                    wallet=sender_wallet,
                    recipient_wallet=recipient_wallet,
                    amount=amount,
                    transaction_type='TRANSFER_SEND',
                    status='FAILED',
                    description=f'Failed transfer to {recipient_wallet.user.username} (self transfer, Boiya ID: {recipient_boiya_id})'
                )
                return Response({"detail": "Cannot send coins to yourself."}, status=status.HTTP_400_BAD_REQUEST)

            if not sender_wallet.remove_coins(amount):
                Transaction.objects.create(
                    wallet=sender_wallet,
                    recipient_wallet=recipient_wallet,
                    amount=amount,
                    transaction_type='TRANSFER_SEND',
                    status='FAILED',
                    description=f'Failed transfer to {recipient_wallet.user.username} (insufficient balance, Boiya ID: {recipient_boiya_id})'
                )
                return Response({"detail": "Insufficient balance."}, status=status.HTTP_400_BAD_REQUEST)

            # Transaction successful
            recipient_wallet.add_coins(amount)
            Transaction.objects.create(
                wallet=sender_wallet,
                recipient_wallet=recipient_wallet,
                amount=amount,
                transaction_type='TRANSFER_SEND',
                status='COMPLETED',
                description=f'Transfer to {recipient_wallet.user.username} (Boiya ID: {recipient_boiya_id})'
            )
            Transaction.objects.create(
                wallet=recipient_wallet,
                recipient_wallet=sender_wallet,
                amount=amount,
                transaction_type='TRANSFER_RECEIVE',
                status='COMPLETED',
                description=f'Transfer from {request.user.username}'
            )

            return Response({
                "detail": "Sent Successful!",
                "amount": str(amount),
                "receiver_boiya_id": recipient_boiya_id,
            }, status=status.HTTP_200_OK)

        except Wallet.DoesNotExist:
            # Log failed transaction for invalid recipient
            Transaction.objects.create(
                wallet=sender_wallet,
                amount=amount,
                transaction_type='TRANSFER_SEND',
                status='FAILED',
                description=f'Failed transfer to Boiya ID {recipient_boiya_id} (invalid recipient)'
            )
            return Response({"detail": "Invalid Recipient Boiya ID."}, status=status.HTTP_400_BAD_REQUEST)

# ---------------------------
# Receive Coins View
# ---------------------------
class ReceiveView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ReceiveSerializer

    def get(self, request, *args, **kwargs):
        serializer = self.get_serializer(request.user)
        wallet = getattr(request.user, 'wallet', None)
        if not wallet:
            wallet = Wallet.objects.create(user=request.user, boiya_id=f"BOIYA{request.user.id:06d}")
        return Response({
            "boiya_id": wallet.boiya_id,
            "message": "Your Boiya ID",
            # QR code generation can be handled by the frontend; return data for it if needed
            "qr_code_data": f"boiya:{wallet.boiya_id}"  # Example data for QR code
        }, status=status.HTTP_200_OK)
    
# ---------------------------
# Grade List View
# ---------------------------
class GradeListView(generics.ListAPIView):
    serializer_class = GradeListSerializer
    permission_classes = [AllowAny]

    def list(self, request, *args, **kwargs):
        # Use GRADE_CHOICES from User model
        grade_choices = User.GRADE_CHOICES
        serializer = self.get_serializer([{'code': code, 'label': label} for code, label in grade_choices], many=True)
        return Response(serializer.data)

# ---------------------------
# Current Balance View
# ---------------------------
class CurrentBalanceView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = CurrentBalanceSerializer

    def get(self, request, *args, **kwargs):
        user = request.user
        wallet = getattr(user, 'wallet', None)
        if not wallet:
            wallet = Wallet.objects.create(user=user, boiya_id=f"BOIYA{user.id:06d}")
        serializer = self.get_serializer(wallet)
        return Response(serializer.data)

# ---------------------------
# Profile View
# ---------------------------
class ProfileView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ProfileSerializer

    def get(self, request, *args, **kwargs):
        user = request.user
        wallet = getattr(user, 'wallet', None)
        if not wallet:
            wallet = Wallet.objects.create(user=user, boiya_id=f"BOIYA{user.id:06d}")
        serializer = self.get_serializer(user)
        return Response(serializer.data)

    def post(self, request, *args, **kwargs):
        user = request.user
        if 'profile_image' not in request.FILES:
            return Response({"detail": "No image file provided."}, status=status.HTTP_400_BAD_REQUEST)

        image_file = request.FILES['profile_image']
        try:
            # Upload to Cloudinary
            result = cloudinary.uploader.upload(image_file, folder="user_profiles")
            image_url = result['secure_url']

            # Update user's profile image
            user.profile_image = image_url
            user.save(update_fields=['profile_image'])

            serializer = self.get_serializer(user)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"detail": f"Image upload failed: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

# ---------------------------
# 2FA Views
# ---------------------------
class TwoFactorAuthSetupView(generics.GenericAPIView):
    """
    Initiate 2FA setup by sending an OTP to the user's email.
    - POST: Requires email (must match user's registered email).
    """
    permission_classes = [IsAuthenticated]
    serializer_class = TwoFactorAuthSetupSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        otp = request.user.set_otp(length=6, expiry_minutes=5)  # Updated to 5 minutes
        send_mail(
            subject='Your 2FA OTP Code',
            message=f'Your 6-digit OTP code is {otp}. It will expire in 5 minutes.',
            from_email=settings.EMAIL_HOST_USER,
            recipient_list=[request.user.email],
            fail_silently=False,
        )
        return Response({"detail": "OTP sent to your email. It expires in 5 minutes."}, status=status.HTTP_200_OK)

class TwoFactorAuthValidateView(generics.GenericAPIView):
    """
    Validate the OTP and enable 2FA.
    - POST: Requires otp (6-digit code).
    """
    permission_classes = [IsAuthenticated]
    serializer_class = TwoFactorAuthValidateSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"detail": "2FA enabled successfully."}, status=status.HTTP_200_OK)

# ---------------------------
# Transaction History View
# ---------------------------
class TransactionHistoryView(generics.ListAPIView):
    """
    Retrieve the transaction history for the authenticated user.
    - GET: Returns a list of transactions.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = TransactionHistorySerializer

    def get_queryset(self):
        user = self.request.user
        wallet = getattr(user, 'wallet', None)
        if not wallet:
            return Transaction.objects.none()
        return Transaction.objects.filter(wallet=wallet).order_by('-created_at')

# ---------------------------
# Resend OTP Views
# ---------------------------
class ResendForgotPasswordOtpView(generics.GenericAPIView):
    """
    Resend OTP for forgot password process.
    - POST: Requires email to resend OTP.
    """
    permission_classes = [permissions.AllowAny]
    serializer_class = ResendForgotPasswordOtpSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email']

        try:
            user = User.objects.get(email=email)
            otp = user.set_otp(length=6, expiry_minutes=5)  # Consistent 5 minutes

            send_mail(
                subject="Your New OTP for Password Reset",
                message=f"Your new 6-digit OTP code is {otp}. It is valid for 5 minutes.",
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[email],
                fail_silently=False,
            )

            return Response({"detail": "New OTP sent to your email.", "otp_token": str(user.pk)}, status=status.HTTP_200_OK)
        except User.DoesNotExist:
            return Response({"detail": "Email not found."}, status=status.HTTP_404_NOT_FOUND)

class ResendTwoFactorAuthOtpView(generics.GenericAPIView):
    """
    Resend OTP for 2FA setup or validation.
    - POST: Requires email (must match authenticated user's email).
    """
    permission_classes = [IsAuthenticated]
    serializer_class = ResendTwoFactorAuthOtpSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email']

        user = request.user
        otp = user.set_otp(length=6, expiry_minutes=5)  # Updated to 5 minutes

        send_mail(
            subject='Your New 2FA OTP Code',
            message=f'Your new 6-digit OTP code is {otp}. It will expire in 5 minutes.',
            from_email=settings.EMAIL_HOST_USER,
            recipient_list=[email],
            fail_silently=False,
        )

        return Response({"detail": "New OTP sent to your email. It expires in 5 minutes."}, status=status.HTTP_200_OK)

# ---------------------------
# Disable 2FA View
# ---------------------------
class DisableTwoFactorAuthView(generics.GenericAPIView):
    """
    Disable 2FA for the authenticated user.
    - POST: Requires current_password to verify identity.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = DisableTwoFactorAuthSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"detail": "2FA has been disabled successfully."}, status=status.HTTP_200_OK)
    

class RecentActivityView(generics.ListAPIView):
    """
    Retrieve the 5 latest transaction activities for the authenticated user.
    - GET: Returns a list of the most recent transactions.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = RecentActivitySerializer

    def get_queryset(self):
        user = self.request.user
        wallet = getattr(user, 'wallet', None)
        if not wallet:
            return Transaction.objects.none()
        return Transaction.objects.filter(wallet=wallet).order_by('-created_at')[:5]    