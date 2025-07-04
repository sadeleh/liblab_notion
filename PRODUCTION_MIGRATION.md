# Production Database Migration Guide

## 🚨 Critical Issue: Voice Notes Tables Missing

Your production database is missing the voice notes tables, causing **500 errors** when accessing `/voice_notes`. This is the **top priority** migration.

### Current Production Error:
```
sqlite3.OperationalError: no such table: voice_note
```

## Required Migrations

### Priority 1: Voice Notes Tables (Critical) 🔥

**This migration is required to fix the 500 errors**

#### Quick Fix:
```bash
# SSH into your Fly.io app and run the migration

 -C "cd /app && python migrate_voice_notes_tables.py"
```

#### Detailed Steps:
```bash
# 1. SSH into your container
fly ssh console -a liblab-notion

# 2. Navigate to app directory  
cd /app

# 3. Run voice notes migration
python migrate_voice_notes_tables.py

# 4. Restart app (optional)
exit
fly restart -a liblab-notion  
```

#### What This Creates:
- `voice_note` - Main ideas/voice notes table
- `voice_recording` - Audio recordings table  
- `voice_comment` - Text comments table
- `voice_summary` - AI-generated summaries table
- Performance indexes for better query speed

### Priority 2: Smart Notion Soft Delete (Optional) 

Only needed if you're seeing smart notion delete errors:

```bash
fly ssh console -a liblab-notion -C "cd /app && python migrate_production.py"
```

## Migration Status Check

### Before Migration:
- ❌ `/voice_notes` returns 500 error
- ❌ Ideas Bank menu item causes crashes
- ✅ Other features work normally

### After Voice Notes Migration:
- ✅ `/voice_notes` loads successfully  
- ✅ Full Ideas Bank functionality
- ✅ Voice recording and AI features work
- ✅ All existing features continue working

## Verification Steps

### 1. Check Migration Success:
```bash
# View logs to confirm migration completed
fly logs -a liblab-notion

# Should see messages like:
# ✅ Created voice_note table
# ✅ Created voice_recording table  
# ✅ Created voice_comment table
# ✅ Created voice_summary table
```

### 2. Test the Website:
- Go to your website's Ideas Bank section
- Should load without 500 errors
- Try creating a new idea

### 3. Verify Tables Exist:
```bash
fly ssh console -a liblab-notion
sqlite3 instance/team_planning.db "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'voice_%';"
```

## Alternative: Manual SQL Migration

If the script fails, you can run the SQL manually:

```bash
# SSH into your app
fly ssh console -a liblab-notion

# Connect to database
sqlite3 instance/team_planning.db

# Run the table creation commands
CREATE TABLE voice_note (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title VARCHAR(200) NOT NULL,
    description TEXT,
    summary_html TEXT,
    created_by VARCHAR(100),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    deleted_at DATETIME
);

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
);

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
);

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
);

# Exit database
.exit
```

## Troubleshooting

### If Migration Script Not Found:
```bash
# Re-deploy to get the latest code with migration scripts
fly deploy -a liblab-notion
```

### If Database is Locked:
```bash
# Restart the app first
fly restart -a liblab-notion

# Wait 30 seconds, then try migration
fly ssh console -a liblab-notion -C "cd /app && python migrate_voice_notes_tables.py"
```

### If Permissions Error:
```bash
# Check database file permissions
fly ssh console -a liblab-notion
ls -la instance/team_planning.db
chmod 664 instance/team_planning.db  # if needed
```

## Safety Notes

- 🔒 **Safe**: Only adds new tables, doesn't modify existing data
- 📋 **Backwards Compatible**: App works before and after migration
- 🚀 **Zero Downtime**: No service interruption required
- 💾 **Data Preserved**: All existing data remains untouched
- 🔄 **Rollback Safe**: Migration can be safely repeated

## Post-Migration Features

After successful migration, you'll have access to:

### Ideas Bank (Voice Notes):
- 💡 Create and organize voice ideas
- 🎙️ Record audio directly in browser  
- 📝 Add text comments and notes
- 🤖 AI-powered transcription (with ElevenLabs)
- 🖨️ Enhanced print functionality for comprehensive reports

### Enhanced Print Features:
- **Complete Reports**: Print full voice note information including recordings, transcripts, comments, and AI analysis
- **Professional Layout**: Clean, Arabic RTL-optimized formatting for sharing or archiving  
- **Historical Support**: Print any version of generated reports
- **Smart Content**: Always available - prints basic voice note data even without AI summaries
- **Detailed Statistics**: Includes comprehensive statistics and metadata
- 📊 Generate comprehensive AI summaries
- 📈 Historical report tracking
- 🔍 Search and organize ideas

### Enhanced Smart Notions:
- 🗑️ Soft delete functionality (if second migration run)
- 📋 Better data management

## Support

If you encounter any issues:

1. **Check Fly.io logs**: `fly logs -a liblab-notion`
2. **Restart app**: `fly restart -a liblab-notion`  
3. **Re-run migration**: The script is safe to run multiple times
4. **Manual SQL**: Use the SQL commands above as fallback

---

## Quick Command Summary

```bash
# Fix the 500 errors (REQUIRED)
fly ssh console -a liblab-notion -C "cd /app && python migrate_voice_notes_tables.py"

# Optional: Add soft delete to smart notions  
fly ssh console -a liblab-notion -C "cd /app && python migrate_production.py"

# Restart app
fly restart -a liblab-notion

# Check logs
fly logs -a liblab-notion
```