#!/usr/bin/env python3
"""
Production-safe database migration for Fly.io deployment
This script safely migrates the production database on Fly.io with ALL recent changes
"""

import sqlite3
import os
from datetime import datetime

def get_db_path():
    """Get the database path for production or local environment"""
    # Production database path on Fly.io
    if os.path.exists('/data'):
        return '/data/team_planning.db'
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

def migrate_task_table(cursor):
    """Migrate Task table with new enhancements"""
    print("🔄 Migrating Task table...")
    
    if not table_exists(cursor, 'task'):
        print("⚠️  Task table doesn't exist, will be created with new schema")
        return
    
    # Add new columns if they don't exist
    task_columns = [
        ('tags', 'VARCHAR(500)'),
        ('updated_at', 'DATETIME'),
        ('completed_at', 'DATETIME')
    ]
    
    migration_needed = False
    
    for column_name, column_type in task_columns:
        if not column_exists(cursor, 'task', column_name):
            print(f"  ➕ Adding column: {column_name}")
            migration_needed = True
            
            cursor.execute(f"ALTER TABLE task ADD COLUMN {column_name} {column_type}")
            
            # Set default values for existing records
            if column_name == 'updated_at':
                cursor.execute("UPDATE task SET updated_at = created_at WHERE updated_at IS NULL")
        else:
            print(f"  ✅ Column {column_name} already exists")
    
    if migration_needed:
        # Update completed_at for tasks that are already completed
        cursor.execute("""
            UPDATE task 
            SET completed_at = updated_at 
            WHERE status = 'completed' AND completed_at IS NULL
        """)
        print("  ✅ Task table migration completed")
    else:
        print("  ✅ Task table already up to date")

def migrate_resource_table(cursor):
    """Migrate Resource table with file upload support"""
    print("🔄 Migrating Resource table...")
    
    if not table_exists(cursor, 'resource'):
        print("⚠️  Resource table doesn't exist, will be created with new schema")
        return
    
    # Add new columns if they don't exist
    resource_columns = [
        ('filename', 'VARCHAR(255)'),
        ('file_size', 'INTEGER'),
        ('updated_at', 'DATETIME')
    ]
    
    migration_needed = False
    
    for column_name, column_type in resource_columns:
        if not column_exists(cursor, 'resource', column_name):
            print(f"  ➕ Adding column: {column_name}")
            migration_needed = True
            
            cursor.execute(f"ALTER TABLE resource ADD COLUMN {column_name} {column_type}")
            
            # Set default values for existing records
            if column_name == 'updated_at':
                cursor.execute("UPDATE resource SET updated_at = created_at WHERE updated_at IS NULL")
        else:
            print(f"  ✅ Column {column_name} already exists")
    
    if migration_needed:
        print("  ✅ Resource table migration completed")
    else:
        print("  ✅ Resource table already up to date")

def migrate_smart_notion_table(cursor):
    """Add soft delete support to SmartNotion table"""
    print("🔄 Migrating SmartNotion table...")
    
    if not table_exists(cursor, 'smart_notion'):
        print("⚠️  SmartNotion table doesn't exist, will be created with new schema")
        return
    
    if not column_exists(cursor, 'smart_notion', 'deleted_at'):
        print("  ➕ Adding deleted_at column for soft delete")
        cursor.execute("ALTER TABLE smart_notion ADD COLUMN deleted_at DATETIME")
        print("  ✅ SmartNotion soft delete migration completed")
    else:
        print("  ✅ SmartNotion table already up to date")

def create_voice_notes_tables(cursor):
    """Create all voice notes related tables"""
    print("🔄 Creating Voice Notes tables...")
    
    # Voice Note table
    if not table_exists(cursor, 'voice_note'):
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
        print("  ✅ Created voice_note table")
    else:
        print("  ✅ voice_note table already exists")
    
    # Voice Recording table
    if not table_exists(cursor, 'voice_recording'):
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
        print("  ✅ Created voice_recording table")
    else:
        print("  ✅ voice_recording table already exists")
    
    # Voice Comment table
    if not table_exists(cursor, 'voice_comment'):
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
        print("  ✅ Created voice_comment table")
    else:
        print("  ✅ voice_comment table already exists")
    
    # Voice Summary table
    if not table_exists(cursor, 'voice_summary'):
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
        print("  ✅ Created voice_summary table")
    else:
        print("  ✅ voice_summary table already exists")

