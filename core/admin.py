from django.contrib import admin
from django.utils.html import format_html
from django.db.models import Sum, Count
from .models import (
    RechargeTransaction, UserBalance, WithdrawalTransaction,
    Product, UserInvestment, ProductTransaction,
    Task, UserTask, UserCheckin, SavedAccount,
    ReferralCode, UserReferral, TeamMember, ReferralCommission,
)


# ─────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────

def status_badge(status, label=None):
    """Return a coloured HTML badge for a status string."""
    label = label or status.replace('_', ' ').title()
    colors = {
        'success': '#16a34a', 'completed': '#16a34a', 'active': '#16a34a',
        'pending': '#d97706', 'in_progress': '#2563eb', 'processing': '#2563eb',
        'failed': '#dc2626', 'cancelled': '#6b7280', 'expired': '#6b7280',
    }
    bg = colors.get(status, '#6b7280')
    return format_html(
        '<span style="background:{};color:#fff;padding:2px 10px;'
        'border-radius:12px;font-size:12px;font-weight:600">{}</span>',
        bg, label,
    )


# ─────────────────────────────────────────────
#  BALANCE
# ─────────────────────────────────────────────

@admin.register(UserBalance)
class UserBalanceAdmin(admin.ModelAdmin):
    list_display = ['user', 'get_phone', 'balance_display', 'currency', 'updated_at']
    search_fields = ['user__phone_number', 'user__profile__full_name']
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['-balance']
    list_select_related = ['user']

    @admin.display(description='Phone')
    def get_phone(self, obj):
        return str(obj.user.phone_number)

    @admin.display(description='Balance')
    def balance_display(self, obj):
        color = 'green' if obj.balance > 0 else 'gray'
        return format_html('<b style="color:{}">₵ {}</b>', color, f'{obj.balance:,.2f}')


# ─────────────────────────────────────────────
#  RECHARGE TRANSACTIONS
# ─────────────────────────────────────────────

