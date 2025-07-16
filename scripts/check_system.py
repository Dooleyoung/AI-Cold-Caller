#!/usr/bin/env python3
"""
System health check script
"""
import os
import sys
import requests
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import settings, validate_settings
from config.credentials import credential_manager
from database.crud import get_db, get_call_statistics
from scheduler.call_scheduler import call_scheduler

def check_configuration():
    """Check system configuration"""
    print("🔧 Checking configuration...")
    
    try:
        validate_settings()
        print("  ✅ Configuration valid")
        return True
    except Exception as e:
        print(f"  ❌ Configuration error: {e}")
        return False

def check_credentials():
    """Check API credentials"""
    print("🔑 Checking credentials...")
    
    try:
        # Check Groq API
        groq_key = credential_manager.get_groq_api_key()
        if groq_key:
            print("  ✅ Groq API key present")
        else:
            print("  ❌ Groq API key missing")
            return False
        
        # Check Twilio credentials
        sid, token, phone = credential_manager.get_twilio_credentials()
        if sid and token and phone:
            print("  ✅ Twilio credentials present")
        else:
            print("  ❌ Twilio credentials missing")
            return False
        
        return True
        
    except Exception as e:
        print(f"  ❌ Credential check failed: {e}")
        return False

def check_database():
    """Check database connectivity"""
    print("🗃️  Checking database...")
    
    try:
        db = get_db()
        
        # Try a simple query
        stats = get_call_statistics(days=1)
        
        db.close()
        print("  ✅ Database accessible")
        return True
        
    except Exception as e:
        print(f"  ❌ Database error: {e}")
        return False

def check_external_services():
    """Check external service connectivity"""
    print("🌐 Checking external services...")
    
    results = []
    
    # Check Groq API
    try:
        from groq import Groq
        client = Groq(api_key=credential_manager.get_groq_api_key())
        
        # Try a simple request
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": "test"}],
            max_completion_tokens=1
        )
        
        print("  ✅ Groq API accessible")
        results.append(True)
        
    except Exception as e:
        print(f"  ❌ Groq API error: {e}")
        results.append(False)
    
    # Check Twilio API
    try:
        from twilio.rest import Client
        
        sid, token, phone = credential_manager.get_twilio_credentials()
        client = Client(sid, token)
        
        # Test account access
        account = client.api.accounts(sid).fetch()
        
        print("  ✅ Twilio API accessible")
        results.append(True)
        
    except Exception as e:
        print(f"  ❌ Twilio API error: {e}")
        results.append(False)
    
    return all(results)

def check_file_system():
    """Check file system permissions and directories"""
    print("📁 Checking file system...")
    
    required_dirs = ['logs', 'data', 'voice']
    results = []
    
    for directory in required_dirs:
        if os.path.exists(directory):
            if os.access(directory, os.R_OK | os.W_OK):
                print(f"  ✅ {directory}/ directory accessible")
                results.append(True)
            else:
                print(f"  ❌ {directory}/ directory not writable")
                results.append(False)
        else:
            print(f"  ⚠️  {directory}/ directory missing (will be created)")
            results.append(True)  # Not critical
    
    # Check for Dia_TTS.py
    dia_tts_path = os.path.join('voice', 'Dia_TTS.py')
    if os.path.exists(dia_tts_path):
        print("  ✅ Dia_TTS.py found")
        results.append(True)
    else:
        print("  ⚠️  Dia_TTS.py not found in voice/ directory")
        results.append(False)
    
    return all(results)

def check_scheduler():
    """Check scheduler status"""
    print("⏰ Checking scheduler...")
    
    try:
        status = call_scheduler.get_status()
        
        if status['running']:
            print("  ✅ Scheduler is running")
            print(f"  📊 Active calls: {status['active_calls']}")
        else:
            print("  ⚠️  Scheduler is stopped")
        
        return True
        
    except Exception as e:
        print(f"  ❌ Scheduler check failed: {e}")
        return False

def generate_report():
    """Generate system health report"""
    print("\n📋 System Health Report")
    print("=" * 40)
    print(f"Generated: {datetime.now()}")
    print(f"Python: {sys.version}")
    print(f"Platform: {sys.platform}")
    print(f"Working Directory: {os.getcwd()}")
    
    try:
        stats = get_call_statistics(days=7)
        print(f"\n📊 Last 7 Days Statistics:")
        print(f"  Total Calls: {stats.get('total_calls', 0)}")
        print(f"  Answered Calls: {stats.get('answered_calls', 0)}")
        print(f"  Meetings Scheduled: {stats.get('meetings_scheduled', 0)}")
        print(f"  Answer Rate: {stats.get('answer_rate', 0)}%")
        print(f"  Meeting Rate: {stats.get('meeting_rate', 0)}%")
    except:
        print("\n⚠️  Could not retrieve statistics")

def main():
    """Main health check function"""
    print("🏥 AI Cold Calling System - Health Check")
    print("=" * 50)
    
    checks = [
        ("Configuration", check_configuration),
        ("Credentials", check_credentials),
        ("Database", check_database),
        ("File System", check_file_system),
        ("External Services", check_external_services),
        ("Scheduler", check_scheduler),
    ]
    
    results = []
    
    for name, check_func in checks:
        try:
            result = check_func()
            results.append(result)
        except Exception as e:
            print(f"❌ {name} check failed with exception: {e}")
            results.append(False)
        print()
    
    # Generate report
    generate_report()
    
    # Summary
    passed = sum(results)
    total = len(results)
    
    print(f"\n🏁 Health Check Summary: {passed}/{total} checks passed")
    
    if passed == total:
        print("🎉 System is healthy!")
        return True
    else:
        print("⚠️  System has issues that need attention")
        return False

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)