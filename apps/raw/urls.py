# apps/raw/urls.py
from django.urls import path
from .views import WalletBalanceView, TransferView, CompleteTaskView, TaskListView

urlpatterns = [
    path('balance/', WalletBalanceView.as_view(), name='wallet_balance'),
    path('transfer/', TransferView.as_view(), name='transfer'),
    path('complete-task/', CompleteTaskView.as_view(), name='complete_task'),
    path('tasks/', TaskListView.as_view(), name='task_list'),
]