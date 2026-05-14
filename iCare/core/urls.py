from django.urls import path
from . import views

urlpatterns = [
    path('home/', views.home, name='home'),
    path('product/', views.product, name='product'),
    path('account/', views.account, name='account'),
    path('recharge/', views.recharge, name='recharge'),
    path('withdraw/', views.withdrawal, name='withdraw'),
    path('tasks/', views.tasks, name='tasks'),
    path('check-in/', views.check_in, name='check_in'),

    path('recharge-records/', views.recharge_records, name='recharge_records'),
    path('withdrawal-records/', views.withdrawal_records, name='withdrawal_records'),
    path('withdrawal/cancel/<uuid:transaction_id>/', views.cancel_withdrawal, name='cancel_withdrawal'),
    
    # Payment handling
    path('payment/callback/', views.payment_callback, name='payment_callback'),
    path('payment/webhook/', views.payment_webhook, name='payment_webhook'),

    # product-related paths
    path('products/data/', views.get_products_data, name='get_products_data'),
    path('products/details/', views.product_details, name='product_details'),
    path('products/purchase/', views.purchase_product, name='purchase_product'),
    path('investments/', views.my_investments, name='my_investments'),
]
