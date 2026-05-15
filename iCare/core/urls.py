from django.urls import path
from . import views

urlpatterns = [
    path('home/', views.home, name='home'),
    path('withdraw/', views.withdrawal, name='withdraw'),
    path('check-in/', views.check_in, name='check_in'),

    path('recharge/', views.recharge, name='recharge'),
    path('recharge-records/', views.recharge_records, name='recharge_records'),
    path('withdrawal-records/', views.withdrawal_records, name='withdrawal_records'),
    path('withdrawal/cancel/<uuid:transaction_id>/', views.cancel_withdrawal, name='cancel_withdrawal'),
    
    # Payment handling
    path('payment/callback/', views.payment_callback, name='payment_callback'),
    path('payment/webhook/', views.payment_webhook, name='payment_webhook'),

   
    # product-related paths
    path('product/', views.product, name='product'),
    path('products/data/', views.get_products_data, name='get_products_data'),
    path('products/details/', views.product_details, name='product_details'),
    path('products/purchase/', views.purchase_product, name='purchase_product'),
    path('product/payment-callback/', views.product_payment_callback, name='product_payment_callback'),
    path('product/payment-webhook/', views.product_payment_webhook, name='product_payment_webhook'),
    path('my-investments/', views.my_investments, name='my_investments'),

    # Saved Account URLs
    path('account/balance/', views.account_balance, name='account'),
    path('account/add-account/', views.add_saved_account, name='add_saved_account'),
    path('account/set-default/<uuid:account_id>/', views.set_default_account, name='set_default_account'),
    path('account/delete-account/<uuid:account_id>/', views.delete_saved_account, name='delete_saved_account'),
    path('account/saved-accounts/json/', views.get_saved_accounts_json, name='get_saved_accounts_json'),
    path('account/saved-payment-methods/', views.saved_payment_methods, name='saved_payment_methods'),

    # Task-related URLs
    path('tasks/', views.tasks, name='tasks'),
    path('tasks/details/', views.task_details, name='task_details'),
    path('tasks/complete/', views.complete_task, name='complete_task'),
    path('tasks/checkin/', views.daily_checkin, name='daily_checkin'),

    # Team URLs
    path('team/', views.team, name='team'),
    path('member-details/', views.member_details, name='member_details'),
]
