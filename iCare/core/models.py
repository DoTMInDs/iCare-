import uuid
from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.crypto import get_random_string
from datetime import timedelta


class UserBalance(models.Model):
    """Track user account balance"""
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='balance'
    )
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    currency = models.CharField(max_length=10, default='GHS')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'User Balance'
        verbose_name_plural = 'User Balances'

    def __str__(self):
        return f"{self.user.phone_number} - {self.balance} {self.currency}"

    def add_balance(self, amount):
        """Add amount to user balance"""
        self.balance += amount
        self.save(update_fields=['balance', 'updated_at'])

    def deduct_balance(self, amount):
        """Deduct amount from user balance"""
        if self.balance >= amount:
            self.balance -= amount
            self.save(update_fields=['balance', 'updated_at'])
            return True
        return False


class RechargeTransaction(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_IN_PROGRESS = 'in_progress'
    STATUS_SUCCESS = 'success'
    STATUS_FAILED = 'failed'

    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_IN_PROGRESS, 'In Progress'),
        (STATUS_SUCCESS, 'Success'),
        (STATUS_FAILED, 'Failed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='recharge_transactions'
    )
    reference = models.CharField(max_length=64, unique=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=10, default='GHS')
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_PENDING)
    payment_method = models.CharField(max_length=64, blank=True, null=True)
    notes = models.TextField(blank=True)
    
    # Paystack integration fields
    paystack_reference = models.CharField(max_length=255, blank=True, null=True, help_text='Paystack payment reference')
    paystack_access_code = models.CharField(max_length=255, blank=True, null=True, help_text='Paystack access code for payment link')
    paystack_auth_url = models.URLField(blank=True, null=True, help_text='Paystack authorization URL')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Recharge Transaction'
        verbose_name_plural = 'Recharge Transactions'

    def __str__(self):
        return f"{self.reference} - {self.amount} {self.currency} ({self.status})"

    def mark_in_progress(self):
        self.status = self.STATUS_IN_PROGRESS
        self.save(update_fields=['status', 'updated_at'])

    def mark_success(self):
        self.status = self.STATUS_SUCCESS
        self.save(update_fields=['status', 'updated_at'])

    def mark_failed(self):
        self.status = self.STATUS_FAILED
        self.save(update_fields=['status', 'updated_at'])


class WithdrawalTransaction(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_PROCESSING = 'processing'
    STATUS_COMPLETED = 'completed'
    STATUS_FAILED = 'failed'
    
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_PROCESSING, 'Processing'),
        (STATUS_COMPLETED, 'Completed'),
        (STATUS_FAILED, 'Failed'),
    ]
    
    WITHDRAWAL_METHODS = [
        ('mobile_money', 'Mobile Money'),
        ('bank_transfer', 'Bank Transfer'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='withdrawal_transactions'
    )
    reference = models.CharField(max_length=64, unique=True, blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=10, default='GHS')
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_PENDING)
    withdrawal_method = models.CharField(max_length=32, choices=WITHDRAWAL_METHODS)
    withdrawal_details = models.JSONField(default=dict, blank=True, help_text='Store withdrawal method details')
    notes = models.TextField(blank=True)
    processed_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Withdrawal Transaction'
        verbose_name_plural = 'Withdrawal Transactions'
    
    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = 'W' + timezone.now().strftime('%y%m%d%H%M%S') + get_random_string(5, '0123456789')
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.reference} - {self.amount} {self.currency} ({self.status})"
    
    def mark_processing(self):
        self.status = self.STATUS_PROCESSING
        self.save(update_fields=['status', 'updated_at'])
    
    def mark_completed(self):
        self.status = self.STATUS_COMPLETED
        self.processed_at = timezone.now()
        self.save(update_fields=['status', 'processed_at', 'updated_at'])
    
    def mark_failed(self):
        self.status = self.STATUS_FAILED
        self.save(update_fields=['status', 'updated_at'])


class Product(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='products'
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=12, decimal_places=2)
    term = models.CharField(max_length=64, blank=True, help_text='E.g. "10 days", "60 days", etc.')
    daily_earnings = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True, help_text='Daily earnings for this product')
    created_at = models.DateTimeField(auto_now_add=True)

    total_earnings = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True, help_text='Total earnings for the term')

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Product'
        verbose_name_plural = 'Products'

    def __str__(self):
        return f"{self.name} - {self.price}"  


