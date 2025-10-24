"""
Migration script to add workspace multi-tenancy support.

This script:
1. Creates the ws-general workspace
2. Creates the admin super user
3. Assigns admin to ws-general workspace
4. Updates all existing data records to belong to ws-general workspace
"""

from app import app, db, User, Workspace, UserWorkspace
from app import Task, Resource, BrainstormSession, Idea, SmartNotion, ChatConversation
from app import VoiceNote, VoiceRecording, VoiceComment, VoiceSummary
from app import MonthlyPlan, MonthlyGoal, Reminder
from app import Project, Phase, UserStory, AcceptanceCriteria, StoryNote

def migrate_to_workspaces():
    """Run the migration to add workspace support"""
    with app.app_context():
        print("Starting workspace migration...")
        
        # Step 1: Create tables if they don't exist
        print("Creating database tables...")
        db.create_all()
        print("✓ Tables created")
        
        # Step 2: Create ws-general workspace
        print("\nCreating ws-general workspace...")
        workspace = Workspace.query.get('ws-general')
        if not workspace:
            workspace = Workspace(
                id='ws-general',
                name='General Work Space',
                description='Default workspace for existing data'
            )
            db.session.add(workspace)
            db.session.commit()
            print("✓ ws-general workspace created")
        else:
            print("✓ ws-general workspace already exists")
        
        # Step 3: Create admin user
        print("\nCreating admin user...")
        admin = User.query.filter_by(username='admin').first()
        if not admin:
            admin = User(
                username='admin',
                is_superadmin=True,
                last_workspace_id='ws-general'
            )
            admin.set_password('admin_@2025')
            db.session.add(admin)
            db.session.commit()
            print("✓ Admin user created (username: admin, password: admin_@2025)")
        else:
            print("✓ Admin user already exists")
            # Ensure admin has correct settings
            if not admin.is_superadmin:
                admin.is_superadmin = True
                db.session.commit()
                print("✓ Updated admin to superadmin")
        
        # Step 4: Assign admin to ws-general workspace
        print("\nAssigning admin to ws-general workspace...")
        user_workspace = UserWorkspace.query.filter_by(
            user_id=admin.id,
            workspace_id='ws-general'
        ).first()
        if not user_workspace:
            user_workspace = UserWorkspace(
                user_id=admin.id,
                workspace_id='ws-general'
            )
            db.session.add(user_workspace)
            db.session.commit()
            print("✓ Admin assigned to ws-general workspace")
        else:
            print("✓ Admin already assigned to ws-general workspace")
        
        # Step 5: Add workspace_id column to existing tables
        print("\nAdding workspace_id column to existing tables...")
        
        # Use raw SQL to add columns since SQLAlchemy models already have them
        from sqlalchemy import text
        
        tables_to_update = [
            'task', 'resource', 'brainstorm_session', 'idea', 'smart_notion', 'chat_conversation',
            'voice_note', 'voice_recording', 'voice_comment', 'voice_summary',
            'monthly_plan', 'monthly_goal', 'reminder',
            'project', 'phase', 'user_story', 'acceptance_criteria', 'story_note'
        ]
        
        for table_name in tables_to_update:
            try:
                # Check if column exists
                result = db.session.execute(text(f"PRAGMA table_info({table_name})"))
                columns = [row[1] for row in result]
                
                if 'workspace_id' not in columns:
                    # Add the column
                    db.session.execute(text(f"ALTER TABLE {table_name} ADD COLUMN workspace_id VARCHAR(50)"))
                    print(f"✓ Added workspace_id column to {table_name}")
                else:
                    print(f"  {table_name}: workspace_id column already exists")
            except Exception as e:
                print(f"⚠ {table_name}: {str(e)}")
        
        db.session.commit()
        
        # Step 6: Migrate existing data to ws-general workspace
        print("\nMigrating existing data to ws-general workspace...")
        
        models_to_migrate = [
            ('Task', Task),
            ('Resource', Resource),
            ('BrainstormSession', BrainstormSession),
            ('Idea', Idea),
            ('SmartNotion', SmartNotion),
            ('ChatConversation', ChatConversation),
            ('VoiceNote', VoiceNote),
            ('VoiceRecording', VoiceRecording),
            ('VoiceComment', VoiceComment),
            ('VoiceSummary', VoiceSummary),
            ('MonthlyPlan', MonthlyPlan),
            ('MonthlyGoal', MonthlyGoal),
            ('Reminder', Reminder),
            ('Project', Project),
            ('Phase', Phase),
            ('UserStory', UserStory),
            ('AcceptanceCriteria', AcceptanceCriteria),
            ('StoryNote', StoryNote),
        ]
        
        for model_name, model_class in models_to_migrate:
            try:
                # Get all records without workspace_id
                records = model_class.query.filter(
                    (model_class.workspace_id == None) | (model_class.workspace_id == '')
                ).all()
                
                if records:
                    for record in records:
                        record.workspace_id = 'ws-general'
                    db.session.commit()
                    print(f"✓ Migrated {len(records)} {model_name} record(s)")
                else:
                    # Check total records
                    total = model_class.query.count()
                    if total > 0:
                        print(f"✓ {model_name}: All {total} records already have workspace_id")
                    else:
                        print(f"  {model_name}: No records to migrate")
            except Exception as e:
                print(f"✗ Error migrating {model_name}: {str(e)}")
                db.session.rollback()
        
        print("\n" + "="*50)
        print("Migration completed successfully!")
        print("="*50)
        print("\nYou can now login with:")
        print("  Username: admin")
        print("  Password: admin_@2025")
        print("\nAll existing data has been migrated to the 'ws-general' workspace.")

if __name__ == '__main__':
    try:
        migrate_to_workspaces()
    except Exception as e:
        print(f"\n✗ Migration failed: {str(e)}")
        import traceback
        traceback.print_exc()

