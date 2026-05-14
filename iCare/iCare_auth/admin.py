from django.contrib import admin
from .models import UserProfile

# Register your models here.
@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'full_name', 'email', 'address', 'date_of_birth', 'created_at']
    search_fields = ['user__phone_number', 'full_name', 'email']
    readonly_fields = ['created_at', 'updated_at']