from django import template
from django.conf import settings

register = template.Library()

@register.inclusion_tag('webpush_radio_button.html', takes_context=True)
def webpush_radio_button(context):
    request = context['request']
    
    return {
        'request': request,
        'vapid_public_key': settings.WEBPUSH_SETTINGS['VAPID_PUBLIC_KEY'],
    }