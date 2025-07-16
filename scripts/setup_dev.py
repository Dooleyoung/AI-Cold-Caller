#!/usr/bin/env python3
"""
Development environment setup script
"""
import os
import sys
import subprocess
from pathlib import Path

def run_command(command, description):
    """Run a command and handle errors"""
    print(f"→ {description}")
    try:
        result = subprocess.run(command, shell=True, check=True, capture_output=True, text=True)
        print(f"  ✅ {description} completed")
        return True
    except subprocess.CalledProcessError as e:
        print(f"  ❌ {description} failed: {e.stderr}")
        return False

def setup_environment():
    """Set up development environment"""
    print("🚀 Setting up AI Cold Calling System Development Environment")
    print("=" * 60)
    
    # Check Python version
    if sys.version_info < (3, 8):
        print("❌ Python 3.8+ required")
        sys.exit(1)
    
    print(f"✅ Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
    
    # Create directories
    directories = ['logs', 'data', 'uploads']
    for directory in directories:
        Path(directory).mkdir(exist_ok=True)
        print(f"✅ Created directory: {directory}")
    
    # Install requirements
    if not run_command("pip install -r requirements.txt", "Installing Python dependencies"):
        return False
    
    # Create .env if it doesn't exist
    if not Path('.env').exists():
        run_command("cp .env.example .env", "Creating .env file")
        print("⚠️  Please edit .env file with your API keys")
    
    # Setup database
    if not run_command("python main.py setup", "Setting up database"):
        return False
    
    # Run basic tests
    if not run_command("python -m pytest tests/test_basic.py -v", "Running basic tests"):
        print("⚠️  Some tests failed, but continuing...")
    
    print("\n" + "=" * 60)
    print("🎉 Development environment setup complete!")
    print("\nNext steps:")
    print("1. Edit .env file with your API keys")
    print("2. Copy your Dia_TTS.py to voice/ directory")
    print("3. Run: python main.py full")
    print("\nAPI Keys needed:")
    print("- Twilio: Account SID, Auth Token, Phone Number")
    print("- Groq: API Key")
    print("- Google: Client ID, Client Secret")
    
    return True

if __name__ == '__main__':
    success = setup_environment()
    sys.exit(0 if success else 1)