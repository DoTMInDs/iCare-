from celery import shared_task
from django.core.mail import send_mail
from django.conf import settings
from .models import User
import logging

logger = logging.getLogger(__name__)

@shared_task
def send_welcome_email(user_id):
    """Send welcome email asynchronously"""
    try:
        user = User.objects.get(id=user_id)
        if user.profile.email:
            subject = 'Welcome to iCare!'
            message = f"""
            Hi {user.profile.full_name or user.phone_number},
            
            Welcome to iCare! You're now part of our investment community.
            
            Your Referral Code: {user.referral_code.code if hasattr(user, 'referral_code') else 'N/A'}
            Share it with friends to earn commissions!
            
            Get started: https://yourdomain.com/home
            
            Best regards,
            iCare Team
            """
            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL,
                [user.profile.email],
                fail_silently=False,
            )
            return f"Welcome email sent to {user.profile.email}"
    except Exception as e:
        logger.error(f"Failed to send welcome email: {e}")
        return str(e)