class UserInvestment(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('active', 'Active'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='investments'
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='investments'
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='pending')
    transaction_reference = models.CharField(max_length=64, blank=True, null=True, help_text='Reference from ProductTransaction')
    purchased_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    
    class Meta:
        ordering = ['-created_at']
    
    def save(self, *args, **kwargs):
        if not self.expires_at and self.product.term:
            # Parse term string (e.g., "10 days", "60 days", "3 months")
            term_parts = self.product.term.lower().split()
            if len(term_parts) >= 2:
                value = int(term_parts[0])
                unit = term_parts[1]
                
                if 'day' in unit:
                    delta = timedelta(days=value)
                elif 'week' in unit:
                    delta = timedelta(weeks=value)
                elif 'month' in unit:
                    delta = timedelta(days=value * 30)
                else:
                    delta = timedelta(days=value)
                
                self.expires_at = timezone.now() + delta
        
        super().save(*args, **kwargs)
    
    def calculate_earned_so_far(self):
        """Calculate earnings based on elapsed time"""
        if self.status != 'active':
            return 0
        
        if not self.product.daily_earnings or not self.expires_at:
            return 0
        
        now = timezone.now()
        if now >= self.expires_at:
            return float(self.product.total_earnings) if self.product.total_earnings else 0
        
        # Calculate days elapsed
        days_elapsed = (now - self.purchased_at).total_seconds() / 86400
        earned = days_elapsed * float(self.product.daily_earnings)
        
        return min(earned, float(self.product.total_earnings or earned))
    
    def get_days_remaining(self):
        """Get remaining days for investment"""
        if not self.expires_at:
            return 0
        
        remaining = (self.expires_at - timezone.now()).total_seconds() / 86400
        return max(0, int(remaining))
    
    def get_progress_percentage(self):
        """Get progress percentage of investment term"""
        if not self.expires_at:
            return 0
        
        total_days = (self.expires_at - self.purchased_at).total_seconds() / 86400
        days_passed = (timezone.now() - self.purchased_at).total_seconds() / 86400
        
        if total_days <= 0:
            return 0
        
        percentage = (days_passed / total_days) * 100
        return min(100, max(0, int(percentage)))
    
    def __str__(self):
        return f"{self.user.phone_number} - {self.product.name} - {self.amount}"


class ProductTransaction(models.Model):
    """Track product purchase transactions"""
    STATUS_PENDING = 'pending'
    STATUS_IN_PROGRESS = 'in_progress'
    STATUS_SUCCESS = 'success'
    STATUS_FAILED = 'failed'
    
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_IN_PROGRESS, 'In Progress'),
        (STATUS_SUCCESS, 'Success'),
        (STATUS_FAILED, 'Failed'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='product_transactions'
    )
    product = models.ForeignKey(
        'Product',
        on_delete=models.CASCADE,
        related_name='transactions'
    )
    reference = models.CharField(max_length=64, unique=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=10, default='GHS')
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_PENDING)
    payment_method = models.CharField(max_length=64, blank=True, null=True)
    
    # Paystack integration fields
    paystack_reference = models.CharField(max_length=255, blank=True, null=True)
    paystack_access_code = models.CharField(max_length=255, blank=True, null=True)
    paystack_auth_url = models.URLField(blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.reference} - {self.product.name} - {self.amount}"
    
    def mark_in_progress(self):
        self.status = self.STATUS_IN_PROGRESS
        self.save(update_fields=['status', 'updated_at'])
    
    def mark_success(self):
        self.status = self.STATUS_SUCCESS
        self.save(update_fields=['status', 'updated_at'])
    
    def mark_failed(self):
        self.status = self.STATUS_FAILED
        self.save(update_fields=['status', 'updated_at'])


class SavedAccount(models.Model):
    ACCOUNT_TYPES = [
        ('mobile_money', 'Mobile Money'),
        ('bank_transfer', 'Bank Transfer'),
    ]
    
    NETWORKS = [
        ('mtn', 'MTN Mobile Money'),
        ('vodafone', 'Vodafone Cash'),
        ('airteltigo', 'AirtelTigo Money'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='saved_accounts'
    )
    account_type = models.CharField(max_length=32, choices=ACCOUNT_TYPES)
    
    # Mobile Money fields
    network = models.CharField(max_length=32, choices=NETWORKS, blank=True, null=True)
    phone_number = models.CharField(max_length=15, blank=True, null=True)
    
    # Bank Transfer fields
    bank_name = models.CharField(max_length=100, blank=True, null=True)
    account_number = models.CharField(max_length=50, blank=True, null=True)
    account_name = models.CharField(max_length=200, blank=True, null=True)
    
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-is_default', '-created_at']
        # Add unique constraints to prevent duplicates
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'account_type', 'network', 'phone_number'],
                condition=models.Q(account_type='mobile_money'),
                name='unique_mobile_money_account'
            ),
            models.UniqueConstraint(
                fields=['user', 'account_type', 'bank_name', 'account_number'],
                condition=models.Q(account_type='bank_transfer'),
                name='unique_bank_account'
            ),
        ]
    
    def clean(self):
        """Clean and validate phone number format"""
        from django.core.exceptions import ValidationError
        
        if self.account_type == 'mobile_money' and self.phone_number:
            # Remove any non-digit characters
            self.phone_number = ''.join(filter(str.isdigit, self.phone_number))
            # Remove leading 0 or 233 if present
            if self.phone_number.startswith('233'):
                self.phone_number = self.phone_number[3:]
            elif self.phone_number.startswith('0'):
                self.phone_number = self.phone_number[1:]
            # Ensure length is valid (9 digits for Ghana)
            if len(self.phone_number) != 9:
                raise ValidationError('Phone number must be 9 digits (e.g., 202739333)')
    
    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)
    
    def __str__(self):
        if self.account_type == 'mobile_money':
            return f"{self.get_network_display()} - {self.phone_number}"
        return f"{self.bank_name} - {self.account_number}"



