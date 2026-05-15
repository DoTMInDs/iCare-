from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from .models import UserProfile
from core.models import (ReferralCode, UserReferral, TeamMember)
from core.views import generate_referral_code

User = get_user_model()

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """Create a UserProfile when a new User is created"""
    if created:
        UserProfile.objects.create(user=instance)


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    """Save the UserProfile when the User is saved"""
    try:
        instance.profile.save()
    except UserProfile.DoesNotExist:
        # If profile doesn't exist, create it
        UserProfile.objects.create(user=instance)


# @receiver(post_save, sender=User)
# def create_referral_code(sender, instance, created, **kwargs):
#     if created:
#         # Create referral code
#         ReferralCode.objects.create(
#             user=instance,
#             code=generate_referral_code()
#         )
        
#         # Create team member record
#         TeamMember.objects.create(user=instance)


@receiver(post_save, sender=User)
def create_user_related_records(sender, instance, created, **kwargs):
    """Create referral code and team member when user is created"""
    if created:
        # Create referral code
        ReferralCode.objects.get_or_create(
            user=instance,
            defaults={'code': generate_referral_code()}
        )
        
        # Create team member record - use get_or_create to avoid duplicate
        TeamMember.objects.get_or_create(
            user=instance,
            defaults={
                'sponsor': None,
                'position': None,
                'left_volume': 0,
                'right_volume': 0,
                'total_volume': 0,
                'is_active': True
            }
        )