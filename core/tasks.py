from celery import shared_task
from django.conf import settings
from decimal import Decimal
from iCare_auth.models import User
from core.models import (
    UserBalance, ReferralCommission, TeamMember, 
    UserReferral, UserInvestment
)
from webpush import send_user_notification
from django.db import transaction
from django.db import models
import logging

logger = logging.getLogger(__name__)

@shared_task
def process_referral_commission(investment_id):
    """Process referral commission asynchronously"""
    try:
        investment = UserInvestment.objects.get(id=investment_id)
        investor = investment.user
        
        # Get all referrers (up to level 10)
        referrals = UserReferral.objects.filter(
            referred_user=investor
        ).order_by('level')
        
        for referral in referrals:
            commission_rate = 0
            if referral.level == 1:
                commission_rate = Decimal('0.10')  # 10%
            elif referral.level == 2:
                commission_rate = Decimal('0.05')  # 5%
            elif referral.level == 3:
                commission_rate = Decimal('0.03')  # 3%
            elif referral.level >= 4:
                commission_rate = Decimal('0.01')  # 1%
            
            commission_amount = investment.amount * commission_rate
            
            if commission_amount > 0:
                with transaction.atomic():
                    # Create commission record
                    ReferralCommission.objects.create(
                        user=referral.referrer,
                        from_user=investor,
                        amount=commission_amount,
                        commission_type='direct',
                        level=referral.level,
                        description=f"{commission_rate*100}% commission from {investor.phone_number}'s investment of ₵{investment.amount}"
                    )
                    
                    # Add to user's balance
                    balance, _ = UserBalance.objects.get_or_create(user=referral.referrer)
                    balance.add_balance(commission_amount)
                    
                    # Send notification to referrer
                    send_commission_notification.delay(
                        referral.referrer.id, 
                        commission_amount,
                        investment.amount,
                        referral.level
                    )
        
        return f"Commissions processed for investment {investment_id}"
    except Exception as e:
        logger.error(f"Failed to process commission: {e}")
        return str(e)
    

@shared_task
def update_team_volumes(user_id):
    """Update team volumes asynchronously"""
    try:
        team_member = TeamMember.objects.get(user_id=user_id)
        
        # Calculate volumes recursively
        def calculate_volume(member):
            if not member:
                return 0
            left = calculate_volume(member.left_child) if member.left_child else 0
            right = calculate_volume(member.right_child) if member.right_child else 0
            
            # Get personal volume from investments
            personal_volume = UserInvestment.objects.filter(
                user=member.user,
                status='active'
            ).aggregate(total=models.Sum('amount'))['total'] or 0
            
            total = left + right + float(personal_volume)
            return total
        
        # Calculate and update volumes
        total_volume = calculate_volume(team_member)
        
        # Update parent volumes
        if team_member.sponsor:
            update_team_volumes.delay(team_member.sponsor.id)
        
        return f"Volumes updated for user {user_id}"
    except Exception as e:
        logger.error(f"Failed to update team volumes: {e}")
        return str(e)

@shared_task
def send_commission_notification(user_id, amount, investment_amount, level):
    """Send commission notification to user"""
    try:
        user = User.objects.get(id=user_id)
        # Send push notification or SMS about commission earned
        print(f"🔔 {user.phone_number} earned ₵{amount} commission from level {level} investment of ₵{investment_amount}")
        
        # Send push notification
        payload = {
            'head': 'Commission Earned! 💰',
            'body': f'You earned ₵{amount} commission from a level {level} investment of ₵{investment_amount}!',
            'icon': '/static/imgs/icons/icon-192x192.png',
            'url': '/core/account/balance/'
        }
        send_user_notification(user=user, payload=payload, ttl=86400)
        
        return f"Notification sent to {user.phone_number}"
    except Exception as e:
        logger.error(f"Failed to send notification: {e}")
        return str(e)


@shared_task
def send_withdrawal_notification(user_id, amount):
    """Send withdrawal completion notification"""
    try:
        user = User.objects.get(id=user_id)
        print(f"✅ {user.phone_number} - Your withdrawal of ₵{amount} has been processed!")
        
        # Send push notification
        payload = {
            'head': 'Withdrawal Successful! ✅',
            'body': f'Your withdrawal of ₵{amount} has been processed.',
            'icon': '/static/imgs/icons/icon-192x192.png',
            'url': '/core/withdrawal-records/'
        }
        send_user_notification(user=user, payload=payload, ttl=86400)
        
        return f"Withdrawal notification sent to {user.phone_number}"
    except Exception as e:
        return str(e)


@shared_task
def send_recharge_notification(user_id, amount):
    """Send recharge success notification"""
    try:
        user = User.objects.get(id=user_id)
        
        # Send push notification
        payload = {
            'head': 'Recharge Successful! 💳',
            'body': f'Your wallet has been credited with ₵{amount}.',
            'icon': '/static/imgs/icons/icon-192x192.png',
            'url': '/core/account/balance/'
        }
        send_user_notification(user=user, payload=payload, ttl=86400)
        
        return f"Recharge notification sent to {user.phone_number}"
    except Exception as e:
        return str(e)


@shared_task
def send_product_purchase_notification(user_id, product_name):
    """Send product purchase success notification"""
    try:
        user = User.objects.get(id=user_id)
        
        # Send push notification
        payload = {
            'head': 'Purchase Successful! 🛍️',
            'body': f'You successfully purchased the {product_name} package. It is now active!',
            'icon': '/static/imgs/icons/icon-192x192.png',
            'url': '/core/my-investments/'
        }
        send_user_notification(user=user, payload=payload, ttl=86400)
        
        return f"Product purchase notification sent to {user.phone_number}"
    except Exception as e:
        return str(e)
    

@shared_task
def calculate_daily_binary_bonus():
    """Scheduled task to calculate binary bonuses daily"""
    from django.db.models import Sum
    
    active_members = TeamMember.objects.filter(is_active=True)
    
    for member in active_members:
        weak_leg = min(member.left_volume, member.right_volume)
        binary_bonus = weak_leg * Decimal('0.10')
        
        if binary_bonus > 0:
            with transaction.atomic():
                # Create commission record
                ReferralCommission.objects.create(
                    user=member.user,
                    amount=binary_bonus,
                    commission_type='binary',
                    description=f"Daily binary bonus from weak leg volume of ₵{weak_leg}"
                )
                
                # Add to user's balance
                balance, _ = UserBalance.objects.get_or_create(user=member.user)
                balance.add_balance(binary_bonus)
                
                # Reset volumes for next day (optional)
                member.left_volume = 0
                member.right_volume = 0
                member.save()
    
    return "Daily binary bonuses calculated"


@shared_task
def send_bulk_notification(user_ids, subject, message):
    """Send bulk notifications to multiple users"""
    from django.core.mail import send_mass_mail
    
    emails = []
    for user_id in user_ids:
        try:
            user = User.objects.get(id=user_id)
            if user.email:
                emails.append((
                    subject,
                    message,
                    settings.DEFAULT_FROM_EMAIL,
                    [user.email]
                ))
        except User.DoesNotExist:
            continue
    
    if emails:
        send_mass_mail(emails, fail_silently=False)
    
    return f"Sent {len(emails)} notifications"
