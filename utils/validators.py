"""
Input validation utilities
"""
import re
import phonenumbers
from typing import Dict, List, Any, Optional
from email_validator import validate_email, EmailNotValidError

def validate_phone_number(phone: str) -> Dict[str, Any]:
    """Validate and format phone number"""
    result = {
        'valid': False,
        'formatted': '',
        'country': '',
        'type': '',
        'error': ''
    }
    
    try:
        # Clean the input
        cleaned_phone = re.sub(r'[^\d+]', '', phone)
        
        # Parse with phonenumbers library
        parsed = phonenumbers.parse(cleaned_phone, "US")  # Default to US
        
        if phonenumbers.is_valid_number(parsed):
            result['valid'] = True
            result['formatted'] = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
            result['country'] = phonenumbers.region_code_for_number(parsed)
            result['type'] = phonenumbers.number_type(parsed).name
        else:
            result['error'] = 'Invalid phone number format'
            
    except phonenumbers.NumberParseException as e:
        result['error'] = f'Phone parsing error: {e.error_type.name}'
    except Exception as e:
        result['error'] = f'Unexpected error: {str(e)}'
    
    return result

def validate_email_address(email: str) -> Dict[str, Any]:
    """Validate email address"""
    result = {
        'valid': False,
        'normalized': '',
        'error': ''
    }
    
    try:
        if not email or not email.strip():
            result['error'] = 'Email is required'
            return result
        
        validated_email = validate_email(email.strip())
        result['valid'] = True
        result['normalized'] = validated_email.email
        
    except EmailNotValidError as e:
        result['error'] = str(e)
    except Exception as e:
        result['error'] = f'Unexpected error: {str(e)}'
    
    return result

def validate_lead_data(lead_data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate lead data before database insertion"""
    result = {
        'valid': True,
        'errors': {},
        'warnings': [],
        'cleaned_data': {}
    }
    
    try:
        # Required fields
        required_fields = ['name', 'phone']
        for field in required_fields:
            if not lead_data.get(field, '').strip():
                result['errors'][field] = f'{field.title()} is required'
                result['valid'] = False
        
        # Clean and validate name
        if 'name' in lead_data:
            name = lead_data['name'].strip().title()
            if len(name) < 2:
                result['errors']['name'] = 'Name must be at least 2 characters'
                result['valid'] = False
            elif len(name) > 100:
                result['errors']['name'] = 'Name must be less than 100 characters'
                result['valid'] = False
            else:
                result['cleaned_data']['name'] = name
        
        # Validate phone
        if 'phone' in lead_data:
            phone_validation = validate_phone_number(lead_data['phone'])
            if phone_validation['valid']:
                result['cleaned_data']['phone'] = phone_validation['formatted']
            else:
                result['errors']['phone'] = phone_validation['error']
                result['valid'] = False
        
        # Validate email if provided
        if lead_data.get('email', '').strip():
            email_validation = validate_email_address(lead_data['email'])
            if email_validation['valid']:
                result['cleaned_data']['email'] = email_validation['normalized']
            else:
                result['warnings'].append(f"Invalid email: {email_validation['error']}")
                result['cleaned_data']['email'] = ''
        
        # Clean company name
        if lead_data.get('company', '').strip():
            company = lead_data['company'].strip()
            if len(company) > 100:
                result['warnings'].append('Company name truncated to 100 characters')
                company = company[:100]
            result['cleaned_data']['company'] = company
        
        # Validate priority
        priority = lead_data.get('priority', 1)
        try:
            priority = int(priority)
            if priority < 1 or priority > 4:
                result['warnings'].append('Priority must be between 1-4, defaulting to 1')
                priority = 1
        except (ValueError, TypeError):
            result['warnings'].append('Invalid priority value, defaulting to 1')
            priority = 1
        result['cleaned_data']['priority'] = priority
        
        # Clean industry and title
        for field in ['industry', 'title', 'notes']:
            if lead_data.get(field, '').strip():
                value = lead_data[field].strip()
                max_length = 50 if field != 'notes' else 500
                if len(value) > max_length:
                    result['warnings'].append(f'{field.title()} truncated to {max_length} characters')
                    value = value[:max_length]
                result['cleaned_data'][field] = value
        
    except Exception as e:
        result['valid'] = False
        result['errors']['general'] = f'Validation error: {str(e)}'
    
    return result

def validate_csv_headers(headers: List[str]) -> Dict[str, Any]:
    """Validate CSV headers for lead import"""
    result = {
        'valid': True,
        'errors': [],
        'warnings': [],
        'mapping': {}
    }
    
    # Required headers (case-insensitive)
    required_headers = ['name', 'phone']
    optional_headers = ['email', 'company', 'industry', 'title', 'priority', 'notes']
    
    # Normalize headers
    normalized_headers = [h.lower().strip() for h in headers]
    
    # Check for required headers
    for required in required_headers:
        if required not in normalized_headers:
            result['errors'].append(f'Required header missing: {required}')
            result['valid'] = False
    
    # Create mapping
    for i, header in enumerate(headers):
        normalized = header.lower().strip()
        if normalized in required_headers + optional_headers:
            result['mapping'][normalized] = i
        else:
            result['warnings'].append(f'Unknown header will be ignored: {header}')
    
    return result

def sanitize_filename(filename: str) -> str:
    """Sanitize filename for safe storage"""
    # Remove path components
    filename = os.path.basename(filename)
    
    # Replace dangerous characters
    filename = re.sub(r'[^\w\-_\.]', '_', filename)
    
    # Limit length
    if len(filename) > 255:
        name, ext = os.path.splitext(filename)
        filename = name[:251] + ext
    
    return filename

def validate_twilio_webhook(data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate Twilio webhook data"""
    result = {
        'valid': True,
        'errors': [],
        'call_sid': '',
        'call_status': '',
        'from_number': '',
        'to_number': ''
    }
    
    # Required Twilio fields
    required_fields = ['CallSid', 'CallStatus']
    
    for field in required_fields:
        if field not in data:
            result['errors'].append(f'Missing required field: {field}')
            result['valid'] = False
    
    if result['valid']:
        result['call_sid'] = data['CallSid']
        result['call_status'] = data['CallStatus']
        result['from_number'] = data.get('From', '')
        result['to_number'] = data.get('To', '')
    
    return result

def validate_google_meet_request(data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate Google Meet meeting request"""
    result = {
        'valid': True,
        'errors': {},
        'cleaned_data': {}
    }
    
    # Validate lead info
    if 'lead_info' not in data:
        result['errors']['lead_info'] = 'Lead information is required'
        result['valid'] = False
    else:
        lead_info = data['lead_info']
        if not lead_info.get('name'):
            result['errors']['lead_name'] = 'Lead name is required'
            result['valid'] = False
        
        if lead_info.get('email'):
            email_validation = validate_email_address(lead_info['email'])
            if not email_validation['valid']:
                result['errors']['lead_email'] = email_validation['error']
                result['valid'] = False
    
    # Validate duration
    duration = data.get('duration_minutes', 30)
    try:
        duration = int(duration)
        if duration < 15 or duration > 180:
            result['errors']['duration'] = 'Duration must be between 15-180 minutes'
            result['valid'] = False
    except (ValueError, TypeError):
        result['errors']['duration'] = 'Invalid duration value'
        result['valid'] = False
    
    result['cleaned_data']['duration_minutes'] = duration
    
    return result

# Export
__all__ = [
    'validate_phone_number',
    'validate_email_address', 
    'validate_lead_data',
    'validate_csv_headers',
    'sanitize_filename',
    'validate_twilio_webhook',
    'validate_google_meet_request'
]