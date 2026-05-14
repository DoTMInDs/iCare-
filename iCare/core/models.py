import uuid
from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.crypto import get_random_string


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