"""
Helper utilities and common functions
"""
import csv
import io
import json
import secrets
import string
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional, Union
import hashlib
import base64

def generate_secure_token(length: int = 32) -> str:
    """Generate a secure random token"""
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))

def hash_phone_number(phone: str) -> str:
    """Hash phone number for privacy/deduplication"""
    return hashlib.sha256(phone.encode()).hexdigest()[:16]

def format_duration(seconds: int) -> str:
    """Format duration in seconds to human readable format"""
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        minutes = seconds // 60
        remaining_seconds = seconds % 60
        return f"{minutes}m {remaining_seconds}s"
    else:
        hours = seconds // 3600
        remaining_minutes = (seconds % 3600) // 60
        return f"{hours}h {remaining_minutes}m"

def format_phone_display(phone: str) -> str:
    """Format phone number for display"""
    # Remove non-digits
    digits = ''.join(filter(str.isdigit, phone))
    
    if len(digits) == 11 and digits.startswith('1'):
        digits = digits[1:]  # Remove country code
    
    if len(digits) == 10:
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    else:
        return phone  # Return original if can't format

def parse_csv_file(file_content: str, has_header: bool = True) -> List[Dict[str, Any]]:
    """Parse CSV file content into list of dictionaries"""
    try:
        csv_reader = csv.DictReader(io.StringIO(file_content)) if has_header else csv.reader(io.StringIO(file_content))
        
        if has_header:
            return list(csv_reader)
        else:
            # If no header, assume: name, phone, email, company
            rows = list(csv_reader)
            result = []
            for row in rows:
                if len(row) >= 2:
                    lead_data = {
                        'name': row[0],
                        'phone': row[1],
                        'email': row[2] if len(row) > 2 else '',
                        'company': row[3] if len(row) > 3 else ''
                    }
                    result.append(lead_data)
            return result
    
    except Exception as e:
        raise ValueError(f"Error parsing CSV: {str(e)}")

def export_to_csv(data: List[Dict[str, Any]], filename: str = None) -> str:
    """Export data to CSV format"""
    if not data:
        return ""
    
    output = io.StringIO()
    
    # Get all unique keys from all dictionaries
    fieldnames = set()
    for item in data:
        fieldnames.update(item.keys())
    
    fieldnames = sorted(list(fieldnames))
    
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(data)
    
    return output.getvalue()

def safe_json_loads(json_str: str, default: Any = None) -> Any:
    """Safely parse JSON string with fallback"""
    try:
        return json.loads(json_str)
    except (json.JSONDecodeError, TypeError):
        return default

def safe_json_dumps(obj: Any, default: str = "{}") -> str:
    """Safely serialize object to JSON with fallback"""
    try:
        return json.dumps(obj, default=str)  # default=str handles datetime objects
    except (TypeError, ValueError):
        return default

def calculate_business_hours_between(start_time: datetime, end_time: datetime) -> float:
    """Calculate business hours between two datetime objects"""
    business_start = 9  # 9 AM
    business_end = 17   # 5 PM
    
    total_hours = 0.0
    current = start_time.replace(hour=business_start, minute=0, second=0, microsecond=0)
    
    while current.date() <= end_time.date():
        # Skip weekends
        if current.weekday() >= 5:
            current += timedelta(days=1)
            continue
        
        day_start = max(current.replace(hour=business_start, minute=0, second=0, microsecond=0), start_time)
        day_end = min(current.replace(hour=business_end, minute=0, second=0, microsecond=0), end_time)
        
        if day_start < day_end:
            total_hours += (day_end - day_start).total_seconds() / 3600
        
        current += timedelta(days=1)
    
    return total_hours

def get_business_day_offset(base_date: datetime, business_days: int) -> datetime:
    """Get date that is N business days from base date"""
    current_date = base_date
    days_added = 0
    
    while days_added < business_days:
        current_date += timedelta(days=1)
        # Count only weekdays
        if current_date.weekday() < 5:
            days_added += 1
    
    return current_date

def mask_sensitive_data(data: str, mask_char: str = "*", reveal_last: int = 4) -> str:
    """Mask sensitive data like phone numbers"""
    if len(data) <= reveal_last:
        return mask_char * len(data)
    
    return mask_char * (len(data) - reveal_last) + data[-reveal_last:]

def calculate_call_success_rate(total_calls: int, successful_calls: int) -> float:
    """Calculate call success rate percentage"""
    if total_calls == 0:
        return 0.0
    return round((successful_calls / total_calls) * 100, 2)

