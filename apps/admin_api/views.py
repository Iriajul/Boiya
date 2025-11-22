# apps/admin_api/views.py
from rest_framework import generics, status, permissions
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken, BlacklistedToken
from rest_framework_simplejwt.exceptions import TokenError
from .serializers import AdminLoginSerializer, AdminProfileSerializer, AdminPasswordSerializer, AdminOtpVerifySerializer, StudentManagementSerializer, GrantCoinsSerializer, ExportStudentSerializer, AllocateCoinsSerializer, AllocationHistorySerializer, CurrencyStatsSerializer, TransactionHistorySerializer, CategorySerializer, ProductSerializer
from apps.users.models import User
from apps.raw.models import Wallet, Transaction
from apps.admin_api.models import Category, Product, Admin
from django.utils import timezone
from decimal import Decimal
import csv
from django.http import HttpResponse, StreamingHttpResponse
from io import StringIO
from django.db.models import Sum, Count
from rest_framework.pagination import PageNumberPagination
from django.db.models import Q
import calendar
from calendar import month_name
from datetime import datetime, timedelta
from django.core.mail import send_mail
from django.conf import settings
import pytz  # Added for timezone handling

class AdminLoginView(generics.GenericAPIView):
    serializer_class = AdminLoginSerializer
    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']

        # Check if user is a superuser
        if not user.is_superuser:
            return Response({"detail": "Only superusers can log in here."}, status=status.HTTP_403_FORBIDDEN)

        # Ensure admin_profile exists, create if it doesn't
        if not hasattr(user, 'admin_profile') or user.admin_profile is None:
            Admin.objects.get_or_create(user=user)  # Creates with default values

        admin = user.admin_profile  # Now safe to access

        # Generate and send OTP
        otp = serializer.generate_otp(admin)  # Use Admin's set_otp via serializer
        send_mail(
            subject='Your Admin Login OTP Code',
            message=f'Your 6-digit OTP code is {otp}. It will expire in 5 minutes.',
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )

        return Response({
            "detail": "OTP sent to your admin email. It expires in 5 minutes.",
            "login_token": str(user.id)
        }, status=status.HTTP_200_OK)

class AdminOtpVerifyView(generics.GenericAPIView):
    serializer_class = AdminOtpVerifySerializer
    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']
        admin = serializer.validated_data['admin']
        admin.clear_otp()  # Use Admin's clear_otp

        # Generate tokens after OTP verification
        refresh = RefreshToken.for_user(user)
        wallet = getattr(user, 'wallet', None) if hasattr(user, 'wallet') else None

        if not wallet:
            wallet = Wallet.objects.create(user=user, boiya_id=f"BOIYA{user.id:06d}")
        wallet.balance = Decimal('99999999.99')
        wallet.last_login_bonus = timezone.now().date()
        wallet.save()

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

        return Response(response_data, status=status.HTTP_200_OK)

class ResendAdminOtpView(generics.GenericAPIView):
    serializer_class = AdminLoginSerializer
    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']
        admin = user.admin_profile  # Get the related Admin instance

        # Generate and send new OTP immediately
        otp = serializer.generate_otp(admin)  # Use Admin's set_otp via serializer
        send_mail(
            subject='Your New Admin Login OTP Code',
            message=f'Your new 6-digit OTP code is {otp}. It will expire in 5 minutes.',
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )

        return Response({
            "detail": "New OTP sent to your admin email. It expires in 5 minutes.",
            "login_token": str(user.id)
        }, status=status.HTTP_200_OK)

class LogoutView(generics.GenericAPIView):
    permission_classes = [permissions.IsAdminUser]

    def post(self, request, *args, **kwargs):
        try:
            refresh_token = request.data["refresh"]
            token = RefreshToken(refresh_token)
            token.blacklist()  # Blacklist the refresh token
            return Response({"detail": "Successfully logged out."}, status=status.HTTP_200_OK)
        except TokenError:
            return Response({"detail": "Invalid token."}, status=status.HTTP400_BAD_REQUEST)
        except KeyError:
            return Response({"detail": "Refresh token is required."}, status=status.HTTP400_BAD_REQUEST)

