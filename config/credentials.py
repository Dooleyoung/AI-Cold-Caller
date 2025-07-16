"""
Credential management and API key handling
"""
import os
from typing import Dict, Optional
from config.settings import settings

class CredentialManager:
    """Secure credential management"""
    
    def __init__(self):
        self._credentials: Dict[str, str] = {}
        self._load_credentials()
    
    def _load_credentials(self):
        """Load credentials from environment and validate"""
        self._credentials = {
            'twilio_sid': settings.TWILIO_ACCOUNT_SID,
            'twilio_token': settings.TWILIO_AUTH_TOKEN,
            'twilio_phone': settings.TWILIO_PHONE_NUMBER,
            'groq_api_key': settings.GROQ_API_KEY,
            'google_client_id': settings.GOOGLE_CLIENT_ID,
            'google_client_secret': settings.GOOGLE_CLIENT_SECRET,
        }
    
    def get_credential(self, key: str) -> Optional[str]:
        """Get a credential by key"""
        return self._credentials.get(key)
    
    def get_twilio_credentials(self) -> tuple:
        """Get Twilio credentials as tuple"""
        return (
            self.get_credential('twilio_sid'),
            self.get_credential('twilio_token'),
            self.get_credential('twilio_phone')
        )
    
    def get_groq_api_key(self) -> str:
        """Get Groq API key"""
        key = self.get_credential('groq_api_key')
        if not key:
            raise ValueError("Groq API key not configured")
        return key
    
    def get_google_credentials(self) -> tuple:
        """Get Google credentials as tuple"""
        return (
            self.get_credential('google_client_id'),
            self.get_credential('google_client_secret')
        )
    
    def validate_all_credentials(self) -> bool:
        """Validate that all required credentials are present"""
        required = ['twilio_sid', 'twilio_token', 'twilio_phone', 'groq_api_key']
        missing = [key for key in required if not self.get_credential(key)]
        
        if missing:
            raise ValueError(f"Missing credentials: {', '.join(missing)}")
        
        return True

# Global credential manager
credential_manager = CredentialManager()