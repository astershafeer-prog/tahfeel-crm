#!/usr/bin/env python3
"""
Automated Database Backup Script for Tahfeel CRM
Backs up PostgreSQL database to local file and optionally uploads to cloud storage
"""

import os
import subprocess
from datetime import datetime
import gzip
import shutil

# Configuration
BACKUP_DIR = os.path.join(os.path.dirname(__file__), 'backups')
DATABASE_URL = os.environ.get('DATABASE_URL', '')
KEEP_BACKUPS = 7  # Keep last 7 backups

def ensure_backup_dir():
    """Create backup directory if it doesn't exist"""
    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR)
        print(f"✓ Created backup directory: {BACKUP_DIR}")

def parse_database_url(url):
    """Parse DATABASE_URL into pg_dump connection parameters"""
    # Format: postgresql://user:password@host:port/database
    url = url.replace('postgres://', 'postgresql://').replace('postgresql://', '')
    
    # Split into parts
    if '@' in url:
        auth, location = url.split('@')
        user_pass = auth.split(':')
        user = user_pass[0]
        password = user_pass[1] if len(user_pass) > 1 else ''
        
        host_port_db = location.split('/')
        host_port = host_port_db[0].split(':')
        host = host_port[0]
        port = host_port[1] if len(host_port) > 1 else '5432'
        database = host_port_db[1] if len(host_port_db) > 1 else ''
        
        return {
            'host': host,
            'port': port,
            'user': user,
            'password': password,
            'database': database
        }
    return None

def backup_database():
    """Create PostgreSQL database backup using pg_dump"""
    if not DATABASE_URL or 'sqlite' in DATABASE_URL:
        print("⚠️  SQLite database detected - copying database file instead")
        backup_sqlite()
        return
    
    db_config = parse_database_url(DATABASE_URL)
    if not db_config:
        print("❌ Could not parse DATABASE_URL")
        return
    
    # Generate backup filename with timestamp
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_file = os.path.join(BACKUP_DIR, f'tahfeel_backup_{timestamp}.sql')
    backup_file_gz = f'{backup_file}.gz'
    
    print(f"📦 Starting database backup...")
    print(f"   Database: {db_config['database']}")
    print(f"   Host: {db_config['host']}")
    
    # Set PGPASSWORD environment variable for authentication
    env = os.environ.copy()
    env['PGPASSWORD'] = db_config['password']
    
    # Run pg_dump command
    try:
        cmd = [
            'pg_dump',
            '-h', db_config['host'],
            '-p', db_config['port'],
            '-U', db_config['user'],
            '-d', db_config['database'],
            '-F', 'p',  # Plain text format
            '-f', backup_file
        ]
        
        result = subprocess.run(cmd, env=env, capture_output=True, text=True)
        
        if result.stdout:
            print(f"pg_dump stdout: {result.stdout}")
        if result.stderr:
            print(f"pg_dump stderr: {result.stderr}")
        
        if result.returncode == 0:
            # Compress the backup
            with open(backup_file, 'rb') as f_in:
                with gzip.open(backup_file_gz, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)
            
            # Remove uncompressed file
            os.remove(backup_file)
            
            file_size = os.path.getsize(backup_file_gz) / 1024 / 1024  # MB
            print(f"✓ Backup created: {os.path.basename(backup_file_gz)} ({file_size:.2f} MB)")
            
            # Cleanup old backups
            cleanup_old_backups()
            
        else:
            print(f"❌ Backup failed: {result.stderr}")
            
    except FileNotFoundError:
        print("❌ pg_dump not found. Install PostgreSQL client tools.")
    except Exception as e:
        print(f"❌ Backup error: {e}")

def backup_sqlite():
    """Backup SQLite database (development mode)"""
    sqlite_db = os.path.join(os.path.dirname(__file__), 'tahfeel.db')
    if not os.path.exists(sqlite_db):
        print("❌ SQLite database not found")
        return
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_file = os.path.join(BACKUP_DIR, f'tahfeel_backup_{timestamp}.db')
    
    shutil.copy2(sqlite_db, backup_file)
    file_size = os.path.getsize(backup_file) / 1024 / 1024  # MB
    print(f"✓ SQLite backup created: {os.path.basename(backup_file)} ({file_size:.2f} MB)")
    
    cleanup_old_backups()

def cleanup_old_backups():
    """Keep only the most recent backups"""
    backups = sorted([
        f for f in os.listdir(BACKUP_DIR) 
        if f.startswith('tahfeel_backup_')
    ], reverse=True)
    
    if len(backups) > KEEP_BACKUPS:
        for old_backup in backups[KEEP_BACKUPS:]:
            old_path = os.path.join(BACKUP_DIR, old_backup)
            os.remove(old_path)
            print(f"🗑️  Removed old backup: {old_backup}")

def list_backups():
    """List all available backups"""
    if not os.path.exists(BACKUP_DIR):
        print("No backups found")
        return
    
    backups = sorted([
        f for f in os.listdir(BACKUP_DIR) 
        if f.startswith('tahfeel_backup_')
    ], reverse=True)
    
    if not backups:
        print("No backups found")
        return
    
    print(f"\n📋 Available backups ({len(backups)}):")
    print("-" * 60)
    for backup in backups:
        backup_path = os.path.join(BACKUP_DIR, backup)
        size = os.path.getsize(backup_path) / 1024 / 1024  # MB
        mtime = datetime.fromtimestamp(os.path.getmtime(backup_path))
        print(f"  {backup:40s} {size:8.2f} MB  {mtime.strftime('%Y-%m-%d %H:%M')}")

if __name__ == '__main__':
    import sys
    
    ensure_backup_dir()
    
    if len(sys.argv) > 1 and sys.argv[1] == 'list':
        list_backups()
    else:
        backup_database()
        print(f"\n💾 Backup location: {BACKUP_DIR}")
        print(f"📝 Keeping last {KEEP_BACKUPS} backups")