@admin.register(RechargeTransaction)
class RechargeTransactionAdmin(admin.ModelAdmin):
    list_display = [
        'reference', 'get_user_phone', 'amount_display',
        'payment_method', 'status_badge_display', 'created_at',
    ]
    list_filter = ['status', 'payment_method', 'created_at']
    search_fields = ['reference', 'paystack_reference', 'user__phone_number', 'user__profile__full_name']
    readonly_fields = [
        'id', 'reference', 'paystack_reference', 'paystack_access_code',
        'paystack_auth_url', 'created_at', 'updated_at',
    ]
    ordering = ['-created_at']
    date_hierarchy = 'created_at'
    list_select_related = ['user']

    fieldsets = (
        ('Transaction Info', {
            'fields': ('id', 'user', 'reference', 'amount', 'currency', 'payment_method', 'status', 'notes')
        }),
        ('Paystack Details', {
            'fields': ('paystack_reference', 'paystack_access_code', 'paystack_auth_url'),
            'classes': ('collapse',),
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    @admin.display(description='User Phone')
    def get_user_phone(self, obj):
        return str(obj.user.phone_number)

    @admin.display(description='Amount')
    def amount_display(self, obj):
        return format_html('<b>₵ {}</b>', f'{obj.amount:,.2f}')

    @admin.display(description='Status')
    def status_badge_display(self, obj):
        return status_badge(obj.status)


# ─────────────────────────────────────────────
#  WITHDRAWAL TRANSACTIONS
# ─────────────────────────────────────────────

@admin.register(WithdrawalTransaction)
class WithdrawalTransactionAdmin(admin.ModelAdmin):
    list_display = [
        'reference', 'get_user_phone', 'amount_display',
        'withdrawal_method', 'status_badge_display',
        'get_destination', 'created_at',
    ]
    list_filter = ['status', 'withdrawal_method', 'created_at']
    search_fields = ['reference', 'user__phone_number', 'user__profile__full_name']
    readonly_fields = ['id', 'reference', 'created_at', 'updated_at']
    ordering = ['-created_at']
    date_hierarchy = 'created_at'
    list_select_related = ['user']

    fieldsets = (
        ('Transaction Info', {
            'fields': ('id', 'user', 'reference', 'amount', 'currency', 'withdrawal_method', 'status', 'notes')
        }),
        ('Destination Details', {
            'fields': ('withdrawal_details',),
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at', 'processed_at'),
            'classes': ('collapse',),
        }),
    )

    @admin.display(description='User Phone')
    def get_user_phone(self, obj):
        return str(obj.user.phone_number)

    @admin.display(description='Amount')
    def amount_display(self, obj):
        return format_html('<b style="color:red">-₵ {}</b>', f'{obj.amount:,.2f}')

    @admin.display(description='Status')
    def status_badge_display(self, obj):
        return status_badge(obj.status)

    @admin.display(description='Destination')
    def get_destination(self, obj):
        if not obj.withdrawal_details:
            return '—'
        d = obj.withdrawal_details
        if obj.withdrawal_method == 'mobile_money':
            return f"{d.get('network', '').upper()} — {d.get('phone_number', '')}"
        return f"{d.get('bank_name', '')} — {d.get('account_number', '')}"


# ─────────────────────────────────────────────
#  PRODUCTS
# ─────────────────────────────────────────────

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'price', 'term', 'daily_earnings', 'total_earnings',
        'get_total_investors', 'created_at',
    ]
    search_fields = ['name', 'description']
    list_filter = ['created_at']
    readonly_fields = ['created_at']

    @admin.display(description='# Investors')
    def get_total_investors(self, obj):
        return UserInvestment.objects.filter(product=obj, status='active').count()


# ─────────────────────────────────────────────
#  INVESTMENTS
# ─────────────────────────────────────────────

@admin.register(UserInvestment)
class UserInvestmentAdmin(admin.ModelAdmin):
    list_display = [
        'get_user_phone', 'product', 'amount_display',
        'status_badge_display', 'purchased_at', 'expires_at',
        'get_days_left', 'get_earned',
    ]
    list_filter = ['status', 'product', 'purchased_at']
    search_fields = ['user__phone_number', 'product__name', 'transaction_reference']
    readonly_fields = ['created_at', 'updated_at', 'purchased_at']
    ordering = ['-purchased_at']
    date_hierarchy = 'purchased_at'
    list_select_related = ['user', 'product']

    @admin.display(description='User Phone')
    def get_user_phone(self, obj):
        return str(obj.user.phone_number)

    @admin.display(description='Amount')
    def amount_display(self, obj):
        return format_html('<b>₵ {}</b>', f'{obj.amount:,.2f}')

    @admin.display(description='Status')
    def status_badge_display(self, obj):
        return status_badge(obj.status)

    @admin.display(description='Days Left')
    def get_days_left(self, obj):
        try:
            remaining = obj.get_days_remaining()
        except Exception:
            remaining = 0
        if remaining <= 0:
            from django.utils.safestring import mark_safe
            return mark_safe('<span style="color:#6b7280; font-weight:500;">Expired</span>')
        elif remaining <= 3:
            from django.utils.safestring import mark_safe
            return mark_safe(f'<span style="color:#dc2626; font-weight:bold;">{remaining} days left ⚠️</span>')
        elif remaining <= 7:
            from django.utils.safestring import mark_safe
            return mark_safe(f'<span style="color:#d97706; font-weight:500;">{remaining} days left</span>')
        return f'{remaining} days'

    @admin.display(description='Earned So Far')
    def get_earned(self, obj):
        try:
            earned = obj.calculate_earned_so_far()
        except Exception:
            earned = 0
        return format_html('<span style="color:green">₵ {}</span>', f'{earned:,.2f}')


# ─────────────────────────────────────────────
#  PRODUCT TRANSACTIONS
# ─────────────────────────────────────────────

@admin.register(ProductTransaction)
class ProductTransactionAdmin(admin.ModelAdmin):
    list_display = [
        'reference', 'get_user_phone', 'product',
        'amount_display', 'payment_method', 'status_badge_display', 'created_at',
    ]
    list_filter = ['status', 'payment_method', 'created_at']
    search_fields = ['reference', 'paystack_reference', 'user__phone_number', 'product__name']
    readonly_fields = ['id', 'reference', 'paystack_reference', 'created_at', 'updated_at']
    ordering = ['-created_at']
    date_hierarchy = 'created_at'
    list_select_related = ['user', 'product']

    @admin.display(description='User Phone')
    def get_user_phone(self, obj):
        return str(obj.user.phone_number)

    @admin.display(description='Amount')
    def amount_display(self, obj):
        return format_html('<b>₵ {}</b>', f'{obj.amount:,.2f}')

    @admin.display(description='Status')
    def status_badge_display(self, obj):
        return status_badge(obj.status)


# ─────────────────────────────────────────────
#  TASKS
# ─────────────────────────────────────────────

@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = [
        'title', 'category', 'difficulty', 'reward',
        'estimated_time', 'is_active', 'get_completion_count', 'created_at',
    ]
    list_filter = ['category', 'difficulty', 'is_active']
    search_fields = ['title', 'description']
    readonly_fields = ['created_at']

    @admin.display(description='Completions Today')
    def get_completion_count(self, obj):
        from datetime import date
        return UserTask.objects.filter(task=obj, last_completed_date=date.today()).count()


@admin.register(UserTask)
class UserTaskAdmin(admin.ModelAdmin):
    list_display = [
        'get_user_phone', 'task', 'status_badge_display',
        'completed_at', 'last_completed_date',
    ]
    list_filter = ['status', 'last_completed_date', 'task__category']
    search_fields = ['user__phone_number', 'task__title']
    readonly_fields = ['created_at']
    ordering = ['-completed_at']
    date_hierarchy = 'last_completed_date'
    list_select_related = ['user', 'task']

    @admin.display(description='User Phone')
    def get_user_phone(self, obj):
        return str(obj.user.phone_number)

    @admin.display(description='Status')
    def status_badge_display(self, obj):
        return status_badge(obj.status)


# ─────────────────────────────────────────────
#  CHECK-INS
# ─────────────────────────────────────────────

@admin.register(UserCheckin)
class UserCheckinAdmin(admin.ModelAdmin):
    list_display = [
        'get_user_phone', 'last_checkin_date', 'streak',
        'total_checkins', 'get_streak_badge',
    ]
    list_filter = ['last_checkin_date']
    search_fields = ['user__phone_number']
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['-streak']
    list_select_related = ['user']

    @admin.display(description='User Phone')
    def get_user_phone(self, obj):
        return str(obj.user.phone_number)

    @admin.display(description='Streak')
    def get_streak_badge(self, obj):
        if obj.streak >= 7:
            return format_html('<span style="color:#f59e0b;font-weight:bold">🔥 {} days</span>', obj.streak)
        return f'{obj.streak} days'


# ─────────────────────────────────────────────
#  SAVED ACCOUNTS
# ─────────────────────────────────────────────

@admin.register(SavedAccount)
class SavedAccountAdmin(admin.ModelAdmin):
    list_display = [
        'get_user_phone', 'account_type', 'get_account_detail',
        'is_default', 'created_at',
    ]
    list_filter = ['account_type', 'is_default']
    search_fields = ['user__phone_number', 'phone_number', 'bank_name', 'account_number']
    readonly_fields = ['created_at']
    list_select_related = ['user']

    @admin.display(description='User Phone')
    def get_user_phone(self, obj):
        return str(obj.user.phone_number)

    @admin.display(description='Account')
    def get_account_detail(self, obj):
        if obj.account_type == 'mobile_money':
            return f'{obj.network.upper()} — {obj.phone_number}'
        return f'{obj.bank_name} — {obj.account_number}'


# ─────────────────────────────────────────────
#  REFERRALS & COMMISSIONS
# ─────────────────────────────────────────────

@admin.register(ReferralCode)
class ReferralCodeAdmin(admin.ModelAdmin):
    list_display = ['user', 'code', 'get_usage_count']
    search_fields = ['user__phone_number', 'code']
    readonly_fields = ['code']

    @admin.display(description='Times Used')
    def get_usage_count(self, obj):
        return UserReferral.objects.filter(referrer=obj.user).count()


@admin.register(UserReferral)
class UserReferralAdmin(admin.ModelAdmin):
    list_display = ['referrer', 'referred_user', 'level', 'created_at']
    list_filter = ['level', 'created_at']
    search_fields = ['referrer__phone_number', 'referred_user__phone_number']
    readonly_fields = ['created_at']
    ordering = ['-created_at']
    list_select_related = ['referrer', 'referred_user']


@admin.register(TeamMember)
class TeamMemberAdmin(admin.ModelAdmin):
    list_display = [
        'user', 'sponsor', 'position',
        'left_volume', 'right_volume', 'total_volume',
    ]
    list_filter = ['position']
    search_fields = ['user__phone_number', 'sponsor__phone_number']
    list_select_related = ['user', 'sponsor']


@admin.register(ReferralCommission)
class ReferralCommissionAdmin(admin.ModelAdmin):
    list_display = [
        'get_user', 'get_from_user', 'commission_type', 'amount_display',
        'is_paid_badge', 'created_at',
    ]
    list_filter = ['is_paid', 'commission_type', 'created_at']
    search_fields = ['user__phone_number', 'from_user__phone_number']
    readonly_fields = ['created_at']
    ordering = ['-created_at']
    date_hierarchy = 'created_at'
    list_select_related = ['user', 'from_user']

    @admin.display(description='User')
    def get_user(self, obj):
        return str(obj.user.phone_number)

    @admin.display(description='From User')
    def get_from_user(self, obj):
        if obj.from_user:
            return str(obj.from_user.phone_number)
        return '—'

    @admin.display(description='Amount')
    def amount_display(self, obj):
        return format_html('<b style="color:green">₵ {}</b>', f'{obj.amount:,.2f}')

    @admin.display(description='Paid')
    def is_paid_badge(self, obj):
        status = 'success' if obj.is_paid else 'pending'
        label = 'Paid' if obj.is_paid else 'Unpaid'
        return status_badge(status, label)