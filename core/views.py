from decimal import Decimal, InvalidOperation
import json
import hmac
import hashlib
import random
import string

from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.utils import timezone
from django.utils.crypto import get_random_string
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse, HttpResponse
from django.core.cache import cache
from django.conf import settings
from django.db import transaction, models
from django.contrib import messages

from .models import (
    RechargeTransaction, UserBalance, WithdrawalTransaction, Product, 
    UserInvestment, ProductTransaction, SavedAccount, Task, UserTask, UserCheckin,
    ReferralCode, UserReferral, TeamMember, ReferralCommission
)
from iCare_auth.models import User
from .paystack_service import PaystackService
from django.db.models import Sum
from django.urls import reverse
from datetime import date, timedelta
from core.tasks import (
    process_referral_commission,
    update_team_volumes
)
from .tasks import (
    send_commission_notification,
    send_withdrawal_notification, 
    send_recharge_notification,
    send_product_purchase_notification
)


def generate_referral_code():
    """Generate unique referral code"""
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))

# Create your views here.
@login_required
def home(request):
    user_balance = UserBalance.get_user_balance(request.user)
    context = {
        'user_balance': user_balance,
    }
    return render(request, 'iCare/services/home.html', context)


@login_required
def recharge(request):
    preset_amounts = [100, 250, 500, 1000, 2000, 4500, 10000, 20000]
    selected_amount = ''
    custom_amount = ''
    selected_payment = 'GHS 1'
    error = ''
    success = ''

    saved_accounts = SavedAccount.objects.filter(user=request.user)

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
                if request.user.profile.email:
                    user_email = request.user.profile.email
                else:
                    # Paystack requires a valid email format - use phone number digits with a real domain
                    phone_digits = ''.join(filter(str.isdigit, str(request.user.phone_number)))
                    # use real email
                    user_email = f"user{phone_digits[-6:]}@roboforxs.vercel.app"  # Use .com instead of .local
                
                # callback_url should point to a view that can handle the payment verification
                callback_url = request.build_absolute_uri(reverse('payment_callback'))

                result = paystack_service.initialize_payment(
                    email=user_email,
                    amount=amount,
                    reference=reference,
                    callback_url=callback_url,
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
        'saved_accounts' : saved_accounts,
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
    
    print(f"=== PAYMENT CALLBACK DEBUG ===")
    print(f"Reference: {reference}")
    print(f"Full URL: {request.build_absolute_uri()}")
    print(f"User: {request.user}")
    
    if not reference:
        print("No reference found in callback")
        messages.error(request, 'Invalid payment reference.')
        return redirect('recharge_records')
    
    # Verify payment with Paystack
    try:
        paystack_service = PaystackService()
        result = paystack_service.verify_payment(reference)
        
        print(f"Verification result: {result}")
        
        # Find the transaction
        try:
            charge_transaction = RechargeTransaction.objects.get(paystack_reference=reference)
            print(f"Found transaction: {charge_transaction.reference}, Amount: {charge_transaction.amount}")
        except RechargeTransaction.DoesNotExist:
            print(f"Transaction not found for reference: {reference}")
            messages.error(request, 'Transaction not found.')
            return redirect('recharge_records')
        
        if result['success'] and result['status'] == 'success':
            print("Payment verification successful!")
            
            if charge_transaction.status != RechargeTransaction.STATUS_SUCCESS:
                # Payment successful - mark transaction and update balance
                charge_transaction.mark_success()
                
                # Get or create user balance
                user_balance, created = UserBalance.objects.get_or_create(
                    user=request.user,
                    defaults={'balance': 0, 'currency': 'GHS'}
                )
                
                # Add the charged amount to user balance
                user_balance.add_balance(charge_transaction.amount)
                print(f"Balance updated. New balance: {user_balance.balance}")
                
                # Send push notification
                send_recharge_notification.delay(request.user.id, float(charge_transaction.amount))
            
            # Add success message
            messages.success(request, f'Payment of GHS {charge_transaction.amount} successful! Your wallet has been credited.')
            
            # Redirect to recharge_records with success message
            return redirect('recharge_records')
        else:
            # Payment failed
            print(f"Payment verification failed. Status: {result.get('status')}")
            charge_transaction.mark_failed()
            messages.error(request, 'Payment verification failed. Please contact support.')
            return redirect('recharge')
    
    except Exception as e:
        print(f"Payment callback error: {str(e)}")
        import traceback
        traceback.print_exc()
        messages.error(request, f'An error occurred: {str(e)}')
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
            if transaction.status != RechargeTransaction.STATUS_SUCCESS:
                transaction.mark_success()
                
                # Update user balance
                user_balance, created = UserBalance.objects.get_or_create(
                    user=transaction.user,
                    defaults={'balance': 0, 'currency': 'GHS'}
                )
                user_balance.add_balance(transaction.amount)
                
                # Send push notification
                send_recharge_notification.delay(transaction.user.id, float(transaction.amount))
                
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
    """Handle withdrawal requests with saved accounts"""
    # Get user balance
    user_balance, created = UserBalance.objects.get_or_create(
        user=request.user,
        defaults={'balance': 0, 'currency': 'GHS'}
    )
    
    # Get saved accounts
    saved_accounts = SavedAccount.objects.filter(user=request.user)
    
    error = ''
    success = ''
    
    if request.method == 'POST':
        amount_str = request.POST.get('amount', '').strip()
        saved_account_id = request.POST.get('saved_account_id', '')
        
        # Validate amount
        try:
            amount = Decimal(amount_str)
        except (InvalidOperation, ValueError):
            error = 'Please enter a valid amount.'
            return render(request, 'iCare/services/pages/withdrawal.html', {
                'user_balance': user_balance,
                'saved_accounts': saved_accounts,
                'error': error,
            })
        
        # Check minimum amount
        if amount < Decimal('100'):
            error = 'Minimum withdrawal amount is GHS 100.'
        elif amount > user_balance.balance:
            error = 'Insufficient balance for this withdrawal.'
        
        # Get the saved account
        if not error and saved_account_id:
            try:
                saved_account = SavedAccount.objects.get(id=saved_account_id, user=request.user)
            except SavedAccount.DoesNotExist:
                error = 'Selected withdrawal method not found.'
        
        if not error:
            with transaction.atomic():
                # Deduct balance
                if user_balance.deduct_balance(amount):
                    # Calculate 30% withdrawal fee
                    fee = amount * Decimal('0.30')
                    net_amount = amount - fee
                    
                    # Create withdrawal transaction record with saved account details
                    withdrawal_details = {
                        'method': saved_account.account_type,
                        'saved_account_id': str(saved_account.id),
                        'gross_amount': str(amount),
                        'fee_percentage': '30%',
                        'fee_amount': str(fee.quantize(Decimal('0.01'))),
                        'net_payable': str(net_amount.quantize(Decimal('0.01'))),
                    }
                    
                    if saved_account.account_type == 'mobile_money':
                        withdrawal_details['network'] = saved_account.network
                        withdrawal_details['phone_number'] = saved_account.phone_number
                    else:
                        withdrawal_details['bank_name'] = saved_account.bank_name
                        withdrawal_details['account_number'] = saved_account.account_number
                        withdrawal_details['account_name'] = saved_account.account_name
                    
                    withdrawal_transaction = WithdrawalTransaction.objects.create(
                        user=request.user,
                        amount=amount,
                        currency='GHS',
                        status=WithdrawalTransaction.STATUS_PENDING,
                        withdrawal_method=saved_account.account_type,
                        withdrawal_details=withdrawal_details
                    )
                    
                    messages.success(request, f'Withdrawal request of GHS {amount} submitted successfully!')
                    return redirect('withdrawal_records')
                else:
                    error = 'Failed to process withdrawal. Please try again.'
        
        # If error, show message
        if error:
            messages.error(request, error)
    
    context = {
        'user_balance': user_balance,
        'saved_accounts': saved_accounts,
    }
    return render(request, 'iCare/services/pages/withdrawal.html', context)


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
def account_balance(request):
    """Display user account and balance information"""
    # Get or create user balance
    user_balance, created = UserBalance.objects.get_or_create(
        user=request.user,
        defaults={'balance': 0, 'currency': 'GHS'}
    )
    
    # Get saved accounts
    saved_accounts = SavedAccount.objects.filter(user=request.user)
    
    # Get recent transactions
    recent_transactions = RechargeTransaction.objects.filter(
        user=request.user
    ).order_by('-created_at')[:5]
    
    # Get recent withdrawals
    recent_withdrawals = WithdrawalTransaction.objects.filter(
        user=request.user
    )[:5]
    
    # Get active investments for display
    active_investments = UserInvestment.objects.filter(
        user=request.user,
        status='active'
    ).select_related('product')[:3]
    
    # Calculate stats across ALL active investments
    all_active_investments = UserInvestment.objects.filter(
        user=request.user,
        status='active'
    )
    total_invested = all_active_investments.aggregate(Sum('amount'))['amount__sum'] or 0
    
    total_earnings = sum(investment.calculate_earned_so_far() for investment in all_active_investments)
    net_balance = user_balance.balance + Decimal(str(total_earnings))
    total_account_value = user_balance.balance + Decimal(str(total_earnings)) + total_invested
    
    context = {
        'user_balance': user_balance,
        'user': request.user,
        'saved_accounts': saved_accounts,
        'recent_transactions': recent_transactions,
        'recent_withdrawals': recent_withdrawals,
        'active_investments': active_investments,
        'total_invested': total_invested,
        'total_earnings': total_earnings,
        'net_balance': net_balance,
        'total_account_value': total_account_value,
    }
    return render(request, 'iCare/services/pages/account_balance.html', context)

@login_required
def product(request):
    """Display available products and user investments"""
    products = cache.get('all_products_cache')
    if products is None:
        products = list(Product.objects.all().order_by('price'))
        cache.set('all_products_cache', products, timeout=900)
        
    user_balance = UserBalance.get_user_balance(request.user)

    saved_accounts = SavedAccount.objects.filter(user=request.user)
    
    # Get user's investments
    user_investments = UserInvestment.objects.filter(
        user=request.user,
        status__in=['active', 'pending', 'completed']
    ).select_related('product')
    
    # Find max purchased price
    max_purchased_price = 0
    for inv in user_investments:
        if inv.product.price > max_purchased_price:
            max_purchased_price = inv.product.price
            
    # Mark products as disabled if price <= max_purchased_price
    for p in products:
        p.is_disabled = (p.price <= max_purchased_price)
        
    # Get user's active investments for display
    display_investments = [inv for inv in user_investments if inv.status in ['active', 'pending']][:5]
    
    # Calculate progress for each investment
    for investment in display_investments:
        investment.total_earned = investment.calculate_earned_so_far()
        investment.days_remaining = investment.get_days_remaining()
        investment.progress_percentage = investment.get_progress_percentage()
    
    context = {
        'products': products,
        'user_balance': user_balance,
        'user_investments': display_investments,
        'saved_accounts': saved_accounts,
    }
    return render(request, 'iCare/services/product.html', context)

@login_required
def get_products_data(request):
    """AJAX endpoint to get all products data"""
    products = cache.get('all_products_values_cache')
    if products is None:
        products = list(Product.objects.all().values('id', 'name', 'price', 'description', 'term', 'daily_earnings', 'total_earnings'))
        cache.set('all_products_values_cache', products, timeout=900)
    return JsonResponse(products, safe=False)

@login_required
def product_details(request):
    """AJAX endpoint to get single product details"""
    product_id = request.GET.get('id')
    try:
        product = Product.objects.get(id=product_id)
        
        # Check if disabled
        user_investments = UserInvestment.objects.filter(
            user=request.user,
            status__in=['active', 'pending', 'completed']
        ).select_related('product')
        max_purchased_price = 0
        for inv in user_investments:
            if inv.product.price > max_purchased_price:
                max_purchased_price = inv.product.price
                
        is_disabled = (product.price <= max_purchased_price)
        
        if request.headers.get('HX-Request'):
            context = {
                'product': product,
                'is_disabled': is_disabled,
            }
            return render(request, 'iCare/partials/product_details_partial.html', context)
            
        data = {
            'id': str(product.id),
            'name': product.name,
            'price': float(product.price),
            'description': product.description,
            'term': product.term,
            'daily_earnings': float(product.daily_earnings) if product.daily_earnings else None,
            'total_earnings': float(product.total_earnings) if product.total_earnings else None,
            'is_disabled': is_disabled,
        }
        return JsonResponse(data)
    except Product.DoesNotExist:
        if request.headers.get('HX-Request'):
            return HttpResponse('<div class="p-4 text-red-600">Product not found.</div>', status=404)
        return JsonResponse({'error': 'Product not found'}, status=404)


@login_required
@require_http_methods(['POST'])
def purchase_product(request):
    """Handle product purchase with Paystack payment integration"""
    product_id = request.POST.get('product_id')
    payment_method_id = request.POST.get('payment_method_id')
    payment_method_type = request.POST.get('payment_method_type')
    
    print(f"=== PURCHASE PRODUCT DEBUG ===")
    print(f"Product ID: {product_id}")
    print(f"Payment Method ID: {payment_method_id}")
    print(f"Payment Method Type: {payment_method_type}")
    
    try:
        product = Product.objects.get(id=product_id)
        print(f"Product found: {product.name}, Price: {product.price}")
    except Product.DoesNotExist:
        messages.error(request, 'Product not found.')
        return redirect('product')
    
    user_balance, created = UserBalance.objects.get_or_create(
        user=request.user,
        defaults={'balance': 0, 'currency': 'GHS'}
    )
    
    # Enforce wallet-only purchases — reject any non-wallet payment attempt
    if payment_method_type != 'wallet':
        messages.error(request, 'Purchases must be made using your wallet balance. Please recharge your wallet first.')
        return redirect('product')

    # Check if user has already purchased this package or a higher package
    user_investments = UserInvestment.objects.filter(
        user=request.user,
        status__in=['active', 'pending', 'completed']
    )
    max_purchased_price = 0
    for inv in user_investments:
        if inv.product.price > max_purchased_price:
            max_purchased_price = inv.product.price
            
    if product.price <= max_purchased_price:
        messages.error(request, 'You have already purchased this package or a higher level package.')
        return redirect('product')

    # Process wallet payment
    print("Processing wallet payment...")
    if user_balance.balance >= product.price:
        with transaction.atomic():
            # Deduct from wallet
            user_balance.deduct_balance(product.price)
            
            # Create investment record
            investment = UserInvestment.objects.create(
                user=request.user,
                product=product,
                amount=product.price,
                status='active'
            )
            
            print(f"Wallet payment successful! Investment ID: {investment.id}")
            
            # Process commissions and team volumes
            process_referral_commission.delay(investment.id)
            update_team_volumes.delay(request.user.id)
            
            # Send push notification
            send_product_purchase_notification.delay(request.user.id, product.name)
            
            messages.success(request, f'Successfully purchased {product.name}! Your investment is now active.')
            return redirect('my_investments')
    else:
        print(f"Insufficient balance. Balance: {user_balance.balance}, Price: {product.price}")
        messages.error(request, 'Insufficient balance. Please recharge your wallet first.')
        return redirect('product')


@login_required
def product_payment_callback(request):
    """
    Handle callback from Paystack after product payment completion.
    Redirects to my_investments page after successful payment.
    """
    reference = request.GET.get('reference')
    
    print(f"=== PRODUCT PAYMENT CALLBACK DEBUG ===")
    print(f"Reference: {reference}")
    
    if not reference:
        messages.error(request, 'Invalid payment reference.')
        return redirect('product')
    
    try:
        paystack_service = PaystackService()
        result = paystack_service.verify_payment(reference)
        
        print(f"Verification result: {result}")
        
        # Find the product transaction
        try:
            product_transaction = ProductTransaction.objects.get(paystack_reference=reference)
            print(f"Found product transaction: {product_transaction.id}")
        except ProductTransaction.DoesNotExist:
            messages.error(request, 'Transaction not found.')
            return redirect('product')
        
        if result['success'] and result['status'] == 'success':
            print("Payment verification successful!")
            
            # Check if investment already exists (to avoid duplicates)
            existing_investment = UserInvestment.objects.filter(
                user=request.user,
                product=product_transaction.product,
                transaction_reference=product_transaction.reference
            ).exists()
            
            if not existing_investment:
                with transaction.atomic():
                    # Mark transaction as success
                    product_transaction.mark_success()
                    
                    # Create investment record
                    investment = UserInvestment.objects.create(
                        user=request.user,
                        product=product_transaction.product,
                        amount=product_transaction.amount,
                        status='active',
                        transaction_reference=product_transaction.reference  # This now exists
                    )
                    print(f"Investment created: {investment.id}")
                    
                    # Process commissions and team volumes
                    process_referral_commission.delay(investment.id)
                    update_team_volumes.delay(request.user.id)
                    
                    # Send push notification
                    send_product_purchase_notification.delay(request.user.id, product_transaction.product.name)
                    
                    messages.success(request, f'Successfully purchased {product_transaction.product.name}! Your investment is now active.')
            else:
                print("Investment already exists")
                messages.info(request, 'Investment already recorded.')
            
            # Clear session data
            if 'pending_product_purchase' in request.session:
                del request.session['pending_product_purchase']
            
            # Redirect to my investments page
            return redirect('my_investments')
        else:
            # Payment failed
            print(f"Payment verification failed. Status: {result.get('status')}")
            product_transaction.mark_failed()
            messages.error(request, 'Payment verification failed. Please contact support.')
            return redirect('product')
    
    except Exception as e:
        print(f"Product payment callback error: {str(e)}")
        import traceback
        traceback.print_exc()
        messages.error(request, f'An error occurred: {str(e)}')
        return redirect('product')


@csrf_exempt
@require_http_methods(['POST'])
def product_payment_webhook(request):
    """
    Handle webhook from Paystack for product payment verification.
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
        event = data.get('event')
        
        if not reference:
            return JsonResponse({'status': 'error', 'message': 'Missing reference'}, status=400)
        
        # Only process charge.success events
        if event == 'charge.success':
            try:
                product_transaction = ProductTransaction.objects.get(paystack_reference=reference)
            except ProductTransaction.DoesNotExist:
                return JsonResponse({'status': 'error', 'message': 'Transaction not found'}, status=404)
            
            # Verify with Paystack
            paystack_service = PaystackService()
            result = paystack_service.verify_payment(reference)
            
            if result['success'] and result['status'] == 'success':
                # Check if investment already created
                existing_investment = UserInvestment.objects.filter(
                    user=product_transaction.user,
                    product=product_transaction.product,
                    transaction_reference=product_transaction.reference
                ).exists()
                
                if not existing_investment:
                    with transaction.atomic():
                        product_transaction.mark_success()
                        
                        # Create investment
                        investment = UserInvestment.objects.create(
                            user=product_transaction.user,
                            product=product_transaction.product,
                            amount=product_transaction.amount,
                            status='active',
                            transaction_reference=product_transaction.reference
                        )
                        
                        # Process commissions and team volumes
                        process_referral_commission.delay(investment.id)
                        update_team_volumes.delay(product_transaction.user.id)
                        
                        # Send push notification
                        send_product_purchase_notification.delay(product_transaction.user.id, product_transaction.product.name)
                
                return JsonResponse({'status': 'success', 'message': 'Product purchase verified'})
            else:
                product_transaction.mark_failed()
                return JsonResponse({'status': 'failed', 'message': 'Payment verification failed'})
        
        return JsonResponse({'status': 'ignored', 'message': 'Event not processed'})
    
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

@login_required
def my_investments(request):
    """Display user's all investments"""
    investments = UserInvestment.objects.filter(user=request.user).select_related('product').order_by('-created_at')
    
    total_invested = 0
    active_count = 0
    
    for investment in investments:
        investment.total_earned = investment.calculate_earned_so_far()
        investment.days_remaining = investment.get_days_remaining()
        investment.progress_percentage = investment.get_progress_percentage()
        
        if investment.status == 'active':
            total_invested += float(investment.amount)
            active_count += 1
    
    context = {
        'investments': investments,
        'total_invested': total_invested,
        'active_count': active_count,
        'user_balance': UserBalance.objects.get_or_create(user=request.user)[0],
    }
    return render(request, 'iCare/services/pages/my_investments.html', context)

@login_required
@require_http_methods(['POST'])
def add_saved_account(request):
    """Add a new saved account for withdrawals"""
    account_type = request.POST.get('account_type')
    
    try:
        with transaction.atomic():
            if account_type == 'mobile_money':
                network = request.POST.get('network')
                phone_number = request.POST.get('phone_number')
                
                # Validate
                if not network or not phone_number:
                    messages.error(request, 'Please fill all mobile money fields.')
                    return redirect('saved_payment_methods')
                
                # Clean phone number
                phone_number = ''.join(filter(str.isdigit, phone_number))
                # Remove leading 0 or 233
                if phone_number.startswith('233'):
                    phone_number = phone_number[3:]
                elif phone_number.startswith('0'):
                    phone_number = phone_number[1:]
                
                # Validate length
                if len(phone_number) != 9:
                    messages.error(request, 'Please enter a valid 9-digit phone number (e.g., 202739333)')
                    return redirect('saved_payment_methods')
                
                # Check for duplicate
                existing = SavedAccount.objects.filter(
                    user=request.user,
                    account_type='mobile_money',
                    network=network,
                    phone_number=phone_number
                ).exists()
                
                if existing:
                    messages.warning(request, f'This {network.upper()} account is already saved.')
                    return redirect('saved_payment_methods')
                
                saved_account = SavedAccount.objects.create(
                    user=request.user,
                    account_type='mobile_money',
                    network=network,
                    phone_number=phone_number,
                )
                
                messages.success(request, f'{network.upper()} account ending with {phone_number[-4:]} saved successfully!')
                
            elif account_type == 'bank_transfer':
                bank_name = request.POST.get('bank_name')
                account_number = request.POST.get('account_number')
                account_name = request.POST.get('account_name')
                
                # Validate
                if not bank_name or not account_number or not account_name:
                    messages.error(request, 'Please fill all bank account fields.')
                    return redirect('saved_payment_methods')
                
                # Clean account number (remove spaces)
                account_number = ''.join(filter(str.isdigit, account_number))
                
                # Check for duplicate
                existing = SavedAccount.objects.filter(
                    user=request.user,
                    account_type='bank_transfer',
                    bank_name=bank_name,
                    account_number=account_number
                ).exists()
                
                if existing:
                    messages.warning(request, f'This {bank_name} account is already saved.')
                    return redirect('saved_payment_methods')
                
                saved_account = SavedAccount.objects.create(
                    user=request.user,
                    account_type='bank_transfer',
                    bank_name=bank_name,
                    account_number=account_number,
                    account_name=account_name,
                )
                
                messages.success(request, f'{bank_name} account ending with {account_number[-4:]} saved successfully!')
            
            else:
                messages.error(request, 'Invalid account type.')
                return redirect('saved_payment_methods')
            
            # If this is the first account, set as default
            if SavedAccount.objects.filter(user=request.user).count() == 1:
                saved_account.is_default = True
                saved_account.save()
                messages.success(request, 'This account has been set as your default payment method.')
            
            return redirect('saved_payment_methods')
            
    except Exception as e:
        messages.error(request, f'Error saving account: {str(e)}')
        return redirect('saved_payment_methods')


@login_required
@require_http_methods(['POST'])
def set_default_account(request, account_id):
    """Set a saved account as default"""
    try:
        with transaction.atomic():
            # Reset all accounts to non-default
            SavedAccount.objects.filter(user=request.user).update(is_default=False)
            
            # Set the selected account as default
            account = SavedAccount.objects.get(id=account_id, user=request.user)
            account.is_default = True
            account.save()
            
            messages.success(request, 'Default payment method updated successfully.')
    except SavedAccount.DoesNotExist:
        messages.error(request, 'Account not found.')
    except Exception as e:
        messages.error(request, f'Error: {str(e)}')
    
    return redirect('account')


@login_required
@require_http_methods(['POST'])
def delete_saved_account(request, account_id):
    """Delete a saved account"""
    try:
        account = SavedAccount.objects.get(id=account_id, user=request.user)
        was_default = account.is_default
        account.delete()
        
        # If we deleted the default account, set another as default if available
        if was_default:
            next_account = SavedAccount.objects.filter(user=request.user).first()
            if next_account:
                next_account.is_default = True
                next_account.save()
        
        messages.success(request, 'Account removed successfully.')
    except SavedAccount.DoesNotExist:
        messages.error(request, 'Account not found.')
    except Exception as e:
        messages.error(request, f'Error: {str(e)}')
    
    return redirect('account')


@login_required
def get_saved_accounts_json(request):
    """AJAX endpoint to get user's saved accounts"""
    accounts = SavedAccount.objects.filter(user=request.user)
    data = []
    for account in accounts:
        data.append({
            'id': str(account.id),
            'account_type': account.account_type,
            'display_name': str(account),
            'is_default': account.is_default,
            'network': account.network,
            'phone_number': account.phone_number,
            'bank_name': account.bank_name,
            'account_number': account.account_number,
            'account_name': account.account_name,
        })
    return JsonResponse(data, safe=False)


def saved_payment_methods(request):
    """Display user's saved payment methods"""
    saved_accounts = SavedAccount.objects.filter(user=request.user)
    
    # Prepare JSON data for JavaScript validation
    accounts_json = []
    for account in saved_accounts:
        if account.account_type == 'mobile_money':
            accounts_json.append({
                'account_type': account.account_type,
                'network': account.network,
                'phone_number': account.phone_number,
            })
        else:
            accounts_json.append({
                'account_type': account.account_type,
                'bank_name': account.bank_name,
                'account_number': account.account_number,
            })
    
    context = {
        'saved_accounts': saved_accounts,
        'saved_accounts_json': json.dumps(accounts_json),
    }
    return render(request, 'iCare/services/pages/saved-payment-methods.html', context)


@login_required
def tasks(request):
    """Display tasks and user progress"""
    from datetime import date as today_date
    today = today_date.today()

    tasks_list = cache.get('active_tasks_cache')
    if tasks_list is None:
        tasks_list = list(Task.objects.filter(is_active=True))
        cache.set('active_tasks_cache', tasks_list, timeout=900)

    # All user task records
    user_task_records = UserTask.objects.filter(user=request.user).select_related('task')

    # Tasks completed today (for the 'Completed Today' badge)
    completed_today_ids = list(user_task_records.filter(
        last_completed_date=today
    ).values_list('task_id', flat=True))

    # All-time completed count (for stats banner)
    all_time_completed = user_task_records.filter(status='completed').values_list('task_id', flat=True)
    
    # Get or create checkin record
    checkin, created = UserCheckin.objects.get_or_create(user=request.user)
    
    # Calculate check-in bonus based on streak
    daily_bonus = 1.00 + (checkin.streak * 0.50)
    if daily_bonus > 10:
        daily_bonus = 10
    
    checked_in_today = checkin.last_checkin_date == today
    
    context = {
        'tasks': tasks_list,
        'completed_tasks': completed_today_ids,       # used by template for 'Completed Today'
        'has_completed_any_today': len(completed_today_ids) > 0,
        'completed_tasks_count': len(completed_today_ids),
        'available_tasks_count': len([t for t in tasks_list if t.id not in completed_today_ids]),
        'total_tasks_count': len(tasks_list),
        'total_task_earnings': UserTask.objects.filter(user=request.user, status='completed').aggregate(Sum('task__reward'))['task__reward__sum'] or 0,
        'checkin_streak': checkin.streak,
        'daily_bonus': daily_bonus,
        'checked_in_today': checked_in_today,
        'referral_link': request.build_absolute_uri(reverse('signup')) + f'?ref={request.user.id}',
        'referral_bonus': 5.00,
    }
    return render(request, 'iCare/services/pages/tasks.html', context)


@login_required
def task_details(request):
    """AJAX endpoint to get task details"""
    task_id = request.GET.get('id')
    try:
        task = Task.objects.get(id=task_id)
        from datetime import date as today_date
        today = today_date.today()
        already_done = UserTask.objects.filter(
            user=request.user, task=task, last_completed_date=today
        ).exists()
        has_completed_any_today = UserTask.objects.filter(
            user=request.user, last_completed_date=today
        ).exists()
        
        if request.headers.get('HX-Request'):
            context = {
                'task': task,
                'already_done': already_done,
                'has_completed_any_today': has_completed_any_today,
            }
            return render(request, 'iCare/partials/task_details_partial.html', context)
            
        data = {
            'id': str(task.id),
            'title': task.title,
            'description': task.description,
            'instructions': task.instructions,
            'steps': task.steps,
            'task_url': task.task_url,
            'reward': float(task.reward),
            'already_done': already_done,
            'has_completed_any_today': has_completed_any_today,
        }
        return JsonResponse(data)
    except Task.DoesNotExist:
        if request.headers.get('HX-Request'):
            return HttpResponse('<div class="p-4 text-red-600">Task not found.</div>', status=404)
        return JsonResponse({'error': 'Task not found'}, status=404)


@login_required
@require_http_methods(['POST'])
def complete_task(request):
    """Complete a task and credit reward — limited to once per day per task/user"""
    from datetime import date as today_date
    task_id = request.POST.get('task_id')
    if not task_id:
        try:
            data = json.loads(request.body)
            task_id = data.get('task_id')
        except Exception:
            pass
            
    today = today_date.today()
    
    try:
        task = Task.objects.get(id=task_id)
    except Task.DoesNotExist:
        if request.headers.get('HX-Request'):
            return HttpResponse('<div class="p-4 text-red-600">Task not found.</div>', status=404)
        return JsonResponse({'success': False, 'message': 'Task not found'})
    
    # Check if already completed today or if ANY task completed today (1 task per day rule)
    already_done = UserTask.objects.filter(
        user=request.user, task=task, last_completed_date=today
    ).exists()
    has_completed_any_today = UserTask.objects.filter(
        user=request.user, last_completed_date=today
    ).exists()

    if already_done or has_completed_any_today:
        if request.headers.get('HX-Request'):
            tasks_list = cache.get('active_tasks_cache')
            if tasks_list is None:
                tasks_list = list(Task.objects.filter(is_active=True))
                cache.set('active_tasks_cache', tasks_list, timeout=900)
            completed_today_ids = list(UserTask.objects.filter(user=request.user, last_completed_date=today).values_list('task_id', flat=True))
            context = {
                'tasks': tasks_list,
                'completed_tasks': completed_today_ids,
                'has_completed_any_today': True,
            }
            return render(request, 'iCare/partials/tasks_list_partial.html', context)
        return JsonResponse({'success': False, 'message': 'You have already completed a task today. Come back tomorrow!'})
    
    with transaction.atomic():
        # Update or create user task record, resetting for today
        user_task, created = UserTask.objects.update_or_create(
            user=request.user,
            task=task,
            defaults={
                'status': 'completed',
                'completed_at': timezone.now(),
                'last_completed_date': today,
            }
        )
        
        # Credit reward to wallet
        user_balance, created = UserBalance.objects.get_or_create(
            user=request.user,
            defaults={'balance': 0, 'currency': 'GHS'}
        )
        user_balance.add_balance(task.reward)
    
    if request.headers.get('HX-Request'):
        tasks_list = cache.get('active_tasks_cache')
        if tasks_list is None:
            tasks_list = list(Task.objects.filter(is_active=True))
            cache.set('active_tasks_cache', tasks_list, timeout=900)
        completed_today_ids = list(UserTask.objects.filter(user=request.user, last_completed_date=today).values_list('task_id', flat=True))
        context = {
            'tasks': tasks_list,
            'completed_tasks': completed_today_ids,
            'has_completed_any_today': True,
        }
        return render(request, 'iCare/partials/tasks_list_partial.html', context)
        
    return JsonResponse({'success': True, 'message': 'Task completed!', 'reward': float(task.reward)})


@login_required
@require_http_methods(['POST'])
def daily_checkin(request):
    """Handle daily check-in bonus"""
    from decimal import Decimal
    checkin, created = UserCheckin.objects.get_or_create(user=request.user)
    
    # Check if already checked in today
    if checkin.last_checkin_date == date.today():
        if request.headers.get('HX-Request'):
            daily_bonus = 1.00 + (checkin.streak * 0.50)
            if daily_bonus > 10: daily_bonus = 10
            context = {
                'checkin_streak': checkin.streak,
                'daily_bonus': daily_bonus,
                'checked_in_today': True,
            }
            return render(request, 'iCare/partials/daily_checkin_partial.html', context)
        return JsonResponse({'success': False, 'message': 'Already checked in today'})
    
    # Calculate bonus based on streak
    if checkin.last_checkin_date == date.today() - timedelta(days=1):
        checkin.streak += 1
    else:
        checkin.streak = 1
    
    # Use Decimal to avoid type errors when adding to DecimalField
    bonus = Decimal('1.00') + (Decimal(min(checkin.streak, 10)) * Decimal('0.50'))
    if bonus > Decimal('10'):
        bonus = Decimal('10')
    
    checkin.last_checkin_date = date.today()
    checkin.total_checkins += 1
    checkin.save()
    
    # Credit bonus to wallet
    user_balance, _ = UserBalance.objects.get_or_create(
        user=request.user,
        defaults={'balance': 0, 'currency': 'GHS'}
    )
    user_balance.add_balance(bonus)
    
    if request.headers.get('HX-Request'):
        context = {
            'checkin_streak': checkin.streak,
            'daily_bonus': bonus,
            'checked_in_today': True,
        }
        return render(request, 'iCare/partials/daily_checkin_partial.html', context)
        
    return JsonResponse({'success': True, 'message': 'Check-in successful!', 'bonus': float(bonus), 'streak': checkin.streak})


@login_required
def check_in(request):
    """Display check-in page with streak information"""
    # Get or create check-in record
    checkin, created = UserCheckin.objects.get_or_create(user=request.user)
    
    # Calculate today's bonus based on streak
    if checkin.streak >= 10:
        today_bonus = 3.00
        next_streak_bonus = 3.00
    elif checkin.streak >= 7:
        today_bonus = 2.50
        next_streak_bonus = 2.50
    elif checkin.streak >= 5:
        today_bonus = 2.00
        next_streak_bonus = 2.00
    elif checkin.streak >= 3:
        today_bonus = 1.50
        next_streak_bonus = 2.00
    else:
        today_bonus = 1.00
        next_streak_bonus = 1.50
    
    # Check if user has checked in today
    has_checked_in_today = (checkin.last_checkin_date == date.today())
    
    # Calculate total check-ins
    total_checkins = checkin.total_checkins
    
    # Calculate total earned from check-ins (simplified)
    total_earned = total_checkins * 1.5  # Approximate average
    
    # Generate week days for calendar
    week_days = []
    today = date.today()
    for i in range(7):
        day_date = today + timedelta(days=i)
        week_days.append({
            'day_short': day_date.strftime('%a'),
            'day_num': day_date.day,
            'checked_in': checkin.last_checkin_date == day_date,
            'is_today': i == 0,
        })
    
    context = {
        'streak': checkin.streak,
        'today_bonus': today_bonus,
        'next_streak_bonus': next_streak_bonus,
        'has_checked_in_today': has_checked_in_today,
        'total_checkins': total_checkins,
        'total_earned': total_earned,
        'week_days': week_days,
    }
    return render(request, 'iCare/services/pages/check_in.html', context)



@login_required
def team(request):
    """Display team structure and referral information"""
    user = request.user
    
    # Get or create referral code
    referral_code, created = ReferralCode.objects.get_or_create(
        user=user,
        defaults={'code': generate_referral_code()}
    )
    
    # Get team member record
    team_member, created = TeamMember.objects.get_or_create(
        user=user,
        defaults={'sponsor': None, 'position': None}
    )
    
    # Calculate team statistics
    direct_downline = UserReferral.objects.filter(referrer=user, level=1).count()
    total_team = UserReferral.objects.filter(referrer=user).count()
    
    # Get left and right team counts
    left_team = TeamMember.objects.filter(sponsor=user, position='left').count()
    right_team = TeamMember.objects.filter(sponsor=user, position='right').count()
    
    # Calculate volumes
    left_volume = team_member.left_volume
    right_volume = team_member.right_volume
    weak_leg_volume = min(left_volume, right_volume)
    
    # Calculate commissions
    matching_bonus = weak_leg_volume * Decimal('0.10')  # 10% of weak leg
    flushed_amount = max(left_volume, right_volume) - weak_leg_volume
    
    # Get downline members with details
    downline_members = []
    referrals = UserReferral.objects.filter(referrer=user).select_related('referred_user')
    
    for ref in referrals:
        referred = ref.referred_user
        # Get referred user's team member record
        try:
            ref_team = TeamMember.objects.get(user=referred)
            position = ref_team.position
        except TeamMember.DoesNotExist:
            position = None
        
        # Get referred user's investment
        total_investment = UserInvestment.objects.filter(
            user=referred,
            status='active'
        ).aggregate(total=models.Sum('amount'))['total'] or 0
        
        downline_members.append({
            'id': referred.id,
            'full_name': f"{referred.profile.full_name}".strip() or str(referred.phone_number),
            'phone_number': str(referred.phone_number),
            'position': position,
            'investment': float(total_investment),
            'joined_date': ref.created_at,
            'is_active': hasattr(referred, 'team_member') and referred.team_member.is_active,
            'level': ref.level,
        })
    
    # Calculate total team volume
    team_volume = TeamMember.objects.filter(sponsor=user).aggregate(
        total=models.Sum('total_volume')
    )['total'] or 0
    
    # Calculate team earnings
    team_earnings = ReferralCommission.objects.filter(
        user=user,
        is_paid=True
    ).aggregate(total=models.Sum('amount'))['total'] or 0
    
    # Get recent team activities
    recent_activities = []
    
    # Recent joins
    recent_joins = UserReferral.objects.filter(
        referrer=user
    ).order_by('-created_at')[:5]
    
    for join in recent_joins:
        recent_activities.append({
            'type': 'join',
            'message': f"{join.referred_user.phone_number} joined your team",
            'time': join.created_at.strftime("%H:%M, %b %d")
        })
    
    # Recent investments from team members
    team_user_ids = UserReferral.objects.filter(referrer=user).values_list('referred_user_id', flat=True)
    recent_investments = UserInvestment.objects.filter(
        user_id__in=team_user_ids,
        status='active'
    ).order_by('-created_at')[:5]
    
    for inv in recent_investments:
        recent_activities.append({
            'type': 'investment',
            'message': f"{inv.user.phone_number} invested ₵{inv.amount:,.2f}",
            'time': inv.created_at.strftime("%H:%M, %b %d")
        })
    
    # Sort activities by time (most recent first)
    recent_activities.sort(key=lambda x: x['time'], reverse=True)
    recent_activities = recent_activities[:5]
    
    # Build referral link
    referral_link = request.build_absolute_uri(
        reverse('signup') + f'?ref={referral_code.code}'
    )
    
    context = {
        'total_team_members': total_team,
        'active_members': UserReferral.objects.filter(referrer=user, referred_user__is_active=True).count(),
        'team_volume': team_volume,
        'team_earnings': team_earnings,
        'left_team_count': left_team,
        'right_team_count': right_team,
        'left_volume': left_volume,
        'right_volume': right_volume,
        'weak_leg_volume': weak_leg_volume,
        'matching_bonus': matching_bonus,
        'flushed_amount': flushed_amount,
        'downline_members': downline_members,
        'recent_activities': recent_activities,
        'referral_link': referral_link,
        'referral_code': referral_code.code,
        'direct_downline': direct_downline,
        'levels': range(1, 6),  # Show up to level 5
    }
    return render(request, 'iCare/services/team.html', context)


# @login_required
# def process_referral_signup(request, referral_code):
#     """Process user signup with referral code"""
#     try:
#         referrer_code = ReferralCode.objects.get(code=referral_code)
#         referrer = referrer_code.user
        
#         # Don't allow self-referral
#         if referrer == request.user:
#             return
        
#         # Check if user already has a referrer
#         if hasattr(request.user, 'referred_by'):
#             return
        
#         # Create referral record (Level 1)
#         UserReferral.objects.create(
#             referrer=referrer,
#             referred_user=request.user,
#             level=1
#         )
        
#         # Process upline referrals (Level 2, 3, etc. up to level 10)
#         current_referrer = referrer
#         for level in range(2, 11):
#             # Check if current referrer has a referrer
#             try:
#                 upline_referral = UserReferral.objects.get(referred_user=current_referrer)
#                 upline_user = upline_referral.referrer
                
#                 # Create referral record for this level
#                 UserReferral.objects.create(
#                     referrer=upline_user,
#                     referred_user=request.user,
#                     level=level
#                 )
#                 current_referrer = upline_user
#             except UserReferral.DoesNotExist:
#                 break
        
#         # Create team member record
#         # Find available position in referrer's binary tree
#         position = None
#         try:
#             referrer_team = TeamMember.objects.get(user=referrer)
            
#             # Check if left position is available
#             if not referrer_team.left_child:
#                 position = 'left'
#                 referrer_team.left_child = request.user
#             # Check if right position is available
#             elif not referrer_team.right_child:
#                 position = 'right'
#                 referrer_team.right_child = request.user
#             else:
#                 # Both positions filled, find next available spot (simple algorithm)
#                 # You can implement more sophisticated placement logic here
#                 position = 'left'  # Default to left for now
            
#             referrer_team.save()
#         except TeamMember.DoesNotExist:
#             pass
        
#         # Create team member record for new user
#         TeamMember.objects.create(
#             user=request.user,
#             sponsor=referrer,
#             position=position
#         )
        
#         # Update volumes
#         try:
#             referrer_team = TeamMember.objects.get(user=referrer)
#             referrer_team.update_volumes()
#         except TeamMember.DoesNotExist:
#             pass
        
#     except ReferralCode.DoesNotExist:
#         pass


@login_required
def calculate_referral_commission(request, investment_id):
    """Calculate commission when a team member invests"""
    investment = UserInvestment.objects.get(id=investment_id)
    investor = investment.user
    
    # Get the investor's referrer chain
    referrals = UserReferral.objects.filter(referred_user=investor).order_by('level')
    
    for referral in referrals:
        commission_rate = 0
        if referral.level == 1:
            commission_rate = Decimal('0.10')  # 10% for direct referral
        elif referral.level == 2:
            commission_rate = Decimal('0.05')  # 5% for level 2
        elif referral.level == 3:
            commission_rate = Decimal('0.03')  # 3% for level 3
        elif referral.level >= 4:
            commission_rate = Decimal('0.01')  # 1% for level 4+
        
        commission_amount = investment.amount * commission_rate
        
        if commission_amount > 0:
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
            user_balance, _ = UserBalance.objects.get_or_create(user=referral.referrer)
            user_balance.add_balance(commission_amount)
    
    # Calculate binary commission
    try:
        investor_team = TeamMember.objects.get(user=investor)
        if investor_team.sponsor:
            sponsor_team = TeamMember.objects.get(user=investor_team.sponsor)
            sponsor_team.update_volumes()
            
            # Calculate binary commission
            weak_leg = min(sponsor_team.left_volume, sponsor_team.right_volume)
            binary_commission = weak_leg * Decimal('0.10')
            
            if binary_commission > 0:
                ReferralCommission.objects.create(
                    user=investor_team.sponsor,
                    from_user=investor,
                    amount=binary_commission,
                    commission_type='binary',
                    description=f"Binary commission from {investor.phone_number}'s investment"
                )
                
                user_balance, _ = UserBalance.objects.get_or_create(user=investor_team.sponsor)
                user_balance.add_balance(binary_commission)
    except TeamMember.DoesNotExist:
        pass


@login_required
def member_details(request):
    """AJAX endpoint to get member details"""
    member_id = request.GET.get('id')
    try:
        if member_id in ['left', 'right']:
            team_member = TeamMember.objects.filter(sponsor=request.user, position=member_id).first()
            if not team_member:
                raise TeamMember.DoesNotExist
            member = team_member.user
        else:
            member = User.objects.get(id=member_id)
            team_member = TeamMember.objects.get(user=member)
        
        total_investment = UserInvestment.objects.filter(
            user=member,
            status='active'
        ).aggregate(total=models.Sum('amount'))['total'] or 0
        
        data = {
            'id': str(member.id),
            'name': f"{member.first_name} {member.last_name}".strip() or str(member.phone_number),
            'phone': str(member.phone_number),
            'joined_date': member.date_joined.strftime("%b %d, %Y"),
            'position': team_member.position if team_member.position else 'N/A',
            'total_investment': f"{float(total_investment):,.2f}",
            'team_count': UserReferral.objects.filter(referrer=member).count(),
        }
        
        if request.headers.get('HX-Request'):
            return render(request, 'iCare/partials/member_details_partial.html', data)
            
        return JsonResponse(data)
    except (User.DoesNotExist, TeamMember.DoesNotExist, ValueError):
        if request.headers.get('HX-Request'):
            return HttpResponse('<div class="p-4 text-red-600">Member not found.</div>', status=404)
        return JsonResponse({'error': 'Member not found'}, status=404)