def create_monthly_planning_tables(cursor):
    """Create monthly planning related tables"""
    print("🔄 Creating Monthly Planning tables...")
    
    # Monthly Plan table
    if not table_exists(cursor, 'monthly_plan'):
        cursor.execute("""
            CREATE TABLE monthly_plan (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title VARCHAR(200) NOT NULL,
                month INTEGER NOT NULL,
                year INTEGER NOT NULL,
                status VARCHAR(20) DEFAULT 'active',
                priority VARCHAR(10) DEFAULT 'medium',
                category VARCHAR(50) DEFAULT 'general',
                tags VARCHAR(500),
                progress_percentage INTEGER DEFAULT 0,
                created_by VARCHAR(100),
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                completed_at DATETIME,
                deleted_at DATETIME
            )
        """)
        print("  ✅ Created monthly_plan table")
    else:
        print("  ✅ monthly_plan table already exists")
    
    # Monthly Goal table
    if not table_exists(cursor, 'monthly_goal'):
        cursor.execute("""
            CREATE TABLE monthly_goal (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                monthly_plan_id INTEGER NOT NULL,
                title VARCHAR(200) NOT NULL,
                target_date DATE,
                status VARCHAR(20) DEFAULT 'pending',
                priority VARCHAR(10) DEFAULT 'medium',
                order_index INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                completed_at DATETIME,
                FOREIGN KEY (monthly_plan_id) REFERENCES monthly_plan (id)
            )
        """)
        print("  ✅ Created monthly_goal table")
    else:
        print("  ✅ monthly_goal table already exists")

def create_reminder_table(cursor):
    """Create reminder table"""
    print("🔄 Creating Reminder table...")
    
    if not table_exists(cursor, 'reminder'):
        cursor.execute("""
            CREATE TABLE reminder (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title VARCHAR(200) NOT NULL,
                reminder_date DATE,
                priority VARCHAR(10) DEFAULT 'medium',
                status VARCHAR(20) DEFAULT 'active',
                category VARCHAR(50) DEFAULT 'general',
                extra_info TEXT,
                created_by VARCHAR(100),
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                completed_at DATETIME,
                deleted_at DATETIME
            )
        """)
        print("  ✅ Created reminder table")
    else:
        print("  ✅ reminder table already exists")
        
        # Handle metadata column rename to extra_info to avoid SQLAlchemy conflict
        if column_exists(cursor, 'reminder', 'metadata'):
            print("  🔄 Renaming metadata column to extra_info to avoid SQLAlchemy conflict")
            # SQLite doesn't support column rename directly, so we need to recreate the table
            cursor.execute("""
                CREATE TABLE reminder_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title VARCHAR(200) NOT NULL,
                    reminder_date DATE,
                    priority VARCHAR(10) DEFAULT 'medium',
                    status VARCHAR(20) DEFAULT 'active',
                    category VARCHAR(50) DEFAULT 'general',
                    extra_info TEXT,
                    created_by VARCHAR(100),
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    completed_at DATETIME,
                    deleted_at DATETIME
                )
            """)
            
            # Copy data from old table to new table
            cursor.execute("""
                INSERT INTO reminder_new (id, title, reminder_date, priority, status, category, extra_info, created_by, created_at, updated_at, completed_at, deleted_at)
                SELECT id, title, reminder_date, priority, status, category, metadata, created_by, created_at, updated_at, completed_at, deleted_at
                FROM reminder
            """)
            
            # Drop old table and rename new table
            cursor.execute("DROP TABLE reminder")
            cursor.execute("ALTER TABLE reminder_new RENAME TO reminder")
            print("  ✅ Successfully renamed metadata column to extra_info")
        elif not column_exists(cursor, 'reminder', 'extra_info'):
            print("  ➕ Adding extra_info column to reminder table")
            cursor.execute("ALTER TABLE reminder ADD COLUMN extra_info TEXT")
            print("  ✅ Added extra_info column to reminder table")

def create_chat_conversation_table(cursor):
    """Create chat conversation table"""
    print("🔄 Creating Chat Conversation table...")
    
    if not table_exists(cursor, 'chat_conversation'):
        cursor.execute("""
            CREATE TABLE chat_conversation (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                notion_id INTEGER NOT NULL,
                user_message TEXT NOT NULL,
                ai_response TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (notion_id) REFERENCES smart_notion (id)
            )
        """)
        print("  ✅ Created chat_conversation table")
    else:
        print("  ✅ chat_conversation table already exists")

