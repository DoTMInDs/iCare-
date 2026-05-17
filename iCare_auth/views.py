from django.shortcuts import render,redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from core.models import (
    UserBalance, RechargeTransaction, WithdrawalTransaction, SavedAccount,
    ReferralCode, UserReferral, TeamMember
)
from django.contrib.auth.decorators import login_required
from .models import UserProfile
from django.views.decorators.http import require_http_methods
from .forms import UserProfileForm, CustomPasswordChangeForm, PhoneRegistrationForm
from django.db.models import Sum
from core.models import UserInvestment
from iCare_auth.tasks import (
    send_welcome_email
)

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from webpush import send_user_notification
import json
from decimal import Decimal

# Create your views here.
def process_referral_on_signup(new_user, referral_code):
    """Helper function to process referral during signup - only updates relationships, doesn't create duplicates"""
    if not referral_code or referral_code.strip() == '':
        return
    
    try:
        # Try to find the referral code
        referrer_code = ReferralCode.objects.get(code=referral_code.upper().strip())
        
        # Don't allow self-referral
        if referrer_code.user == new_user:
            return
        
        # Check if user already has a referrer (from UserReferral model)
        if UserReferral.objects.filter(referred_user=new_user).exists():
            return
        
        # Get the existing TeamMember record for new_user (created by signal)
        try:
            team_member = TeamMember.objects.get(user=new_user)
        except TeamMember.DoesNotExist:
            # This shouldn't happen if signal is working, but just in case
            team_member = TeamMember.objects.create(
                user=new_user,
                sponsor=None,
                position=None
            )
        
        # Create referral record (Level 1)
        UserReferral.objects.create(
            referrer=referrer_code.user,
            referred_user=new_user,
            level=1
        )
        
        # Update the existing TeamMember record (don't create new one)
        team_member.sponsor = referrer_code.user
        team_member.save()
        
        # Update sponsor's team structure
        try:
            # Get sponsor's existing TeamMember record
            sponsor_team = TeamMember.objects.get(user=referrer_code.user)
            
            # Find available position
            if not sponsor_team.left_child:
                sponsor_team.left_child = new_user
                sponsor_team.save()
                team_member.position = 'left'
                team_member.save()
            elif not sponsor_team.right_child:
                sponsor_team.right_child = new_user
                sponsor_team.save()
                team_member.position = 'right'
                team_member.save()
            # If both positions filled, place in left by default (or you can implement overflow logic)
            else:
                team_member.position = 'left'
                team_member.save()
            
            # Update volumes
            sponsor_team.update_volumes()
            
        except TeamMember.DoesNotExist:
            # Sponsor doesn't have a TeamMember record yet - create one
            sponsor_team = TeamMember.objects.create(
                user=referrer_code.user,
                sponsor=None,
                position=None
            )
            
            # Place in left position
            sponsor_team.left_child = new_user
            sponsor_team.save()
            team_member.position = 'left'
            team_member.save()
        
        # Process upline referrals (Level 2, 3, etc. up to level 10)
        current_referrer = referrer_code.user
        for level in range(2, 11):
            try:
                # Check if current referrer has a referrer
                upline_referral = UserReferral.objects.get(referred_user=current_referrer)
                upline_user = upline_referral.referrer
                
                # Check if this referral already exists
                if not UserReferral.objects.filter(referrer=upline_user, referred_user=new_user, level=level).exists():
                    UserReferral.objects.create(
                        referrer=upline_user,
                        referred_user=new_user,
                        level=level
                    )
                current_referrer = upline_user
            except UserReferral.DoesNotExist:
                break
                
    except ReferralCode.DoesNotExist:
        # Invalid referral code - just continue without creating referral
        pass
    except Exception as e:
        # Log error but don't prevent signup
        print(f"Referral processing error: {e}")
        pass

def signup(request):
    if request.method == 'POST':
        form = PhoneRegistrationForm(request.POST)
        if form.is_valid():
            # Save the form and get the created user
            new_user = form.save()  # Signal automatically creates TeamMember and ReferralCode
            
            # Send welcome notifications asynchronously
            send_welcome_email.delay(new_user.id)
            messages.success(request, 'Account created successfully!')
            
            # Process referral AFTER user is saved
            # Get referral code from POST (visible field) or GET (URL param)
            referral_code = request.POST.get('ref', '').strip()
            if not referral_code:
                referral_code = request.GET.get('ref', '').strip()
            
            if referral_code:
                process_referral_on_signup(new_user, referral_code)
            
            # Log the user in immediately after signup
            login(request, new_user, backend='iCare_auth.backends.PhoneNumberBackend')
            
            return redirect('home')
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"Error: {error}")
    else:
        form = PhoneRegistrationForm()
    
    # Get referral code from URL parameter for the form
    referral_code = request.GET.get('ref', '')
    
    return render(request, 'auth/signup.html', {
        'form': form, 
        'referral_code': referral_code
    })


