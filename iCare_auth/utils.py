# utils.py or directly in your views
from webpush import send_user_notification

def send_push_notification(user, title, message, url='/account/'):
    """Send push notification to a user"""
    try:
        payload = {
            'head': title,
            'body': message,
            'icon': '/static/imgs/icons/icon-192x192.png',
            'url': url
        }
        send_user_notification(user=user, payload=payload, ttl=86400)
        return True
    except Exception as e:
        print(f"Failed to send notification: {e}")
        return False

# Usage in your views:
# from .utils import send_push_notification
# 
# send_push_notification(
#     user=request.user,
#     title='Top-up Successful! 💰',
#     message=f'Your account has been credited with ₵{amount}',
#     url='/account/'
# )