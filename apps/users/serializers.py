from rest_framework import serializers
from django.contrib.auth import authenticate
from .models import User

# ---------------------------
# Login Serializer
# ---------------------------
class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, data):
        email = data.get("email")
        password = data.get("password")
        user = authenticate(email=email, password=password)

        if not user:
            raise serializers.ValidationError("Invalid email or password")
        data["user"] = user
        return data


# ---------------------------
# Register Serializer
# ---------------------------
class RegisterSerializer(serializers.ModelSerializer):
    confirm_password = serializers.CharField(write_only=True)
    accepted_terms = serializers.BooleanField(write_only=True)

    class Meta:
        model = User
        fields = [
            "full_name", "username", "date_of_birth", "grade",
            "email", "password", "confirm_password",
            "accepted_terms"
        ]
        extra_kwargs = {"password": {"write_only": True}}

    def validate(self, data):
        # Check password match
        if data["password"] != data["confirm_password"]:
            raise serializers.ValidationError("Passwords do not match.")
        # Check terms acceptance
        if not data.get("accepted_terms"):
            raise serializers.ValidationError("You must accept the Terms & Conditions.")
        return data

    def create(self, validated_data):
        # Remove confirm_password and accepted_terms from validated_data
        validated_data.pop("confirm_password")
        accepted_terms = validated_data.pop("accepted_terms", False)
        # Create user
        user = User.objects.create_user(**validated_data)
        user.accepted_terms = accepted_terms
        user.save()
        return user

# -----------------------------
# Forgot password / OTP / Reset password serializers
# -----------------------------
class ForgotPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()


class VerifyOtpSerializer(serializers.Serializer):
    otp = serializers.CharField(max_length=6)
    otp_token = serializers.CharField(required=True)


class ResetPasswordSerializer(serializers.Serializer):
    new_password = serializers.CharField(write_only=True)
    confirm_password = serializers.CharField(write_only=True)
    otp_token = serializers.CharField(required=True)

    def validate(self, attrs):
        if attrs.get('new_password') != attrs.get('confirm_password'):
            raise serializers.ValidationError({"password": "Passwords must match."})
        return attrs


# -----------------------------
# Logout serializer
# -----------------------------
class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()