from decimal import Decimal, InvalidOperation
import json
import hmac
import hashlib

from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.utils import timezone
from django.utils.crypto import get_random_string
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from django.conf import settings
from django.db import transaction

from .models import RechargeTransaction, UserBalance, WithdrawalTransaction
from .paystack_service import PaystackService
from django.db.models import Sum
from django.urls import reverse

# Create your views here.
@login_required
def home(request):
    user_balance, created = UserBalance.objects.get_or_create(
        user=request.user,
        defaults={'balance': 0, 'currency': 'GHS'}
    )
    context = {
        'user_balance': user_balance,
    }
    return render(request, 'iCare/services/home.html',context)


def product(request):
    return render(request, 'iCare/services/product.html')


@login_required
def recharge(request):
    preset_amounts = [100, 250, 500, 1000, 2000, 4500, 10000, 20000]
    selected_amount = ''
    custom_amount = ''
    selected_payment = 'GHS 1'
    error = ''
    success = ''

    if request.method == 'POST':
        selected_amount = request.POST.get('amount', '').strip()
        custom_amount = request.POST.get('custom_amount', '').strip()
        selected_payment = request.POST.get('payment_method', 'GHS 1')
        amount_to_use = custom_amount or selected_amount

        if not amount_to_use:
            error = 'Please choose a preset amount or enter a custom amount.'
        else:
            try:
                amount = Decimal(amount_to_use)
            except InvalidOperation:
                error = 'Please enter a valid numeric amount.'
            else:
                if amount < Decimal('100'):
                    error = 'The minimum top-up amount is GHS 100.'

        if not error:
            # Generate reference first
            reference = 'T' + timezone.now().strftime('%y%m%d%H%M%S') + get_random_string(5, '0123456789')
            
            # Initialize Paystack payment first
            try:
                paystack_service = PaystackService()
                # Generate a valid email for Paystack
                if request.user.email:
                    user_email = request.user.email
                else:
                    # Paystack requires a valid email format - use phone number digits with a real domain
                    phone_digits = ''.join(filter(str.isdigit, str(request.user.phone_number)))
                    user_email = f"user{phone_digits[-6:]}@icare.com"  # Use .com instead of .local
                
                result = paystack_service.initialize_payment(
                    email=user_email,
                    amount=amount,
                    reference=reference,
                    metadata={
                        'user_id': request.user.id,
                        'payment_method': selected_payment,
                    }
                )
                
                if result['success']:
                    # Create transaction record only after Paystack success
                    with transaction.atomic():
                        charge_transaction = RechargeTransaction.objects.create(
                            user=request.user,
                            reference=reference,
                            amount=amount,
                            currency='GHS',
                            payment_method=selected_payment,
                            status=RechargeTransaction.STATUS_IN_PROGRESS,
                            paystack_reference=result['reference'],
                            paystack_access_code=result['access_code'],
                            paystack_auth_url=result['authorization_url'],
                            notes='Top-up submitted from recharge page.'
                        )
                    
                    # Redirect to Paystack payment page
                    return redirect(result['authorization_url'])
                else:
                    error = result['message']
            except Exception as e:
                error = f'Payment service error: {str(e)}'

    context = {
        'preset_amounts': preset_amounts,
        'selected_amount': selected_amount,
        'custom_amount': custom_amount,
        'selected_payment': selected_payment,
        'error': error,
        'success': success,
    }
    return render(request, 'iCare/services/pages/recharge.html', context)


@login_required
def recharge_records(request):
    transactions = RechargeTransaction.objects.filter(user=request.user).order_by('-created_at')
     # Calculate statistics
    total_amount = transactions.filter(status='success').aggregate(Sum('amount'))['amount__sum'] or 0
    success_count = transactions.filter(status='success').count()
    pending_count = transactions.filter(status='pending').count()
    failed_count = transactions.filter(status='failed').count()
    in_progress_count = transactions.filter(status='in_progress').count()

    success_message = request.GET.get('message', '')
    if not success_message and request.GET.get('payment_success'):
        success_message = 'Payment successful! Your wallet has been credited.'

    context = {
        'transactions': transactions,
        'total_amount': total_amount,
        'success_count': success_count,
        'pending_count': pending_count,
        'failed_count': failed_count,
        'in_progress_count': in_progress_count,
        'success_message': success_message,
    }
    return render(request, 'iCare/services/pages/recharge-records.html', context)


