import requests
from decimal import Decimal
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


class PaystackService:
    """Service to handle Paystack payment integration."""
    
    BASE_URL = "https://api.paystack.co"
    
    def __init__(self):
        self.secret_key = getattr(settings, 'PAYSTACK_SECRET_KEY', '')
        self.public_key = getattr(settings, 'PAYSTACK_PUBLIC_KEY', '')
        if not self.secret_key:
            raise ValueError("PAYSTACK_SECRET_KEY is not configured in settings")
    
    def _get_headers(self):
        """Get headers for Paystack API requests."""
        return {
            'Authorization': f'Bearer {self.secret_key}',
            'Content-Type': 'application/json',
        }
    
    def initialize_payment(self, email, amount, reference, callback_url=None, metadata=None):
        """
        Initialize a Paystack payment.
        
        Args:
            email: Customer email
            amount: Amount in GHS (will be converted to Paystack pesewas - 1 GHS = 100 pesewas)
            reference: Unique reference for tracking
            callback_url: Optional URL to redirect after payment
            metadata: Optional dict with additional data
        
        Returns:
            dict with keys:
                - 'success': bool
                - 'authorization_url': payment URL (if successful)
                - 'access_code': Paystack access code (if successful)
                - 'reference': Paystack reference (if successful)
                - 'message': Status message
        """
        try:
            # Convert GHS to pesewas (1 GHS = 100 pesewas)
            amount_in_pesewas = int(Decimal(str(amount)) * 100)
            
            payload = {
                'email': email,
                'amount': amount_in_pesewas,
                'reference': reference,
                'metadata': metadata or {},
            }
            
            # Add callback URL if provided
            if callback_url:
                payload['callback_url'] = callback_url
            
            logger.info(f"Initializing Paystack payment for reference {reference}, amount {amount} GHS")
            response = requests.post(
                f'{self.BASE_URL}/transaction/initialize',
                json=payload,
                headers=self._get_headers(),
                timeout=10
            )
            
            data = response.json()
            logger.info(f"Paystack initialize response for {reference}: status {response.status_code}")
            
            if response.status_code == 200 and data.get('status'):
                result = data.get('data', {})
                logger.info(f"Payment initialized successfully for {reference}")
                return {
                    'success': True,
                    'authorization_url': result.get('authorization_url'),
                    'access_code': result.get('access_code'),
                    'reference': result.get('reference'),
                    'message': 'Payment initialized successfully',
                }
            else:
                logger.error(f"Paystack initialize failed for {reference}: {data.get('message')}")
                return {
                    'success': False,
                    'message': data.get('message', 'Payment initialization failed'),
                }
        
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error initializing payment for {reference}: {e}", exc_info=True)
            return {
                'success': False,
                'message': f'Network error: {str(e)}',
            }
        except Exception as e:
            logger.error(f"Unexpected error initializing payment for {reference}: {e}", exc_info=True)
            return {
                'success': False,
                'message': f'Error: {str(e)}',
            }
    
    def verify_payment(self, reference):
        """
        Verify a Paystack payment.
        
        Args:
            reference: Paystack payment reference
        
        Returns:
            dict with keys:
                - 'success': bool
                - 'status': Payment status (if verified)
                - 'amount': Amount paid (if verified)
                - 'message': Status message
        """
        try:
            logger.info(f"Verifying Paystack payment for reference {reference}")
            response = requests.get(
                f'{self.BASE_URL}/transaction/verify/{reference}',
                headers=self._get_headers(),
                timeout=10
            )
            
            data = response.json()
            logger.info(f"Paystack verify response for {reference}: status {response.status_code}")
            
            if response.status_code == 200 and data.get('status'):
                result = data.get('data', {})
                logger.info(f"Payment verified successfully for {reference}: status {result.get('status')}")
                return {
                    'success': True,
                    'status': result.get('status'),
                    'amount': result.get('amount') / 100,  # Convert back to GHS
                    'customer_code': result.get('customer', {}).get('customer_code'),
                    'message': 'Payment verified',
                }
            else:
                logger.error(f"Paystack verify failed for {reference}: {data.get('message')}")
                return {
                    'success': False,
                    'message': data.get('message', 'Payment verification failed'),
                }
        
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error verifying payment for {reference}: {e}", exc_info=True)
            return {
                'success': False,
                'message': f'Network error: {str(e)}',
            }
        except Exception as e:
            logger.error(f"Unexpected error verifying payment for {reference}: {e}", exc_info=True)
            return {
                'success': False,
                'message': f'Error: {str(e)}',
            }
