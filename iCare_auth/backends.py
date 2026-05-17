from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model

User = get_user_model()

class PhoneNumberBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        # username can be entered in any format: 0597362178, +233597362178, or 233597362178
        if username is None:
            username = kwargs.get('phone_number') or kwargs.get('phone')
            
        if not username:
            return None
            
        try:
            # PhoneNumberField will normalize it automatically when querying
            user = User.objects.get(phone_number=username)
        except User.DoesNotExist:
            return None
        
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None