def create_backlog_tables(cursor):
    """Create backlog management tables for development workflow"""
    print("🔄 Creating Backlog Management tables...")
    
    # Project table
    if not table_exists(cursor, 'project'):
        cursor.execute("""
            CREATE TABLE project (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(200) NOT NULL,
                name_arabic VARCHAR(200) DEFAULT '',
                description TEXT,
                status VARCHAR(20) DEFAULT 'active',
                priority VARCHAR(10) DEFAULT 'medium',
                start_date DATE,
                end_date DATE,
                created_by VARCHAR(100),
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                deleted_at DATETIME,
                order_index INTEGER DEFAULT 0
            )
        """)
        print("  ✅ Created project table")
    else:
        print("  ✅ project table already exists")
    
    # Phase table
    if not table_exists(cursor, 'phase'):
        cursor.execute("""
            CREATE TABLE phase (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                name VARCHAR(200) NOT NULL,
                name_arabic VARCHAR(200) DEFAULT '',
                description TEXT,
                duration_weeks INTEGER,
                goal TEXT,
                status VARCHAR(20) DEFAULT 'pending',
                order_index INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (project_id) REFERENCES project (id) ON DELETE CASCADE
            )
        """)
        print("  ✅ Created phase table")
    else:
        print("  ✅ phase table already exists")
    
    # UserStory table
    if not table_exists(cursor, 'user_story'):
        cursor.execute("""
            CREATE TABLE user_story (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phase_id INTEGER NOT NULL,
                story_id VARCHAR(20) NOT NULL,
                title VARCHAR(300) NOT NULL,
                title_arabic VARCHAR(300),
                user_role VARCHAR(100),
                user_goal TEXT,
                user_benefit TEXT,
                description TEXT,
                priority VARCHAR(10) DEFAULT 'medium',
                complexity VARCHAR(10) DEFAULT 'medium',
                status VARCHAR(20) DEFAULT 'pending',
                technical_notes TEXT,
                order_index INTEGER DEFAULT 0,
                completed_at DATETIME,
                created_by VARCHAR(100),
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (phase_id) REFERENCES phase (id) ON DELETE CASCADE
            )
        """)
        print("  ✅ Created user_story table")
    else:
        print("  ✅ user_story table already exists")
    
    # AcceptanceCriteria table
    if not table_exists(cursor, 'acceptance_criteria'):
        cursor.execute("""
            CREATE TABLE acceptance_criteria (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_story_id INTEGER NOT NULL,
                description TEXT NOT NULL,
                description_arabic TEXT,
                is_completed BOOLEAN DEFAULT 0,
                order_index INTEGER DEFAULT 0,
                completed_at DATETIME,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_story_id) REFERENCES user_story (id) ON DELETE CASCADE
            )
        """)
        print("  ✅ Created acceptance_criteria table")
    else:
        print("  ✅ acceptance_criteria table already exists")
    
    # StoryNote table
    if not table_exists(cursor, 'story_note'):
        cursor.execute("""
            CREATE TABLE story_note (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_story_id INTEGER NOT NULL,
                content TEXT NOT NULL,
                note_type VARCHAR(20) DEFAULT 'general',
                author VARCHAR(100),
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_story_id) REFERENCES user_story (id) ON DELETE CASCADE
            )
        """)
        print("  ✅ Created story_note table")
    else:
        print("  ✅ story_note table already exists")

def create_indexes(cursor):
    """Create performance indexes"""
    print("🔄 Creating performance indexes...")
    
    indexes = [
        ("idx_voice_note_deleted", "CREATE INDEX IF NOT EXISTS idx_voice_note_deleted ON voice_note(deleted_at)"),
        ("idx_voice_recording_note", "CREATE INDEX IF NOT EXISTS idx_voice_recording_note ON voice_recording(voice_note_id)"),
        ("idx_voice_comment_note", "CREATE INDEX IF NOT EXISTS idx_voice_comment_note ON voice_comment(voice_note_id)"),
        ("idx_voice_summary_note", "CREATE INDEX IF NOT EXISTS idx_voice_summary_note ON voice_summary(voice_note_id)"),
        ("idx_voice_summary_current", "CREATE INDEX IF NOT EXISTS idx_voice_summary_current ON voice_summary(is_current)"),
        ("idx_smart_notion_deleted", "CREATE INDEX IF NOT EXISTS idx_smart_notion_deleted ON smart_notion(deleted_at)"),
        ("idx_monthly_plan_date", "CREATE INDEX IF NOT EXISTS idx_monthly_plan_date ON monthly_plan(year, month)"),
        ("idx_monthly_goal_plan", "CREATE INDEX IF NOT EXISTS idx_monthly_goal_plan ON monthly_goal(monthly_plan_id)"),
        ("idx_reminder_date", "CREATE INDEX IF NOT EXISTS idx_reminder_date ON reminder(reminder_date)"),
        ("idx_chat_conversation_notion", "CREATE INDEX IF NOT EXISTS idx_chat_conversation_notion ON chat_conversation(notion_id)"),
        ("idx_phase_project", "CREATE INDEX IF NOT EXISTS idx_phase_project ON phase(project_id)"),
        ("idx_story_phase", "CREATE INDEX IF NOT EXISTS idx_story_phase ON user_story(phase_id)"),
        ("idx_story_status", "CREATE INDEX IF NOT EXISTS idx_story_status ON user_story(status)"),
        ("idx_criteria_story", "CREATE INDEX IF NOT EXISTS idx_criteria_story ON acceptance_criteria(user_story_id)"),
        ("idx_note_story", "CREATE INDEX IF NOT EXISTS idx_note_story ON story_note(user_story_id)"),
        ("idx_project_status", "CREATE INDEX IF NOT EXISTS idx_project_status ON project(status)")
    ]
    
    for index_name, sql in indexes:
        try:
            cursor.execute(sql)
            print(f"  ✅ Created index: {index_name}")
        except sqlite3.Error as e:
            print(f"  ⚠️  Index {index_name} already exists or error: {e}")

