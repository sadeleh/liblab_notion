#!/usr/bin/env python3
"""
Production Migration Script: Add Voice Notes Tables
==================================================

This script adds all the voice notes related tables to the production database.
Run this on the production server to enable the Ideas Bank functionality.

Tables to be created:
- voice_note
- voice_recording 
- voice_comment
- voice_summary

Usage:
python migrate_voice_notes_tables.py

"""

import sqlite3
import os
from datetime import datetime

def get_db_path():
    """Get the database path"""
    # Try common locations
    possible_paths = [
        'instance/team_planning.db',
        '/app/instance/team_planning.db',
        'team_planning.db'
    ]
    
    for path in possible_paths:
        if os.path.exists(path):
            return path
    
    # If none found, create in instance directory
    instance_dir = 'instance'
    if not os.path.exists(instance_dir):
        os.makedirs(instance_dir)
    return 'instance/team_planning.db'

def table_exists(cursor, table_name):
    """Check if a table exists"""
    cursor.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name=?
    """, (table_name,))
    return cursor.fetchone() is not None

def create_voice_note_table(cursor):
    """Create voice_note table"""
    if table_exists(cursor, 'voice_note'):
        print("✅ voice_note table already exists")
        return
    
    cursor.execute("""
        CREATE TABLE voice_note (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title VARCHAR(200) NOT NULL,
            description TEXT,
            summary_html TEXT,
            created_by VARCHAR(100),
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            deleted_at DATETIME
        )
    """)
    print("✅ Created voice_note table")

def create_voice_recording_table(cursor):
    """Create voice_recording table"""
    if table_exists(cursor, 'voice_recording'):
        print("✅ voice_recording table already exists")
        return
    
    cursor.execute("""
        CREATE TABLE voice_recording (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            voice_note_id INTEGER NOT NULL,
            filename VARCHAR(255) NOT NULL,
            original_name VARCHAR(255),
            file_size INTEGER,
            duration INTEGER,
            content_type VARCHAR(50) DEFAULT 'audio/webm',
            transcription TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (voice_note_id) REFERENCES voice_note (id)
        )
    """)
    print("✅ Created voice_recording table")

def create_voice_comment_table(cursor):
    """Create voice_comment table"""
    if table_exists(cursor, 'voice_comment'):
        print("✅ voice_comment table already exists")
        return
    
    cursor.execute("""
        CREATE TABLE voice_comment (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            voice_note_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            author VARCHAR(100),
            comment_type VARCHAR(20) DEFAULT 'text',
            recording_id INTEGER,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (voice_note_id) REFERENCES voice_note (id),
            FOREIGN KEY (recording_id) REFERENCES voice_recording (id)
        )
    """)
    print("✅ Created voice_comment table")

def create_voice_summary_table(cursor):
    """Create voice_summary table"""
    if table_exists(cursor, 'voice_summary'):
        print("✅ voice_summary table already exists")
        return
    
    cursor.execute("""
        CREATE TABLE voice_summary (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            voice_note_id INTEGER NOT NULL,
            summary_html TEXT NOT NULL,
            summary_version INTEGER DEFAULT 1,
            transcripts_count INTEGER DEFAULT 0,
            comments_count INTEGER DEFAULT 0,
            model_used VARCHAR(100),
            created_by VARCHAR(100),
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            is_current BOOLEAN DEFAULT 1,
            FOREIGN KEY (voice_note_id) REFERENCES voice_note (id)
        )
    """)
    print("✅ Created voice_summary table")

def check_smart_notion_deleted_at(cursor):
    """Check and add deleted_at column to smart_notion table if missing"""
    try:
        cursor.execute("SELECT deleted_at FROM smart_notion LIMIT 1")
        print("✅ smart_notion.deleted_at column already exists")
    except sqlite3.OperationalError:
        # Column doesn't exist, add it
        cursor.execute("ALTER TABLE smart_notion ADD COLUMN deleted_at DATETIME")
        print("✅ Added deleted_at column to smart_notion table")

def create_indexes(cursor):
    """Create indexes for better performance"""
    indexes = [
        ("idx_voice_note_deleted", "CREATE INDEX IF NOT EXISTS idx_voice_note_deleted ON voice_note(deleted_at)"),
        ("idx_voice_recording_note", "CREATE INDEX IF NOT EXISTS idx_voice_recording_note ON voice_recording(voice_note_id)"),
        ("idx_voice_comment_note", "CREATE INDEX IF NOT EXISTS idx_voice_comment_note ON voice_comment(voice_note_id)"),
        ("idx_voice_summary_note", "CREATE INDEX IF NOT EXISTS idx_voice_summary_note ON voice_summary(voice_note_id)"),
        ("idx_voice_summary_current", "CREATE INDEX IF NOT EXISTS idx_voice_summary_current ON voice_summary(is_current)"),
        ("idx_smart_notion_deleted", "CREATE INDEX IF NOT EXISTS idx_smart_notion_deleted ON smart_notion(deleted_at)")
    ]
    
    for index_name, sql in indexes:
        cursor.execute(sql)
        print(f"✅ Created index: {index_name}")

def run_migration():
    """Run the complete migration"""
    db_path = get_db_path()
    print(f"🗄️  Using database: {db_path}")
    
    # Backup database first
    backup_path = f"{db_path}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    try:
        import shutil
        shutil.copy2(db_path, backup_path)
        print(f"📋 Created backup: {backup_path}")
    except Exception as e:
        print(f"⚠️  Warning: Could not create backup: {e}")
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        print("\n🚀 Starting voice notes tables migration...")
        
        # Create all voice notes tables
        create_voice_note_table(cursor)
        create_voice_recording_table(cursor)
        create_voice_comment_table(cursor)
        create_voice_summary_table(cursor)
        
        # Check smart_notion table
        check_smart_notion_deleted_at(cursor)
        
        # Create indexes
        print("\n📊 Creating indexes...")
        create_indexes(cursor)
        
        # Commit changes
        conn.commit()
        
        print("\n🎉 Migration completed successfully!")
        print("\n📊 Database schema updated:")
        
        # Show table information
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = cursor.fetchall()
        print("\nTables in database:")
        for table in tables:
            cursor.execute(f"SELECT COUNT(*) FROM {table[0]}")
            count = cursor.fetchone()[0]
            print(f"  📋 {table[0]}: {count} records")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Error during migration: {e}")
        print("Rolling back changes...")
        conn.rollback()
        return False
        
    finally:
        conn.close()

def verify_migration():
    """Verify that the migration was successful"""
    db_path = get_db_path()
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check all required tables exist
        required_tables = ['voice_note', 'voice_recording', 'voice_comment', 'voice_summary']
        
        print("\n🔍 Verifying migration...")
        all_good = True
        
        for table in required_tables:
            if table_exists(cursor, table):
                print(f"✅ {table} table exists")
            else:
                print(f"❌ {table} table missing")
                all_good = False
        
        # Check smart_notion has deleted_at
        try:
            cursor.execute("SELECT deleted_at FROM smart_notion LIMIT 1")
            print("✅ smart_notion.deleted_at column exists")
        except sqlite3.OperationalError:
            print("❌ smart_notion.deleted_at column missing")
            all_good = False
        
        if all_good:
            print("\n🎉 All tables and columns verified successfully!")
            print("The Ideas Bank feature is now ready to use.")
        else:
            print("\n⚠️  Some issues found. Please check the errors above.")
        
        return all_good
        
    except Exception as e:
        print(f"\n❌ Error during verification: {e}")
        return False
        
    finally:
        conn.close()

if __name__ == "__main__":
    print("=" * 60)
    print("Voice Notes Tables Migration Script")
    print("=" * 60)
    
    success = run_migration()
    
    if success:
        verify_migration()
        print("\n" + "=" * 60)
        print("🚀 Ready to deploy! The application should now work without errors.")
        print("=" * 60)
    else:
        print("\n" + "=" * 60)
        print("❌ Migration failed. Please check the errors above.")
        print("=" * 60) 