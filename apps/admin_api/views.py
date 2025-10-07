# apps/admin_api/views.py
from rest_framework import generics, status, permissions
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from .serializers import AdminLoginSerializer, StudentManagementSerializer, GrantCoinsSerializer
from apps.users.models import User
from apps.raw.models import Wallet, Transaction
from django.utils import timezone
from decimal import Decimal

class AdminLoginView(generics.GenericAPIView):
    serializer_class = AdminLoginSerializer
    permission_classes = [permissions.AllowAny]  # No pre-auth required for login

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']
        wallet = getattr(user, 'wallet', None)  # Safely get wallet, default to None if missing

        # Ensure admin has a wallet with unlimited balance
        if not wallet:
            wallet = Wallet.objects.create(user=user, boiya_id=f"BOIYA{user.id:06d}")
        wallet.balance = Decimal('99999999.99')  # Set unlimited balance
        wallet.last_login_bonus = timezone.now().date()  # Initialize or update
        wallet.save()

        # Optional daily login bonus (commented out since balance is unlimited)
        # if wallet.last_login_bonus != timezone.now().date():
        #     wallet.add_coins(50)
        #     wallet.last_login_bonus = timezone.now().date()
        #     wallet.save()
        #     Transaction.objects.create(
        #         wallet=wallet,
        #         amount=50,
        #         transaction_type='DAILY_LOGIN',
        #         description='Daily login bonus'
        #     )

        refresh = RefreshToken.for_user(user)
        return Response({
            "refresh": str(refresh),
            "access": str(refresh.access_token),
            "user": {
                "id": user.id,
                "email": user.email,
                "username": user.username,
                "balance": str(wallet.balance)
            }
        }, status=status.HTTP_200_OK)

class GrantCoinsView(generics.GenericAPIView):
    permission_classes = [permissions.IsAdminUser]
    serializer_class = GrantCoinsSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user_id = serializer.validated_data['user_id']
        amount = serializer.validated_data['amount']

        try:
            user = User.objects.get(id=user_id, is_staff=False)
            wallet = user.wallet
            if not wallet:
                wallet = Wallet.objects.create(user=user, boiya_id=f"BOIYA{user.id:06d}")

            wallet.add_coins(amount)
            Transaction.objects.create(
                wallet=wallet,
                amount=amount,
                transaction_type='ADMIN_GRANT',
                description=f'Coins granted by admin {request.user.username}'
            )

            return Response({
                "detail": f"Granted {amount} coins to user {user.username}",
                "user_balance": str(wallet.balance)
            }, status=status.HTTP_200_OK)

        except User.DoesNotExist:
            return Response({"detail": "User not found or is an admin."}, status=status.HTTP_404_NOT_FOUND)

class StudentManagementListView(generics.ListAPIView):
    serializer_class = StudentManagementSerializer
    permission_classes = [permissions.IsAdminUser]
    queryset = User.objects.filter(is_staff=False).order_by('-date_joined')

    def get_queryset(self):
        queryset = super().get_queryset()
        search_query = self.request.query_params.get('search', None)
        if search_query:
            queryset = queryset.filter(
                username__icontains=search_query
            ) | queryset.filter(
                email__icontains=search_query
            )
        return queryset

class StudentStatusUpdateView(generics.UpdateAPIView):
    serializer_class = StudentManagementSerializer
    permission_classes = [permissions.IsAdminUser]
    queryset = User.objects.filter(is_staff=False)
    lookup_field = 'id'

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        is_active = request.data.get('is_active', None)
        if is_active is not None:
            instance.is_active = bool(is_active)
            instance.save()
            status = "activated" if is_active else "suspended"
            return Response({"detail": f"Student {status} successfully"})
        return Response({"detail": "No action specified"}, status=400)

class StudentDeleteView(generics.DestroyAPIView):
    permission_classes = [permissions.IsAdminUser]
    queryset = User.objects.filter(is_staff=False)
    lookup_field = 'id'

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.delete()
        return Response({"detail": "Student deleted successfully"})