class AdminProfileView(generics.RetrieveUpdateAPIView):
    """
    Retrieve and update the current admin's profile information.
    - GET: Fetch the admin's profile.
    - PATCH: Update profile details (name, phone, location, department, bio, profile picture).
    - Only accessible to the logged-in admin (is_superuser=True).
    """
    permission_classes = [permissions.IsAdminUser]
    serializer_class = AdminProfileSerializer

    def get_object(self):
        user = self.request.user
        admin_profile, created = Admin.objects.get_or_create(user=user)
        return admin_profile

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', True)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        # Return the updated serialized data
        return Response(serializer.data)

class AdminPasswordChangeView(generics.GenericAPIView):
    """
    Change the current admin's password.
    - POST: Requires current_password, new_password, and confirm_password.
    - Only accessible to the logged-in admin (is_superuser=True).
    """
    permission_classes = [permissions.IsAdminUser]
    serializer_class = AdminPasswordSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        user = request.user
        user.set_password(serializer.validated_data['new_password'])
        user.save()
        return Response({"detail": "Password changed successfully."}, status=status.HTTP_200_OK)

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
                status='COMPLETED',
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
    queryset = User.objects.filter(is_staff=False).order_by('-date_joined').prefetch_related('wallet__transactions')

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

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)

        print("Serializer data:", serializer.data)

        total_students = User.objects.filter(is_staff=False).count()
        active_students = User.objects.filter(is_staff=False, is_active=True).count()
        blocked_students = User.objects.filter(is_staff=False, is_active=False).count()

        response_data = {
            "students": serializer.data,
            "counts": {
                "total_students": total_students,
                "active_students": active_students,
                "blocked_students": blocked_students
            }
        }
        return Response(response_data)

class ExportStudentsView(generics.GenericAPIView):
    permission_classes = [permissions.IsAdminUser]
 
    def get(self, request, *args, **kwargs):
        students = User.objects.filter(is_staff=False).order_by('-date_joined').prefetch_related('wallet__transactions')
        serializer = ExportStudentSerializer(students, many=True)
 
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="students_export.csv"'
        writer = csv.writer(response)
        writer.writerow(['username', 'email', 'date_joined', 'is_active', 'balance', 'boiya_id', 'transactions'])
 
        for student_data in serializer.data:
            writer.writerow([
                student_data.get('username', ''),
                student_data.get('email', ''),
                student_data.get('date_joined', ''),
                student_data.get('is_active', ''),
                student_data.get('balance', '0.00'),
                student_data.get('boiya_id', ''),
                student_data.get('transactions', 0)
            ])
 
        return response

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

