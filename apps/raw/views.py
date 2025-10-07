# apps/raw/views.py
from rest_framework import generics, permissions
from rest_framework.response import Response
from .models import Wallet, Transaction, Task, UserTaskCompletion
from .serializers import WalletSerializer, TransferSerializer, TaskCompletionSerializer, TaskSerializer

class WalletBalanceView(generics.RetrieveAPIView):
    serializer_class = WalletSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user.wallet

class TransferView(generics.GenericAPIView):
    serializer_class = TransferSerializer
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        sender_wallet = request.user.wallet
        recipient_wallet = Wallet.objects.get(boiya_id=serializer.validated_data['recipient_boiya_id'])
        amount = serializer.validated_data['amount']

        sender_wallet.subtract_coins(amount)
        recipient_wallet.add_coins(amount)

        Transaction.objects.create(
            wallet=sender_wallet,
            amount=amount,
            transaction_type='TRANSFER_SEND',
            recipient_wallet=recipient_wallet
        )
        Transaction.objects.create(
            wallet=recipient_wallet,
            amount=amount,
            transaction_type='TRANSFER_RECEIVE',
            recipient_wallet=sender_wallet
        )

        return Response({"detail": "Transfer successful", "new_balance": sender_wallet.balance})

class CompleteTaskView(generics.GenericAPIView):
    serializer_class = TaskCompletionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        task_id = serializer.validated_data['task_id']
        try:
            task = Task.objects.get(id=task_id, is_active=True)
        except Task.DoesNotExist:
            return Response({"detail": "Invalid or inactive task"}, status=400)

        if UserTaskCompletion.objects.filter(user=request.user, task=task).exists():
            return Response({"detail": "Task already completed"}, status=400)

        UserTaskCompletion.objects.create(user=request.user, task=task)
        wallet = request.user.wallet
        wallet.add_coins(task.reward_coins)
        Transaction.objects.create(
            wallet=wallet,
            amount=task.reward_coins,
            transaction_type='TASK_REWARD',
            description=f"Completed task: {task.title}"
        )

        return Response({"detail": "Task completed", "reward": task.reward_coins, "new_balance": wallet.balance})

class TaskListView(generics.ListAPIView):
    serializer_class = TaskSerializer
    permission_classes = [permissions.IsAuthenticated]
    queryset = Task.objects.filter(is_active=True)