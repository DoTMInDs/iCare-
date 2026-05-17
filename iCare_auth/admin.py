from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html
from django.db.models import Sum
from django.urls import reverse
from django.utils.safestring import mark_safe
from .models import User, UserProfile


class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    verbose_name_plural = 'Profile'
    fk_name = 'user'
    fields = ['full_name', 'email', 'address', 'date_of_birth']
    extra = 0


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    inlines = [UserProfileInline]

    list_display = [
        'phone_number', 'get_full_name', 'email',
        'is_active', 'is_staff', 'date_joined',
        'get_balance', 'get_total_invested', 'get_total_recharged', 'get_total_withdrawn',
    ]
    list_filter = ['is_active', 'is_staff', 'is_superuser', 'date_joined']
    search_fields = ['phone_number', 'email', 'profile__full_name']
    ordering = ['-date_joined']
    readonly_fields = ['date_joined', 'last_login', 'get_balance', 'get_stats_summary']

    fieldsets = (
        ('Account', {'fields': ('phone_number', 'email', 'password')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Dates', {'fields': ('date_joined', 'last_login')}),
        ('Financial Summary', {'fields': ('get_balance', 'get_stats_summary')}),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('phone_number', 'email', 'password1', 'password2', 'is_staff', 'is_active'),
        }),
    )

    # ---------- computed columns ----------

    @admin.display(description='Full Name')
    def get_full_name(self, obj):
        try:
            return obj.profile.full_name or '—'
        except UserProfile.DoesNotExist:
            return '—'

    @admin.display(description='Wallet Balance')
    def get_balance(self, obj):
        try:
            bal = obj.balance.balance
            color = 'green' if bal > 0 else 'gray'
            return format_html('<b style="color:{}">₵ {}</b>', color, f'{bal:,.2f}')
        except Exception:
            return '₵ 0.00'

    @admin.display(description='Total Invested')
    def get_total_invested(self, obj):
        from core.models import UserInvestment
        total = UserInvestment.objects.filter(user=obj).aggregate(s=Sum('amount'))['s'] or 0
        return f'₵ {total:,.2f}'

    @admin.display(description='Total Recharged')
    def get_total_recharged(self, obj):
        from core.models import RechargeTransaction
        total = RechargeTransaction.objects.filter(user=obj, status='success').aggregate(s=Sum('amount'))['s'] or 0
        return f'₵ {total:,.2f}'

    @admin.display(description='Total Withdrawn')
    def get_total_withdrawn(self, obj):
        from core.models import WithdrawalTransaction
        total = WithdrawalTransaction.objects.filter(user=obj, status='completed').aggregate(s=Sum('amount'))['s'] or 0
        return f'₵ {total:,.2f}'

    @admin.display(description='Stats Summary')
    def get_stats_summary(self, obj):
        from core.models import UserInvestment, RechargeTransaction, WithdrawalTransaction, UserTask
        investments = UserInvestment.objects.filter(user=obj).count()
        recharges = RechargeTransaction.objects.filter(user=obj).count()
        withdrawals = WithdrawalTransaction.objects.filter(user=obj).count()
        tasks = UserTask.objects.filter(user=obj, status='completed').count()
        return format_html(
            '<table style="border-collapse:collapse">'
            '<tr><td style="padding:4px 12px 4px 0"><b>Investments:</b></td><td>{}</td></tr>'
            '<tr><td style="padding:4px 12px 4px 0"><b>Recharges:</b></td><td>{}</td></tr>'
            '<tr><td style="padding:4px 12px 4px 0"><b>Withdrawals:</b></td><td>{}</td></tr>'
            '<tr><td style="padding:4px 12px 4px 0"><b>Tasks completed:</b></td><td>{}</td></tr>'
            '</table>',
            investments, recharges, withdrawals, tasks,
        )


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'full_name', 'email', 'address', 'date_of_birth', 'created_at']
    search_fields = ['user__phone_number', 'full_name', 'email']
    readonly_fields = ['created_at', 'updated_at']
    list_select_related = ['user']