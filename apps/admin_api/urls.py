from django.urls import path
from .views import StudentManagementListView, StudentStatusUpdateView, StudentDeleteView, AdminLoginView

urlpatterns = [
    path('login/', AdminLoginView.as_view(), name='admin_login'),
    path('students/', StudentManagementListView.as_view(), name='student_management_list'),
    path('students/<int:id>/status/', StudentStatusUpdateView.as_view(), name='student_status_update'),
    path('students/<int:id>/', StudentDeleteView.as_view(), name='student_delete'),
]