@login_required
def payment_callback(request):
    """
    Handle callback from Paystack after payment completion.
    Paystack redirects here with reference parameter.
    """
    reference = request.GET.get('reference')
    
    if not reference:
        return redirect('recharge_records')
    
    # Verify payment with Paystack
    try:
        paystack_service = PaystackService()
        result = paystack_service.verify_payment(reference)
        
        # Find the transaction
        try:
            charge_transaction = RechargeTransaction.objects.get(paystack_reference=reference)
        except RechargeTransaction.DoesNotExist:
            return redirect('recharge_records')
        
        if result['success'] and result['status'] == 'success':
            # Payment successful - mark transaction and update balance
            charge_transaction.mark_success()
            
            # Get or create user balance
            user_balance, created = UserBalance.objects.get_or_create(
                user=request.user,
                defaults={'balance': 0, 'currency': 'GHS'}
            )
            
            # Add the charged amount to user balance
            user_balance.add_balance(charge_transaction.amount)
            
            # Redirect to recharge_records with success message
            return redirect(f"{reverse('recharge_records')}?payment_success=1&amount={charge_transaction.amount}")
        else:
            # Payment failed
            charge_transaction.mark_failed()
            return redirect('recharge')
    
    except Exception as e:
        print(f"Payment callback error: {str(e)}")
        return redirect('recharge_records')


@csrf_exempt
@require_http_methods(['POST'])
def payment_webhook(request):
    """
    Handle webhook from Paystack for payment verification.
    Paystack sends a POST request to this endpoint.
    """
    # Verify Paystack signature
    signature = request.META.get('HTTP_X_PAYSTACK_SIGNATURE', '')
    body = request.body
    secret = settings.PAYSTACK_SECRET_KEY.encode()
    
    hash_object = hmac.new(secret, body, hashlib.sha512)
    computed_signature = hash_object.hexdigest()
    
    if not hmac.compare_digest(signature, computed_signature):
        return JsonResponse({'status': 'error', 'message': 'Invalid signature'}, status=401)
    
    try:
        data = json.loads(request.body)
        reference = data.get('data', {}).get('reference')
        
        if not reference:
            return JsonResponse({'status': 'error', 'message': 'Missing reference'}, status=400)
        
        # Find transaction by Paystack reference
        try:
            transaction = RechargeTransaction.objects.get(paystack_reference=reference)
        except RechargeTransaction.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Transaction not found'}, status=404)
        
        # Verify with Paystack
        paystack_service = PaystackService()
        result = paystack_service.verify_payment(reference)
        
        if result['success'] and result['status'] == 'success':
            transaction.mark_success()
            return JsonResponse({'status': 'success', 'message': 'Payment verified'})
        else:
            transaction.mark_failed()
            return JsonResponse({'status': 'failed', 'message': 'Payment verification failed'})
    
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

