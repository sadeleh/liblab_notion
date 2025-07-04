#!/usr/bin/env python3
"""
Migration script to add deleted_at column to production database
Run this on fly.io production environment
"""

import sqlite3
import os
from datetime import datetime

def migrate_database():
    # Get database path
    db_path = os.path.join('instance', 'team_planning.db')
    
    if not os.path.exists(db_path):
        print(f"❌ Database not found at {db_path}")
        return False
    
    try:
        # Connect to database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if deleted_at column already exists
        cursor.execute("PRAGMA table_info(smart_notion)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'deleted_at' in columns:
            print("✅ Column 'deleted_at' already exists. No migration needed.")
            conn.close()
            return True
        
        print("🔄 Adding 'deleted_at' column to smart_notion table...")
        
        # Add deleted_at column
        cursor.execute("ALTER TABLE smart_notion ADD COLUMN deleted_at DATETIME")
        
        # Commit changes
        conn.commit()
        
        # Verify the column was added
        cursor.execute("PRAGMA table_info(smart_notion)")
        columns_after = [column[1] for column in cursor.fetchall()]
        
        if 'deleted_at' in columns_after:
            print("✅ Migration completed successfully!")
            print(f"✅ Column 'deleted_at' added to smart_notion table")
            
            # Show current record count
            cursor.execute("SELECT COUNT(*) FROM smart_notion WHERE deleted_at IS NULL")
            active_count = cursor.fetchone()[0]
            print(f"📊 Active records: {active_count}")
            
            conn.close()
            return True
        else:
            print("❌ Migration failed - column not found after adding")
            conn.close()
            return False
            
    except Exception as e:
        print(f"❌ Migration failed: {str(e)}")
        if 'conn' in locals():
            conn.close()
        return False

if __name__ == "__main__":
    print("🚀 Starting production database migration...")
    print(f"⏰ Migration started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    success = migrate_database()
    
    if success:
        print("🎉 Migration completed successfully!")
    else:
        print("💥 Migration failed! Please check the errors above.")
        exit(1) 