def migrate_production_database():
    """Migrate the production database with all recent changes"""
    
    db_path = get_db_path()
    print(f"🗄️  Using database path: {db_path}")
    
    # Check if database exists
    if not os.path.exists(db_path):
        print("Database not found. Will be created with new schema...")
        return True
    
    # Create backup
    backup_path = f"{db_path}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    try:
        import shutil
        shutil.copy2(db_path, backup_path)
        print(f"📋 Created backup: {backup_path}")
    except Exception as e:
        print(f"⚠️  Warning: Could not create backup: {e}")
    
    print("\n🚀 Starting comprehensive production database migration...")
    
    try:
        # Connect to database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Run all migrations
        migrate_task_table(cursor)
        migrate_resource_table(cursor)
        migrate_smart_notion_table(cursor)
        create_voice_notes_tables(cursor)
        create_monthly_planning_tables(cursor)
        create_reminder_table(cursor)
        create_chat_conversation_table(cursor)
        create_backlog_tables(cursor)
        create_indexes(cursor)
        
        # Commit all changes
        conn.commit()
        
        print("\n🎉 Production migration completed successfully!")
        print("\n📊 Database schema summary:")
        
        # Show table information
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = cursor.fetchall()
        print("\nTables in database:")
        for table in tables:
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {table[0]}")
                count = cursor.fetchone()[0]
                print(f"  📋 {table[0]}: {count} records")
            except sqlite3.Error:
                print(f"  📋 {table[0]}: (unable to count)")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"\n❌ Production migration failed: {str(e)}")
        if 'conn' in locals():
            conn.rollback()
            conn.close()
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("🚀 COMPREHENSIVE PRODUCTION DATABASE MIGRATION")
    print("=" * 60)
    print("This script will safely migrate the production database with ALL recent changes:")
    print()
    print("📋 TABLE ENHANCEMENTS:")
    print("  • Task table: tags, updated_at, completed_at fields")
    print("  • Resource table: filename, file_size, updated_at fields")
    print("  • SmartNotion table: deleted_at field for soft delete")
    print()
    print("🆕 NEW TABLES:")
    print("  • Voice Notes system (4 tables): voice_note, voice_recording, voice_comment, voice_summary")
    print("  • Monthly Planning system (2 tables): monthly_plan, monthly_goal")
    print("  • Reminder system: reminder table")
    print("  • Chat system: chat_conversation table")
    print("  • Backlog Management system (5 tables): project, phase, user_story, acceptance_criteria, story_note")
    print()
    print("⚡ PERFORMANCE:")
    print("  • Database indexes for better query performance")
    print("  • Foreign key relationships for data integrity")
    print()
    print("🔒 SAFETY:")
    print("  • Automatic database backup before migration")
    print("  • Safe column additions (no data loss)")
    print("  • Rollback support on errors")
    print()
    
    # Run migration
    if migrate_production_database():
        print("\n" + "=" * 60)
        print("🎉 PRODUCTION MIGRATION COMPLETED SUCCESSFULLY!")
        print("=" * 60)
        print("✅ All database changes have been applied safely")
        print("✅ Your application now has all the latest features:")
        print("   • Enhanced task management with tags and timestamps")
        print("   • File upload support for resources")
        print("   • Voice notes and Ideas Bank functionality")
        print("   • Monthly planning and goal tracking")
        print("   • Reminder system")
        print("   • AI chat conversations")
        print("   • Backlog management for development workflow")
        print("   • Soft delete for smart notions")
        print()
        print("🚀 Your production environment is now fully up to date!")
        print("=" * 60)
    else:
        print("\n" + "=" * 60)
        print("❌ PRODUCTION MIGRATION FAILED!")
        print("=" * 60)
        print("Please check the error messages above and try again.")
        print("If the issue persists, check the backup file created before migration.")
        exit(1)