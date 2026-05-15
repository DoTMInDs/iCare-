from django import forms
from django.contrib.auth import get_user_model
from phonenumber_field.formfields import PhoneNumberField
from .models import UserProfile
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm


User = get_user_model()

class PhoneRegistrationForm(forms.ModelForm):
    phone_number = PhoneNumberField(
        region='GH',
        widget=forms.TextInput(attrs={'placeholder': '0597362178 or +233597362178'})
    )
    password = forms.CharField(widget=forms.PasswordInput)
    confirm_password = forms.CharField(widget=forms.PasswordInput)
    
    class Meta:
        model = User
        fields = ['phone_number', 'password', 'confirm_password']

    def clean_phone_number(self):
        phone_number = self.cleaned_data.get('phone_number')
        if User.objects.filter(phone_number=phone_number).exists():
            raise forms.ValidationError('Phone number already registered')
        return phone_number
    
    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        confirm_password = cleaned_data.get('confirm_password')
        
        if password and confirm_password and password != confirm_password:
            raise forms.ValidationError('Passwords do not match')
        
        if password and len(password) < 8:
            raise forms.ValidationError('Password must be at least 8 characters long')
        
        return cleaned_data
    
    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password'])
        user.username = str(self.cleaned_data['phone_number'])
        if commit:
            user.save()
        return user
    
class UserProfileForm(forms.ModelForm):
    """Form for updating user profile information"""
    full_name = forms.CharField(
        max_length=255,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-3 text-slate-600 border border-gray-200 rounded-xl focus:outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100',
            'placeholder': 'Enter your full name'
        })
    )
    email = forms.EmailField(
        required=False,
        widget=forms.EmailInput(attrs={
            'class': 'w-full px-4 py-3 text-slate-600 border border-gray-200 rounded-xl focus:outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100',
            'placeholder': 'Enter email address'
        })
    )
    
    class Meta:
        model = UserProfile
        fields = ['full_name', 'email', 'date_of_birth', 'address']
        widgets = {
            'date_of_birth': forms.DateInput(attrs={
                'type': 'date',
                'class': 'w-full px-4 py-3 text-slate-600 border border-gray-200 rounded-xl focus:outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100'
            }),
            'address': forms.Textarea(attrs={
                'class': 'w-full px-4 py-3 text-slate-600 border border-gray-200 rounded-xl focus:outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100',
                'rows': 3,
                'placeholder': 'Enter your address'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # If user instance is provided, populate initial data
        if self.user:
            # Get or create profile to get existing values
            try:
                profile = self.user.profile
                if not self.instance.id:
                    self.instance = profile
            except UserProfile.DoesNotExist:
                pass
    
    def clean_email(self):
        email = self.cleaned_data.get('email')
        if email and self.user:
            # Check if email is taken by another user
            if User.objects.exclude(id=self.user.id).filter(email=email).exists():
                raise forms.ValidationError('This email is already in use by another account.')
        return email
    
    def save(self, commit=True):
        # Save user email
        if self.user:
            self.user.email = self.cleaned_data.get('email', '')
            if commit:
                self.user.save()
        
        # Save profile data
        profile = super().save(commit=False)
        profile.user = self.user
        if commit:
            profile.save()
        return profile


class CustomPasswordChangeForm(PasswordChangeForm):
    """Custom password change form with better styling"""
    old_password = forms.CharField(
        label='Current Password',
        widget=forms.PasswordInput(attrs={
            'class': 'w-full px-4 py-3 text-slate-600 border border-gray-200 rounded-xl focus:outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100',
            'placeholder': 'Enter current password'
        })
    )
    new_password1 = forms.CharField(
        label='New Password',
        widget=forms.PasswordInput(attrs={
            'class': 'w-full px-4 py-3 text-slate-600 border border-gray-200 rounded-xl focus:outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100',
            'placeholder': 'Enter new password'
        })
    )
    new_password2 = forms.CharField(
        label='Confirm New Password',
        widget=forms.PasswordInput(attrs={
            'class': 'w-full px-4 py-3 text-slate-600 border border-gray-200 rounded-xl focus:outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100',
            'placeholder': 'Confirm new password'
        })
    )
    
    def clean_new_password2(self):
        password1 = self.cleaned_data.get('new_password1')
        password2 = self.cleaned_data.get('new_password2')
        
        if password1 and password2 and password1 != password2:
            raise forms.ValidationError('Passwords do not match.')
        
        if password1 and len(password1) < 6:
            raise forms.ValidationError('Password must be at least 6 characters long.')
        
        return password2