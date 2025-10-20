# boiya_digital_wallet/urls.py
from django.contrib import admin
from django.urls import path, include
from rest_framework_simplejwt.views import TokenRefreshView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/users/', include('apps.users.urls')),
    path('api/raw/', include('apps.raw.urls')),
    path('api/admin-api/', include('apps.admin_api.urls')),
    path('shop/', include('apps.shop.urls')),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
]