def login_view(request):
    if request.method == 'POST':
        phone_number = request.POST.get('phone')
        password = request.POST.get('password')
        user = authenticate(request, phone_number=phone_number, password=password)
        if user is not None:
            login(request, user)
            messages.success(request, 'Logged in successfully!')
            return redirect('home')  # Replace 'home' with your desired redirect URL
        else:
            messages.error(request, 'Invalid phone number or password. Please try again.')
    return render(request, 'auth/login.html')

def logout_view(request):
    logout(request)
    messages.info(request, 'You have been logged out.')
    return redirect('login')

@login_required
def profile(request):
    user_balance, created = UserBalance.objects.get_or_create(
        user=request.user,
        defaults={'balance': 0, 'currency': 'GHS'}
    )

    # Get or create user profile
    profile, created = UserProfile.objects.get_or_create(
        user=request.user,
        defaults={
            'full_name': f"{request.user.profile.full_name}".strip() or str(request.user.phone_number),
            'email': request.user.email,
        }
    )

    saved_accounts = SavedAccount.objects.filter(user=request.user)
    
    # # Get or create user profile
    # try:
    #     profile = request.user.profile
    # except:
    #     # Create profile if it doesn't exist
    #     profile = UserProfile.objects.create(user=request.user)
    
    # Get recent transactions
    recent_transactions = RechargeTransaction.objects.filter(
        user=request.user
    ).order_by('-created_at')[:5]
    
    # Get recent withdrawals
    recent_withdrawals = WithdrawalTransaction.objects.filter(
        user=request.user
    ).order_by('-created_at')[:5]

    active_investments = UserInvestment.objects.filter(
        user=request.user,
        status='active'
    ).select_related('product')[:3]

    all_active_investments = UserInvestment.objects.filter(
        user=request.user,
        status='active'
    )
    total_invested = all_active_investments.aggregate(Sum('amount'))['amount__sum'] or 0
    
    total_earnings = sum(investment.calculate_earned_so_far() for investment in all_active_investments)
    net_balance = user_balance.balance + Decimal(str(total_earnings))
    total_account_value = user_balance.balance + Decimal(str(total_earnings)) + total_invested

    # Initialize forms
    profile_form = UserProfileForm(instance=profile, user=request.user)
    password_form = CustomPasswordChangeForm(user=request.user)

    
    context = {
        'user_balance': user_balance,
        'user': request.user,
        'profile': profile,
        'saved_accounts': saved_accounts,
        'recent_transactions': recent_transactions,
        'recent_withdrawals': recent_withdrawals,
        'active_investments': active_investments,
        'total_invested': total_invested,
        'total_earnings': total_earnings,
        'net_balance': net_balance,
        'total_account_value': total_account_value,
        'profile_form': profile_form,
        'password_form': password_form,
    }
    return render(request, 'auth/profile.html', context)



@login_required
@require_http_methods(['POST'])
def update_profile(request):
    """Update user profile information"""
    user = request.user
    
     # Get or create profile
    profile, created = UserProfile.objects.get_or_create(user=user)

    # Bind form with POST data
    form = UserProfileForm(request.POST, instance=profile, user=user)

    if form.is_valid():
        form.save()
        messages.success(request, 'Profile updated successfully!')
    else:
        # Collect form errors
        for field, errors in form.errors.items():
            for error in errors:
                messages.error(request, f'{error}')
    
    return redirect('profile')



@login_required
@require_http_methods(['POST'])
def change_password(request):
    """Change user password"""
    form = CustomPasswordChangeForm(user=request.user, data=request.POST)
    
    if form.is_valid():
        user = form.save()
        # Update session to prevent logout
        update_session_auth_hash(request, user)
        messages.success(request, 'Password changed successfully!')
    else:
        for field, errors in form.errors.items():
            for error in errors:
                messages.error(request, f'{error}')
    
    return redirect('profile')


@csrf_exempt
@login_required
def save_notification_preference(request):
    """Save user's notification type preference"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            notification_type = data.get('notification_type', 'all')
            
            # Save to user profile
            profile = request.user.profile
            profile.notification_type = notification_type
            profile.save()
            
            return JsonResponse({'status': 'success'})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    
    return JsonResponse({'error': 'Invalid method'}, status=400)

@login_required
def get_notification_preference(request):
    """Get user's notification type preference"""
    try:
        notification_type = request.user.profile.notification_type
        return JsonResponse({'notification_type': notification_type})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

# views.py
@csrf_exempt
@require_http_methods(["POST"])
def send_test_notification(request):
    """Send a test push notification"""
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Not authenticated'}, status=401)
    
    try:
        data = json.loads(request.body)
        
        payload = {
            'head': data.get('title', 'RoBosForx'),
            'body': data.get('message', 'Test notification'),
            'icon': '/static/imgs/icons/icon-192x192.png',
            'url': data.get('url', '/')  # Changed to root
        }
        
        send_user_notification(user=request.user, payload=payload, ttl=86400)
        
        return JsonResponse({'status': 'success'})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
    
    