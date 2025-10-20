# apps/shop/serializers.py
from rest_framework import serializers
from apps.admin_api.models import Product, Category
from apps.raw.models import Wallet
from apps.users.models import User
from apps.shop.models import UserPurchase

class CategorySerializer(serializers.ModelSerializer):
    """
    Serializer for listing categories in the shop.
    - Includes only non-paused categories.
    """
    class Meta:
        model = Category
        fields = ['id', 'name']

class ProductListSerializer(serializers.ModelSerializer):
    """
    Serializer for listing products in the shop.
    - Includes category name for filtering.
    - Only shows active (non-paused) products from active categories.
    - file_url is excluded until purchase.
    """
    category_name = serializers.CharField(source='category.name')

    class Meta:
        model = Product
        fields = ['id', 'name', 'price', 'thumbnail_url', 'description', 'category_name']

class PurchaseDetailSerializer(serializers.ModelSerializer):
    """
    Serializer for purchase response, including file_url if available.
    """
    class Meta:
        model = Product
        fields = ['id', 'name', 'price', 'thumbnail_url', 'description', 'file_url']

class PurchaseSerializer(serializers.Serializer):
    """
    Serializer for processing a purchase.
    - Validates user balance and creates a purchase record.
    """
    product_id = serializers.IntegerField()

    def validate(self, data):
        user = self.context['request'].user
        product_id = data.get('product_id')
        try:
            product = Product.objects.get(id=product_id, paused=False, category__paused=False)
            wallet = user.wallet
            if not wallet or wallet.balance < product.price:
                raise serializers.ValidationError("Insufficient balance.")
            data['product'] = product
            data['wallet'] = wallet
            return data
        except Product.DoesNotExist:
            raise serializers.ValidationError("Product not found or not available.")