class CurrencyStatsView(generics.GenericAPIView):
    permission_classes = [permissions.IsAdminUser]
    serializer_class = CurrencyStatsSerializer

    def get(self, request, *args, **kwargs):
        # Total Coins Issued: Sum of ADMIN_GRANT transactions
        total_coins_issued = Transaction.objects.filter(
            transaction_type='ADMIN_GRANT'
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

        # Coins Redeemed: 0 for now (pending shop implementation)
        coins_redeemed = Transaction.objects.filter(
            transaction_type='SHOP_REDEMPTION',
            status='COMPLETED'
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

        # Active Balance: Sum of all non-admin user wallet balances
        active_balance = Wallet.objects.filter(
            user__is_staff=False
        ).aggregate(total=Sum('balance'))['total'] or Decimal('0.00')

        serializer = self.get_serializer({
            'total_coins_issued': total_coins_issued,
            'coins_redeemed': coins_redeemed,
            'active_balance': active_balance
        })
        return Response(serializer.data)

class AllocateCoinsView(generics.GenericAPIView):
    permission_classes = [permissions.IsAdminUser]
    serializer_class = AllocateCoinsSerializer

    def get(self, request, *args, **kwargs):
        # Return a list of users for the admin to select
        users = User.objects.filter(is_staff=False).values('id', 'username')
        return Response({"users": list(users)})

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user_id = serializer.validated_data['user_id']
        amount = serializer.validated_data['amount']
        reason = serializer.validated_data['reason']

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
                status='COMPLETED',
                description=reason
            )

            return Response({
                "detail": f"Allocated {amount} coins to user {user.username}",
                "user_balance": str(wallet.balance)
            }, status=status.HTTP_200_OK)

        except User.DoesNotExist:
            return Response({"detail": "User not found or is an admin."}, status=status.HTTP_404_NOT_FOUND)

class AllocationHistoryView(generics.ListAPIView):
    permission_classes = [permissions.IsAdminUser]
    serializer_class = AllocationHistorySerializer

    def get_queryset(self):
        # Define queryset dynamically per request
        return Transaction.objects.filter(transaction_type='ADMIN_GRANT').order_by('-created_at')

class CustomPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 100

class TransactionHistoryView(generics.ListAPIView):
    permission_classes = [permissions.IsAdminUser]
    serializer_class = TransactionHistorySerializer
    pagination_class = CustomPagination

    def get_queryset(self):
        # Base queryset for all relevant transactions
        queryset = Transaction.objects.filter(
            transaction_type__in=['TRANSFER_SEND', 'TRANSFER_RECEIVE', 'SHOP_REDEMPTION']
        ).order_by('-created_at')
        # Search by from or to username
        search_query = self.request.query_params.get('search', '').lower()
        if search_query:
            queryset = queryset.filter(
                Q(wallet__user__username__icontains=search_query) |
                Q(recipient_wallet__user__username__icontains=search_query)
            )

        return queryset

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

# New Views for Marketplace

class CategoryListCreateView(generics.ListCreateAPIView):
    """
    List all categories or create a new category.
    - Requires admin authentication.
    - POST requires 'name' field.
    """
    permission_classes = [permissions.IsAdminUser]
    serializer_class = CategorySerializer
    queryset = Category.objects.all()

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return Response({"message": "Category created", "data": serializer.data}, status=status.HTTP_201_CREATED)

class CategoryPauseView(generics.UpdateAPIView):
    """
    Toggle the paused status of a category.
    - Requires admin authentication.
    - PATCH to toggle between paused and active.
    """
    permission_classes = [permissions.IsAdminUser]
    serializer_class = CategorySerializer
    queryset = Category.objects.all()

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.paused = not instance.paused
        instance.save(update_fields=['paused'])
        return Response({"message": "Category paused" if instance.paused else "Category resumed", "data": self.get_serializer(instance).data})

class CategoryPlayView(generics.UpdateAPIView):
    """
    Resume a paused category.
    - Requires admin authentication.
    - PATCH to set paused to false.
    """
    permission_classes = [permissions.IsAdminUser]
    serializer_class = CategorySerializer
    queryset = Category.objects.all()

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        if not instance.paused:
            return Response({"message": "Category is already active"}, status=status.HTTP_400_BAD_REQUEST)
        instance.paused = False
        instance.save(update_fields=['paused'])
        return Response({"message": "Category resumed", "data": self.get_serializer(instance).data})

class CategoryDeleteView(generics.DestroyAPIView):
    """
    Delete a category if it has no items.
    - Requires admin authentication.
    - Fails if item_count > 0.
    """
    permission_classes = [permissions.IsAdminUser]
    queryset = Category.objects.all()

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.item_count > 0:
            return Response({"error": f"Cannot delete category with {instance.item_count} items left."}, status=status.HTTP_400_BAD_REQUEST)
        self.perform_destroy(instance)
        return Response({"message": "Category deleted"}, status=status.HTTP_200_OK)

class ProductListCreateView(generics.ListCreateAPIView):
    """
    List all products or create a new product.
    - Requires admin authentication.
    - POST requires 'name', 'description', 'price', 'category', and optional 'thumbnail' and 'file'.
    """
    permission_classes = [permissions.IsAdminUser]
    serializer_class = ProductSerializer
    queryset = Product.objects.all()

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return Response({"message": "Product created", "data": serializer.data}, status=status.HTTP_201_CREATED)

class ProductUpdateView(generics.UpdateAPIView):
    """
    Update an existing product.
    - Requires admin authentication.
    - PATCH allows editing all fields, including category and date_submitted, with optional file uploads.
    """
    permission_classes = [permissions.IsAdminUser]
    serializer_class = ProductSerializer
    queryset = Product.objects.all()

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True, context={'request': request})
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response({"message": "Product updated", "data": serializer.data})

class ProductPauseView(generics.UpdateAPIView):
    """
    Toggle the paused status of a product.
    - Requires admin authentication.
    - PATCH to toggle between paused and active.
    """
    permission_classes = [permissions.IsAdminUser]
    serializer_class = ProductSerializer
    queryset = Product.objects.all()

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.paused = not instance.paused
        instance.save(update_fields=['paused'])
        return Response({"message": "Product paused" if instance.paused else "Product resumed", "data": self.get_serializer(instance).data})