class Task(models.Model):
    CATEGORY_CHOICES = [
        ('daily', 'Daily Task'),
        ('one-time', 'One-Time Task'),
        ('social', 'Social Task'),
        ('surveys', 'Survey'),
    ]
    
    DIFFICULTY_CHOICES = [
        ('easy', 'Easy'),
        ('medium', 'Medium'),
        ('hard', 'Hard'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)
    description = models.TextField()
    instructions = models.TextField(blank=True, null=True)
    steps = models.JSONField(default=list, blank=True)
    task_url = models.URLField(blank=True, null=True)
    reward = models.DecimalField(max_digits=10, decimal_places=2)
    category = models.CharField(max_length=32, choices=CATEGORY_CHOICES, default='one-time')
    difficulty = models.CharField(max_length=16, choices=DIFFICULTY_CHOICES, default='easy')
    estimated_time = models.CharField(max_length=64, blank=True, help_text='E.g., "5 minutes"')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.title} - ₵{self.reward}"


class UserTask(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='completed_tasks'
    )
    task = models.ForeignKey(Task, on_delete=models.CASCADE)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='pending')
    completed_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ['user', 'task']
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.user.email} - {self.task.title} - {self.status}"


class UserCheckin(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='checkin'
    )
    streak = models.IntegerField(default=0)
    last_checkin_date = models.DateField(blank=True, null=True)
    total_checkins = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.user.email} - Streak: {self.streak}"
    

class ReferralCode(models.Model):
    """Referral code for each user"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='referral_code'
    )
    code = models.CharField(max_length=20, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.user.phone_number} - {self.code}"


class UserReferral(models.Model):
    """Track who referred whom"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    referrer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='referred_users'
    )
    referred_user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='referred_by'
    )
    level = models.IntegerField(default=1, help_text="Referral level (1 = direct, 2 = indirect, etc.)")
    commission_earned = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['level', '-created_at']
    
    def __str__(self):
        return f"{self.referrer.phone_number} -> {self.referred_user.phone_number} (Level {self.level})"


class TeamMember(models.Model):
    """Team structure with binary tree"""
    POSITION_CHOICES = [
        ('left', 'Left'),
        ('right', 'Right'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='team_member'
    )
    sponsor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='downline_members'
    )
    position = models.CharField(max_length=10, choices=POSITION_CHOICES, blank=True, null=True)
    left_child = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='parent_left'
    )
    right_child = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='parent_right'
    )
    left_volume = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    right_volume = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_volume = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)
    joined_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-joined_at']
    
    def __str__(self):
        return f"{self.user.phone_number} - Sponsor: {self.sponsor.phone_number if self.sponsor else 'None'}"
    
    def update_volumes(self):
        """Update team volumes"""
        self.left_volume = self.calculate_team_volume(self.left_child)
        self.right_volume = self.calculate_team_volume(self.right_child)
        self.total_volume = self.left_volume + self.right_volume
        self.save(update_fields=['left_volume', 'right_volume', 'total_volume', 'updated_at'])
        
        # Update parent volumes
        if self.sponsor:
            try:
                parent_member = TeamMember.objects.get(user=self.sponsor)
                parent_member.update_volumes()
            except TeamMember.DoesNotExist:
                pass
    
    def calculate_team_volume(self, child_user):
        """Calculate total volume for a child team"""
        if not child_user:
            return 0
        
        try:
            child_member = TeamMember.objects.get(user=child_user)
            return child_member.total_volume + (child_member.get_personal_volume())
        except TeamMember.DoesNotExist:
            return 0
    
    def get_personal_volume(self):
        """Get user's personal investment volume"""
        investments = UserInvestment.objects.filter(
            user=self.user,
            status='active'
        ).aggregate(total=models.Sum('amount'))['total'] or 0
        return float(investments)


class ReferralCommission(models.Model):
    """Track commissions earned from referrals"""
    COMMISSION_TYPES = [
        ('direct', 'Direct Commission'),
        ('binary', 'Binary Commission'),
        ('matching', 'Matching Bonus'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='commissions'
    )
    from_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='given_commissions',
        null=True,
        blank=True
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    commission_type = models.CharField(max_length=20, choices=COMMISSION_TYPES)
    level = models.IntegerField(default=1)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_paid = models.BooleanField(default=False)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.user.phone_number} - {self.commission_type} - ₵{self.amount}"