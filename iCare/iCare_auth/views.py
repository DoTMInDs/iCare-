from django.shortcuts import render,redirect
from .forms import PhoneRegistrationForm
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from core.models import UserBalance
from django.contrib.auth.decorators import login_required

# Create your views here.
def signup(request):
    if request.method == 'POST':
        form = PhoneRegistrationForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Account created successfully!')
            return redirect('home')
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"Error in {field}: {error}")
    else:
        form = PhoneRegistrationForm()
    return render(request, 'auth/signup.html', {'form': form})

def login_view(request):
    if request.method == 'POST':
        phone_number = request.POST.get('phone')
        password = request.POST.get('password')
        user = authenticate(request, phone_number=phone_number, password=password)
        if user is not None:
            login(request, user)
            messages.success(request, 'Logged in successfully!')
            return redirect('home')  # Replace 'home' with your desired redirect URL
        # else:
        #     messages.error(request, 'Invalid phone number or password. Please try again.')
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
    
    # saved_accounts = SavedAccount.objects.filter(user=request.user)
    
    context = {
        'user_balance': user_balance,
        'user': request.user,
        # 'saved_accounts': saved_accounts,
    }
    return render(request, 'auth/profile.html', context)