class ProductPlayView(generics.UpdateAPIView):
    """
    Resume a paused product.
    - Requires admin authentication.
    - PATCH to set paused to false.
    """
    permission_classes = [permissions.IsAdminUser]
    serializer_class = ProductSerializer
    queryset = Product.objects.all()

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        if not instance.paused:
            return Response({"message": "Product is already active"}, status=status.HTTP_400_BAD_REQUEST)
        instance.paused = False
        instance.save(update_fields=['paused'])
        return Response({"message": "Product resumed", "data": self.get_serializer(instance).data})

class ProductDeleteView(generics.DestroyAPIView):
    """
    Delete a product.
    - Requires admin authentication.
    - Decrements category item_count upon deletion.
    """
    permission_classes = [permissions.IsAdminUser]
    queryset = Product.objects.all()

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.category.item_count -= 1
        instance.category.save(update_fields=['item_count'])
        self.perform_destroy(instance)
        return Response({"message": "Product deleted"}, status=status.HTTP_200_OK)

class TopPurchasingProductsView(generics.ListAPIView):
    """
    List the top purchasing products based on sales count.
    - Shows the top products with their category and sales.
    - Limited to 5 items by default.
    """
    permission_classes = [permissions.IsAdminUser]
    serializer_class = ProductSerializer

    def get_queryset(self):
        return Product.objects.all().order_by('-sales')[:2]

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        data = [
            {
                "name": item['name'],
                "category": Category.objects.get(id=item['category']).name if item['category'] else 'Uncategorized',
                "sales": item['sales']
            } for item in serializer.data
        ]
        return Response(data)

class CategoryDistributionView(generics.GenericAPIView):
    """
    Provide distribution of products across categories.
    - Shows total products and products per category.
    """
    permission_classes = [permissions.IsAdminUser]

    def get(self, request, *args, **kwargs):
        total_products = Product.objects.count()
        category_stats = Category.objects.annotate(
            product_count=Count('products')
        ).values('name', 'product_count')
        data = [
            {
                "category": item['name'],
                "distribution": f"{item['product_count']}/{total_products}"
            } for item in category_stats
        ]
        return Response(data)

class CoinAnalyticsView(generics.GenericAPIView):
    """
    Provide analytics on coins issued vs coins spent per month.
    - Coins issued: Total coins allocated by admin via AllocateCoinsView (ADMIN_GRANT).
    - Coins spent: Total coins spent on product purchases via PurchaseView.
    - Data is aggregated monthly for the current year.
    """
    permission_classes = [permissions.IsAdminUser]

    def get(self, request, *args, **kwargs):
        # Get all months (1-12) with their names
        months = [month_name[i] for i in range(1, 13)]
        current_year = timezone.now().year  # 2025

        # Initialize data structure
        analytics_data = {month: {"issued": Decimal('0.00'), "spent": Decimal('0.00')} for month in months}

        # Coins issued (from AllocateCoinsView transactions)
        allocation_transactions = Transaction.objects.filter(
            transaction_type='ADMIN_GRANT',
            created_at__year=current_year
        ).values('created_at__month').annotate(total_issued=Sum('amount'))
        for entry in allocation_transactions:
            month = months[entry['created_at__month'] - 1]
            analytics_data[month]["issued"] += entry['total_issued'] or Decimal('0.00')

        # Coins spent (from PurchaseView transactions)
        purchase_transactions = Transaction.objects.filter(
            transaction_type='SHOP_REDEMPTION',
            created_at__year=current_year
        ).values('created_at__month').annotate(total_spent=Sum('amount'))
        for entry in purchase_transactions:
            month = months[entry['created_at__month'] - 1]
            analytics_data[month]["spent"] += entry['total_spent'] or Decimal('0.00')

        # Convert to list of dictionaries for response
        response_data = [
            {
                "month": month,
                "issued": float(analytics_data[month]["issued"]),
                "spent": float(analytics_data[month]["spent"])
            } for month in months
        ]

        return Response(response_data)

