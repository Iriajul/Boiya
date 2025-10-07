# apps/raw/serializers.py
from rest_framework import serializers
from .models import Wallet, Transaction, Task

class WalletSerializer(serializers.ModelSerializer):
    class Meta:
        model = Wallet
        fields = ['balance', 'boiya_id', 'last_login_bonus']
        read_only_fields = ['boiya_id', 'last_login_bonus']

class TransferSerializer(serializers.Serializer):
    recipient_boiya_id = serializers.CharField()
    amount = serializers.DecimalField(min_value=0.01, max_digits=15, decimal_places=2)

    def validate(self, data):
        try:
            recipient_wallet = Wallet.objects.get(boiya_id=data['recipient_boiya_id'])
        except Wallet.DoesNotExist:
            raise serializers.ValidationError("Invalid Booya ID")
        if recipient_wallet == self.context['request'].user.wallet:
            raise serializers.ValidationError("Cannot transfer to yourself")
        return data

class TransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transaction
        fields = ['amount', 'transaction_type', 'recipient_wallet', 'description', 'created_at']
        read_only_fields = ['created_at']

class TaskSerializer(serializers.ModelSerializer):
    class Meta:
        model = Task
        fields = ['id', 'title', 'description', 'reward_coins', 'is_active']

class TaskCompletionSerializer(serializers.Serializer):
    task_id = serializers.IntegerField()