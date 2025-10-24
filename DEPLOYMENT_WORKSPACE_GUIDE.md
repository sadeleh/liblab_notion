# Workspace & User Management Deployment Guide

## Overview

This guide walks you through deploying workspace and user management features to your Fly.io production environment.

## What's Being Deployed

### New Features
1. **User Authentication System**
   - Login/logout functionality
   - Password hashing and security
   - User management

2. **Workspace Multi-Tenancy**
   - Multiple workspaces support
   - Workspace-based data isolation
   - User-workspace assignments

3. **Admin Panel**
   - User management interface
   - Workspace management interface
   - Super admin capabilities

### Database Changes
1. **New Tables**
   - `user` - User accounts
   - `workspace` - Workspaces/tenants
   - `user_workspace` - Many-to-many relationship

2. **Modified Tables**
   - All data tables get a `workspace_id` column
   - Existing data migrated to `ws-general` workspace

3. **Default Data**
   - Default workspace: `ws-general`
   - Default admin user: `admin` / `admin_@2025`

## Pre-Deployment Checklist

- [ ] Verify local changes are working correctly
- [ ] Ensure all code changes are committed
- [ ] Review the deployment script: `deploy_workspace_to_production.py`
- [ ] Have Fly.io CLI installed and logged in

## Deployment Steps

### Step 1: Verify Fly.io Access

```bash
# Check if you're logged in
fly auth whoami

# Check your app status
fly status -a liblab-notion

# Check your app's current environment
fly ssh console -a liblab-notion
```

### Step 2: Upload Deployment Script

You have two options:

#### Option A: Using fly ssh console (Recommended)

```bash
# 1. Open SSH console
fly ssh console -a liblab-notion

# 2. Create the script (copy-paste the content)
cat > deploy_workspace_to_production.py << 'EOF'
[paste the script content here]
EOF

# 3. Run the script
python deploy_workspace_to_production.py

# 4. Exit SSH console
exit
```

#### Option B: Using fly deploy (Alternative)

```bash
# 1. Ensure the deployment script is in your project
# (already created as deploy_workspace_to_production.py)

# 2. Deploy the entire app with the new script
fly deploy -a liblab-notion

# 3. SSH into the app
fly ssh console -a liblab-notion

# 4. Run the script
python deploy_workspace_to_production.py

# 5. Exit SSH console
exit
```

### Step 3: Restart the Application

```bash
# Restart to apply all changes
fly apps restart liblab-notion

# Monitor the restart
fly logs -a liblab-notion
```

### Step 4: Verify Deployment

```bash
# Open the app in browser
fly apps open liblab-notion

# You should be redirected to /login
# Login with:
#   Username: admin
#   Password: admin_@2025
```

### Step 5: Post-Deployment Verification

1. **Test Login**
   - Navigate to your app URL
   - You should see the login page
   - Login with admin credentials

2. **Verify Data Migration**
   - Check that all your existing data is visible
   - All data should be in the 'ws-general' workspace

3. **Test Admin Panel**
   - Navigate to /admin/users
   - Navigate to /admin/workspaces
   - Verify you can see the admin user and ws-general workspace

4. **Test User Creation**
   - Create a test user via admin panel
   - Assign them to ws-general workspace
   - Try logging in with the new user

## Detailed Deployment Commands

Here's the complete command sequence:

```bash
# === STEP 1: Connect to Fly.io ===
fly ssh console -a liblab-notion

# === STEP 2: Inside SSH Console ===
# Check current database location
ls -la /app/instance/team_planning.db

# Upload and run the deployment script
python << 'EOF'
# [The entire deploy_workspace_to_production.py script content]
EOF

# OR if you've already uploaded the file:
python deploy_workspace_to_production.py

# === STEP 3: Exit and Restart ===
exit

fly apps restart liblab-notion

# === STEP 4: Monitor ===
fly logs -a liblab-notion

# === STEP 5: Test ===
fly apps open liblab-notion
```

## Rollback Procedure

If something goes wrong:

