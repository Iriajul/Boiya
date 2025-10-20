# apps/shop/views.py
from rest_framework import generics, status, permissions
from rest_framework.response import Response
from .serializers import ProductListSerializer, PurchaseSerializer, PurchaseDetailSerializer, CategorySerializer
from apps.admin_api.models import Product, Category
from apps.raw.models import Wallet, Transaction
from apps.shop.models import UserPurchase
from decimal import Decimal
from rest_framework.exceptions import PermissionDenied

class CategoryListView(generics.ListAPIView):
    """
    List all available categories for the shop.
    - Shows only non-paused categories.
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = CategorySerializer

    def get_queryset(self):
        return Category.objects.filter(paused=False)

class ProductListView(generics.ListAPIView):
    """
    List all available products for the shop with category filtering.
    - Shows only non-paused products from non-paused categories.
    - Filters by category if 'category' query parameter is provided (e.g., ?category=1).
    - 'All' is implied when no category is specified.
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ProductListSerializer

    def get_queryset(self):
        queryset = Product.objects.filter(paused=False, category__paused=False)
        category_id = self.request.query_params.get('category', None)
        if category_id and category_id != 'all':
            queryset = queryset.filter(category_id=category_id)
        return queryset

class PurchaseView(generics.GenericAPIView):
    """
    Process a product purchase.
    - Deducts coins from the user's wallet and records the purchase.
    - Returns file_url if available.
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = PurchaseSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        user = request.user
        product = serializer.validated_data['product']
        wallet = serializer.validated_data['wallet']

        if wallet.remove_coins(product.price):
            transaction = Transaction.objects.create(
                wallet=wallet,
                amount=product.price,
                transaction_type='SHOP_REDEMPTION',
                product_id=product.id,
                status='COMPLETED',
                description=f'Purchase of {product.name}'
            )
            purchase = UserPurchase.objects.create(
                user=user,
                product=product,
                transaction_id=transaction
            )
            product.sales += 1
            product.save(update_fields=['sales'])
            purchase_serializer = PurchaseDetailSerializer(product)
            return Response({
                "message": f"Purchase successful! You bought the {product.name}.",
                "download": purchase_serializer.data.get('file_url')
            }, status=status.HTTP_200_OK)
        return Response({"error": "Purchase failed due to insufficient balance."}, status=status.HTTP_400_BAD_REQUEST)
