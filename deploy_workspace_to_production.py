#!/usr/bin/env python3
"""
Complete deployment script for workspace and user management to Fly.io production.

This script combines both the database schema migration and the workspace migration
into a single production-ready deployment.

WHAT THIS SCRIPT DOES:
1. Creates all new tables (if not exist)
2. Adds user management tables (User, Workspace, UserWorkspace)
3. Adds workspace_id column to all existing tables
4. Creates default 'ws-general' workspace
5. Creates admin user (username: admin, password: admin_@2025)
6. Migrates all existing data to ws-general workspace

USAGE ON FLY.IO:
    fly ssh console
    python deploy_workspace_to_production.py
"""

import sqlite3
import os
from datetime import datetime
from werkzeug.security import generate_password_hash

def get_db_path():
    """Get the database path for production or local environment"""
    # Production database path on Fly.io (mounted volume)
    if os.path.exists('/app/instance'):
        return '/app/instance/team_planning.db'
    # Fallback to local instance path
    return 'instance/team_planning.db'

def table_exists(cursor, table_name):
    """Check if a table exists"""
    cursor.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name=?
    """, (table_name,))
    return cursor.fetchone() is not None

def column_exists(cursor, table_name, column_name):
    """Check if a column exists in a table"""
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = [column[1] for column in cursor.fetchall()]
    return column_name in columns

def create_user_management_tables(cursor):
    """Create User, Workspace, and UserWorkspace tables"""
    print("\n🔄 Creating User Management tables...")
    
    # User table
    if not table_exists(cursor, 'user'):
        cursor.execute("""
            CREATE TABLE user (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username VARCHAR(100) UNIQUE NOT NULL,
                password_hash VARCHAR(200) NOT NULL,
                is_superadmin BOOLEAN DEFAULT 0,
                last_workspace_id VARCHAR(50),
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        print("  ✅ Created user table")
    else:
        print("  ✅ user table already exists")
    
    # Workspace table
    if not table_exists(cursor, 'workspace'):
        cursor.execute("""
            CREATE TABLE workspace (
                id VARCHAR(50) PRIMARY KEY,
                name VARCHAR(200) NOT NULL,
                description TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        print("  ✅ Created workspace table")
    else:
        print("  ✅ workspace table already exists")
    
    # UserWorkspace table
    if not table_exists(cursor, 'user_workspace'):
        cursor.execute("""
            CREATE TABLE user_workspace (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                workspace_id VARCHAR(50) NOT NULL,
                assigned_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES user (id),
                FOREIGN KEY (workspace_id) REFERENCES workspace (id)
            )
        """)
        print("  ✅ Created user_workspace table")
    else:
        print("  ✅ user_workspace table already exists")

def create_default_workspace_and_admin(cursor, conn):
    """Create the default workspace and admin user"""
    print("\n🔄 Setting up default workspace and admin user...")
    
    # Create ws-general workspace
    cursor.execute("SELECT id FROM workspace WHERE id = 'ws-general'")
    if not cursor.fetchone():
        cursor.execute("""
            INSERT INTO workspace (id, name, description, created_at, updated_at)
            VALUES ('ws-general', 'General Work Space', 'Default workspace for existing data', ?, ?)
        """, (datetime.now(), datetime.now()))
        print("  ✅ Created 'ws-general' workspace")
    else:
        print("  ✅ 'ws-general' workspace already exists")
    
    # Create admin user
    cursor.execute("SELECT id FROM user WHERE username = 'admin'")
    admin_row = cursor.fetchone()
    
    if not admin_row:
        password_hash = generate_password_hash('admin_@2025')
        cursor.execute("""
            INSERT INTO user (username, password_hash, is_superadmin, last_workspace_id, created_at, updated_at)
            VALUES ('admin', ?, 1, 'ws-general', ?, ?)
        """, (password_hash, datetime.now(), datetime.now()))
        admin_id = cursor.lastrowid
        print("  ✅ Created admin user (username: admin, password: admin_@2025)")
    else:
        admin_id = admin_row[0]
        # Update to ensure is_superadmin
        cursor.execute("UPDATE user SET is_superadmin = 1 WHERE id = ?", (admin_id,))
        print("  ✅ Admin user already exists")
    
    # Assign admin to ws-general
    cursor.execute("""
        SELECT id FROM user_workspace 
        WHERE user_id = ? AND workspace_id = 'ws-general'
    """, (admin_id,))
    
    if not cursor.fetchone():
        cursor.execute("""
            INSERT INTO user_workspace (user_id, workspace_id, assigned_at)
            VALUES (?, 'ws-general', ?)
        """, (admin_id, datetime.now()))
        print("  ✅ Assigned admin to ws-general workspace")
    else:
        print("  ✅ Admin already assigned to ws-general workspace")
    
    conn.commit()

def add_workspace_columns(cursor, conn):
    """Add workspace_id column to all data tables"""
    print("\n🔄 Adding workspace_id columns to existing tables...")
    
    tables_to_update = [
        'task', 'resource', 'brainstorm_session', 'idea', 'smart_notion', 'chat_conversation',
        'voice_note', 'voice_recording', 'voice_comment', 'voice_summary',
        'monthly_plan', 'monthly_goal', 'reminder',
        'project', 'phase', 'user_story', 'acceptance_criteria', 'story_note'
    ]
    
    for table_name in tables_to_update:
        if not table_exists(cursor, table_name):
            print(f"  ⊘ {table_name}: table doesn't exist yet (will be created with schema)")
            continue
        
        if not column_exists(cursor, table_name, 'workspace_id'):
            try:
                cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN workspace_id VARCHAR(50)")
                print(f"  ✅ Added workspace_id to {table_name}")
            except Exception as e:
                print(f"  ⚠ Error adding workspace_id to {table_name}: {e}")
        else:
            print(f"  ✅ {table_name} already has workspace_id column")
    
    conn.commit()

def migrate_data_to_workspace(cursor, conn):
    """Migrate all existing data to ws-general workspace"""
    print("\n🔄 Migrating existing data to ws-general workspace...")
    
    tables_to_migrate = [
        'task', 'resource', 'brainstorm_session', 'idea', 'smart_notion', 'chat_conversation',
        'voice_note', 'voice_recording', 'voice_comment', 'voice_summary',
        'monthly_plan', 'monthly_goal', 'reminder',
        'project', 'phase', 'user_story', 'acceptance_criteria', 'story_note'
    ]
    
    for table_name in tables_to_migrate:
        if not table_exists(cursor, table_name):
            continue
        
        if not column_exists(cursor, table_name, 'workspace_id'):
            continue
        
        try:
            # Count records without workspace_id
            cursor.execute(f"SELECT COUNT(*) FROM {table_name} WHERE workspace_id IS NULL OR workspace_id = ''")
            count = cursor.fetchone()[0]
            
            if count > 0:
                # Update records to ws-general
                cursor.execute(f"UPDATE {table_name} SET workspace_id = 'ws-general' WHERE workspace_id IS NULL OR workspace_id = ''")
                print(f"  ✅ Migrated {count} {table_name} record(s) to ws-general")
            else:
                # Check total records
                cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
                total = cursor.fetchone()[0]
                if total > 0:
                    print(f"  ✅ {table_name}: All {total} records already have workspace_id")
                else:
                    print(f"  ⊘ {table_name}: No records to migrate")
        except Exception as e:
            print(f"  ⚠ Error migrating {table_name}: {e}")
    
    conn.commit()

def deploy_to_production():
    """Main deployment function"""
    
    db_path = get_db_path()
    print(f"\n🗄️  Using database path: {db_path}")
    
    # Check if database exists
    if not os.path.exists(db_path):
        print("⚠️  Database not found. It will be created by Flask on first run.")
        print("   Please run the app first to create the database, then run this script.")
        return False
    
    # Create backup
    backup_path = f"{db_path}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    try:
        import shutil
        shutil.copy2(db_path, backup_path)
        print(f"📋 Created backup: {backup_path}")
    except Exception as e:
        print(f"⚠️  Warning: Could not create backup: {e}")
        print("   Continuing anyway...")
    
    print("\n" + "="*80)
    print("🚀 STARTING WORKSPACE & USER MANAGEMENT DEPLOYMENT")
    print("="*80)
    
    try:
        # Connect to database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Step 1: Create user management tables
        create_user_management_tables(cursor)
        
        # Step 2: Create default workspace and admin user
        create_default_workspace_and_admin(cursor, conn)
        
        # Step 3: Add workspace_id columns to existing tables
        add_workspace_columns(cursor, conn)
        
        # Step 4: Migrate existing data to ws-general workspace
        migrate_data_to_workspace(cursor, conn)
        
        # Commit all changes
        conn.commit()
        
        print("\n" + "="*80)
        print("🎉 DEPLOYMENT COMPLETED SUCCESSFULLY!")
        print("="*80)
        print("\n✅ Changes Applied:")
        print("   • Created User Management tables (User, Workspace, UserWorkspace)")
        print("   • Created 'ws-general' workspace")
        print("   • Created admin superuser")
        print("   • Added workspace_id to all data tables")
        print("   • Migrated all existing data to ws-general workspace")
        print("\n🔐 Admin Credentials:")
        print("   Username: admin")
        print("   Password: admin_@2025")
        print("\n📊 Database schema summary:")
        
        # Show table information
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = cursor.fetchall()
        print(f"\n   Total tables: {len(tables)}")
        
        # Count records in key tables
        key_tables = ['user', 'workspace', 'user_workspace', 'task', 'resource', 'project', 'user_story']
        for table_name in key_tables:
            if any(t[0] == table_name for t in tables):
                cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
                count = cursor.fetchone()[0]
                print(f"   📋 {table_name}: {count} records")
        
        conn.close()
        
        print("\n" + "="*80)
        print("🚀 Next Steps:")
        print("="*80)
        print("1. Restart your Fly.io app: fly apps restart liblab-notion")
        print("2. Open your app: fly apps open liblab-notion")
        print("3. You will be redirected to the login page")
        print("4. Login with admin/admin_@2025")
        print("5. All your existing data will be in the 'ws-general' workspace")
        print("="*80)
        
        return True
        
    except Exception as e:
        print(f"\n❌ Deployment failed: {str(e)}")
        if 'conn' in locals():
            conn.rollback()
            conn.close()
        print(f"\nBackup is available at: {backup_path}")
        return False

if __name__ == "__main__":
    print("="*80)
    print("🚀 WORKSPACE & USER MANAGEMENT DEPLOYMENT TO PRODUCTION")
    print("="*80)
    print("\nThis script will:")
    print("  1. Create user management tables")
    print("  2. Create default workspace and admin user")
    print("  3. Add workspace support to all tables")
    print("  4. Migrate existing data to default workspace")
    print("\n⚠️  Make sure you've backed up your database!")
    print("="*80)
    
    if deploy_to_production():
        print("\n✅ DEPLOYMENT SUCCESSFUL!")
    else:
        print("\n❌ DEPLOYMENT FAILED!")
        exit(1)