def time_until_next_business_hour() -> timedelta:
    """Calculate time until next business hour"""
    now = datetime.now()
    
    # If it's a weekday during business hours, return 0
    if now.weekday() < 5 and 9 <= now.hour < 17:
        return timedelta(0)
    
    # Find next business hour
    next_business = now.replace(hour=9, minute=0, second=0, microsecond=0)
    
    # If it's after business hours today, move to tomorrow
    if now.hour >= 17:
        next_business += timedelta(days=1)
    
    # Skip weekends
    while next_business.weekday() >= 5:
        next_business += timedelta(days=1)
    
    return next_business - now

def chunk_list(lst: List[Any], chunk_size: int) -> List[List[Any]]:
    """Split list into chunks of specified size"""
    return [lst[i:i + chunk_size] for i in range(0, len(lst), chunk_size)]

def merge_dicts(dict1: Dict[str, Any], dict2: Dict[str, Any]) -> Dict[str, Any]:
    """Safely merge two dictionaries"""
    result = dict1.copy()
    result.update(dict2)
    return result

def retry_on_exception(max_retries: int = 3, delay: float = 1.0):
    """Decorator to retry function on exception"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries:
                        import time
                        time.sleep(delay * (2 ** attempt))  # Exponential backoff
                    continue
            
            raise last_exception
        
        return wrapper
    return decorator

def validate_time_range(start_time: str, end_time: str) -> bool:
    """Validate that time range is valid (HH:MM format)"""
    try:
        start_hour, start_min = map(int, start_time.split(':'))
        end_hour, end_min = map(int, end_time.split(':'))
        
        if not (0 <= start_hour <= 23 and 0 <= start_min <= 59):
            return False
        if not (0 <= end_hour <= 23 and 0 <= end_min <= 59):
            return False
        
        start_minutes = start_hour * 60 + start_min
        end_minutes = end_hour * 60 + end_min
        
        return start_minutes < end_minutes
    
    except (ValueError, AttributeError):
        return False

def get_timezone_offset(timezone_name: str = "UTC") -> int:
    """Get timezone offset in hours"""
    try:
        import pytz
        tz = pytz.timezone(timezone_name)
        now = datetime.now(tz)
        return int(now.utcoffset().total_seconds() / 3600)
    except:
        return 0  # Default to UTC

def sanitize_for_filename(text: str, max_length: int = 50) -> str:
    """Sanitize text for use in filename"""
    import re
    
    # Remove non-alphanumeric characters except spaces and dashes
    sanitized = re.sub(r'[^\w\s-]', '', text)
    
    # Replace spaces with underscores
    sanitized = re.sub(r'\s+', '_', sanitized)
    
    # Remove consecutive underscores
    sanitized = re.sub(r'_+', '_', sanitized)
    
    # Trim and limit length
    sanitized = sanitized.strip('_')[:max_length]
    
    return sanitized

class RateLimiter:
    """Simple rate limiter class"""
    
    def __init__(self, max_calls: int, time_window: int):
        """
        max_calls: Maximum number of calls allowed
        time_window: Time window in seconds
        """
        self.max_calls = max_calls
        self.time_window = time_window
        self.calls = []
    
    def is_allowed(self) -> bool:
        """Check if a call is allowed under rate limit"""
        now = datetime.now()
        
        # Remove old calls outside the time window
        cutoff = now - timedelta(seconds=self.time_window)
        self.calls = [call_time for call_time in self.calls if call_time > cutoff]
        
        # Check if we're under the limit
        if len(self.calls) < self.max_calls:
            self.calls.append(now)
            return True
        
        return False
    
    def time_until_next_call(self) -> Optional[float]:
        """Get seconds until next call is allowed"""
        if not self.calls:
            return 0
        
        oldest_call = min(self.calls)
        next_allowed = oldest_call + timedelta(seconds=self.time_window)
        now = datetime.now()
        
        if next_allowed <= now:
            return 0
        
        return (next_allowed - now).total_seconds()

# Export
__all__ = [
    'generate_secure_token', 'hash_phone_number', 'format_duration', 'format_phone_display',
    'parse_csv_file', 'export_to_csv', 'safe_json_loads', 'safe_json_dumps',
    'calculate_business_hours_between', 'get_business_day_offset', 'mask_sensitive_data',
    'calculate_call_success_rate', 'time_until_next_business_hour', 'chunk_list',
    'merge_dicts', 'retry_on_exception', 'validate_time_range', 'get_timezone_offset',
    'sanitize_for_filename', 'RateLimiter'
]