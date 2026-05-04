#!/usr/bin/env python3
"""
Automated Database Backup Script for Tahfeel CRM
"""

import os
import subprocess
from datetime import datetime
import gzip
import shutil

BACKUP_DIR = os.path.join(os.path.dirname(__file__), 'backups')
DATABASE_URL = os.environ.get('DATABASE_URL', '')
KEEP_BACKUPS = 7

def ensure_backup_dir():
    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR)
    print(f"✓ Backup directory ready: {BACKUP_DIR}")

def parse_database_url(url):
    try:
        url = url.strip()
        # Handle both postgres:// and postgresql://
        url = url.replace('postgres://', 'postgresql://')
        url = url.replace('postgresql://', '')
        
        # Remove SSL params if present
        if '?' in url:
            url = url.split('?')[0]

        auth, rest = url.split('@')
        user_pass = auth.split(':', 1)
        user = user_pass[0]
        password = user_pass[1] if len(user_pass) > 1 else ''

        host_db = rest.split('/', 1)
        host_port = host_db[0].split(':')
        host = host_port[0]
        port = host_port[1] if len(host_port) > 1 else '5432'
        database = host_db[1] if len(host_db) > 1 else ''

        return {'host': host, 'port': port, 'user': user, 'password': password, 'database': database}
    except Exception as e:
        print(f"❌ Failed to parse DATABASE_URL: {e}")
        return None

def backup_database():
    if not DATABASE_URL:
        print("❌ DATABASE_URL environment variable is not set!")
        print("   Make sure DATABASE_URL is added as a GitHub Secret.")
        return False

    print(f"🔍 DATABASE_URL found (length: {len(DATABASE_URL)} chars)")

    db_config = parse_database_url(DATABASE_URL)
    if not db_config:
        return False

    print(f"   Host: {db_config['host']}")
    print(f"   Port: {db_config['port']}")
    print(f"   User: {db_config['user']}")
    print(f"   Database: {db_config['database']}")

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_file = os.path.join(BACKUP_DIR, f'tahfeel_backup_{timestamp}.sql')
    backup_file_gz = f'{backup_file}.gz'

    print(f"\n📦 Running pg_dump...")

    env = os.environ.copy()
    env['PGPASSWORD'] = db_config['password']
    env['PGSSLMODE'] = 'require'

    cmd = [
        'pg_dump',
        '-h', db_config['host'],
        '-p', db_config['port'],
        '-U', db_config['user'],
        '-d', db_config['database'],
        '--no-password',
        '-F', 'p',
        '-f', backup_file
    ]

    result = subprocess.run(cmd, env=env, capture_output=True, text=True)

    print(f"   pg_dump exit code: {result.returncode}")
    if result.stdout:
        print(f"   stdout: {result.stdout}")
    if result.stderr:
        print(f"   stderr: {result.stderr}")

    if result.returncode == 0 and os.path.exists(backup_file):
        # Compress
        with open(backup_file, 'rb') as f_in:
            with gzip.open(backup_file_gz, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
        os.remove(backup_file)

        size_mb = os.path.getsize(backup_file_gz) / 1024 / 1024
        print(f"\n✅ Backup created: {os.path.basename(backup_file_gz)} ({size_mb:.2f} MB)")
        cleanup_old_backups()
        return True
    else:
        print(f"\n❌ pg_dump failed or no output file created")
        if os.path.exists(backup_file):
            os.remove(backup_file)
        return False

def cleanup_old_backups():
    backups = sorted([
        f for f in os.listdir(BACKUP_DIR)
        if f.startswith('tahfeel_backup_')
    ], reverse=True)

    if len(backups) > KEEP_BACKUPS:
        for old_backup in backups[KEEP_BACKUPS:]:
            os.remove(os.path.join(BACKUP_DIR, old_backup))
            print(f"🗑️  Removed old backup: {old_backup}")

if __name__ == '__main__':
    ensure_backup_dir()
    success = backup_database()
    if not success:
        exit(1)
    print(f"\n💾 Backup location: {BACKUP_DIR}")
