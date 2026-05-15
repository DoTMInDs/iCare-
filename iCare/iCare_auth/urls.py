from django.urls import path
from . import views

urlpatterns = [
    path('', views.login_view, name='login'),
    path('register/', views.signup, name='signup'),
    path('logout/', views.logout_view, name='logout'),
    path('profile/', views.profile, name='profile'),
    path('account/update/', views.update_profile, name='update_profile'),
    path('account/change-password/', views.change_password, name='change_password'),
]
