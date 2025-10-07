# apps/users/views.py (partial update for LoginView)
from rest_framework import generics, status, permissions
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework_simplejwt.tokens import RefreshToken
from .serializers import LoginSerializer, RegisterSerializer, ForgotPasswordSerializer, VerifyOtpSerializer, ResetPasswordSerializer, LogoutSerializer
from .models import User
from django.core.mail import send_mail
from django.conf import settings
from apps.raw.models import Wallet, Transaction
from django.utils import timezone

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
        wallet = user.wallet  # Fetch the user's wallet

        # Daily login bonus
        today = timezone.now().date()
        if wallet and wallet.last_login_bonus != today:
            wallet.add_coins(50)
            wallet.last_login_bonus = today
            wallet.save()
            Transaction.objects.create(
                wallet=wallet,
                amount=50,
                transaction_type='DAILY_LOGIN',
                description='Daily login bonus'
            )

        refresh = RefreshToken.for_user(user)

        return Response({
            "refresh": str(refresh),
            "access": str(refresh.access_token),
            "user": {
                "id": user.id,
                "email": user.email,
                "username": user.username,
                "balance": str(wallet.balance) if wallet else "0.00"  # Include balance
            }
        }, status=status.HTTP_200_OK)

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

        otp = user.set_otp()

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

        # Track logout activity
        request.user.update_last_activity()

        return Response({"detail": "Logged out successfully."}, status=status.HTTP_205_RESET_CONTENT)