#!/usr/bin/env python3
"""
Main entry point for AI Cold Calling System
"""
import os
import sys
import argparse
import signal
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config.settings import settings, validate_settings
from database.crud import create_tables
from scheduler.call_scheduler import call_scheduler
from web.dashboard import app as dashboard_app
from web.api import app as api_app
from utils.logger import get_logger

logger = get_logger(__name__)

def setup_database():
    """Initialize database"""
    try:
        logger.info("Setting up database...")
        create_tables()
        logger.info("Database setup completed")
    except Exception as e:
        logger.error(f"Database setup failed: {e}")
        sys.exit(1)

def start_scheduler():
    """Start the call scheduler"""
    try:
        logger.info("Starting call scheduler...")
        call_scheduler.start()
        logger.info("Call scheduler started successfully")
    except Exception as e:
        logger.error(f"Failed to start call scheduler: {e}")

def signal_handler(signum, frame):
    """Handle shutdown signals"""
    logger.info(f"Received signal {signum}, shutting down...")
    
    # Stop scheduler
    try:
        call_scheduler.stop()
        logger.info("Call scheduler stopped")
    except Exception as e:
        logger.error(f"Error stopping scheduler: {e}")
    
    sys.exit(0)

def run_dashboard(host='0.0.0.0', port=5000, debug=False):
    """Run the web dashboard"""
    logger.info(f"Starting web dashboard on {host}:{port}")
    dashboard_app.run(host=host, port=port, debug=debug)

def run_api(host='0.0.0.0', port=5001, debug=False):
    """Run the API server"""
    logger.info(f"Starting API server on {host}:{port}")
    api_app.run(host=host, port=port, debug=debug)

def run_full_system(dashboard_port=5000, api_port=5001, debug=False):
    """Run complete system with scheduler, dashboard, and API"""
    import threading
    import time
    
    logger.info("Starting complete AI Cold Calling System...")
    
    # Setup signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Start scheduler
    start_scheduler()
    
    # Start API server in separate thread
    api_thread = threading.Thread(
        target=run_api,
        args=('0.0.0.0', api_port, debug),
        daemon=True
    )
    api_thread.start()
    
    # Give API time to start
    time.sleep(2)
    
    # Start dashboard (main thread)
    logger.info("System fully initialized and running")
    run_dashboard(port=dashboard_port, debug=debug)

def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='AI Cold Calling System')
    parser.add_argument('command', choices=['setup', 'dashboard', 'api', 'scheduler', 'full'], 
                       help='Command to run')
    parser.add_argument('--host', default='0.0.0.0', help='Host to bind to')
    parser.add_argument('--dashboard-port', type=int, default=5000, help='Dashboard port')
    parser.add_argument('--api-port', type=int, default=5001, help='API port')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')
    parser.add_argument('--validate-only', action='store_true', help='Only validate configuration')
    
    args = parser.parse_args()
    
    # Print startup banner
    print("="*60)
    print("🤖 AI Cold Calling System")
    print("="*60)
    print(f"Starting at: {datetime.now()}")
    print(f"Command: {args.command}")
    print(f"Debug mode: {args.debug}")
    print("="*60)
    
    try:
        # Validate configuration
        logger.info("Validating configuration...")
        validate_settings()
        logger.info("Configuration validation successful")
        
        if args.validate_only:
            print("✅ Configuration is valid")
            return
        
        # Setup database for all commands
        if args.command != 'scheduler':
            setup_database()
        
        # Execute command
        if args.command == 'setup':
            logger.info("Database setup completed successfully")
            print("✅ Database setup completed")
            
        elif args.command == 'dashboard':
            run_dashboard(args.host, args.dashboard_port, args.debug)
            
        elif args.command == 'api':
            run_api(args.host, args.api_port, args.debug)
            
        elif args.command == 'scheduler':
            start_scheduler()
            try:
                while True:
                    import time
                    time.sleep(1)
            except KeyboardInterrupt:
                logger.info("Scheduler stopped by user")
                
        elif args.command == 'full':
            run_full_system(args.dashboard_port, args.api_port, args.debug)
        
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        print(f"❌ Error: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()