```bash
# 1. Connect to production
fly ssh console -a liblab-notion

# 2. List backups
ls -la /app/instance/team_planning.db.backup_*

# 3. Restore from backup (replace timestamp with your backup)
cp /app/instance/team_planning.db.backup_20250101_120000 /app/instance/team_planning.db

# 4. Exit and restart
exit
fly apps restart liblab-notion
```

## Troubleshooting

### Issue: Can't access /login page

**Solution:**
```bash
# Check if app is running
fly status -a liblab-notion

# Check logs for errors
fly logs -a liblab-notion

# Restart the app
fly apps restart liblab-notion
```

### Issue: Database locked error

**Solution:**
```bash
# SSH into production
fly ssh console -a liblab-notion

# Check database integrity
sqlite3 /app/instance/team_planning.db "PRAGMA integrity_check;"

# If needed, restart the app
exit
fly apps restart liblab-notion
```

### Issue: Admin user can't login

**Solution:**
```bash
# SSH into production
fly ssh console -a liblab-notion

# Reset admin password
python << 'EOF'
import sqlite3
from werkzeug.security import generate_password_hash

conn = sqlite3.connect('/app/instance/team_planning.db')
cursor = conn.cursor()
password_hash = generate_password_hash('admin_@2025')
cursor.execute("UPDATE user SET password_hash = ? WHERE username = 'admin'", (password_hash,))
conn.commit()
conn.close()
print("✓ Admin password reset to: admin_@2025")
EOF

exit
```

### Issue: Existing data not visible

**Solution:**
```bash
# SSH into production
fly ssh console -a liblab-notion

# Check workspace migration
python << 'EOF'
import sqlite3

conn = sqlite3.connect('/app/instance/team_planning.db')
cursor = conn.cursor()

# Check task table
cursor.execute("SELECT COUNT(*) FROM task WHERE workspace_id = 'ws-general'")
print(f"Tasks in ws-general: {cursor.fetchone()[0]}")

# Check if any tasks don't have workspace_id
cursor.execute("SELECT COUNT(*) FROM task WHERE workspace_id IS NULL OR workspace_id = ''")
unmigrated = cursor.fetchone()[0]
print(f"Unmigrated tasks: {unmigrated}")

if unmigrated > 0:
    cursor.execute("UPDATE task SET workspace_id = 'ws-general' WHERE workspace_id IS NULL OR workspace_id = ''")
    conn.commit()
    print(f"✓ Migrated {unmigrated} tasks to ws-general")

conn.close()
EOF

exit
fly apps restart liblab-notion
```

## Post-Deployment Tasks

1. **Change Admin Password**
   - Login as admin
   - Go to admin panel
   - Change the default password to something secure

2. **Create Additional Users** (if needed)
   - Use the admin panel to create users
   - Assign them to appropriate workspaces

3. **Create Additional Workspaces** (if needed)
   - Use the admin panel to create workspaces
   - Assign users to workspaces

4. **Test All Features**
   - Test task creation
   - Test resource uploads
   - Test voice notes
   - Test backlog management
   - Test monthly planning

## Security Considerations

1. **Change Default Admin Password**
   - The default password `admin_@2025` should be changed immediately after deployment

2. **User Password Policy**
   - Passwords are hashed using werkzeug.security
   - Consider enforcing strong password requirements

3. **Session Management**
   - Sessions are stored in Flask's session cookies
   - Make sure SECRET_KEY is set to a strong random value in production

## Support

If you encounter issues not covered in this guide:

1. Check Fly.io logs: `fly logs -a liblab-notion`
2. Check database integrity: See troubleshooting section
3. Review the deployment script output for specific errors
4. Consider reaching out with specific error messages

## Summary

After successful deployment, you will have:
- ✅ User authentication system with login/logout
- ✅ Multi-workspace support with data isolation
- ✅ Admin panel for user and workspace management
- ✅ All existing data migrated to 'ws-general' workspace
- ✅ Admin user (admin/admin_@2025) with full access
- ✅ Backward compatible with all existing features

Your app is now ready for multi-user, multi-workspace usage! 🎉

