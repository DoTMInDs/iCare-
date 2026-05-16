from django.urls import path
from . import views

urlpatterns = [
    path('', views.login_view, name='login'),
    path('register/', views.signup, name='signup'),
    path('logout/', views.logout_view, name='logout'),
    path('profile/', views.profile, name='profile'),
    path('account/update/', views.update_profile, name='update_profile'),
    path('account/change-password/', views.change_password, name='change_password'),
    
    path('api/save-notification-preference/', views.save_notification_preference, name='save_notification_preference'),
    path('api/get-notification-preference/', views.get_notification_preference, name='get_notification_preference'),
    path('api/send-test-notification/', views.send_test_notification, name='send_test_notification'),
]