@login_required
def withdrawal(request):
    """Handle withdrawal requests"""
    # Get user balance
    user_balance, created = UserBalance.objects.get_or_create(
        user=request.user,
        defaults={'balance': 0, 'currency': 'GHS'}
    )
    
    error = ''
    success = ''
    selected_method = 'mobile_money'  # Default
    context_data = {
        'user_balance': user_balance,
        'selected_method': selected_method,
    }
    
    if request.method == 'POST':
        amount_str = request.POST.get('amount', '').strip()
        selected_method = request.POST.get('withdrawal_method', 'mobile_money')
        
        # Validate amount
        try:
            amount = Decimal(amount_str)
        except (InvalidOperation, ValueError):
            error = 'Please enter a valid amount.'
            return render(request, 'iCare/services/pages/withdrawal.html', {
                'user_balance': user_balance,
                'error': error,
                'selected_method': selected_method,
                **request.POST
            })
        
        # Check minimum amount
        if amount < Decimal('100'):
            error = 'Minimum withdrawal amount is GHS 100.'
        elif amount > user_balance.balance:
            error = 'Insufficient balance for this withdrawal.'
        
        # Validate based on withdrawal method
        if not error:
            if selected_method == 'mobile_money':
                network = request.POST.get('network', '')
                phone_number = request.POST.get('phone_number', '')
                
                if not network:
                    error = 'Please select your mobile money network.'
                elif not phone_number or len(phone_number.replace(' ', '')) < 9:
                    error = 'Please enter a valid phone number.'
            
            elif selected_method == 'bank_transfer':
                bank_name = request.POST.get('bank_name', '')
                account_number = request.POST.get('account_number', '')
                account_name = request.POST.get('account_name', '')
                
                if not bank_name:
                    error = 'Please select your bank.'
                elif not account_number or len(account_number) < 10:
                    error = 'Please enter a valid account number.'
                elif not account_name:
                    error = 'Please enter the account holder name.'
        
        # Process withdrawal if no errors
        if not error:
            with transaction.atomic():
                # Deduct balance
                if user_balance.deduct_balance(amount):
                    # Create withdrawal transaction record
                    withdrawal_transaction = WithdrawalTransaction.objects.create(
                        user=request.user,
                        amount=amount,
                        currency='GHS',
                        status=WithdrawalTransaction.STATUS_PENDING,
                        withdrawal_method=selected_method,
                        # Store withdrawal details in JSON or separate fields
                        withdrawal_details={
                            'method': selected_method,
                            'network': request.POST.get('network') if selected_method == 'mobile_money' else None,
                            'phone_number': request.POST.get('phone_number') if selected_method == 'mobile_money' else None,
                            'bank_name': request.POST.get('bank_name') if selected_method == 'bank_transfer' else None,
                            'account_number': request.POST.get('account_number') if selected_method == 'bank_transfer' else None,
                            'account_name': request.POST.get('account_name') if selected_method == 'bank_transfer' else None,
                        }
                    )
                    
                    success = f'Withdrawal request of GHS {amount} submitted successfully! Funds will be processed shortly.'
                    return redirect(f"{reverse('withdrawal_records')}?success_message={success}")
                else:
                    error = 'Failed to process withdrawal. Please try again.'
        
        # Update context with form data
        context_data.update({
            'error': error,
            'success': success,
            'selected_method': selected_method,
            'network': request.POST.get('network', ''),
            'phone_number': request.POST.get('phone_number', ''),
            'bank_name': request.POST.get('bank_name', ''),
            'account_number': request.POST.get('account_number', ''),
            'account_name': request.POST.get('account_name', ''),
        })
    
    return render(request, 'iCare/services/pages/withdrawal.html', context_data)


@login_required
def withdrawal_records(request):
    """Display user's withdrawal transaction history"""
    transactions = WithdrawalTransaction.objects.filter(user=request.user).order_by('-created_at')
    
    # Calculate statistics
    total_withdrawn = transactions.filter(status='completed').aggregate(Sum('amount'))['amount__sum'] or 0
    completed_count = transactions.filter(status='completed').count()
    pending_count = transactions.filter(status='pending').count()
    failed_count = transactions.filter(status='failed').count()
    processing_count = transactions.filter(status='processing').count()

    
    context = {
        'transactions': transactions,
        'total_withdrawn': total_withdrawn,
        'completed_count': completed_count,
        'pending_count': pending_count,
        'failed_count': failed_count,
        'processing_count': processing_count,
    }
    return render(request, 'iCare/services/pages/withdrawal-records.html', context)

@login_required
@require_http_methods(['POST'])
def cancel_withdrawal(request, transaction_id):
    """Cancel a pending withdrawal request"""
    try:
        transaction = WithdrawalTransaction.objects.get(
            id=transaction_id, 
            user=request.user,
            status=WithdrawalTransaction.STATUS_PENDING
        )
        
        # Reverse the deduction
        user_balance = UserBalance.objects.get(user=request.user)
        user_balance.add_balance(transaction.amount)
        
        # Mark as failed/cancelled
        transaction.status = WithdrawalTransaction.STATUS_FAILED
        transaction.notes = 'Cancelled by user'
        transaction.save()
        
        return JsonResponse({'success': True, 'message': 'Withdrawal cancelled successfully'})
    except WithdrawalTransaction.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Transaction not found'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)

@login_required
def account(request):
    """Display user account and balance information"""
    # Get or create user balance
    user_balance, created = UserBalance.objects.get_or_create(
        user=request.user,
        defaults={'balance': 0, 'currency': 'GHS'}
    )
    
    # Get recent transactions
    recent_transactions = RechargeTransaction.objects.filter(
        user=request.user
    ).order_by('-created_at')[:10]
    
    context = {
        'user_balance': user_balance,
        'recent_transactions': recent_transactions,
    }
    return render(request, 'iCare/services/pages/account.html', context)


def tasks(request):
    return render(request, 'iCare/services/pages/tasks.html')


def check_in(request):
    return render(request, 'iCare/services/pages/check_in.html')