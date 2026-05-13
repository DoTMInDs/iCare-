from django import forms
from django.contrib.auth import get_user_model
from phonenumber_field.formfields import PhoneNumberField


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
        
        return cleaned_data
    
    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password'])
        if commit:
            user.save()
        return user