from django.contrib import admin
from .models import (
    RechargeTransaction, UserBalance, WithdrawalTransaction,
      Product, UserInvestment, ProductTransaction, Task, UserTask, UserCheckin, SavedAccount
    )

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

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['name', 'description', 'price', 'term', 'daily_earnings', 'total_earnings', 'created_at']
    search_fields = ['name', 'description']
    readonly_fields = ['created_at']

@admin.register(UserInvestment)
class UserInvestmentAdmin(admin.ModelAdmin):
    list_display = ['user', 'product', 'amount', 'purchased_at', 'expires_at', 'status']
    list_filter = ['status', 'purchased_at', 'expires_at']
    search_fields = ['user__phone_number', 'product__name']
    readonly_fields = ['created_at', 'updated_at']

@admin.register(ProductTransaction)
class ProductTransactionAdmin(admin.ModelAdmin):
    list_display = ['reference', 'user', 'product', 'amount', 'payment_method', 'status', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['reference', 'user__phone_number', 'product__name']
    readonly_fields = ['id', 'reference', 'created_at', 'updated_at']
    ordering = ['-created_at']


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ['title', 'description', 'instructions', 'task_url', 'reward', 'steps', 'category', 'estimated_time', 'created_at']
    search_fields = ['title', 'description']
    readonly_fields = ['created_at']

@admin.register(UserTask)
class UserTaskAdmin(admin.ModelAdmin):
    list_display = ['user', 'task', 'status', 'completed_at']
    list_filter = ['status', 'completed_at']
    search_fields = ['user__phone_number', 'task__title']
    readonly_fields = ['created_at']

@admin.register(UserCheckin)
class UserCheckinAdmin(admin.ModelAdmin):
    list_display = ['user', 'last_checkin_date', 'streak', 'total_checkins']
    list_filter = ['last_checkin_date']
    search_fields = ['user__phone_number']
    readonly_fields = ['created_at', 'updated_at']