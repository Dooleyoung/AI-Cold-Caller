"""
Basic system tests for AI Cold Calling System
"""
import pytest
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.crud import create_lead, get_lead, get_all_leads
from database.models import Base
from config.settings import settings
from utils.validators import validate_phone_number, validate_email_address
from utils.helpers import format_phone_display, parse_csv_file

def test_phone_validation():
    """Test phone number validation"""
    # Valid numbers
    result = validate_phone_number("+1234567890")
    assert result['valid'] == True
    
    result = validate_phone_number("(123) 456-7890")
    assert result['valid'] == True
    
    # Invalid numbers
    result = validate_phone_number("123")
    assert result['valid'] == False
    
    result = validate_phone_number("abc")
    assert result['valid'] == False

def test_email_validation():
    """Test email validation"""
    # Valid emails
    result = validate_email_address("test@example.com")
    assert result['valid'] == True
    
    # Invalid emails
    result = validate_email_address("invalid-email")
    assert result['valid'] == False
    
    result = validate_email_address("")
    assert result['valid'] == False

def test_phone_formatting():
    """Test phone number display formatting"""
    formatted = format_phone_display("+1234567890")
    assert "(" in formatted and ")" in formatted and "-" in formatted
    
    formatted = format_phone_display("1234567890")
    assert "(" in formatted and ")" in formatted and "-" in formatted

def test_csv_parsing():
    """Test CSV parsing functionality"""
    csv_content = "name,phone,email\nJohn Doe,1234567890,john@example.com\nJane Smith,0987654321,jane@example.com"
    
    result = parse_csv_file(csv_content)
    assert len(result) == 2
    assert result[0]['name'] == 'John Doe'
    assert result[0]['phone'] == '1234567890'
    assert result[0]['email'] == 'john@example.com'

def test_database_operations():
    """Test basic database operations"""
    # This would require setting up a test database
    # For now, just test that the functions exist and are callable
    assert callable(create_lead)
    assert callable(get_lead)
    assert callable(get_all_leads)

def test_settings_exist():
    """Test that required settings exist"""
    # Test that settings object exists
    assert settings is not None
    
    # Test that key settings have default values
    assert hasattr(settings, 'DATABASE_URL')
    assert hasattr(settings, 'WEBHOOK_BASE_URL')
    assert hasattr(settings, 'MAX_CALL_DURATION')

if __name__ == '__main__':
    pytest.main([__file__])