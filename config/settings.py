"""
Application settings and configuration
"""
import os
from typing import Optional
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    
    # Database
    DATABASE_URL: str = "sqlite:///ai_cold_caller.db"
    
    # Twilio Configuration
    TWILIO_ACCOUNT_SID: Optional[str] = None
    TWILIO_AUTH_TOKEN: Optional[str] = None
    TWILIO_PHONE_NUMBER: Optional[str] = None
    
    # Groq API
    GROQ_API_KEY: Optional[str] = None
    
    # Google Calendar API
    GOOGLE_CLIENT_ID: Optional[str] = None
    GOOGLE_CLIENT_SECRET: Optional[str] = None
    GOOGLE_CREDENTIALS_FILE: str = "credentials.json"
    
    # Application
    WEBHOOK_BASE_URL: str = "http://localhost:5000"
    SECRET_KEY: str = "your-secret-key-change-in-production"
    DEBUG: bool = True
    
    # Redis for Celery
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # Call Settings
    MAX_CALL_DURATION: int = 300  # 5 minutes
    MAX_RETRY_ATTEMPTS: int = 3
    CALL_TIMEOUT: int = 30  # seconds
    
    # AI Settings
    AI_RESPONSE_MAX_TOKENS: int = 150
    AI_TEMPERATURE: float = 0.7
    
    # Voice Settings
    DEFAULT_VOICE: str = "af_sarah"
    TTS_SAMPLE_RATE: int = 24000
    
    # ===========================================
    # EMAIL & SMS NOTIFICATION SETTINGS
    # ===========================================
    
    # Notification Recipients
    NOTIFICATION_EMAIL: Optional[str] = None  # Where to send meeting notifications
    
    # SMTP Email Settings (choose one: SMTP or SendGrid)
    SMTP_SERVER: Optional[str] = None  # e.g., "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USE_TLS: bool = True
    SMTP_USERNAME: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None  # Use app password for Gmail
    SMTP_FROM_EMAIL: Optional[str] = None  # Email address to send from
    
    # SendGrid Settings (alternative to SMTP)
    SENDGRID_API_KEY: Optional[str] = None
    SENDGRID_FROM_EMAIL: Optional[str] = None
    
    class Config:
        env_file = ".env"
        case_sensitive = False

# Global settings instance
settings = Settings()

# Validation
def validate_settings():
    """Validate that all required settings are present"""
    required_settings = [
        'TWILIO_ACCOUNT_SID',
        'TWILIO_AUTH_TOKEN', 
        'TWILIO_PHONE_NUMBER',
        'GROQ_API_KEY'
    ]
    
    missing = []
    for setting in required_settings:
        if not getattr(settings, setting):
            missing.append(setting)
    
    if missing:
        print(f"⚠️  Warning: Missing optional environment variables: {', '.join(missing)}")
        print("   You can add these later when you get the API keys")
    else:
        print("✅ All required settings present")
    
    # Check notification settings
    if settings.NOTIFICATION_EMAIL:
        email_configured = bool(
            (settings.SMTP_SERVER and settings.SMTP_FROM_EMAIL) or
            (settings.SENDGRID_API_KEY and settings.SENDGRID_FROM_EMAIL)
        )
        
        if email_configured:
            print("✅ Email notifications configured")
        else:
            print("⚠️  NOTIFICATION_EMAIL set but no email service configured")
            print("   Configure either SMTP or SendGrid settings")
    
    if settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN:
        print("✅ SMS notifications available via Twilio")

# Export settings
__all__ = ['settings', 'validate_settings']