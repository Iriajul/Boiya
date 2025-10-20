from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from .views import LoginView, RegisterView, VerifyOtpLoginView, LogoutView, ForgotPasswordView, VerifyOtpView, ResetPasswordView, SendView, ReceiveView, TransactionHistoryView, GradeListView, CurrentBalanceView, ProfileView, TwoFactorAuthSetupView, TwoFactorAuthValidateView

urlpatterns = [
    path('register/', RegisterView.as_view(), name='user_register'),
    path('login/', LoginView.as_view(), name='user_login'),
    path('forgot-password/', ForgotPasswordView.as_view(), name='forgot_password'),
    path('verify-otp/', VerifyOtpView.as_view(), name='verify_otp'),
    path('reset-password/', ResetPasswordView.as_view(), name='reset_password'),
    path('logout/', LogoutView.as_view(), name='user_logout'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('send/', SendView.as_view(), name='user_send'),
    path('receive/', ReceiveView.as_view(), name='user_receive'),
    path('profile/transactions/', TransactionHistoryView.as_view(), name='transaction-history'),
    path('grade-list/', GradeListView.as_view(), name='grade-list'),
    path('current-balance/', CurrentBalanceView.as_view(), name='current-balance'),
    path('profile/', ProfileView.as_view(), name='profile'),
    path('profile/2fa/setup/', TwoFactorAuthSetupView.as_view(), name='two-factor-auth-setup'),
    path('profile/2fa/validate/', TwoFactorAuthValidateView.as_view(), name='two-factor-auth-validate'),
    path('login/verify-otp/', VerifyOtpLoginView.as_view(), name='login-verify-otp'),
]