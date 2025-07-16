#!/usr/bin/env python3
"""
Database backup script
"""
import os
import sys
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import settings
from database.crud import get_all_leads, get_call_records
from utils.helpers import export_to_csv

def backup_database():
    """Create a backup of the SQLite database"""
    print("📦 Creating database backup...")
    
    # Get database path
    db_path = settings.DATABASE_URL.replace('sqlite:///', '')
    
    if not os.path.exists(db_path):
        print(f"❌ Database file not found: {db_path}")
        return False
    
    # Create backup directory
    backup_dir = Path('backups')
    backup_dir.mkdir(exist_ok=True)
    
    # Create timestamped backup
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = backup_dir / f'ai_cold_caller_backup_{timestamp}.db'
    
    try:
        shutil.copy2(db_path, backup_path)
        print(f"✅ Database backed up to: {backup_path}")
        return True
    except Exception as e:
        print(f"❌ Backup failed: {e}")
        return False

def export_data_csv():
    """Export data to CSV files"""
    print("📊 Exporting data to CSV...")
    
    # Create exports directory
    export_dir = Path('exports')
    export_dir.mkdir(exist_ok=True)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    try:
        # Export leads
        leads = get_all_leads()
        leads_data = [lead.to_dict() for lead in leads]
        
        leads_csv = export_to_csv(leads_data)
        leads_file = export_dir / f'leads_export_{timestamp}.csv'
        
        with open(leads_file, 'w') as f:
            f.write(leads_csv)
        
        print(f"✅ Leads exported to: {leads_file}")
        
        # Export call records
        calls = get_call_records(limit=10000)
        calls_data = [call.to_dict() for call in calls]
        
        calls_csv = export_to_csv(calls_data)
        calls_file = export_dir / f'calls_export_{timestamp}.csv'
        
        with open(calls_file, 'w') as f:
            f.write(calls_csv)
        
        print(f"✅ Calls exported to: {calls_file}")
        
        return True
        
    except Exception as e:
        print(f"❌ CSV export failed: {e}")
        return False

def main():
    """Main backup function"""
    print("🔄 AI Cold Calling System - Data Backup")
    print("=" * 50)
    
    success = True
    
    # Backup database
    if not backup_database():
        success = False
    
    # Export CSV data
    if not export_data_csv():
        success = False
    
    if success:
        print("\n🎉 Backup completed successfully!")
    else:
        print("\n❌ Backup completed with errors")
    
    return success

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)