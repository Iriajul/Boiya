# apps/shop/urls.py
from django.urls import path
from .views import ProductListView, PurchaseView, CategoryListView

urlpatterns = [
    path('categories/', CategoryListView.as_view(), name='shop-categories'),
    path('products/', ProductListView.as_view(), name='shop-products'),
    path('purchase/', PurchaseView.as_view(), name='shop-purchase'),
]