class ProductCategoryRedemptionView(generics.GenericAPIView):
    """
    Provide analytics on how students spend their coins across store categories.
    - Calculates the percentage of total coins spent per category based on product sales.
    - Includes an 'Other' category for categories with less than 5% contribution.
    """
    permission_classes = [permissions.IsAdminUser]

    def get(self, request, *args, **kwargs):
        current_year = timezone.now().year  # 2025

        # Aggregate total coins spent per category via SHOP_REDEMPTION transactions
        category_spending = Transaction.objects.filter(
            transaction_type='SHOP_REDEMPTION',
            created_at__year=current_year
        ).values('product_id').annotate(total_spent=Sum('amount')).values('product_id', 'total_spent')

        # Map product IDs to categories and sum spending
        category_totals = {}
        total_spent = Decimal('0.00')
        for transaction in category_spending:
            product_id = transaction['product_id']
            if product_id:  # Ensure product_id exists
                try:
                    product = Product.objects.get(id=product_id)
                    category_name = product.category.name if product.category else 'Uncategorized'
                    category_totals[category_name] = category_totals.get(category_name, Decimal('0.00')) + transaction['total_spent']
                    total_spent += transaction['total_spent']
                except Product.DoesNotExist:
                    continue

        # Calculate percentages
        category_percentages = {}
        for category, amount in category_totals.items():
            percentage = (amount / total_spent * 100) if total_spent > 0 else 0
            category_percentages[category] = percentage

        # Group small categories (<5%) into 'Other'
        main_categories = {}
        other_total = Decimal('0.00')
        for category, percentage in category_percentages.items():
            if percentage >= 5:
                main_categories[category] = percentage
            else:
                other_total += amount

        if other_total > 0 and total_spent > 0:
            other_percentage = (other_total / total_spent * 100)
            if other_percentage >= 1:  # Only include 'Other' if it contributes at least 1%
                main_categories['Other'] = other_percentage

        # Prepare response data
        response_data = [
            {"category": category, "percentage": round(percentage, 2)}
            for category, percentage in main_categories.items()
        ]

        return Response(response_data)

class WeeklyTransactionVolumeView(generics.GenericAPIView):
    """
    Provide analytics on weekly transaction volume based on month-based weeks.
    - Marketplace: Total coins spent on SHOP_REDEMPTION transactions.
    - P2P: Total coins sent on TRANSFER_SEND transactions.
    - Data is aggregated over the weeks of the current month, with weeks defined from the 1st to Sundays.
    - Only includes status='COMPLETED' transactions.
    - Supports any month length (28, 30, or 31 days).
    """
    permission_classes = [permissions.IsAdminUser]

    def get(self, request, *args, **kwargs):
        today = timezone.now()
        current_year = today.year  # 2025
        current_month = today.month  # October
        _, last_day_of_month = calendar.monthrange(current_year, current_month)  # Get actual last day (e.g., 31 for October)

        # Get the first and last day of the current month with UTC timezone
        utc = pytz.UTC
        first_day = utc.localize(datetime(current_year, current_month, 1))
        last_day = utc.localize(datetime(current_year, current_month, last_day_of_month, 23, 59, 59, 999999))

        # Calculate week boundaries based on Sundays, including the full day
        weeks = []
        current_date = first_day
        week_number = 1

        while current_date.date() <= last_day.date():
            week_start = current_date
            # Move to the end of the week (Sunday 23:59:59) or beyond the month end
            while current_date.weekday() != 6 and current_date <= last_day:
                current_date += timedelta(days=1)
            week_end = min(current_date.replace(hour=23, minute=59, second=59, microsecond=999999), last_day)
            current_week = {
                "week": f"W{week_number}",
                "start": week_start,
                "end": week_end
            }
            weeks.append(current_week)
            print(f"Week {current_week['week']}: {current_week['start']} to {current_week['end']}")  # Debug output
            current_date += timedelta(days=1)  # Move past Sunday
            week_number += 1

        # Aggregate transaction data for the entire month, including all weeks
        response_data = []
        for week in weeks:
            marketplace_volume = Transaction.objects.filter(
                transaction_type='SHOP_REDEMPTION',
                status='COMPLETED',
                created_at__range=(week['start'], week['end'])
            ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
            p2p_volume = Transaction.objects.filter(
                transaction_type='TRANSFER_SEND',
                status='COMPLETED',
                created_at__range=(week['start'], week['end'])
            ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
            response_data.append({
                "week": week['week'],
                "marketplace": float(marketplace_volume),
                "p2p": float(p2p_volume)
            })

        return Response(response_data)
    