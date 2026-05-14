from django.contrib import admin
from .models import RechargeTransaction, UserBalance, WithdrawalTransaction

@admin.register(UserBalance)
class UserBalanceAdmin(admin.ModelAdmin):
    list_display = ['user', 'balance', 'currency', 'updated_at']
    search_fields = ['user__phone_number']
    readonly_fields = ['created_at', 'updated_at']

@admin.register(RechargeTransaction)
class RechargeTransactionAdmin(admin.ModelAdmin):
    list_display = ['reference', 'user', 'amount', 'status', 'created_at', 'paystack_reference']
    list_filter = ['status', 'created_at', 'payment_method']
    search_fields = ['reference', 'paystack_reference', 'user__phone_number']
    readonly_fields = ['id', 'reference', 'paystack_reference', 'paystack_access_code', 'created_at', 'updated_at']
    ordering = ['-created_at']

@admin.register(WithdrawalTransaction)
class WithdrawalTransactionAdmin(admin.ModelAdmin):
    list_display = ['reference', 'user', 'amount', 'status', 'created_at']
    list_filter = ['status', 'created_at', 'withdrawal_method']
    search_fields = ['reference', 'user__phone_number']
    readonly_fields = ['id', 'reference', 'created_at', 'updated_at']
    ordering = ['-created_at']
