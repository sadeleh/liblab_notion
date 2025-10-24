from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session, send_from_directory, make_response
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text, or_
from datetime import datetime, date
import os
import uuid
import google.generativeai as genai
import json
import re
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from storage_service import create_storage_service, StorageService

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///team_planning.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# File upload configuration for resources
RESOURCES_UPLOAD_FOLDER = os.path.join(os.getcwd(), 'instance', 'resources')
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max file size
ALLOWED_EXTENSIONS = {'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'zip', 'rar', '7z', 'mp4', 'avi', 'mov', 'mp3', 'wav', 'csv', 'json', 'xml', 'md'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_file_type(filename):
    """Determine file type based on extension"""
    if not filename:
        return 'file'
    
    ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    
    if ext in ['pdf', 'doc', 'docx', 'txt', 'md']:
        return 'document'
    elif ext in ['png', 'jpg', 'jpeg', 'gif', 'bmp', 'svg']:
        return 'image'
    elif ext in ['mp4', 'avi', 'mov', 'mkv', 'wmv']:
        return 'video'
    elif ext in ['mp3', 'wav', 'flac', 'aac', 'ogg']:
        return 'audio'
    elif ext in ['zip', 'rar', '7z', 'tar', 'gz']:
        return 'archive'
    elif ext in ['xls', 'xlsx', 'csv']:
        return 'spreadsheet'
    elif ext in ['ppt', 'pptx']:
        return 'presentation'
    else:
        return 'file'

def generate_unique_filename(filename):
    """Generate a unique filename to avoid conflicts"""
    if not filename:
        return str(uuid.uuid4())
    
    name, ext = os.path.splitext(secure_filename(filename))
    unique_id = str(uuid.uuid4())[:8]
    return f"{name}_{unique_id}{ext}"

def format_file_size(size_bytes):
    """Format file size in human readable format"""
    if size_bytes == 0:
        return "0B"
    size_names = ["B", "KB", "MB", "GB"]
    i = 0
    while size_bytes >= 1024 and i < len(size_names) - 1:
        size_bytes /= 1024.0
        i += 1
    return f"{size_bytes:.1f}{size_names[i]}"

db = SQLAlchemy(app)

# Global request logger
@app.before_request
def log_request():
    """Log every incoming request"""
    import threading
    print("\n" + "🌐" + "="*79)
    print(f"🌐 INCOMING REQUEST")
    print(f"   - Thread ID: {threading.current_thread().ident}")
    print(f"   - Thread Name: {threading.current_thread().name}")
    print(f"   - Active Threads: {threading.active_count()}")
    print(f"   - Method: {request.method}")
    print(f"   - URL: {request.url}")
    print(f"   - Path: {request.path}")
    print(f"   - Endpoint: {request.endpoint}")
    print(f"   - Remote Address: {request.remote_addr}")
    print(f"   - User Agent: {request.user_agent.string if request.user_agent else 'None'}")
    print("="*80)

@app.after_request
def log_response(response):
    """Log every outgoing response"""
    print("\n" + "📤" + "="*79)
    print(f"📤 OUTGOING RESPONSE")
    print(f"   - Status: {response.status}")
    print(f"   - Content-Type: {response.content_type}")
    print(f"   - Content-Length: {response.content_length}")
    print("="*80 + "\n")
    return response

# Create upload directories
VOICE_UPLOAD_FOLDER = os.path.join(app.instance_path, 'voice_recordings')
app.config['UPLOAD_FOLDER'] = VOICE_UPLOAD_FOLDER  # Default for voice recordings

# Ensure upload directories exist
os.makedirs(VOICE_UPLOAD_FOLDER, exist_ok=True)
os.makedirs(RESOURCES_UPLOAD_FOLDER, exist_ok=True)
os.makedirs(app.instance_path, exist_ok=True)

# Initialize Storage Service (S3 or local fallback)
# Will use S3 if AWS credentials are available in environment, otherwise falls back to local storage
storage_service: StorageService = None

def get_storage_service(workspace_id='ws-general') -> StorageService:
    """Get or create the storage service instance for a specific workspace."""
    global storage_service
    # Note: For simplicity, we're using a single global instance
    # In production, you might want to cache per workspace
    if storage_service is None:
        # Check if we should use S3 (credentials available)
        use_s3 = bool(os.environ.get('AWS_ACCESS_KEY_ID') and os.environ.get('AWS_SECRET_ACCESS_KEY'))
        with app.app_context():
            storage_service = create_storage_service(use_s3=use_s3, workspace_id=workspace_id)
        print(f"✓ Storage service initialized: {'S3 (AWS)' if use_s3 else 'Local filesystem'}")
    return storage_service

# Database Models - User Management
class User(db.Model):
    """User model for authentication and workspace access"""
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    is_superadmin = db.Column(db.Boolean, default=False)
    last_workspace_id = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    workspaces = db.relationship('UserWorkspace', backref='user', lazy=True, cascade='all, delete-orphan')
    
    def set_password(self, password):
        """Hash and set password"""
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        """Check if provided password matches hash"""
        return check_password_hash(self.password_hash, password)

class Workspace(db.Model):
    """Workspace model for multi-tenancy"""
    id = db.Column(db.String(50), primary_key=True)  # e.g., ws-general
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    users = db.relationship('UserWorkspace', backref='workspace', lazy=True, cascade='all, delete-orphan')

class UserWorkspace(db.Model):
    """Many-to-many relationship between users and workspaces"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    workspace_id = db.Column(db.String(50), db.ForeignKey('workspace.id'), nullable=False)
    assigned_at = db.Column(db.DateTime, default=datetime.utcnow)

# Authentication Decorators and Helpers
def login_required(f):
    """Decorator to require authentication for routes"""
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('user_id'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def superadmin_required(f):
    """Decorator to require superadmin access"""
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        print(f"\n🔐 SUPERADMIN_REQUIRED DECORATOR CHECK")
        print(f"   - Function: {f.__name__}")
        print(f"   - Session user_id: {session.get('user_id')}")
        
        if not session.get('user_id'):
            print(f"   ❌ No user_id in session, redirecting to login")
            return redirect(url_for('login'))
        
        print(f"   🔍 Querying user with id: {session['user_id']}")
        try:
            user = User.query.get(session['user_id'])
            print(f"   ✅ User query completed")
            print(f"      - User found: {user is not None}")
            if user:
                print(f"      - Username: {user.username}")
                print(f"      - Is superadmin: {user.is_superadmin}")
        except Exception as e:
            print(f"   ❌ Error querying user: {e}")
            import traceback
            traceback.print_exc()
            raise
        
        if not user or not user.is_superadmin:
            print(f"   ❌ Access denied - user is not superadmin")
            flash('Access denied. Super admin privileges required.', 'error')
            return redirect(url_for('index'))
        
        print(f"   ✅ Superadmin check passed, calling function")
        return f(*args, **kwargs)
    return decorated_function

def get_current_user():
    """Get current logged-in user"""
    user_id = session.get('user_id')
    if user_id:
        return User.query.get(user_id)
    return None

def get_current_workspace():
    """Get current workspace from session"""
    workspace_id = session.get('current_workspace_id')
    if workspace_id:
        return Workspace.query.get(workspace_id)
    return None

def has_workspace_access(user, workspace_id):
    """Check if user has access to a workspace"""
    if user.is_superadmin:
        return True
    return UserWorkspace.query.filter_by(user_id=user.id, workspace_id=workspace_id).first() is not None

# Database Models - Data Entities
class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    workspace_id = db.Column(db.String(50), db.ForeignKey('workspace.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    status = db.Column(db.String(20), default='pending')
    priority = db.Column(db.String(10), default='medium')
    assigned_to = db.Column(db.String(100))
    due_date = db.Column(db.Date)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    category = db.Column(db.String(50), default='general')
    tags = db.Column(db.String(500))  # Comma-separated tags
    completed_at = db.Column(db.DateTime, nullable=True)
    
    @property
    def is_overdue(self):
        """Check if task is overdue"""
        if not self.due_date or self.status == 'completed':
            return False
        return self.due_date < date.today()
        
    @property
    def days_until_due(self):
        """Calculate days until due date"""
        if not self.due_date:
            return None
        delta = self.due_date - date.today()
        return delta.days

class Resource(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    workspace_id = db.Column(db.String(50), db.ForeignKey('workspace.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    url = db.Column(db.String(500))
    resource_type = db.Column(db.String(50))  # link, document, file, image, note, tool, reference
    tags = db.Column(db.String(200))
    filename = db.Column(db.String(255))  # For uploaded files
    file_size = db.Column(db.Integer)  # File size in bytes
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.String(100))

class BrainstormSession(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    workspace_id = db.Column(db.String(50), db.ForeignKey('workspace.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    status = db.Column(db.String(20), default='active')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.String(100))

class Idea(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    workspace_id = db.Column(db.String(50), db.ForeignKey('workspace.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    session_id = db.Column(db.Integer, db.ForeignKey('brainstorm_session.id'), nullable=False)
    author = db.Column(db.String(100))
    votes = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class SmartNotion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    workspace_id = db.Column(db.String(50), db.ForeignKey('workspace.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    content_html = db.Column(db.Text, nullable=False)
    created_by = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    deleted_at = db.Column(db.DateTime, nullable=True)
    
class ChatConversation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    workspace_id = db.Column(db.String(50), db.ForeignKey('workspace.id'), nullable=False)
    notion_id = db.Column(db.Integer, db.ForeignKey('smart_notion.id'), nullable=False)
    user_message = db.Column(db.Text, nullable=False)
    ai_response = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class VoiceNote(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    workspace_id = db.Column(db.String(50), db.ForeignKey('workspace.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    summary_html = db.Column(db.Text)  # Gemini-generated summary and insights
    created_by = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    deleted_at = db.Column(db.DateTime, nullable=True)
    
class VoiceRecording(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    workspace_id = db.Column(db.String(50), db.ForeignKey('workspace.id'), nullable=False)
    voice_note_id = db.Column(db.Integer, db.ForeignKey('voice_note.id'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    original_name = db.Column(db.String(255))
    file_size = db.Column(db.Integer)  # in bytes
    duration = db.Column(db.Integer)  # in seconds
    content_type = db.Column(db.String(50), default='audio/webm')
    transcription = db.Column(db.Text)  # for future transcription
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
class VoiceComment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    workspace_id = db.Column(db.String(50), db.ForeignKey('workspace.id'), nullable=False)
    voice_note_id = db.Column(db.Integer, db.ForeignKey('voice_note.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    author = db.Column(db.String(100))
    comment_type = db.Column(db.String(20), default='text')  # 'text' or 'voice'
    recording_id = db.Column(db.Integer, db.ForeignKey('voice_recording.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class VoiceSummary(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    workspace_id = db.Column(db.String(50), db.ForeignKey('workspace.id'), nullable=False)
    voice_note_id = db.Column(db.Integer, db.ForeignKey('voice_note.id'), nullable=False)
    summary_html = db.Column(db.Text, nullable=False)  # The generated summary content
    summary_version = db.Column(db.Integer, default=1)  # Version number for tracking
    transcripts_count = db.Column(db.Integer, default=0)  # Number of transcripts analyzed
    comments_count = db.Column(db.Integer, default=0)  # Number of comments analyzed
    model_used = db.Column(db.String(100))  # Which AI model was used
    created_by = db.Column(db.String(100))  # Who generated this summary
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_current = db.Column(db.Boolean, default=True)  # Flag for the current/latest summary

class MonthlyPlan(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    workspace_id = db.Column(db.String(50), db.ForeignKey('workspace.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    month = db.Column(db.Integer, nullable=False)  # 1-12
    year = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), default='active')  # active, completed, archived
    priority = db.Column(db.String(10), default='medium')  # low, medium, high
    category = db.Column(db.String(50), default='general')
    tags = db.Column(db.String(500))  # Comma-separated tags
    progress_percentage = db.Column(db.Integer, default=0)  # 0-100
    created_by = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = db.Column(db.DateTime, nullable=True)
    deleted_at = db.Column(db.DateTime, nullable=True)
    
    @property
    def month_name_arabic(self):
        """Get Arabic month name"""
        months = {
            1: 'يناير', 2: 'فبراير', 3: 'مارس', 4: 'أبريل',
            5: 'مايو', 6: 'يونيو', 7: 'يوليو', 8: 'أغسطس',
            9: 'سبتمبر', 10: 'أكتوبر', 11: 'نوفمبر', 12: 'ديسمبر'
        }
        return months.get(self.month, 'غير محدد')
    
    @property
    def is_current_month(self):
        """Check if this plan is for the current month"""
        now = datetime.now()
        return self.month == now.month and self.year == now.year

class MonthlyGoal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    workspace_id = db.Column(db.String(50), db.ForeignKey('workspace.id'), nullable=False)
    monthly_plan_id = db.Column(db.Integer, db.ForeignKey('monthly_plan.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    target_date = db.Column(db.Date)
    status = db.Column(db.String(20), default='pending')  # pending, in_progress, completed
    priority = db.Column(db.String(10), default='medium')
    order_index = db.Column(db.Integer, default=0)  # For ordering goals
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = db.Column(db.DateTime, nullable=True)
    
    @property
    def is_overdue(self):
        """Check if goal is overdue"""
        if not self.target_date or self.status == 'completed':
            return False
        return self.target_date < date.today()
        
    @property
    def days_until_target(self):
        """Calculate days until target date"""
        if not self.target_date:
            return None
        delta = self.target_date - date.today()
        return delta.days

class Reminder(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    workspace_id = db.Column(db.String(50), db.ForeignKey('workspace.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    reminder_date = db.Column(db.Date)  # When to be reminded
    priority = db.Column(db.String(10), default='medium')  # low, medium, high
    status = db.Column(db.String(20), default='active')  # active, completed, dismissed
    category = db.Column(db.String(50), default='general')
    extra_info = db.Column(db.Text)  # Additional information like links, notes, etc.
    created_by = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = db.Column(db.DateTime, nullable=True)
    deleted_at = db.Column(db.DateTime, nullable=True)
    
    @property
    def is_due_today(self):
        """Check if reminder is due today"""
        if not self.reminder_date or self.status != 'active':
            return False
        return self.reminder_date <= date.today()
    
    @property
    def is_overdue(self):
        """Check if reminder is overdue"""
        if not self.reminder_date or self.status != 'active':
            return False
        return self.reminder_date < date.today()
        
    @property
    def days_until_reminder(self):
        """Calculate days until reminder date"""
        if not self.reminder_date:
            return None
        delta = self.reminder_date - date.today()
        return delta.days

# Backlog Management Models
class Project(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    workspace_id = db.Column(db.String(50), db.ForeignKey('workspace.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    name_arabic = db.Column(db.String(200), default='')
    description = db.Column(db.Text)
    status = db.Column(db.String(20), default='active')  # active, completed, archived
    priority = db.Column(db.String(10), default='medium')  # low, medium, high
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    created_by = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    deleted_at = db.Column(db.DateTime, nullable=True)
    order_index = db.Column(db.Integer, default=0)
    
    phases = db.relationship('Phase', backref='project', lazy=True, cascade='all, delete-orphan')
    
    @property
    def total_stories(self):
        """Count total user stories in all phases"""
        return sum(len(phase.user_stories) for phase in self.phases)
    
    @property
    def completed_stories(self):
        """Count completed user stories"""
        return sum(sum(1 for story in phase.user_stories if story.status == 'completed') for phase in self.phases)

class Phase(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    workspace_id = db.Column(db.String(50), db.ForeignKey('workspace.id'), nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    name_arabic = db.Column(db.String(200), default='')
    description = db.Column(db.Text)
    duration_weeks = db.Column(db.Integer)
    goal = db.Column(db.Text)
    status = db.Column(db.String(20), default='pending')  # pending, in_progress, completed
    order_index = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    user_stories = db.relationship('UserStory', backref='phase', lazy=True, cascade='all, delete-orphan')
    
    @property
    def progress_percentage(self):
        """Calculate phase completion percentage"""
        if not self.user_stories:
            return 0
        completed = sum(1 for story in self.user_stories if story.status == 'completed')
        return int((completed / len(self.user_stories)) * 100)

class UserStory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    workspace_id = db.Column(db.String(50), db.ForeignKey('workspace.id'), nullable=False)
    phase_id = db.Column(db.Integer, db.ForeignKey('phase.id'), nullable=False)
    story_id = db.Column(db.String(20), nullable=False)  # e.g., US-001
    title = db.Column(db.String(300), nullable=False)
    title_arabic = db.Column(db.String(300))
    user_role = db.Column(db.String(100))  # "As a [role]"
    user_goal = db.Column(db.Text)  # "I want to [goal]"
    user_benefit = db.Column(db.Text)  # "so I can [benefit]"
    description = db.Column(db.Text)
    priority = db.Column(db.String(10), default='medium')  # low, medium, high
    complexity = db.Column(db.String(10), default='medium')  # low, medium, high
    status = db.Column(db.String(20), default='pending')  # pending, in_progress, completed, blocked
    technical_notes = db.Column(db.Text)
    order_index = db.Column(db.Integer, default=0)
    completed_at = db.Column(db.DateTime, nullable=True)
    created_by = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    acceptance_criteria = db.relationship('AcceptanceCriteria', backref='user_story', lazy=True, cascade='all, delete-orphan')
    notes = db.relationship('StoryNote', backref='user_story', lazy=True, cascade='all, delete-orphan')
    
    @property
    def completion_percentage(self):
        """Calculate acceptance criteria completion percentage"""
        if not self.acceptance_criteria:
            return 0
        completed = sum(1 for ac in self.acceptance_criteria if ac.is_completed)
        return int((completed / len(self.acceptance_criteria)) * 100)
    
    @property
    def is_fully_completed(self):
        """Check if all acceptance criteria are completed"""
        return all(ac.is_completed for ac in self.acceptance_criteria) if self.acceptance_criteria else False

class AcceptanceCriteria(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    workspace_id = db.Column(db.String(50), db.ForeignKey('workspace.id'), nullable=False)
    user_story_id = db.Column(db.Integer, db.ForeignKey('user_story.id'), nullable=False)
    description = db.Column(db.Text, nullable=False)
    description_arabic = db.Column(db.Text)
    is_completed = db.Column(db.Boolean, default=False)
    order_index = db.Column(db.Integer, default=0)
    completed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class StoryNote(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    workspace_id = db.Column(db.String(50), db.ForeignKey('workspace.id'), nullable=False)
    user_story_id = db.Column(db.Integer, db.ForeignKey('user_story.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    note_type = db.Column(db.String(20), default='general')  # general, technical, design, question
    author = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# Gemini AI Configuration
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')
GEMINI_ENABLED = bool(GEMINI_API_KEY and GEMINI_API_KEY != 'your-gemini-api-key-here')

if GEMINI_ENABLED:
    genai.configure(api_key=GEMINI_API_KEY)

# ElevenLabs Speech-to-Text Configuration
ELEVENLABS_API_KEY = os.environ.get('ELEVENLABS_API_KEY', '')
ELEVENLABS_ENABLED = bool(ELEVENLABS_API_KEY and ELEVENLABS_API_KEY != 'your-elevenlabs-api-key-here')
ELEVENLABS_STT_URL = 'https://api.elevenlabs.io/v1/speech-to-text'

def test_gemini_connection():
    if not GEMINI_ENABLED:
        return False, "API key not configured"
    
    try:
        models = genai.list_models()
        available_models = []
        for model in models:
            if 'generateContent' in model.supported_generation_methods:
                available_models.append(model.name)
        
        return True, available_models
    except Exception as e:
        return False, str(e)

def get_best_gemini_model():
    if not GEMINI_ENABLED:
        return None
    
    preferred_models = [
        'models/gemini-2.5-flash', 
        'models/gemini-2.5-pro',
        'models/gemini-2.5-pro-preview-06-05',
        'models/gemini-2.0-flash-exp',
        'models/gemini-1.5-pro',
        'models/gemini-1.5-flash',
        'models/gemini-pro',
        'models/gemini-1.0-pro'
    ]
    
    try:
        models = genai.list_models()
        available_models = [m.name for m in models if 'generateContent' in m.supported_generation_methods]
        
        for preferred in preferred_models:
            if preferred in available_models:
                return preferred
                
        if available_models:
            return available_models[0]
            
        return None
    except Exception:
        return 'models/gemini-1.5-pro'

def is_valid_gemini_model(model_name):
    """Check if the provided model name is valid and available"""
    if not GEMINI_ENABLED or not model_name:
        return False
    
    # Only allow specific models for security
    allowed_models = [
        'models/gemini-2.5-flash',
        'models/gemini-2.5-pro'
    ]
    
    if model_name not in allowed_models:
        return False
    
    try:
        models = genai.list_models()
        available_models = [m.name for m in models if 'generateContent' in m.supported_generation_methods]
        return model_name in available_models
    except Exception:
        return False

def get_gemini_response(user_input, context="", preferred_model=None):
    if not GEMINI_ENABLED:
        return json.dumps({
            "action": "error",
            "html_content": '''<div dir="rtl" style="font-family: 'Noto Kufi Arabic', 'Cairo', 'Tahoma', sans-serif;" class="text-right p-4 sm:p-6 lg:p-8 mx-4 sm:mx-0 bg-yellow-50 border border-yellow-200 rounded-lg">
                <h3 dir="rtl" style="font-family: 'Noto Kufi Arabic', 'Cairo', 'Tahoma', sans-serif;" class="text-base sm:text-lg lg:text-xl font-semibold text-yellow-800 mb-2 sm:mb-3 text-right">⚠️ مطلوب إعداد مفتاح Gemini AI</h3>
                <p dir="rtl" style="font-family: 'Noto Kufi Arabic', 'Cairo', 'Tahoma', sans-serif;" class="text-sm sm:text-base text-yellow-700 text-right leading-relaxed">يرجى تكوين متغير البيئة GEMINI_API_KEY لاستخدام الملاحظات الذكية</p>
            </div>''',
            "explanation": "مطلوب إعداد مفتاح Gemini AI لاستخدام هذه الميزة"
        })
    
    try:
        # Use preferred model if provided, otherwise get best available
        if preferred_model and is_valid_gemini_model(preferred_model):
            model_name = preferred_model
        else:
            model_name = get_best_gemini_model()
            
        if not model_name:
            raise Exception("No compatible Gemini models available")
            
        model = genai.GenerativeModel(model_name)
        
        system_prompt = f"""
        أنت مساعد ذكي لإنشاء وتعديل صفحات الملاحظات الذكية. 
        
        المهام التي يمكنك القيام بها:
        1. إضافة محتوى جديد إلى المحتوى الموجود (الافتراضي)
        2. تعديل أجزاء محددة من المحتوى الموجود
        3. استبدال المحتوى بالكامل (فقط عند الطلب الصريح)
        4. حذف أجزاء محددة (فقط عند الطلب الصريح)
        
        قواعد أساسية للتنسيق:
        - استخدم HTML صحيح مع Tailwind CSS للتنسيق فقط - لا تستخدم Markdown أبداً
        - لا تستخدم رموز Markdown مثل ** أو * أو # - استخدم HTML tags بدلاً منها
        - للنص الغامق استخدم <strong class="font-bold"> بدلاً من **
        - للعناوين استخدم <h2 class="text-lg font-bold"> بدلاً من ##
        - للقوائم استخدم <ul class="list-disc"> و <li> بدلاً من -
        - اجعل التصميم متجاوب وجميل - يجب أن يعمل على الهواتف والأجهزة اللوحية وأجهزة الكمبيوتر
        - استخدم الألوان المتناسقة مع موقعنا (cyan-950, cyan-900, gray-700, etc.)
        
        قواعد الاستجابة للأجهزة المحمولة (مهم جداً):
        - استخدم فئات Tailwind المتجاوبة مثل: sm:, md:, lg:, xl:
        - للنصوص: استخدم text-sm sm:text-base md:text-lg للأحجام المختلفة  
        - للمساحات: استخدم p-4 sm:p-6 lg:p-8 للحشو المتدرج
        - للعروض: استخدم w-full sm:w-auto للعرض المتجاوب
        - للجداول: لفها في <div class="overflow-x-auto"> واستخدم min-w-full
        - للبطاقات والمكونات: استخدم mx-4 sm:mx-auto للمحاذاة
        - للشبكات: استخدم grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3
        - للـ Flexbox: استخدم flex-col sm:flex-row للاتجاه المتجاوب
        - تجنب العروض الثابتة واستخدم max-w-xs sm:max-w-sm md:max-w-md
        - للصور: استخدم w-full h-auto object-cover للتجاوب
        - للأزرار: استخدم w-full sm:w-auto للعرض المناسب
        
        قواعد التنسيق حسب اللغة والتفضيلات:
        
        1. إذا طلب المستخدم خط معين أو اتجاه معين، استخدم تفضيلاته بالضبط
        2. إذا طلب المستخدم تنسيق LTR أو خط إنجليزي، طبق ذلك
        3. إذا لم يحدد المستخدم تفضيلات خاصة:
        
        الإعدادات الافتراضية للنصوص العربية:
        - استخدم dir="rtl" لأي عنصر يحتوي على نص عربي
        - استخدم font-family: 'Noto Kufi Arabic', 'Cairo', 'Tahoma', sans-serif للنصوص العربية
        - أضف class="text-right" للمحاذاة العربية
        - لف المحتوى العربي في: <div dir="rtl" style="font-family: 'Noto Kufi Arabic', 'Cairo', 'Tahoma', sans-serif;" class="text-right">
        
        الإعدادات الافتراضية للنصوص الإنجليزية:
        - استخدم dir="ltr" للنصوص الإنجليزية
        - استخدم font-family: 'Inter', sans-serif للنصوص الإنجليزية
        - أضف class="text-left" للمحاذاة الإنجليزية
        
        تحليل طلب المستخدم أولاً:
        - هل طلب خط معين؟ (مثل: استخدم Arial، أو خط Times New Roman)
        - هل طلب اتجاه معين؟ (مثل: اجعله من اليسار لليمين، أو LTR)
        - هل طلب محاذاة معينة؟ (مثل: محاذاة يسار، أو توسيط)
        - هل المحتوى بالعربية أم الإنجليزية أم مختلط؟
        
        إذا لم يطلب تفضيلات خاصة، استخدم الإعدادات الافتراضية حسب اللغة.
        
        مثال على إضافة محتوى جديد (الافتراضي):
        إذا كان المحتوى الحالي: 
        <div>محتوى موجود سابقاً...</div>
        
        والمستخدم طلب: "أضف جدول"
        
        فيجب أن يكون الرد:
        <div>محتوى موجود سابقاً...</div>
        <!-- فاصل بين الأقسام -->
        <div class="mt-6 sm:mt-8"></div>
        <div dir="rtl" style="font-family: 'Noto Kufi Arabic', 'Cairo', 'Tahoma', sans-serif;" class="text-right space-y-4 p-4 sm:p-6 lg:p-8 mx-4 sm:mx-0">
            <h2 dir="rtl" class="text-xl sm:text-2xl lg:text-3xl font-bold text-cyan-950 mb-3 sm:mb-4">الجدول الجديد</h2>
            <div class="overflow-x-auto">
                <table dir="rtl" class="min-w-full bg-white border border-gray-200 rounded-lg">
                    <!-- محتوى الجدول -->
                </table>
            </div>
        </div>
        
        مثال على التنسيق المتجاوب للإنجليزية:
        <div dir="ltr" style="font-family: 'Inter', sans-serif;" class="text-left space-y-4 p-4 sm:p-6 lg:p-8 mx-4 sm:mx-0">
            <h2 dir="ltr" class="text-xl sm:text-2xl lg:text-3xl font-bold text-cyan-950 mb-3 sm:mb-4">Section Title</h2>
            <p dir="ltr" class="text-sm sm:text-base lg:text-lg text-gray-700 leading-relaxed">English text here</p>
        </div>
        
        مثال على جدول متجاوب:
        <div class="overflow-x-auto">
            <table dir="rtl" class="min-w-full bg-white border border-gray-200 rounded-lg">
                <thead class="bg-cyan-50">
                    <tr>
                        <th class="px-3 sm:px-6 py-2 sm:py-3 text-right text-xs sm:text-sm font-medium text-cyan-900">العمود</th>
                    </tr>
                </thead>
                <tbody>
                    <tr>
                        <td class="px-3 sm:px-6 py-2 sm:py-4 text-xs sm:text-sm text-gray-700">البيانات</td>
                    </tr>
                </tbody>
            </table>
        </div>
        
        - لا تستخدم markdown (```json أو ```)
        
        قواعد مهمة حول التعامل مع المحتوى الموجود:
        
        🚫 لا تستبدل أو تحذف المحتوى الموجود إلا إذا طلب المستخدم ذلك صراحة!
        
        السلوك الافتراضي - إضافة المحتوى:
        ✅ "أضف جدول" ← أضف الجدول بعد المحتوى الموجود
        ✅ "أنشئ قائمة مهام" ← أضف القائمة إلى نهاية المحتوى
        ✅ "اكتب فقرة عن..." ← أضف الفقرة بعد المحتوى الحالي
        ✅ "أضف قسم جديد" ← أضف القسم في نهاية الصفحة
        
        عبارات تتطلب الاستبدال (فقط هذه):
        🔄 "استبدل كل المحتوى بـ..."
        🔄 "امسح الصفحة واكتب..."
        🔄 "احذف كل شيء وأنشئ..."
        🔄 "أعد كتابة الصفحة من البداية"
        🔄 "ابدأ من جديد"
        
        عبارات تتطلب التعديل المحدد:
        ✏️ "عدّل الجدول الأول"
        ✏️ "غيّر العنوان إلى..."
        ✏️ "احذف الفقرة الثالثة"
        ✏️ "استبدل القائمة بـ..."
        
        قاعدة ذهبية: احتفظ بالمحتوى الموجود وأضف الجديد إليه، إلا إذا طُلب خلاف ذلك!
        
        ملاحظة للجوال: 70% من المستخدمين يشاهدون المحتوى على الهواتف المحمولة، لذا تأكد من:
        ✓ عدم استخدام عروض ثابتة كبيرة
        ✓ أن تكون النصوص قابلة للقراءة على الشاشات الصغيرة
        ✓ أن تكون الأزرار قابلة للنقر بسهولة
        ✓ أن تكون الجداول قابلة للتمرير أفقياً
        ✓ أن تكون المساحات مناسبة للمس
        
        السياق الحالي: {context}
        طلب المستخدم: {user_input}
        
        تعليمات مهمة للرد:
        - إذا كان المحتوى الحالي موجود، اعرضه كاملاً ثم أضف المحتوى الجديد
        - استخدم فواصل مناسبة بين الأقسام الموجودة والجديدة
        - إذا لم يكن هناك محتوى موجود، أنشئ المحتوى من البداية
        
        أرجع فقط JSON صحيح:
        {{
            "action": "add" | "modify" | "replace",
            "html_content": "المحتوى HTML الكامل (الموجود + الجديد) مع احترام تفضيلات المستخدم",
            "explanation": "شرح ما تم عمله مع التأكيد على أن المحتوى السابق محفوظ"
        }}
        """
        
        response = model.generate_content(system_prompt)
        return response.text
    except Exception as e:
        return json.dumps({
            "action": "error",
            "html_content": f'''<div dir="rtl" style="font-family: 'Noto Kufi Arabic', 'Cairo', 'Tahoma', sans-serif;" class="text-right p-4 sm:p-6 lg:p-8 mx-4 sm:mx-0 bg-red-50 border border-red-200 rounded-lg">
                <h3 dir="rtl" style="font-family: 'Noto Kufi Arabic', 'Cairo', 'Tahoma', sans-serif;" class="text-base sm:text-lg lg:text-xl font-semibold text-red-800 mb-2 sm:mb-3 text-right">❌ حدث خطأ</h3>
                <p dir="rtl" style="font-family: 'Noto Kufi Arabic', 'Cairo', 'Tahoma', sans-serif;" class="text-sm sm:text-base text-red-700 text-right leading-relaxed break-words">{str(e)}</p>
            </div>''',
            "explanation": f"خطأ في الاتصال: {str(e)}"
        })

def convert_markdown_to_html(text):
    """Convert basic Markdown formatting to HTML with Tailwind classes"""
    if not text:
        return text
    
    # Convert **bold** to <strong class="font-bold">bold</strong>
    text = re.sub(r'\*\*(.*?)\*\*', r'<strong class="font-bold text-gray-900">\1</strong>', text)
    
    # Convert *italic* to <em class="italic">italic</em>
    text = re.sub(r'\*(.*?)\*', r'<em class="italic">\1</em>', text)
    
    # Convert ### Headers to <h3>
    text = re.sub(r'^### (.*?)$', r'<h3 dir="rtl" class="text-lg font-bold text-cyan-900 mb-3 mt-4">\1</h3>', text, flags=re.MULTILINE)
    
    # Convert ## Headers to <h2>
    text = re.sub(r'^## (.*?)$', r'<h2 dir="rtl" class="text-xl font-bold text-cyan-950 mb-4 mt-6">\1</h2>', text, flags=re.MULTILINE)
    
    # Convert # Headers to <h1>
    text = re.sub(r'^# (.*?)$', r'<h1 dir="rtl" class="text-2xl font-bold text-cyan-950 mb-4 mt-6">\1</h1>', text, flags=re.MULTILINE)
    
    # Convert bullet points to proper lists
    lines = text.split('\n')
    in_list = False
    result_lines = []
    
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('- ') or stripped.startswith('• '):
            if not in_list:
                result_lines.append('<ul dir="rtl" class="list-disc list-inside space-y-2 mb-4 mr-4">')
                in_list = True
            list_item = stripped[2:].strip()  # Remove '- ' or '• '
            result_lines.append(f'<li class="text-gray-700">{list_item}</li>')
        else:
            if in_list:
                result_lines.append('</ul>')
                in_list = False
            if stripped:  # Non-empty line
                result_lines.append(f'<p dir="rtl" class="text-gray-700 mb-3 leading-relaxed">{line}</p>')
            else:
                result_lines.append(line)
    
    if in_list:
        result_lines.append('</ul>')
    
    return '\n'.join(result_lines)

def extract_html_from_response(ai_response):
    try:
        cleaned_response = ai_response.strip()
        
        if cleaned_response.startswith('```json'):
            cleaned_response = cleaned_response[7:]
        if cleaned_response.startswith('```'):
            cleaned_response = cleaned_response[3:]
        if cleaned_response.endswith('```'):
            cleaned_response = cleaned_response[:-3]
        
        cleaned_response = cleaned_response.strip()
        response_data = json.loads(cleaned_response)
        
        html_content = response_data.get("html_content", "")
        explanation = response_data.get("explanation", "")
        action = response_data.get("action", "add")
        
        if html_content:
            html_content = html_content.replace('\\n', '\n')
            html_content = re.sub(r'\n\s*\n\s*\n+', '\n\n', html_content)
            html_content = html_content.strip()
            
            # Convert any remaining Markdown to HTML
            html_content = convert_markdown_to_html(html_content)
        
        # Enhance explanation based on action
        if action == "add" and explanation:
            explanation = f"✅ تم إضافة المحتوى الجديد مع الحفاظ على المحتوى السابق - {explanation}"
        elif action == "modify" and explanation:
            explanation = f"✏️ تم تعديل المحتوى المحدد - {explanation}"
        elif action == "replace" and explanation:
            explanation = f"🔄 تم استبدال المحتوى كما طُلب - {explanation}"
        
        return html_content, explanation
        
    except json.JSONDecodeError as e:
        cleaned = re.sub(r'```json|```', '', ai_response).strip()
        # If JSON parsing fails, assume it's raw text and convert markdown
        cleaned = convert_markdown_to_html(cleaned)
        return cleaned, f"تم استخراج المحتوى: {str(e)}"

def convert_audio_to_transcript(audio_file_path):
    """Convert audio file to transcript using ElevenLabs Speech-to-Text API"""
    if not ELEVENLABS_ENABLED:
        return {
            'success': False,
            'error': 'ElevenLabs API key not configured'
        }
    
    if not os.path.exists(audio_file_path):
        return {
            'success': False,
            'error': 'Audio file not found'
        }
    
    try:
        import requests
        
        # Prepare the request
        headers = {
            'xi-api-key': ELEVENLABS_API_KEY
        }
        
        # Prepare form data
        files = {
            'file': open(audio_file_path, 'rb')
        }
        
        data = {
            'model_id': 'scribe_v1',  # Use the standard model
            #'language_code': 'ar',    # Arabic language code
            'tag_audio_events': 'true',
            'timestamps_granularity': 'word',
            'diarize': 'false'
        }
        
        # Make the API request
        response = requests.post(
            ELEVENLABS_STT_URL,
            headers=headers,
            files=files,
            data=data,
            timeout=60  # 1 minute timeout
        )
        
        # Close the file
        files['file'].close()
        
        if response.status_code == 200:
            result = response.json()
            return {
                'success': True,
                'text': result.get('text', ''),
                'language_code': result.get('language_code', ''),
                'language_probability': result.get('language_probability', 0),
                'words': result.get('words', [])
            }
        else:
            error_detail = response.text if response.text else f"HTTP {response.status_code}"
            return {
                'success': False,
                'error': f'ElevenLabs API error: {error_detail}'
            }
            
    except requests.exceptions.Timeout:
        return {
            'success': False,
            'error': 'Request timeout - audio file may be too long'
        }
    except requests.exceptions.RequestException as e:
        return {
            'success': False,
            'error': f'Network error: {str(e)}'
        }
    except Exception as e:
        return {
            'success': False,
            'error': f'Unexpected error: {str(e)}'
        }

# Routes
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        # Authenticate against User model
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            session['user_id'] = user.id
            session['username'] = user.username
            session['is_superadmin'] = user.is_superadmin
            
            # Set current workspace (last accessed or first available)
            if user.last_workspace_id:
                session['current_workspace_id'] = user.last_workspace_id
                workspace = Workspace.query.get(user.last_workspace_id)
                if workspace:
                    session['current_workspace_name'] = workspace.name
            else:
                # Get first workspace user has access to
                if user.is_superadmin:
                    # Super admin defaults to ws-general
                    session['current_workspace_id'] = 'ws-general'
                    workspace = Workspace.query.get('ws-general')
                    if workspace:
                        session['current_workspace_name'] = workspace.name
                else:
                    user_workspace = UserWorkspace.query.filter_by(user_id=user.id).first()
                    if user_workspace:
                        session['current_workspace_id'] = user_workspace.workspace_id
                        workspace = Workspace.query.get(user_workspace.workspace_id)
                        if workspace:
                            session['current_workspace_name'] = workspace.name
                    else:
                        flash('لا توجد workspaces مخصصة لك. يرجى الاتصال بالمسؤول.', 'error')
                        return render_template('login.html')
            
            flash('تم تسجيل الدخول بنجاح', 'success')
            return redirect(url_for('index'))
        else:
            flash('اسم المستخدم أو كلمة المرور غير صحيحة', 'error')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('تم تسجيل الخروج بنجاح', 'success')
    return redirect(url_for('login'))

# Context processor to make user workspaces available in all templates
@app.context_processor
def inject_user_workspaces():
    """Make user workspaces available to all templates"""
    if session.get('user_id'):
        user = get_current_user()
        if user:
            if user.is_superadmin:
                # Super admin has access to all workspaces
                workspaces = Workspace.query.all()
            else:
                # Regular user - only their assigned workspaces
                workspaces = [uw.workspace for uw in user.workspaces]
            return dict(user_workspaces=workspaces)
    return dict(user_workspaces=[])

@app.route('/')
@login_required
def index():
    current_workspace_id = session.get('current_workspace_id', 'ws-general')
    
    recent_tasks = Task.query.filter_by(workspace_id=current_workspace_id).order_by(Task.created_at.desc()).limit(5).all()
    recent_resources = Resource.query.filter_by(workspace_id=current_workspace_id).order_by(Resource.created_at.desc()).limit(3).all()
    active_sessions = BrainstormSession.query.filter_by(workspace_id=current_workspace_id, status='active').limit(3).all()
    
    total_tasks = Task.query.filter_by(workspace_id=current_workspace_id).count()
    completed_tasks = Task.query.filter_by(workspace_id=current_workspace_id, status='completed').count()
    pending_tasks = Task.query.filter_by(workspace_id=current_workspace_id, status='pending').count()
    in_progress_tasks = Task.query.filter_by(workspace_id=current_workspace_id, status='in_progress').count()
    
    # Monthly plan statistics
    try:
        total_monthly_plans = MonthlyPlan.query.filter(
            MonthlyPlan.workspace_id == current_workspace_id,
            MonthlyPlan.deleted_at.is_(None)
        ).count()
        current_month_plan = MonthlyPlan.query.filter(
            MonthlyPlan.workspace_id == current_workspace_id,
            MonthlyPlan.month == datetime.now().month,
            MonthlyPlan.year == datetime.now().year,
            MonthlyPlan.deleted_at.is_(None)
        ).first()
    except Exception:
        total_monthly_plans = 0
        current_month_plan = None
    
    # Reminder statistics
    try:
        total_reminders = Reminder.query.filter(
            Reminder.workspace_id == current_workspace_id,
            Reminder.deleted_at.is_(None)
        ).count()
        due_today_reminders = Reminder.query.filter(
            Reminder.workspace_id == current_workspace_id,
            Reminder.deleted_at.is_(None),
            Reminder.status == 'active',
            Reminder.reminder_date <= date.today()
        ).count()
    except Exception:
        total_reminders = 0
        due_today_reminders = 0
    
    stats = {
        'total': total_tasks,
        'completed': completed_tasks,
        'pending': pending_tasks,
        'in_progress': in_progress_tasks,
        'monthly_plans': total_monthly_plans,
        'current_month_plan': current_month_plan,
        'reminders': total_reminders,
        'due_today_reminders': due_today_reminders
    }
    
    return render_template('index.html', 
                         recent_tasks=recent_tasks,
                         recent_resources=recent_resources,
                         active_sessions=active_sessions,
                         stats=stats,
                         user=get_current_user())

@app.route('/switch_workspace/<workspace_id>')
@login_required
def switch_workspace(workspace_id):
    """Switch to a different workspace"""
    user = get_current_user()
    
    # Check if user has access to this workspace
    if not has_workspace_access(user, workspace_id):
        flash('ليس لديك صلاحية الوصول إلى هذا الـ workspace', 'error')
        return redirect(url_for('index'))
    
    # Verify workspace exists
    workspace = Workspace.query.get(workspace_id)
    if not workspace:
        flash('الـ workspace غير موجود', 'error')
        return redirect(url_for('index'))
    
    # Update session
    session['current_workspace_id'] = workspace_id
    session['current_workspace_name'] = workspace.name
    
    # Update user's last workspace
    user.last_workspace_id = workspace_id
    db.session.commit()
    
    flash(f'تم التبديل إلى workspace: {workspace.name}', 'success')
    return redirect(url_for('index'))

@app.route('/tasks')
@login_required
def tasks():
    current_workspace_id = session.get('current_workspace_id', 'ws-general')
    
    status_filter = request.args.get('status', 'all')
    category_filter = request.args.get('category', 'all')
    tag_filter = request.args.get('tag', 'all')
    search_query = request.args.get('search', '')
    sort_by = request.args.get('sort', 'created_at')
    order = request.args.get('order', 'desc')
    
    query = Task.query.filter_by(workspace_id=current_workspace_id)
    
    if status_filter != 'all':
        query = query.filter_by(status=status_filter)
    if category_filter != 'all':
        query = query.filter_by(category=category_filter)
    if tag_filter != 'all':
        query = query.filter(Task.tags.contains(tag_filter))
    if search_query:
        query = query.filter(
            db.or_(
                Task.title.contains(search_query),
                Task.description.contains(search_query),
                Task.assigned_to.contains(search_query)
            )
        )
    
    # Sorting
    if sort_by == 'due_date':
        if order == 'asc':
            query = query.order_by(Task.due_date.asc().nullslast())
        else:
            query = query.order_by(Task.due_date.desc().nullsfirst())
    elif sort_by == 'priority':
        priority_order = ['high', 'medium', 'low']
        if order == 'asc':
            priority_order.reverse()
        query = query.order_by(db.case(
            *[(Task.priority == p, i) for i, p in enumerate(priority_order)]
        ))
    elif sort_by == 'updated_at':
        if order == 'asc':
            query = query.order_by(Task.updated_at.asc())
        else:
            query = query.order_by(Task.updated_at.desc())
    else:  # created_at
        if order == 'asc':
            query = query.order_by(Task.created_at.asc())
        else:
            query = query.order_by(Task.created_at.desc())
    
    tasks = query.all()
    categories = db.session.query(Task.category).distinct().all()
    
    # Get all unique tags
    all_tags = set()
    for task in Task.query.all():
        if task.tags:
            all_tags.update([tag.strip() for tag in task.tags.split(',') if tag.strip()])
    
    return render_template('tasks.html', tasks=tasks, categories=categories,
                         current_status=status_filter, current_category=category_filter,
                         current_tag=tag_filter, current_search=search_query,
                         current_sort=sort_by, current_order=order, all_tags=sorted(all_tags))

@app.route('/tasks/new', methods=['GET', 'POST'])
@login_required
def new_task():
    current_workspace_id = session.get('current_workspace_id', 'ws-general')
    
    if request.method == 'POST':
        task = Task(
            workspace_id=current_workspace_id,
            title=request.form['title'],
            description=request.form['description'],
            priority=request.form['priority'],
            assigned_to=request.form['assigned_to'],
            category=request.form['category'],
            tags=request.form.get('tags', ''),
            due_date=datetime.strptime(request.form['due_date'], '%Y-%m-%d').date() if request.form['due_date'] else None
        )
        db.session.add(task)
        db.session.commit()
        flash('تم إنشاء المهمة بنجاح!', 'success')
        return redirect(url_for('tasks'))
    
    return render_template('task_form.html', task=None)

@app.route('/tasks/<int:task_id>/update_status')
@login_required
def update_task_status(task_id):
    current_workspace_id = session.get('current_workspace_id', 'ws-general')
    task = Task.query.filter_by(workspace_id=current_workspace_id, id=task_id).first_or_404()
    new_status = request.args.get('status')
    
    if new_status in ['pending', 'in_progress', 'completed']:
        old_status = task.status
        task.status = new_status
        task.updated_at = datetime.utcnow()
        
        # Set completed_at when task is completed
        if new_status == 'completed' and old_status != 'completed':
            task.completed_at = datetime.utcnow()
        elif new_status != 'completed':
            task.completed_at = None
            
        db.session.commit()
        flash('تم تحديث حالة المهمة!', 'success')
    
    # Preserve filter parameters when redirecting
    filter_params = {}
    if request.args.get('filter_status') and request.args.get('filter_status') != 'all':
        filter_params['status'] = request.args.get('filter_status')
    if request.args.get('filter_category') and request.args.get('filter_category') != 'all':
        filter_params['category'] = request.args.get('filter_category')
    if request.args.get('filter_tag') and request.args.get('filter_tag') != 'all':
        filter_params['tag'] = request.args.get('filter_tag')
    if request.args.get('filter_search'):
        filter_params['search'] = request.args.get('filter_search')
    if request.args.get('filter_sort') and request.args.get('filter_sort') != 'created_at':
        filter_params['sort'] = request.args.get('filter_sort')
    if request.args.get('filter_order') and request.args.get('filter_order') != 'desc':
        filter_params['order'] = request.args.get('filter_order')
    
    return redirect(url_for('tasks', **filter_params))

@app.route('/tasks/<int:task_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_task(task_id):
    current_workspace_id = session.get('current_workspace_id', 'ws-general')
    task = Task.query.filter_by(workspace_id=current_workspace_id, id=task_id).first_or_404()
    
    if request.method == 'POST':
        task.title = request.form['title']
        task.description = request.form['description']
        task.priority = request.form['priority']
        task.assigned_to = request.form['assigned_to']
        task.category = request.form['category']
        task.tags = request.form.get('tags', '')
        task.status = request.form['status']
        task.updated_at = datetime.utcnow()
        
        if request.form['due_date']:
            task.due_date = datetime.strptime(request.form['due_date'], '%Y-%m-%d').date()
        else:
            task.due_date = None
            
        # Handle completed_at timestamp
        if task.status == 'completed' and request.form.get('original_status') != 'completed':
            task.completed_at = datetime.utcnow()
        elif task.status != 'completed':
            task.completed_at = None
            
        db.session.commit()
        flash('تم تحديث المهمة بنجاح!', 'success')
        return redirect(url_for('tasks'))
    
    return render_template('task_form.html', task=task)

@app.route('/tasks/<int:task_id>/delete', methods=['POST'])
@login_required
def delete_task(task_id):
    current_workspace_id = session.get('current_workspace_id', 'ws-general')
    task = Task.query.filter_by(workspace_id=current_workspace_id, id=task_id).first_or_404()
    db.session.delete(task)
    db.session.commit()
    flash('تم حذف المهمة بنجاح!', 'success')
    
    # Preserve filter parameters when redirecting
    filter_params = {}
    if request.form.get('filter_status') and request.form.get('filter_status') != 'all':
        filter_params['status'] = request.form.get('filter_status')
    if request.form.get('filter_category') and request.form.get('filter_category') != 'all':
        filter_params['category'] = request.form.get('filter_category')
    if request.form.get('filter_tag') and request.form.get('filter_tag') != 'all':
        filter_params['tag'] = request.form.get('filter_tag')
    if request.form.get('filter_search'):
        filter_params['search'] = request.form.get('filter_search')
    if request.form.get('filter_sort') and request.form.get('filter_sort') != 'created_at':
        filter_params['sort'] = request.form.get('filter_sort')
    if request.form.get('filter_order') and request.form.get('filter_order') != 'desc':
        filter_params['order'] = request.form.get('filter_order')
    
    return redirect(url_for('tasks', **filter_params))

@app.route('/tasks/<int:task_id>/duplicate', methods=['POST'])
@login_required
def duplicate_task(task_id):
    current_workspace_id = session.get('current_workspace_id', 'ws-general')
    original_task = Task.query.filter_by(workspace_id=current_workspace_id, id=task_id).first_or_404()
    
    new_task = Task(
        workspace_id=current_workspace_id,
        title=f"نسخة من {original_task.title}",
        description=original_task.description,
        priority=original_task.priority,
        assigned_to=original_task.assigned_to,
        category=original_task.category,
        tags=original_task.tags,
        status='pending',
        due_date=original_task.due_date
    )
    
    db.session.add(new_task)
    db.session.commit()
    flash('تم إنشاء نسخة من المهمة بنجاح!', 'success')
    
    # Preserve filter parameters when redirecting
    filter_params = {}
    if request.form.get('filter_status') and request.form.get('filter_status') != 'all':
        filter_params['status'] = request.form.get('filter_status')
    if request.form.get('filter_category') and request.form.get('filter_category') != 'all':
        filter_params['category'] = request.form.get('filter_category')
    if request.form.get('filter_tag') and request.form.get('filter_tag') != 'all':
        filter_params['tag'] = request.form.get('filter_tag')
    if request.form.get('filter_search'):
        filter_params['search'] = request.form.get('filter_search')
    if request.form.get('filter_sort') and request.form.get('filter_sort') != 'created_at':
        filter_params['sort'] = request.form.get('filter_sort')
    if request.form.get('filter_order') and request.form.get('filter_order') != 'desc':
        filter_params['order'] = request.form.get('filter_order')
    
    return redirect(url_for('tasks', **filter_params))

@app.route('/resources')
@login_required
def resources():
    current_workspace_id = session.get('current_workspace_id', 'ws-general')
    
    # Get filter parameters
    resource_type = request.args.get('type', 'all')
    search_query = request.args.get('search', '')
    sort_by = request.args.get('sort', 'created_at')
    order = request.args.get('order', 'desc')
    
    # Build query
    query = Resource.query.filter_by(workspace_id=current_workspace_id)
    
    # Apply filters
    if resource_type != 'all':
        query = query.filter_by(resource_type=resource_type)
    
    if search_query:
        search_pattern = f"%{search_query}%"
        query = query.filter(
            or_(
                Resource.title.ilike(search_pattern),
                Resource.description.ilike(search_pattern),
                Resource.tags.ilike(search_pattern),
                Resource.filename.ilike(search_pattern),
                Resource.url.ilike(search_pattern),
                Resource.created_by.ilike(search_pattern)
            )
        )
    
    # Apply sorting
    if sort_by == 'title':
        if order == 'asc':
            query = query.order_by(Resource.title.asc())
        else:
            query = query.order_by(Resource.title.desc())
    elif sort_by == 'type':
        if order == 'asc':
            query = query.order_by(Resource.resource_type.asc())
        else:
            query = query.order_by(Resource.resource_type.desc())
    elif sort_by == 'updated_at':
        if order == 'asc':
            query = query.order_by(Resource.updated_at.asc())
        else:
            query = query.order_by(Resource.updated_at.desc())
    else:  # created_at
        if order == 'asc':
            query = query.order_by(Resource.created_at.asc())
        else:
            query = query.order_by(Resource.created_at.desc())
    
    resources = query.all()
    
    # Get distinct resource types for filter dropdown
    resource_types = db.session.query(Resource.resource_type).distinct().all()
    
    # Add file size formatting to resources
    for resource in resources:
        if resource.file_size:
            resource.formatted_size = format_file_size(resource.file_size)
        else:
            resource.formatted_size = None
    
    return render_template('resources.html', 
                         resources=resources, 
                         resource_types=resource_types, 
                         current_type=resource_type,
                         current_search=search_query,
                         current_sort=sort_by,
                         current_order=order)

@app.route('/resources/new', methods=['GET', 'POST'])
@login_required
def new_resource():
    current_workspace_id = session.get('current_workspace_id', 'ws-general')
    
    if request.method == 'POST':
        try:
            # Handle file upload
            uploaded_file = request.files.get('file')
            filename = None
            file_size = None
            resource_type = request.form.get('resource_type', 'link')
            
            if uploaded_file and uploaded_file.filename:
                if allowed_file(uploaded_file.filename):
                    # Generate unique filename
                    filename = generate_unique_filename(uploaded_file.filename)
                    file_path = os.path.join(RESOURCES_UPLOAD_FOLDER, filename)
                    
                    # Ensure upload directory exists
                    os.makedirs(RESOURCES_UPLOAD_FOLDER, exist_ok=True)
                    
                    # Save file
                    uploaded_file.save(file_path)
                    file_size = os.path.getsize(file_path)
                    
                    # Auto-detect resource type based on file extension
                    resource_type = get_file_type(uploaded_file.filename)
                else:
                    flash('نوع الملف غير مدعوم. الأنواع المسموحة: ' + ', '.join(ALLOWED_EXTENSIONS), 'error')
                    return render_template('resource_form.html')
            
            # Validate required fields
            title = request.form.get('title', '').strip()
            if not title:
                flash('عنوان المورد مطلوب', 'error')
                return render_template('resource_form.html')
            
            # Create resource
            resource = Resource(
                workspace_id=current_workspace_id,
                title=title,
                description=request.form.get('description', '').strip(),
                url=request.form.get('url', '').strip() if not filename else None,
                resource_type=resource_type,
                tags=request.form.get('tags', '').strip(),
                filename=filename,
                file_size=file_size,
                created_by=request.form.get('created_by', 'مجهول').strip()
            )
            
            db.session.add(resource)
            db.session.commit()
            flash('تم إضافة المورد بنجاح!', 'success')
            return redirect(url_for('resources'))
            
        except Exception as e:
            flash(f'حدث خطأ أثناء إضافة المورد: {str(e)}', 'error')
            return render_template('resource_form.html')
    
    return render_template('resource_form.html')

@app.route('/resources/<int:resource_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_resource(resource_id):
    current_workspace_id = session.get('current_workspace_id', 'ws-general')
    resource = Resource.query.filter_by(workspace_id=current_workspace_id, id=resource_id).first_or_404()
    
    if request.method == 'POST':
        try:
            # Handle file upload (optional for edit)
            uploaded_file = request.files.get('file')
            
            if uploaded_file and uploaded_file.filename:
                if allowed_file(uploaded_file.filename):
                    # Delete old file if exists
                    if resource.filename:
                        old_file_path = os.path.join(RESOURCES_UPLOAD_FOLDER, resource.filename)
                        if os.path.exists(old_file_path):
                            os.remove(old_file_path)
                    
                    # Save new file
                    filename = generate_unique_filename(uploaded_file.filename)
                    file_path = os.path.join(RESOURCES_UPLOAD_FOLDER, filename)
                    uploaded_file.save(file_path)
                    
                    resource.filename = filename
                    resource.file_size = os.path.getsize(file_path)
                    resource.resource_type = get_file_type(uploaded_file.filename)
                else:
                    flash('نوع الملف غير مدعوم. الأنواع المسموحة: ' + ', '.join(ALLOWED_EXTENSIONS), 'error')
                    return render_template('resource_form.html', resource=resource)
            
            # Update resource fields
            resource.title = request.form.get('title', '').strip()
            resource.description = request.form.get('description', '').strip()
            resource.tags = request.form.get('tags', '').strip()
            resource.created_by = request.form.get('created_by', '').strip()
            resource.updated_at = datetime.utcnow()
            
            # Update URL only if no file is uploaded
            if not resource.filename:
                resource.url = request.form.get('url', '').strip()
                resource.resource_type = request.form.get('resource_type', 'link')
            
            if not resource.title:
                flash('عنوان المورد مطلوب', 'error')
                return render_template('resource_form.html', resource=resource)
            
            db.session.commit()
            flash('تم تحديث المورد بنجاح!', 'success')
            return redirect(url_for('resources'))
            
        except Exception as e:
            flash(f'حدث خطأ أثناء تحديث المورد: {str(e)}', 'error')
            return render_template('resource_form.html', resource=resource)
    
    return render_template('resource_form.html', resource=resource)

@app.route('/resources/<int:resource_id>/delete', methods=['POST'])
@login_required
def delete_resource(resource_id):
    current_workspace_id = session.get('current_workspace_id', 'ws-general')
    try:
        resource = Resource.query.filter_by(workspace_id=current_workspace_id, id=resource_id).first_or_404()
        
        # Delete associated file if exists
        if resource.filename:
            file_path = os.path.join(RESOURCES_UPLOAD_FOLDER, resource.filename)
            if os.path.exists(file_path):
                os.remove(file_path)
        
        db.session.delete(resource)
        db.session.commit()
        flash('تم حذف المورد بنجاح!', 'success')
        
    except Exception as e:
        flash(f'حدث خطأ أثناء حذف المورد: {str(e)}', 'error')
    
    return redirect(url_for('resources'))

@app.route('/resources/file/<filename>')
@login_required
def serve_resource_file(filename):
    """Serve uploaded resource files"""
    try:
        return send_from_directory(RESOURCES_UPLOAD_FOLDER, filename)
    except FileNotFoundError:
        flash('الملف غير موجود', 'error')
        return redirect(url_for('resources'))

@app.route('/brainstorm')
@login_required
def brainstorm():
    current_workspace_id = session.get('current_workspace_id', 'ws-general')
    sessions = BrainstormSession.query.filter_by(workspace_id=current_workspace_id).order_by(BrainstormSession.created_at.desc()).all()
    return render_template('brainstorm.html', sessions=sessions)

@app.route('/brainstorm/new', methods=['GET', 'POST'])
@login_required
def new_brainstorm_session():
    current_workspace_id = session.get('current_workspace_id', 'ws-general')
    
    if request.method == 'POST':
        brainstorm_session = BrainstormSession(
            workspace_id=current_workspace_id,
            title=request.form['title'],
            description=request.form['description'],
            created_by=request.form['created_by']
        )
        db.session.add(brainstorm_session)
        db.session.commit()
        flash('Brainstorm session created!', 'success')
        return redirect(url_for('brainstorm_session', session_id=brainstorm_session.id))
    
    return render_template('brainstorm_form.html')

@app.route('/brainstorm/<int:session_id>')
@login_required
def brainstorm_session(session_id):
    current_workspace_id = session.get('current_workspace_id', 'ws-general')
    brainstorm = BrainstormSession.query.filter_by(workspace_id=current_workspace_id, id=session_id).first_or_404()
    ideas = Idea.query.filter_by(workspace_id=current_workspace_id, session_id=session_id).order_by(Idea.votes.desc(), Idea.created_at.desc()).all()
    return render_template('brainstorm_session.html', brainstorm_session=brainstorm, ideas=ideas)

@app.route('/brainstorm/<int:session_id>/add_idea', methods=['POST'])
@login_required
def add_idea(session_id):
    current_workspace_id = session.get('current_workspace_id', 'ws-general')
    
    idea = Idea(
        workspace_id=current_workspace_id,
        content=request.form['content'],
        session_id=session_id,
        author=request.form['author']
    )
    db.session.add(idea)
    db.session.commit()
    flash('Idea added!', 'success')
    return redirect(url_for('brainstorm_session', session_id=session_id))

@app.route('/api/vote_idea/<int:idea_id>')
@login_required
def vote_idea(idea_id):
    idea = Idea.query.get_or_404(idea_id)
    idea.votes += 1
    db.session.commit()
    return jsonify({'votes': idea.votes})

@app.route('/brainstorm/<int:session_id>/edit_idea/<int:idea_id>', methods=['GET', 'POST'])
@login_required
def edit_idea(session_id, idea_id):
    idea = Idea.query.get_or_404(idea_id)
    session = BrainstormSession.query.get_or_404(session_id)
    
    # Verify the idea belongs to this session
    if idea.session_id != session_id:
        flash('خطأ: الفكرة لا تنتمي لهذه الجلسة', 'error')
        return redirect(url_for('brainstorm_session', session_id=session_id))
    
    if request.method == 'POST':
        idea.content = request.form['content']
        idea.author = request.form['author']
        db.session.commit()
        flash('تم تحديث الفكرة بنجاح!', 'success')
        return redirect(url_for('brainstorm_session', session_id=session_id))
    
    return jsonify({
        'id': idea.id,
        'content': idea.content,
        'author': idea.author or ''
    })

@app.route('/brainstorm/<int:session_id>/delete_idea/<int:idea_id>', methods=['POST'])
@login_required
def delete_idea(session_id, idea_id):
    idea = Idea.query.get_or_404(idea_id)
    
    # Verify the idea belongs to this session
    if idea.session_id != session_id:
        return jsonify({'success': False, 'message': 'خطأ: الفكرة لا تنتمي لهذه الجلسة'}), 400
    
    db.session.delete(idea)
    db.session.commit()
    flash('تم حذف الفكرة بنجاح!', 'success')
    return jsonify({'success': True, 'message': 'تم حذف الفكرة بنجاح'})

@app.route('/brainstorm/<int:session_id>/delete', methods=['POST'])
@login_required
def delete_brainstorm_session(session_id):
    session = BrainstormSession.query.get_or_404(session_id)
    
    try:
        # Delete all ideas in this session first
        ideas = Idea.query.filter_by(session_id=session_id).all()
        for idea in ideas:
            db.session.delete(idea)
        
        # Delete the session itself
        db.session.delete(session)
        db.session.commit()
        
        flash('تم حذف جلسة العصف الذهني وجميع الأفكار المرتبطة بها بنجاح!', 'success')
        return jsonify({
            'success': True, 
            'message': 'تم حذف جلسة العصف الذهني بنجاح',
            'redirect': '/brainstorm'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False, 
            'message': f'حدث خطأ أثناء حذف الجلسة: {str(e)}'
        }), 500

def has_deleted_at_column():
    """Check if deleted_at column exists in SmartNotion table"""
    try:
        # Try to access the column
        db.session.execute(text("SELECT deleted_at FROM smart_notion LIMIT 1"))
        return True
    except Exception:
        return False

@app.route('/smart_notion')
@login_required
def smart_notion():
    current_workspace_id = session.get('current_workspace_id', 'ws-general')
    
    try:
        # Check if deleted_at column exists
        if has_deleted_at_column():
            # Use new filtering with deleted_at
            notions = SmartNotion.query.filter(
                SmartNotion.workspace_id == current_workspace_id,
                SmartNotion.deleted_at.is_(None)
            ).order_by(SmartNotion.updated_at.desc()).all()
            total_notions = SmartNotion.query.filter(
                SmartNotion.workspace_id == current_workspace_id,
                SmartNotion.deleted_at.is_(None)
            ).count()
            today_count = SmartNotion.query.filter(
                SmartNotion.workspace_id == current_workspace_id,
                SmartNotion.created_at >= datetime.now().replace(hour=0, minute=0, second=0, microsecond=0),
                SmartNotion.deleted_at.is_(None)
            ).count()
        else:
            # Use old filtering without deleted_at (backward compatibility)
            notions = SmartNotion.query.filter_by(
                workspace_id=current_workspace_id
            ).order_by(SmartNotion.updated_at.desc()).all()
            total_notions = SmartNotion.query.filter_by(workspace_id=current_workspace_id).count()
            today_count = SmartNotion.query.filter(
                SmartNotion.workspace_id == current_workspace_id,
                SmartNotion.created_at >= datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            ).count()
        
        stats = {
            'total': total_notions,
            'today': today_count
        }
        
        return render_template('smart_notion.html', notions=notions, stats=stats)
        
    except Exception as e:
        # Fallback to basic query if there's any issue
        notions = SmartNotion.query.order_by(SmartNotion.updated_at.desc()).all()
        stats = {
            'total': len(notions),
            'today': len([n for n in notions if n.created_at.date() == datetime.now().date()])
        }
        return render_template('smart_notion.html', notions=notions, stats=stats)

@app.route('/smart_notion/new', methods=['GET', 'POST'])
@login_required
def new_smart_notion():
    current_workspace_id = session.get('current_workspace_id', 'ws-general')
    
    if request.method == 'POST':
        notion = SmartNotion(
            workspace_id=current_workspace_id,
            title=request.form['title'],
            content_html='''<div dir="rtl" style="font-family: 'Noto Kufi Arabic', 'Cairo', 'Tahoma', sans-serif;" class="text-right p-4 sm:p-6 lg:p-8 mx-4 sm:mx-0 bg-gradient-to-r from-cyan-50 to-blue-50 rounded-lg border border-cyan-200">
                <h2 dir="rtl" style="font-family: 'Noto Kufi Arabic', 'Cairo', 'Tahoma', sans-serif;" class="text-xl sm:text-2xl lg:text-3xl font-bold text-cyan-950 mb-3 sm:mb-4 text-right">🎉 مرحباً بك في ملاحظتك الذكية الجديدة!</h2>
                <p dir="rtl" style="font-family: 'Noto Kufi Arabic', 'Cairo', 'Tahoma', sans-serif;" class="text-sm sm:text-base lg:text-lg text-gray-700 mb-4 sm:mb-6 text-right leading-relaxed">استخدم نافذة الدردشة لبدء إنشاء المحتوى</p>
                <div dir="rtl" style="font-family: 'Noto Kufi Arabic', 'Cairo', 'Tahoma', sans-serif;" class="text-right bg-cyan-100 p-3 sm:p-4 rounded-lg">
                    <p dir="rtl" class="text-cyan-800 text-sm sm:text-base font-medium mb-2">💡 اقتراحات للبداية:</p>
                    <div class="grid grid-cols-1 sm:grid-cols-2 gap-2 sm:gap-3">
                        <div dir="rtl" class="bg-white bg-opacity-50 p-2 sm:p-3 rounded text-xs sm:text-sm text-cyan-700">📝 أنشئ قائمة مهام</div>
                        <div dir="rtl" class="bg-white bg-opacity-50 p-2 sm:p-3 rounded text-xs sm:text-sm text-cyan-700">📄 اكتب مقالة أو تقرير</div>
                        <div dir="rtl" class="bg-white bg-opacity-50 p-2 sm:p-3 rounded text-xs sm:text-sm text-cyan-700">📊 أضف جدول بيانات</div>
                        <div dir="rtl" class="bg-white bg-opacity-50 p-2 sm:p-3 rounded text-xs sm:text-sm text-cyan-700">📋 قم بتلخيص معلومات</div>
                    </div>
                </div>
            </div>''',
            created_by=request.form.get('created_by', 'مجهول')
        )
        db.session.add(notion)
        db.session.commit()
        flash('Smart Notion created successfully!', 'success')
        return redirect(url_for('edit_smart_notion', notion_id=notion.id))
    
    return render_template('smart_notion_form.html')

@app.route('/smart_notion/<int:notion_id>')
@login_required
def edit_smart_notion(notion_id):
    current_workspace_id = session.get('current_workspace_id', 'ws-general')
    
    try:
        # Check if deleted_at column exists
        if has_deleted_at_column():
            # Only allow editing non-deleted notions
            notion = SmartNotion.query.filter_by(
                workspace_id=current_workspace_id,
                id=notion_id,
                deleted_at=None
            ).first_or_404()
        else:
            # Backward compatibility - no deleted_at filtering
            notion = SmartNotion.query.filter_by(
                workspace_id=current_workspace_id,
                id=notion_id
            ).first_or_404()
            
        conversations = ChatConversation.query.filter_by(
            workspace_id=current_workspace_id,
            notion_id=notion_id
        ).order_by(ChatConversation.created_at.asc()).all()
        return render_template('smart_notion_edit.html', notion=notion, conversations=conversations)
        
    except Exception as e:
        # Fallback to basic query
        notion = SmartNotion.query.filter_by(
            workspace_id=current_workspace_id,
            id=notion_id
        ).first_or_404()
        conversations = ChatConversation.query.filter_by(
            workspace_id=current_workspace_id,
            notion_id=notion_id
        ).order_by(ChatConversation.created_at.asc()).all()
        return render_template('smart_notion_edit.html', notion=notion, conversations=conversations)

@app.route('/api/smart_notion/<int:notion_id>/delete', methods=['POST'])
@login_required
def delete_smart_notion(notion_id):
    """Soft delete a smart notion"""
    current_workspace_id = session.get('current_workspace_id', 'ws-general')
    
    try:
        # Check if deleted_at column exists
        if has_deleted_at_column():
            # Only allow deleting non-deleted notions
            notion = SmartNotion.query.filter_by(
                workspace_id=current_workspace_id,
                id=notion_id,
                deleted_at=None
            ).first_or_404()
            
            # Soft delete: set deleted_at timestamp
            notion.deleted_at = datetime.utcnow()
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': 'تم حذف الملاحظة بنجاح'
            })
        else:
            # If deleted_at column doesn't exist, return error asking for migration
            return jsonify({
                'success': False,
                'message': 'يجب تشغيل migration أولاً لدعم ميزة الحذف الآمن'
            }), 400
            
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'حدث خطأ أثناء حذف الملاحظة: {str(e)}'
        }), 500

@app.route('/api/smart_notion/<int:notion_id>/chat', methods=['POST'])
@login_required
def smart_notion_chat(notion_id):
    current_workspace_id = session.get('current_workspace_id', 'ws-general')
    
    try:
        # Check if deleted_at column exists
        if has_deleted_at_column():
            # Only allow chat with non-deleted notions
            notion = SmartNotion.query.filter_by(
                workspace_id=current_workspace_id,
                id=notion_id,
                deleted_at=None
            ).first_or_404()
        else:
            # Backward compatibility - no deleted_at filtering
            notion = SmartNotion.query.filter_by(
                workspace_id=current_workspace_id,
                id=notion_id
            ).first_or_404()
            
        user_message = request.json.get('message', '')
        preferred_model = request.json.get('model', None)
    except Exception as e:
        # Fallback to basic query
        notion = SmartNotion.query.filter_by(
            workspace_id=current_workspace_id,
            id=notion_id
        ).first_or_404()
        user_message = request.json.get('message', '')
        preferred_model = request.json.get('model', None)
    
    if not user_message:
        return jsonify({'error': 'Message is required'}), 400
    
    context_parts = []
    context_parts.append(f"المحتوى الحالي للملاحظة:\n{notion.content_html}")
    
    recent_conversations = ChatConversation.query.filter_by(notion_id=notion_id)\
        .order_by(ChatConversation.created_at.desc()).limit(5).all()
    
    if recent_conversations:
        context_parts.append("\nتاريخ المحادثة الأخير:")
        for conv in reversed(recent_conversations):
            context_parts.append(f"المستخدم: {conv.user_message}")
            context_parts.append(f"المساعد: {conv.ai_response}")
    
    context = "\n".join(context_parts)
    
    # Use preferred model if provided and valid
    ai_response = get_gemini_response(user_message, context, preferred_model)
    html_content, explanation = extract_html_from_response(ai_response)
    
    if html_content:
        notion.content_html = html_content
        notion.updated_at = datetime.utcnow()
        
        conversation = ChatConversation(
            workspace_id=current_workspace_id,
            notion_id=notion_id,
            user_message=user_message,
            ai_response=explanation
        )
        db.session.add(conversation)
        db.session.commit()
    
    # Get the actual model used for response
    actual_model = preferred_model if is_valid_gemini_model(preferred_model) else get_best_gemini_model()
    
    return jsonify({
        'ai_response': explanation,
        'updated_content': html_content,
        'success': True,
        'model_used': actual_model
    })

# Voice Notes Routes
@app.route('/voice_notes')
@login_required
def voice_notes():
    """List all voice notes"""
    current_workspace_id = session.get('current_workspace_id', 'ws-general')
    
    try:
        # Get all non-deleted voice notes
        voice_notes = VoiceNote.query.filter(
            VoiceNote.workspace_id == current_workspace_id,
            VoiceNote.deleted_at.is_(None)
        ).order_by(VoiceNote.updated_at.desc()).all()
        
        # Get statistics
        total_notes = VoiceNote.query.filter(
            VoiceNote.workspace_id == current_workspace_id,
            VoiceNote.deleted_at.is_(None)
        ).count()
        today_count = VoiceNote.query.filter(
            VoiceNote.workspace_id == current_workspace_id,
            VoiceNote.created_at >= datetime.now().replace(hour=0, minute=0, second=0, microsecond=0),
            VoiceNote.deleted_at.is_(None)
        ).count()
        
        stats = {
            'total': total_notes,
            'today': today_count
        }
        
        return render_template('voice_notes.html', voice_notes=voice_notes, stats=stats)
        
    except Exception as e:
        # Fallback in case deleted_at column doesn't exist yet
        voice_notes = VoiceNote.query.order_by(VoiceNote.updated_at.desc()).all()
        stats = {
            'total': len(voice_notes),
            'today': len([n for n in voice_notes if n.created_at.date() == datetime.now().date()])
        }
        return render_template('voice_notes.html', voice_notes=voice_notes, stats=stats)

@app.route('/voice_notes/new', methods=['GET', 'POST'])
@login_required
def new_voice_note():
    """Create a new voice note"""
    current_workspace_id = session.get('current_workspace_id', 'ws-general')
    
    if request.method == 'POST':
        voice_note = VoiceNote(
            workspace_id=current_workspace_id,
            title=request.form['title'],
            description=request.form.get('description', ''),
            created_by=request.form.get('created_by', 'مجهول')
        )
        db.session.add(voice_note)
        db.session.commit()
        flash('تم إضافة الفكرة إلى بنك الأفكار بنجاح!', 'success')
        return redirect(url_for('edit_voice_note', note_id=voice_note.id))
    
    return render_template('voice_note_form.html')

@app.route('/voice_notes/<int:note_id>')
@login_required
def edit_voice_note(note_id):
    """View and edit a voice note"""
    current_workspace_id = session.get('current_workspace_id', 'ws-general')
    
    try:
        # Get non-deleted voice note
        voice_note = VoiceNote.query.filter_by(
            workspace_id=current_workspace_id,
            id=note_id,
            deleted_at=None
        ).first_or_404()
    except Exception:
        # Fallback without deleted_at filtering
        voice_note = VoiceNote.query.filter_by(
            workspace_id=current_workspace_id,
            id=note_id
        ).first_or_404()
    
    # Get all recordings for this note
    recordings = VoiceRecording.query.filter_by(
        workspace_id=current_workspace_id,
        voice_note_id=note_id
    ).order_by(VoiceRecording.created_at.asc()).all()
    
    # Get all comments for this note
    comments = VoiceComment.query.filter_by(voice_note_id=note_id).order_by(VoiceComment.created_at.asc()).all()
    
    # Get current summary and all historical summaries
    current_summary = VoiceSummary.query.filter_by(voice_note_id=note_id, is_current=True).first()
    all_summaries = VoiceSummary.query.filter_by(voice_note_id=note_id).order_by(VoiceSummary.summary_version.desc()).all()
    
    return render_template('voice_note_edit.html', 
                         voice_note=voice_note, 
                         recordings=recordings, 
                         comments=comments,
                         current_summary=current_summary,
                         all_summaries=all_summaries)

@app.route('/api/voice_notes/<int:note_id>/upload', methods=['POST'])
@login_required
def upload_voice_recording(note_id):
    """Upload a voice recording to a voice note"""
    current_workspace_id = session.get('current_workspace_id', 'ws-general')
    
    try:
        # Check if voice note exists and is not deleted
        try:
            voice_note = VoiceNote.query.filter_by(id=note_id, deleted_at=None).first_or_404()
        except Exception:
            voice_note = VoiceNote.query.filter_by(id=note_id).first_or_404()
        
        if 'audio' not in request.files:
            return jsonify({'success': False, 'message': 'لم يتم العثور على ملف صوتي'}), 400
        
        audio_file = request.files['audio']
        if audio_file.filename == '':
            return jsonify({'success': False, 'message': 'لم يتم اختيار ملف'}), 400
        
        # Generate unique filename
        import uuid
        file_extension = '.webm'  # Default for web audio recordings
        if audio_file.content_type:
            if 'mp3' in audio_file.content_type:
                file_extension = '.mp3'
            elif 'wav' in audio_file.content_type:
                file_extension = '.wav'
            elif 'ogg' in audio_file.content_type:
                file_extension = '.ogg'
        
        unique_filename = f"{uuid.uuid4()}{file_extension}"
        
        # Upload to storage service (S3 or local)
        storage = get_storage_service()
        upload_result = storage.upload_file(
            file_obj=audio_file.stream,
            filename=unique_filename,
            content_type=audio_file.content_type or 'audio/webm'
        )
        
        if not upload_result.get('success'):
            return jsonify({
                'success': False,
                'message': f'فشل رفع الملف: {upload_result.get("error", "خطأ غير معروف")}'
            }), 500
        
        # Create recording record
        recording = VoiceRecording(
            workspace_id=current_workspace_id,
            voice_note_id=note_id,
            filename=unique_filename,
            original_name=audio_file.filename,
            file_size=upload_result.get('size', 0),
            content_type=audio_file.content_type or 'audio/webm'
        )
        
        db.session.add(recording)
        
        # Update voice note timestamp
        voice_note.updated_at = datetime.utcnow()
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'تم رفع التسجيل الصوتي بنجاح',
            'recording_id': recording.id,
            'filename': unique_filename,
            'file_size': upload_result.get('size', 0),
            'storage_url': upload_result.get('url')
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'حدث خطأ أثناء رفع التسجيل: {str(e)}'
        }), 500

@app.route('/api/voice_notes/<int:note_id>/comment', methods=['POST'])
@login_required
def add_voice_comment(note_id):
    """Add a text comment to a voice note"""
    current_workspace_id = session.get('current_workspace_id', 'ws-general')
    
    try:
        # Check if voice note exists and is not deleted
        try:
            voice_note = VoiceNote.query.filter_by(id=note_id, deleted_at=None).first_or_404()
        except Exception:
            voice_note = VoiceNote.query.filter_by(id=note_id).first_or_404()
        
        data = request.get_json()
        content = data.get('content', '').strip()
        author = data.get('author', 'مجهول')
        
        if not content:
            return jsonify({'success': False, 'message': 'المحتوى مطلوب'}), 400
        
        # Create comment
        comment = VoiceComment(
            workspace_id=current_workspace_id,
            voice_note_id=note_id,
            content=content,
            author=author,
            comment_type='text'
        )
        
        db.session.add(comment)
        
        # Update voice note timestamp
        voice_note.updated_at = datetime.utcnow()
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'تم إضافة التعليق بنجاح',
            'comment_id': comment.id,
            'created_at': comment.created_at.strftime('%Y-%m-%d %H:%M')
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'حدث خطأ أثناء إضافة التعليق: {str(e)}'
        }), 500

@app.route('/api/voice_notes/<int:note_id>/delete', methods=['POST'])
@login_required
def delete_voice_note(note_id):
    """Soft delete a voice note"""
    current_workspace_id = session.get('current_workspace_id', 'ws-general')
    
    try:
        # Try to get and soft delete the voice note
        try:
            voice_note = VoiceNote.query.filter_by(
                workspace_id=current_workspace_id,
                id=note_id,
                deleted_at=None
            ).first_or_404()
            voice_note.deleted_at = datetime.utcnow()
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': 'تم حذف الفكرة من بنك الأفكار بنجاح'
            })
        except Exception:
            # If deleted_at column doesn't exist, return error
            return jsonify({
                'success': False,
                'message': 'يجب تشغيل migration أولاً لدعم ميزة الحذف الآمن'
            }), 400
            
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'حدث خطأ أثناء حذف الملاحظة: {str(e)}'
        }), 500

@app.route('/voice_recordings/<filename>')
@login_required
def serve_voice_recording(filename):
    """Serve voice recording files"""
    try:
        # Security check - only allow files that contain only allowed characters
        import re
        if not re.match(r'^[a-zA-Z0-9\-_.]+$', filename):
            return "Invalid filename", 400
        
        # Get storage service
        storage = get_storage_service()
        
        # Check if file exists
        if not storage.file_exists(filename):
            return "File not found", 404
        
        # For S3, get presigned URL and redirect
        # For local storage, serve the file from filesystem
        if hasattr(storage, 's3_client'):  # S3 storage
            # Generate presigned URL (temporary, expires in 1 hour)
            presigned_url = storage.get_file_url(filename)
            return redirect(presigned_url)
        else:  # Local storage
            # Serve from local filesystem
            return send_from_directory(app.config['UPLOAD_FOLDER'], filename)
        
    except Exception as e:
        return f"Error serving file: {str(e)}", 500

@app.route('/api/voice_recordings/<int:recording_id>/transcript', methods=['POST'])
@login_required
def generate_transcript(recording_id):
    """Generate transcript for a voice recording using ElevenLabs API"""
    try:
        # Get the recording
        recording = VoiceRecording.query.get_or_404(recording_id)
        
        # Check if transcript already exists
        if recording.transcription:
            return jsonify({
                'success': True,
                'transcript': recording.transcription,
                'message': 'النص المكتوب متوفر مسبقاً',
                'cached': True
            })
        
        # Get storage service
        storage = get_storage_service()
        
        # If using S3, download file temporarily for transcription
        if hasattr(storage, 's3_client'):  # S3 storage
            import tempfile
            # Create temporary file
            with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(recording.filename)[1]) as tmp_file:
                temp_path = tmp_file.name
                
            # Download from S3
            if not storage.download_file(recording.filename, temp_path):
                return jsonify({
                    'success': False,
                    'message': 'فشل في تحميل الملف من التخزين'
                }), 500
            
            audio_file_path = temp_path
            cleanup_temp = True
        else:  # Local storage
            audio_file_path = os.path.join(app.config['UPLOAD_FOLDER'], recording.filename)
            cleanup_temp = False
        
        try:
            # Convert audio to transcript
            result = convert_audio_to_transcript(audio_file_path)
            
            if result['success']:
                # Save transcript to database
                recording.transcription = result['text']
                db.session.commit()
                
                return jsonify({
                    'success': True,
                    'transcript': result['text'],
                    'language_code': result.get('language_code', ''),
                    'language_probability': result.get('language_probability', 0),
                    'message': 'تم تحويل التسجيل إلى نص بنجاح',
                    'cached': False
                })
            else:
                return jsonify({
                    'success': False,
                    'message': f'فشل في تحويل التسجيل: {result["error"]}'
                }), 500
        finally:
            # Clean up temporary file if S3 was used
            if cleanup_temp and os.path.exists(audio_file_path):
                os.remove(audio_file_path)
            
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'حدث خطأ أثناء تحويل التسجيل: {str(e)}'
        }), 500

@app.route('/api/voice_notes/<int:note_id>/generate_summary', methods=['POST'])
@login_required
def generate_voice_note_summary(note_id):
    """Generate AI summary and insights for a voice note using Gemini with historical tracking"""
    current_workspace_id = session.get('current_workspace_id', 'ws-general')
    
    try:
        # Check if voice note exists and is not deleted
        try:
            voice_note = VoiceNote.query.filter_by(id=note_id, deleted_at=None).first_or_404()
        except Exception:
            voice_note = VoiceNote.query.filter_by(id=note_id).first_or_404()
        
        # Get all transcripts for this voice note
        recordings = VoiceRecording.query.filter_by(voice_note_id=note_id).order_by(VoiceRecording.created_at.asc()).all()
        transcripts = []
        for recording in recordings:
            if recording.transcription:
                transcripts.append({
                    'created_at': recording.created_at.strftime('%Y-%m-%d %H:%M'),
                    'text': recording.transcription
                })
        
        # Get all comments for this voice note
        comments = VoiceComment.query.filter_by(voice_note_id=note_id).order_by(VoiceComment.created_at.asc()).all()
        comments_list = []
        for comment in comments:
            comments_list.append({
                'created_at': comment.created_at.strftime('%Y-%m-%d %H:%M'),
                'author': comment.author,
                'content': comment.content
            })
        
        # Prepare context for Gemini
        context_parts = []
        context_parts.append(f"عنوان الفكرة: {voice_note.title}")
        if voice_note.description:
            context_parts.append(f"وصف الفكرة: {voice_note.description}")
        
        context_parts.append(f"تاريخ الإنشاء: {voice_note.created_at.strftime('%Y-%m-%d %H:%M')}")
        context_parts.append(f"صاحب الفكرة: {voice_note.created_by or 'مجهول'}")
        
        if transcripts:
            context_parts.append("\n--- النصوص المحولة من التسجيلات الصوتية ---")
            for i, transcript in enumerate(transcripts, 1):
                context_parts.append(f"\nتسجيل رقم {i} ({transcript['created_at']}):")
                context_parts.append(transcript['text'])
        
        if comments_list:
            context_parts.append("\n--- التعليقات النصية ---")
            for i, comment in enumerate(comments_list, 1):
                context_parts.append(f"\nتعليق رقم {i} ({comment['created_at']}) - {comment['author']}:")
                context_parts.append(comment['content'])
        
        context = "\n".join(context_parts)
        
        # Create specialized prompt for voice note summarization
        user_prompt = """أنشئ تقريراً شاملاً وتحليلاً للفكرة التالية من بنك الأفكار. يجب أن يشمل التقرير:

1. **ملخص تنفيذي** - أهم النقاط والمحتوى الرئيسي
2. **النقاط الرئيسية** - استخراج أهم الأفكار والمعلومات
3. **التحليل والرؤى** - تحليل عميق للمحتوى والاستنتاجات
4. **الخطوات والإجراءات** - أي مهام أو خطوات مذكورة
5. **الكلمات المفتاحية** - المفاهيم والمصطلحات الهامة
6. **التوصيات** - اقتراحات للمتابعة أو الإجراءات التالية

اجعل التقرير منظماً ومفصلاً وسهل القراءة.

تنسيق مهم: استخدم HTML فقط مع Tailwind CSS - لا تستخدم Markdown أبداً:
- للعناوين: <h2 class="text-xl font-bold text-cyan-950 mb-4">العنوان</h2>
- للنص الغامق: <strong class="font-bold text-gray-900">النص</strong>
- للقوائم: <ul class="list-disc mr-6 space-y-2"><li>البند</li></ul>
- للفقرات: <p dir="rtl" class="text-gray-700 mb-3 leading-relaxed">الفقرة</p>

لا تستخدم ** أو # أو - في التنسيق."""
        
        # Use Gemini to generate summary
        preferred_model = request.json.get('model', None) if request.is_json else None
        ai_response = get_gemini_response(user_prompt, context, preferred_model)
        html_content, explanation = extract_html_from_response(ai_response)
        
        if html_content:
            # Get current version number
            latest_summary = VoiceSummary.query.filter_by(voice_note_id=note_id).order_by(VoiceSummary.summary_version.desc()).first()
            next_version = (latest_summary.summary_version + 1) if latest_summary else 1
            
            # Mark all previous summaries as not current
            VoiceSummary.query.filter_by(voice_note_id=note_id, is_current=True).update({'is_current': False})
            
            # Create new summary record
            model_used = preferred_model if is_valid_gemini_model(preferred_model) else get_best_gemini_model()
            new_summary = VoiceSummary(
                workspace_id=current_workspace_id,
                voice_note_id=note_id,
                summary_html=html_content,
                summary_version=next_version,
                transcripts_count=len(transcripts),
                comments_count=len(comments_list),
                model_used=model_used,
                created_by=request.json.get('created_by', 'مجهول') if request.is_json else 'مجهول',
                is_current=True
            )
            
            db.session.add(new_summary)
            
            # Update voice note timestamp
            voice_note.updated_at = datetime.utcnow()
            
            db.session.commit()
            
            return jsonify({
                'success': True,
                'summary_html': html_content,
                'summary_id': new_summary.id,
                'summary_version': next_version,
                'message': f'تم إنشاء التقرير والتحليل (الإصدار {next_version}) بنجاح',
                'transcripts_count': len(transcripts),
                'comments_count': len(comments_list),
                'model_used': model_used
            })
        else:
            return jsonify({
                'success': False,
                'message': 'فشل في إنشاء التقرير'
            }), 500
            
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'حدث خطأ أثناء إنشاء التقرير: {str(e)}'
        }), 500

@app.route('/api/voice_notes/<int:note_id>/summaries', methods=['GET'])
@login_required
def get_voice_note_summaries(note_id):
    """Get all historical summaries for a voice note"""
    try:
        # Check if voice note exists and is not deleted
        try:
            voice_note = VoiceNote.query.filter_by(id=note_id, deleted_at=None).first_or_404()
        except Exception:
            voice_note = VoiceNote.query.filter_by(id=note_id).first_or_404()
        
        # Get all summaries for this voice note, ordered by version (newest first)
        summaries = VoiceSummary.query.filter_by(voice_note_id=note_id).order_by(VoiceSummary.summary_version.desc()).all()
        
        summaries_data = []
        for summary in summaries:
            summaries_data.append({
                'id': summary.id,
                'version': summary.summary_version,
                'transcripts_count': summary.transcripts_count,
                'comments_count': summary.comments_count,
                'model_used': summary.model_used,
                'created_by': summary.created_by,
                'created_at': summary.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                'is_current': summary.is_current
            })
        
        return jsonify({
            'success': True,
            'summaries': summaries_data,
            'total_count': len(summaries)
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'حدث خطأ أثناء جلب التقارير: {str(e)}'
        }), 500

@app.route('/api/voice_summaries/<int:summary_id>', methods=['GET'])
@login_required
def get_voice_summary(summary_id):
    """Get a specific voice summary by ID"""
    try:
        summary = VoiceSummary.query.get_or_404(summary_id)
        
        return jsonify({
            'success': True,
            'summary': {
                'id': summary.id,
                'voice_note_id': summary.voice_note_id,
                'summary_html': summary.summary_html,
                'version': summary.summary_version,
                'transcripts_count': summary.transcripts_count,
                'comments_count': summary.comments_count,
                'model_used': summary.model_used,
                'created_by': summary.created_by,
                'created_at': summary.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                'is_current': summary.is_current
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'حدث خطأ أثناء جلب التقرير: {str(e)}'
        }), 500

# Monthly Plan Routes
@app.route('/monthly_plans')
@login_required
def monthly_plans():
    """List all monthly plans"""
    current_workspace_id = session.get('current_workspace_id', 'ws-general')
    
    try:
        # Get filter parameters
        year_filter = request.args.get('year', str(datetime.now().year))
        status_filter = request.args.get('status', 'all')
        category_filter = request.args.get('category', 'all')
        
        # Build query
        query = MonthlyPlan.query.filter_by(workspace_id=current_workspace_id).filter(MonthlyPlan.deleted_at.is_(None))
        
        if year_filter != 'all':
            query = query.filter_by(year=int(year_filter))
        if status_filter != 'all':
            query = query.filter_by(status=status_filter)
        if category_filter != 'all':
            query = query.filter_by(category=category_filter)
        
        # Order by year desc, month desc
        monthly_plans = query.order_by(MonthlyPlan.year.desc(), MonthlyPlan.month.desc()).all()
        
        # Get available years and categories
        available_years = db.session.query(MonthlyPlan.year).filter(MonthlyPlan.deleted_at.is_(None)).distinct().order_by(MonthlyPlan.year.desc()).all()
        available_categories = db.session.query(MonthlyPlan.category).filter(MonthlyPlan.deleted_at.is_(None)).distinct().all()
        
        # Get statistics
        total_plans = MonthlyPlan.query.filter(MonthlyPlan.deleted_at.is_(None)).count()
        current_month_plan = MonthlyPlan.query.filter(
            MonthlyPlan.month == datetime.now().month,
            MonthlyPlan.year == datetime.now().year,
            MonthlyPlan.deleted_at.is_(None)
        ).first()
        
        stats = {
            'total': total_plans,
            'current_month': current_month_plan is not None,
            'current_month_plan': current_month_plan
        }
        
        return render_template('monthly_plans.html', 
                             monthly_plans=monthly_plans,
                             available_years=[year[0] for year in available_years],
                             available_categories=[cat[0] for cat in available_categories],
                             current_year=year_filter,
                             current_status=status_filter,
                             current_category=category_filter,
                             stats=stats)
        
    except Exception as e:
        flash(f'حدث خطأ في تحميل الخطط الشهرية: {str(e)}', 'error')
        return render_template('monthly_plans.html', monthly_plans=[], available_years=[], available_categories=[], stats={'total': 0, 'current_month': False})

@app.route('/monthly_plans/new', methods=['GET', 'POST'])
@login_required
def new_monthly_plan():
    """Create a new monthly plan"""
    current_workspace_id = session.get('current_workspace_id', 'ws-general')
    
    if request.method == 'POST':
        try:
            # Check if plan for this month/year already exists
            existing_plan = MonthlyPlan.query.filter_by(
                workspace_id=current_workspace_id,
                month=int(request.form['month']),
                year=int(request.form['year']),
                deleted_at=None
            ).first()
            
            if existing_plan:
                flash(f'يوجد خطة شهرية بالفعل لشهر {existing_plan.month_name_arabic} {existing_plan.year}', 'error')
                return render_template('monthly_plan_form.html', plan=None)
            
            monthly_plan = MonthlyPlan(
                workspace_id=current_workspace_id,
                title=request.form['title'],
                month=int(request.form['month']),
                year=int(request.form['year']),
                priority=request.form.get('priority', 'medium'),
                category=request.form.get('category', 'general'),
                tags=request.form.get('tags', ''),
                created_by=request.form.get('created_by', 'مجهول')
            )
            
            db.session.add(monthly_plan)
            db.session.commit()
            flash('تم إنشاء الخطة الشهرية بنجاح!', 'success')
            return redirect(url_for('edit_monthly_plan', plan_id=monthly_plan.id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'حدث خطأ في إنشاء الخطة: {str(e)}', 'error')
    
    return render_template('monthly_plan_form.html', plan=None)

@app.route('/monthly_plans/<int:plan_id>')
@login_required
def edit_monthly_plan(plan_id):
    """View and edit a monthly plan"""
    try:
        monthly_plan = MonthlyPlan.query.filter_by(id=plan_id, deleted_at=None).first_or_404()
        
        # Get goals for this plan
        goals = MonthlyGoal.query.filter_by(monthly_plan_id=plan_id).order_by(MonthlyGoal.order_index.asc(), MonthlyGoal.created_at.asc()).all()
        
        # Calculate progress based on completed goals
        if goals:
            completed_goals = len([g for g in goals if g.status == 'completed'])
            progress = int((completed_goals / len(goals)) * 100)
            
            # Update progress if different
            if monthly_plan.progress_percentage != progress:
                monthly_plan.progress_percentage = progress
                monthly_plan.updated_at = datetime.utcnow()
                db.session.commit()
        
        return render_template('monthly_plan_edit.html', 
                             monthly_plan=monthly_plan, 
                             goals=goals)
        
    except Exception as e:
        flash(f'حدث خطأ في تحميل الخطة: {str(e)}', 'error')
        return redirect(url_for('monthly_plans'))

@app.route('/monthly_plans/<int:plan_id>/edit', methods=['GET', 'POST'])
@login_required
def update_monthly_plan(plan_id):
    """Update monthly plan details"""
    current_workspace_id = session.get('current_workspace_id', 'ws-general')
    monthly_plan = MonthlyPlan.query.filter_by(
        workspace_id=current_workspace_id,
        id=plan_id,
        deleted_at=None
    ).first_or_404()
    
    if request.method == 'POST':
        try:
            # Check if changing month/year conflicts with existing plan
            new_month = int(request.form['month'])
            new_year = int(request.form['year'])
            
            if new_month != monthly_plan.month or new_year != monthly_plan.year:
                existing_plan = MonthlyPlan.query.filter_by(
                    month=new_month,
                    year=new_year,
                    deleted_at=None
                ).filter(MonthlyPlan.id != plan_id).first()
                
                if existing_plan:
                    flash(f'يوجد خطة شهرية أخرى بالفعل لشهر {new_month}/{new_year}', 'error')
                    return render_template('monthly_plan_form.html', plan=monthly_plan)
            
            monthly_plan.title = request.form['title']
            monthly_plan.month = new_month
            monthly_plan.year = new_year
            monthly_plan.priority = request.form.get('priority', 'medium')
            monthly_plan.category = request.form.get('category', 'general')
            monthly_plan.tags = request.form.get('tags', '')
            monthly_plan.status = request.form.get('status', 'active')
            monthly_plan.updated_at = datetime.utcnow()
            
            # Handle completion
            if monthly_plan.status == 'completed' and not monthly_plan.completed_at:
                monthly_plan.completed_at = datetime.utcnow()
                monthly_plan.progress_percentage = 100
            elif monthly_plan.status != 'completed':
                monthly_plan.completed_at = None
            
            db.session.commit()
            flash('تم تحديث الخطة الشهرية بنجاح!', 'success')
            return redirect(url_for('edit_monthly_plan', plan_id=plan_id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'حدث خطأ في تحديث الخطة: {str(e)}', 'error')
    
    return render_template('monthly_plan_form.html', plan=monthly_plan)

@app.route('/api/monthly_plans/<int:plan_id>/delete', methods=['POST'])
@login_required
def delete_monthly_plan(plan_id):
    """Soft delete a monthly plan"""
    try:
        monthly_plan = MonthlyPlan.query.filter_by(id=plan_id, deleted_at=None).first_or_404()
        monthly_plan.deleted_at = datetime.utcnow()
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'تم حذف الخطة الشهرية بنجاح'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'حدث خطأ أثناء حذف الخطة: {str(e)}'
        }), 500

# Monthly Goal Routes
@app.route('/api/monthly_plans/<int:plan_id>/goals', methods=['POST'])
@login_required
def add_goal(plan_id):
    """Add a goal to a monthly plan"""
    current_workspace_id = session.get('current_workspace_id', 'ws-general')
    
    try:
        monthly_plan = MonthlyPlan.query.filter_by(id=plan_id, deleted_at=None).first_or_404()
        
        data = request.get_json()
        title = data.get('title', '').strip()
        
        if not title:
            return jsonify({'success': False, 'message': 'عنوان الهدف مطلوب'}), 400
        
        # Get next order index
        max_order = db.session.query(db.func.max(MonthlyGoal.order_index)).filter_by(monthly_plan_id=plan_id).scalar() or 0
        
        goal = MonthlyGoal(
            workspace_id=current_workspace_id,
            monthly_plan_id=plan_id,
            title=title,
            target_date=datetime.strptime(data.get('target_date'), '%Y-%m-%d').date() if data.get('target_date') else None,
            priority=data.get('priority', 'medium'),
            order_index=max_order + 1
        )
        
        db.session.add(goal)
        monthly_plan.updated_at = datetime.utcnow()
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'تم إضافة الهدف بنجاح',
            'goal_id': goal.id
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'حدث خطأ أثناء إضافة الهدف: {str(e)}'
        }), 500

@app.route('/api/goals/<int:goal_id>/update_status')
@login_required
def update_goal_status(goal_id):
    """Update goal status"""
    try:
        goal = MonthlyGoal.query.get_or_404(goal_id)
        new_status = request.args.get('status')
        
        if new_status in ['pending', 'in_progress', 'completed']:
            old_status = goal.status
            goal.status = new_status
            goal.updated_at = datetime.utcnow()
            
            # Set completed_at when goal is completed
            if new_status == 'completed' and old_status != 'completed':
                goal.completed_at = datetime.utcnow()
            elif new_status != 'completed':
                goal.completed_at = None
            
            # Update parent plan timestamp
            monthly_plan = MonthlyPlan.query.get(goal.monthly_plan_id)
            if monthly_plan:
                monthly_plan.updated_at = datetime.utcnow()
            
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': 'تم تحديث حالة الهدف'
            })
        else:
            return jsonify({
                'success': False,
                'message': 'حالة غير صحيحة'
            }), 400
            
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'حدث خطأ أثناء تحديث الهدف: {str(e)}'
        }), 500

@app.route('/api/goals/<int:goal_id>/delete', methods=['POST'])
@login_required
def delete_goal(goal_id):
    """Delete a goal"""
    try:
        goal = MonthlyGoal.query.get_or_404(goal_id)
        monthly_plan = MonthlyPlan.query.get(goal.monthly_plan_id)
        
        db.session.delete(goal)
        
        if monthly_plan:
            monthly_plan.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'تم حذف الهدف بنجاح'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'حدث خطأ أثناء حذف الهدف: {str(e)}'
        }), 500

# Reminder Routes
@app.route('/reminders')
@login_required
def reminders():
    """List all reminders"""
    current_workspace_id = session.get('current_workspace_id', 'ws-general')
    
    try:
        # Get filter parameters
        status_filter = request.args.get('status', 'active')
        category_filter = request.args.get('category', 'all')
        
        # Build query
        query = Reminder.query.filter(
            Reminder.workspace_id == current_workspace_id,
            Reminder.deleted_at.is_(None)
        )
        
        if status_filter != 'all':
            query = query.filter_by(status=status_filter)
        if category_filter != 'all':
            query = query.filter_by(category=category_filter)
        
        # Order by reminder date (due items first), then by priority
        reminders = query.order_by(
            Reminder.reminder_date.asc().nullslast(),
            db.case(
                (Reminder.priority == 'high', 1),
                (Reminder.priority == 'medium', 2),
                (Reminder.priority == 'low', 3)
            ),
            Reminder.created_at.desc()
        ).all()
        
        # Get available categories
        available_categories = db.session.query(Reminder.category).filter(Reminder.deleted_at.is_(None)).distinct().all()
        
        # Get statistics
        total_reminders = Reminder.query.filter(Reminder.deleted_at.is_(None)).count()
        active_reminders = Reminder.query.filter(Reminder.deleted_at.is_(None), Reminder.status == 'active').count()
        due_today = Reminder.query.filter(
            Reminder.deleted_at.is_(None),
            Reminder.status == 'active',
            Reminder.reminder_date <= date.today()
        ).count()
        
        stats = {
            'total': total_reminders,
            'active': active_reminders,
            'due_today': due_today
        }
        
        return render_template('reminders.html', 
                             reminders=reminders,
                             available_categories=[cat[0] for cat in available_categories],
                             current_status=status_filter,
                             current_category=category_filter,
                             stats=stats)
        
    except Exception as e:
        flash(f'حدث خطأ في تحميل التذكيرات: {str(e)}', 'error')
        return render_template('reminders.html', reminders=[], available_categories=[], stats={'total': 0, 'active': 0, 'due_today': 0})

@app.route('/api/reminders', methods=['POST'])
@login_required
def add_reminder():
    """Add a new reminder"""
    current_workspace_id = session.get('current_workspace_id', 'ws-general')
    
    try:
        data = request.get_json()
        title = data.get('title', '').strip()
        
        if not title:
            return jsonify({'success': False, 'message': 'عنوان التذكير مطلوب'}), 400
        
        reminder = Reminder(
            workspace_id=current_workspace_id,
            title=title,
            reminder_date=datetime.strptime(data.get('reminder_date'), '%Y-%m-%d').date() if data.get('reminder_date') else None,
            priority=data.get('priority', 'medium'),
            category=data.get('category', 'general'),
            extra_info=data.get('extra_info', '').strip() if data.get('extra_info') else None,
            created_by=data.get('created_by', 'مجهول')
        )
        
        db.session.add(reminder)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'تم إضافة التذكير بنجاح',
            'reminder_id': reminder.id
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'حدث خطأ أثناء إضافة التذكير: {str(e)}'
        }), 500

@app.route('/api/reminders/<int:reminder_id>/update_status')
@login_required
def update_reminder_status(reminder_id):
    """Update reminder status"""
    try:
        reminder = Reminder.query.get_or_404(reminder_id)
        new_status = request.args.get('status')
        
        if new_status in ['active', 'completed', 'dismissed']:
            old_status = reminder.status
            reminder.status = new_status
            reminder.updated_at = datetime.utcnow()
            
            # Set completed_at when reminder is completed
            if new_status == 'completed' and old_status != 'completed':
                reminder.completed_at = datetime.utcnow()
            elif new_status != 'completed':
                reminder.completed_at = None
            
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': 'تم تحديث حالة التذكير'
            })
        else:
            return jsonify({
                'success': False,
                'message': 'حالة غير صحيحة'
            }), 400
            
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'حدث خطأ أثناء تحديث التذكير: {str(e)}'
        }), 500

@app.route('/api/reminders/<int:reminder_id>/edit', methods=['POST'])
@login_required
def edit_reminder(reminder_id):
    """Edit/update a reminder"""
    try:
        reminder = Reminder.query.filter_by(id=reminder_id, deleted_at=None).first_or_404()
        data = request.get_json()
        
        title = data.get('title', '').strip()
        if not title:
            return jsonify({'success': False, 'message': 'عنوان التذكير مطلوب'}), 400
        
        # Update reminder fields
        reminder.title = title
        reminder.reminder_date = datetime.strptime(data.get('reminder_date'), '%Y-%m-%d').date() if data.get('reminder_date') else None
        reminder.priority = data.get('priority', 'medium')
        reminder.category = data.get('category', 'general')
        reminder.extra_info = data.get('extra_info', '').strip() if data.get('extra_info') else None
        reminder.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'تم تحديث التذكير بنجاح'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'حدث خطأ أثناء تحديث التذكير: {str(e)}'
        }), 500

@app.route('/api/reminders/<int:reminder_id>/delete', methods=['POST'])
@login_required
def delete_reminder(reminder_id):
    """Soft delete a reminder"""
    try:
        reminder = Reminder.query.filter_by(id=reminder_id, deleted_at=None).first_or_404()
        reminder.deleted_at = datetime.utcnow()
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'تم حذف التذكير بنجاح'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'حدث خطأ أثناء حذف التذكير: {str(e)}'
        }), 500

@app.route('/api/ai-status')
@login_required
def ai_status():
    """Check if Gemini AI is available and test connection"""
    if not GEMINI_ENABLED:
        return jsonify({
            'enabled': False,
            'status': 'not_configured',
            'message': 'API key not configured'
        })
    
    # Test connection
    connection_ok, result = test_gemini_connection()
    
    if connection_ok:
        best_model = get_best_gemini_model()
        return jsonify({
            'enabled': True,
            'status': 'available',
            'message': 'Gemini AI is ready',
            'available_models': result[:5],  # Show first 5 models
            'selected_model': best_model
        })
    else:
        return jsonify({
            'enabled': False,
            'status': 'error',
            'message': f'Connection failed: {result}'
        })

@app.route('/api/test-gemini')
@login_required
def test_gemini():
    """Test Gemini AI with a simple request"""
    if not GEMINI_ENABLED:
        return jsonify({
            'success': False,
            'error': 'API key not configured'
        })
    
    try:
        # Test with a simple Arabic request
        test_response = get_gemini_response("أنشئ عنوان ترحيبي بسيط", "")
        html_content, explanation = extract_html_from_response(test_response)
        
        return jsonify({
            'success': True,
            'raw_response': test_response[:200] + "..." if len(test_response) > 200 else test_response,
            'extracted_html': html_content[:200] + "..." if len(html_content) > 200 else html_content,
            'explanation': explanation
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })

# ============================================
# BACKLOG MANAGEMENT ROUTES
# ============================================

@app.route('/backlog')
@login_required
def backlog():
    """Display all projects in the backlog"""
    current_workspace_id = session.get('current_workspace_id', 'ws-general')
    projects = Project.query.filter_by(
        workspace_id=current_workspace_id,
        deleted_at=None
    ).order_by(Project.order_index, Project.created_at.desc()).all()
    return render_template('backlog.html', projects=projects)

@app.route('/backlog/project/<int:project_id>')
@login_required
def backlog_project(project_id):
    """Display project details with phases and stories"""
    project = Project.query.get_or_404(project_id)
    if project.deleted_at:
        flash('هذا المشروع محذوف', 'error')
        return redirect(url_for('backlog'))
    
    phases = Phase.query.filter_by(project_id=project_id).order_by(Phase.order_index, Phase.created_at).all()
    return render_template('backlog_project.html', project=project, phases=phases)

@app.route('/backlog/project/add', methods=['GET', 'POST'])
@login_required
def backlog_project_add():
    """Add a new project"""
    current_workspace_id = session.get('current_workspace_id', 'ws-general')
    
    if request.method == 'POST':
        project = Project(
            workspace_id=current_workspace_id,
            name=request.form['name'],
            name_arabic=request.form.get('name_arabic', ''),
            description=request.form.get('description', ''),
            status=request.form.get('status', 'active'),
            priority=request.form.get('priority', 'medium'),
            created_by=session.get('username', 'admin')
        )
        
        if request.form.get('start_date'):
            project.start_date = datetime.strptime(request.form['start_date'], '%Y-%m-%d').date()
        if request.form.get('end_date'):
            project.end_date = datetime.strptime(request.form['end_date'], '%Y-%m-%d').date()
        
        db.session.add(project)
        db.session.commit()
        flash('تم إضافة المشروع بنجاح!', 'success')
        return redirect(url_for('backlog_project', project_id=project.id))
    
    return render_template('backlog_project_form.html')

@app.route('/backlog/project/<int:project_id>/edit', methods=['GET', 'POST'])
@login_required
def backlog_project_edit(project_id):
    """Edit an existing project"""
    project = Project.query.get_or_404(project_id)
    
    if request.method == 'POST':
        project.name = request.form['name']
        project.name_arabic = request.form.get('name_arabic', '')
        project.description = request.form.get('description', '')
        project.status = request.form.get('status', 'active')
        project.priority = request.form.get('priority', 'medium')
        
        if request.form.get('start_date'):
            project.start_date = datetime.strptime(request.form['start_date'], '%Y-%m-%d').date()
        if request.form.get('end_date'):
            project.end_date = datetime.strptime(request.form['end_date'], '%Y-%m-%d').date()
        
        project.updated_at = datetime.utcnow()
        db.session.commit()
        flash('تم تحديث المشروع بنجاح!', 'success')
        return redirect(url_for('backlog_project', project_id=project.id))
    
    return render_template('backlog_project_form.html', project=project)

@app.route('/backlog/project/<int:project_id>/delete', methods=['POST'])
@login_required
def backlog_project_delete(project_id):
    """Soft delete a project"""
    project = Project.query.get_or_404(project_id)
    project.deleted_at = datetime.utcnow()
    db.session.commit()
    flash('تم حذف المشروع بنجاح!', 'success')
    return redirect(url_for('backlog'))

@app.route('/backlog/phase/add/<int:project_id>', methods=['GET', 'POST'])
@login_required
def backlog_phase_add(project_id):
    """Add a new phase to a project"""
    current_workspace_id = session.get('current_workspace_id', 'ws-general')
    project = Project.query.get_or_404(project_id)
    
    if request.method == 'POST':
        # Get max order index
        max_order = db.session.query(db.func.max(Phase.order_index)).filter_by(project_id=project_id).scalar() or 0
        
        phase = Phase(
            workspace_id=current_workspace_id,
            project_id=project_id,
            name=request.form['name'],
            name_arabic=request.form.get('name_arabic', ''),
            description=request.form.get('description', ''),
            goal=request.form.get('goal', ''),
            duration_weeks=int(request.form['duration_weeks']) if request.form.get('duration_weeks') else None,
            status=request.form.get('status', 'pending'),
            order_index=max_order + 1
        )
        
        db.session.add(phase)
        db.session.commit()
        flash('تم إضافة المرحلة بنجاح!', 'success')
        return redirect(url_for('backlog_project', project_id=project_id))
    
    return render_template('backlog_phase_form.html', project=project)

@app.route('/backlog/phase/<int:phase_id>/edit', methods=['GET', 'POST'])
@login_required
def backlog_phase_edit(phase_id):
    """Edit an existing phase"""
    phase = Phase.query.get_or_404(phase_id)
    
    if request.method == 'POST':
        phase.name = request.form['name']
        phase.name_arabic = request.form.get('name_arabic', '')
        phase.description = request.form.get('description', '')
        phase.goal = request.form.get('goal', '')
        phase.duration_weeks = int(request.form['duration_weeks']) if request.form.get('duration_weeks') else None
        phase.status = request.form.get('status', 'pending')
        phase.updated_at = datetime.utcnow()
        
        try:
            db.session.commit()
            flash('تم تحديث المرحلة بنجاح!', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating phase: {str(e)}', 'error')
        
        return redirect(url_for('backlog_project', project_id=phase.project_id, phase_id=phase_id))
    
    return render_template('backlog_phase_form.html', phase=phase, project=phase.project)

@app.route('/backlog/phase/<int:phase_id>/delete', methods=['POST'])
@login_required
def backlog_phase_delete(phase_id):
    """Delete a phase and all its stories"""
    phase = Phase.query.get_or_404(phase_id)
    project_id = phase.project_id
    stories_count = len(phase.user_stories)
    
    try:
        # Delete phase (will cascade delete all user stories, acceptance criteria, and notes)
        db.session.delete(phase)
        db.session.commit()
        flash(f'Phase deleted successfully! ({stories_count} stories removed)', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting phase: {str(e)}', 'error')
    
    return redirect(url_for('backlog_project', project_id=project_id))

@app.route('/backlog/story/<int:story_id>')
@login_required
def backlog_story(story_id):
    """Display user story details"""
    story = UserStory.query.get_or_404(story_id)
    return_phase = request.args.get('return_phase', type=int)
    return render_template('backlog_story.html', story=story, return_phase=return_phase)

@app.route('/backlog/story/add/<int:phase_id>', methods=['GET', 'POST'])
@login_required
def backlog_story_add(phase_id):
    """Add a new user story to a phase"""
    current_workspace_id = session.get('current_workspace_id', 'ws-general')
    phase = Phase.query.get_or_404(phase_id)
    
    if request.method == 'POST':
        # Get max order index
        max_order = db.session.query(db.func.max(UserStory.order_index)).filter_by(phase_id=phase_id).scalar() or 0
        
        story = UserStory(
            workspace_id=current_workspace_id,
            phase_id=phase_id,
            story_id=request.form['story_id'],
            title=request.form['title'],
            title_arabic=request.form.get('title_arabic', ''),
            user_role=request.form.get('user_role', ''),
            user_goal=request.form.get('user_goal', ''),
            user_benefit=request.form.get('user_benefit', ''),
            description=request.form.get('description', ''),
            priority=request.form.get('priority', 'medium'),
            complexity=request.form.get('complexity', 'medium'),
            status=request.form.get('status', 'pending'),
            technical_notes=request.form.get('technical_notes', ''),
            created_by=session.get('username', 'admin'),
            order_index=max_order + 1
        )
        
        db.session.add(story)
        db.session.flush()  # Get the story ID
        
        # Add acceptance criteria
        ac_descriptions = request.form.getlist('ac_description[]')
        for idx, ac_desc in enumerate(ac_descriptions):
            if ac_desc.strip():
                ac = AcceptanceCriteria(
                    user_story_id=story.id,
                    description=ac_desc.strip(),
                    order_index=idx
                )
                db.session.add(ac)
        
        db.session.commit()
        flash('تم إضافة القصة بنجاح!', 'success')
        # Redirect back to project page with phase anchor
        return redirect(url_for('backlog_project', project_id=phase.project_id, phase_id=phase_id))
    
    return render_template('backlog_story_form.html', phase=phase)

@app.route('/backlog/story/<int:story_id>/edit', methods=['GET', 'POST'])
@login_required
def backlog_story_edit(story_id):
    """Edit an existing user story"""
    story = UserStory.query.get_or_404(story_id)
    # Get return_phase from GET params (when loading form) or from request args (when submitting form)
    return_phase = request.args.get('return_phase', type=int)
    
    if request.method == 'POST':
        story.story_id = request.form['story_id']
        story.title = request.form['title']
        story.title_arabic = request.form.get('title_arabic', '')
        story.user_role = request.form.get('user_role', '')
        story.user_goal = request.form.get('user_goal', '')
        story.user_benefit = request.form.get('user_benefit', '')
        story.description = request.form.get('description', '')
        story.priority = request.form.get('priority', 'medium')
        story.complexity = request.form.get('complexity', 'medium')
        story.status = request.form.get('status', 'pending')
        story.technical_notes = request.form.get('technical_notes', '')
        story.updated_at = datetime.utcnow()
        
        # Update status timestamp
        if story.status == 'completed' and not story.completed_at:
            story.completed_at = datetime.utcnow()
        elif story.status != 'completed':
            story.completed_at = None
        
        try:
            db.session.commit()
            flash('Story updated successfully!', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating story: {str(e)}', 'error')
        
        # Redirect back to project page with phase anchor and story ID - use return_phase if provided
        phase_id = return_phase if return_phase else story.phase_id
        return redirect(url_for('backlog_project', project_id=story.phase.project_id, phase_id=phase_id, story_id=story_id))
    
    return render_template('backlog_story_form.html', story=story, phase=story.phase, return_phase=return_phase)

@app.route('/backlog/story/<int:story_id>/delete', methods=['POST'])
@login_required
def backlog_story_delete(story_id):
    """Delete a user story"""
    story = UserStory.query.get_or_404(story_id)
    project_id = story.phase.project_id
    phase_id = story.phase_id
    return_phase = request.form.get('return_phase', type=int)
    
    try:
        # Delete story (will cascade delete acceptance criteria and notes)
        db.session.delete(story)
        db.session.commit()
        flash('Story deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting story: {str(e)}', 'error')
    
    # Return to the phase if return_phase is provided, otherwise use story's phase
    redirect_phase_id = return_phase if return_phase else phase_id
    return redirect(url_for('backlog_project', project_id=project_id, phase_id=redirect_phase_id))

@app.route('/backlog/story/<int:story_id>/reorder', methods=['POST'])
@login_required
def backlog_story_reorder(story_id):
    """Reorder user stories via drag and drop"""
    story = UserStory.query.get_or_404(story_id)
    data = request.get_json()
    
    new_order = data.get('new_order')
    new_phase_id = data.get('new_phase_id')
    
    if new_phase_id and new_phase_id != story.phase_id:
        story.phase_id = new_phase_id
    
    if new_order is not None:
        story.order_index = new_order
    
    db.session.commit()
    return jsonify({'success': True})

@app.route('/backlog/criteria/<int:criteria_id>/toggle', methods=['POST'])
@login_required
def backlog_criteria_toggle(criteria_id):
    """Toggle acceptance criteria completion status"""
    criteria = AcceptanceCriteria.query.get_or_404(criteria_id)
    criteria.is_completed = not criteria.is_completed
    
    if criteria.is_completed:
        criteria.completed_at = datetime.utcnow()
    else:
        criteria.completed_at = None
    
    db.session.commit()
    
    # Check if all criteria are completed and update story status
    story = criteria.user_story
    if story.is_fully_completed and story.status != 'completed':
        story.status = 'completed'
        story.completed_at = datetime.utcnow()
        db.session.commit()
    
    return jsonify({
        'success': True,
        'is_completed': criteria.is_completed,
        'story_completion': story.completion_percentage
    })

@app.route('/backlog/criteria/<int:criteria_id>/edit', methods=['POST'])
@login_required
def backlog_criteria_edit(criteria_id):
    """Edit acceptance criteria description"""
    criteria = AcceptanceCriteria.query.get_or_404(criteria_id)
    data = request.get_json()
    
    new_description = data.get('description', '').strip()
    if not new_description:
        return jsonify({'success': False, 'error': 'Description cannot be empty'})
    
    criteria.description = new_description
    criteria.updated_at = datetime.utcnow()
    db.session.commit()
    
    return jsonify({
        'success': True,
        'description': criteria.description
    })

@app.route('/backlog/criteria/<int:criteria_id>/delete', methods=['POST'])
@login_required
def backlog_criteria_delete(criteria_id):
    """Delete acceptance criteria"""
    criteria = AcceptanceCriteria.query.get_or_404(criteria_id)
    
    db.session.delete(criteria)
    db.session.commit()
    
    return jsonify({'success': True})

@app.route('/backlog/criteria/add/<int:story_id>', methods=['POST'])
@login_required
def backlog_criteria_add(story_id):
    """Add a new acceptance criteria to a story"""
    current_workspace_id = session.get('current_workspace_id', 'ws-general')
    story = UserStory.query.get_or_404(story_id)
    data = request.get_json()
    
    max_order = db.session.query(db.func.max(AcceptanceCriteria.order_index)).filter_by(user_story_id=story_id).scalar() or 0
    
    criteria = AcceptanceCriteria(
        workspace_id=current_workspace_id,
        user_story_id=story_id,
        description=data.get('description', ''),
        order_index=max_order + 1
    )
    
    db.session.add(criteria)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'id': criteria.id,
        'description': criteria.description,
        'is_completed': criteria.is_completed
    })

@app.route('/backlog/note/add/<int:story_id>', methods=['POST'])
@login_required
def backlog_note_add(story_id):
    """Add a note to a user story"""
    current_workspace_id = session.get('current_workspace_id', 'ws-general')
    story = UserStory.query.get_or_404(story_id)
    data = request.get_json()
    
    note = StoryNote(
        workspace_id=current_workspace_id,
        user_story_id=story_id,
        content=data.get('content', ''),
        note_type=data.get('note_type', 'general'),
        author=session.get('username', 'admin')
    )
    
    db.session.add(note)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'id': note.id,
        'content': note.content,
        'note_type': note.note_type,
        'author': note.author,
        'created_at': note.created_at.strftime('%Y-%m-%d %H:%M')
    })

@app.route('/backlog/note/<int:note_id>/delete', methods=['POST'])
@login_required
def backlog_note_delete(note_id):
    """Delete a story note"""
    note = StoryNote.query.get_or_404(note_id)
    db.session.delete(note)
    db.session.commit()
    
    return jsonify({'success': True})

@app.route('/backlog/project/<int:project_id>/export')
@login_required
def backlog_export_project(project_id):
    """Export a specific project as JSON"""
    project = Project.query.get_or_404(project_id)
    
    if project.deleted_at:
        flash('هذا المشروع محذوف', 'error')
        return redirect(url_for('backlog'))
    
    export_data = {
        'version': '1.0',
        'exported_at': datetime.utcnow().isoformat(),
        'exported_by': session.get('username', 'admin'),
        'projects': []
    }
    
    # Export only this project
    project_data = {
        'name': project.name,
        'name_arabic': project.name_arabic,
        'description': project.description,
        'status': project.status,
        'priority': project.priority,
        'start_date': project.start_date.isoformat() if project.start_date else None,
        'end_date': project.end_date.isoformat() if project.end_date else None,
        'order_index': project.order_index,
        'phases': []
    }
    
    phases = Phase.query.filter_by(project_id=project.id).order_by(Phase.order_index, Phase.created_at).all()
    for phase in phases:
        phase_data = {
            'name': phase.name,
            'name_arabic': phase.name_arabic,
            'description': phase.description,
            'duration_weeks': phase.duration_weeks,
            'goal': phase.goal,
            'status': phase.status,
            'order_index': phase.order_index,
            'user_stories': []
        }
        
        stories = UserStory.query.filter_by(phase_id=phase.id).order_by(UserStory.order_index, UserStory.created_at).all()
        for story in stories:
            story_data = {
                'story_id': story.story_id,
                'title': story.title,
                'title_arabic': story.title_arabic,
                'user_role': story.user_role,
                'user_goal': story.user_goal,
                'user_benefit': story.user_benefit,
                'description': story.description,
                'priority': story.priority,
                'complexity': story.complexity,
                'status': story.status,
                'technical_notes': story.technical_notes,
                'order_index': story.order_index,
                'acceptance_criteria': [],
                'notes': []
            }
            
            criteria = AcceptanceCriteria.query.filter_by(user_story_id=story.id).order_by(AcceptanceCriteria.order_index, AcceptanceCriteria.created_at).all()
            for criterion in criteria:
                story_data['acceptance_criteria'].append({
                    'description': criterion.description,
                    'description_arabic': criterion.description_arabic,
                    'is_completed': criterion.is_completed,
                    'order_index': criterion.order_index
                })
            
            notes = StoryNote.query.filter_by(user_story_id=story.id).order_by(StoryNote.created_at).all()
            for note in notes:
                story_data['notes'].append({
                    'content': note.content,
                    'note_type': note.note_type,
                    'author': note.author
                })
            
            phase_data['user_stories'].append(story_data)
        
        project_data['phases'].append(phase_data)
    
    export_data['projects'].append(project_data)
    
    # Create JSON response with download
    from flask import Response
    import json
    
    json_str = json.dumps(export_data, ensure_ascii=False, indent=2)
    # Use project name in filename
    safe_project_name = "".join(c for c in project.name if c.isalnum() or c in (' ', '-', '_')).strip()[:30]
    filename = f"backlog_{safe_project_name}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
    
    return Response(
        json_str,
        mimetype='application/json',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )

@app.route('/backlog/template')
@login_required
def backlog_template():
    """Download a JSON template for backlog import"""
    template_data = {
        'version': '1.0',
        'projects': [
            {
                'name': 'Example Project Name',
                'name_arabic': 'اسم المشروع بالعربية',
                'description': 'Project description here',
                'status': 'active',  # active, completed, archived
                'priority': 'high',  # low, medium, high
                'start_date': '2025-01-01',  # YYYY-MM-DD format or null
                'end_date': '2025-12-31',  # YYYY-MM-DD format or null
                'order_index': 0,
                'phases': [
                    {
                        'name': 'Phase 1',
                        'name_arabic': 'المرحلة الأولى',
                        'description': 'Phase description',
                        'duration_weeks': 4,
                        'goal': 'Phase goal',
                        'status': 'pending',  # pending, in_progress, completed
                        'order_index': 0,
                        'user_stories': [
                            {
                                'story_id': 'US-001',
                                'title': 'Story title',
                                'title_arabic': 'عنوان القصة',
                                'user_role': 'user',
                                'user_goal': 'I want to do something',
                                'user_benefit': 'so I can achieve something',
                                'description': 'Detailed description',
                                'priority': 'high',  # low, medium, high
                                'complexity': 'medium',  # low, medium, high
                                'status': 'pending',  # pending, in_progress, completed, blocked
                                'technical_notes': 'Technical implementation notes',
                                'order_index': 0,
                                'acceptance_criteria': [
                                    {
                                        'description': 'Acceptance criterion 1',
                                        'description_arabic': 'معيار القبول 1',
                                        'is_completed': False,
                                        'order_index': 0
                                    }
                                ],
                                'notes': [
                                    {
                                        'content': 'Note content',
                                        'note_type': 'general',  # general, technical, design, question
                                        'author': 'admin'
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        ]
    }
    
    from flask import Response
    import json
    
    json_str = json.dumps(template_data, ensure_ascii=False, indent=2)
    
    return Response(
        json_str,
        mimetype='application/json',
        headers={'Content-Disposition': 'attachment; filename=backlog_template.json'}
    )

@app.route('/backlog/import', methods=['GET', 'POST'])
@login_required
def backlog_import():
    """Import backlog data from JSON file"""
    current_workspace_id = session.get('current_workspace_id', 'ws-general')
    
    if request.method == 'GET':
        return render_template('backlog.html', show_import_modal=True)
    
    # Handle POST request with file upload
    if 'json_file' not in request.files:
        flash('لم يتم رفع ملف', 'error')
        return redirect(url_for('backlog'))
    
    file = request.files['json_file']
    
    if file.filename == '':
        flash('لم يتم اختيار ملف', 'error')
        return redirect(url_for('backlog'))
    
    if not file.filename.endswith('.json'):
        flash('يجب رفع ملف JSON فقط', 'error')
        return redirect(url_for('backlog'))
    
    try:
        import json
        data = json.load(file)
        
        # Validate structure
        if 'projects' not in data:
            flash('صيغة الملف غير صحيحة: يجب أن يحتوي على "projects"', 'error')
            return redirect(url_for('backlog'))
        
        imported_count = 0
        username = session.get('username', 'admin')
        
        # Import projects
        for project_data in data['projects']:
            # Create project
            project = Project(
                workspace_id=current_workspace_id,
                name=project_data.get('name', 'Untitled Project'),
                name_arabic=project_data.get('name_arabic', ''),
                description=project_data.get('description', ''),
                status=project_data.get('status', 'active'),
                priority=project_data.get('priority', 'medium'),
                order_index=project_data.get('order_index', 0),
                created_by=username
            )
            
            if project_data.get('start_date'):
                try:
                    project.start_date = datetime.fromisoformat(project_data['start_date']).date()
                except:
                    pass
            
            if project_data.get('end_date'):
                try:
                    project.end_date = datetime.fromisoformat(project_data['end_date']).date()
                except:
                    pass
            
            db.session.add(project)
            db.session.flush()  # Get project ID
            
            # Import phases
            for phase_data in project_data.get('phases', []):
                phase = Phase(
                    workspace_id=current_workspace_id,
                    project_id=project.id,
                    name=phase_data.get('name', 'Untitled Phase'),
                    name_arabic=phase_data.get('name_arabic', ''),
                    description=phase_data.get('description', ''),
                    duration_weeks=phase_data.get('duration_weeks'),
                    goal=phase_data.get('goal', ''),
                    status=phase_data.get('status', 'pending'),
                    order_index=phase_data.get('order_index', 0)
                )
                
                db.session.add(phase)
                db.session.flush()  # Get phase ID
                
                # Import user stories
                for story_data in phase_data.get('user_stories', []):
                    story = UserStory(
                        workspace_id=current_workspace_id,
                        phase_id=phase.id,
                        story_id=story_data.get('story_id', 'US-000'),
                        title=story_data.get('title', 'Untitled Story'),
                        title_arabic=story_data.get('title_arabic'),
                        user_role=story_data.get('user_role', ''),
                        user_goal=story_data.get('user_goal', ''),
                        user_benefit=story_data.get('user_benefit', ''),
                        description=story_data.get('description', ''),
                        priority=story_data.get('priority', 'medium'),
                        complexity=story_data.get('complexity', 'medium'),
                        status=story_data.get('status', 'pending'),
                        technical_notes=story_data.get('technical_notes', ''),
                        order_index=story_data.get('order_index', 0),
                        created_by=username
                    )
                    
                    db.session.add(story)
                    db.session.flush()  # Get story ID
                    
                    # Import acceptance criteria
                    for criteria_data in story_data.get('acceptance_criteria', []):
                        criterion = AcceptanceCriteria(
                            user_story_id=story.id,
                            description=criteria_data.get('description', ''),
                            description_arabic=criteria_data.get('description_arabic'),
                            is_completed=criteria_data.get('is_completed', False),
                            order_index=criteria_data.get('order_index', 0)
                        )
                        db.session.add(criterion)
                    
                    # Import notes
                    for note_data in story_data.get('notes', []):
                        note = StoryNote(
                            workspace_id=current_workspace_id,
                            user_story_id=story.id,
                            content=note_data.get('content', ''),
                            note_type=note_data.get('note_type', 'general'),
                            author=note_data.get('author', username)
                        )
                        db.session.add(note)
            
            imported_count += 1
        
        db.session.commit()
        flash(f'تم استيراد {imported_count} مشروع بنجاح!', 'success')
        
    except json.JSONDecodeError:
        flash('خطأ في قراءة ملف JSON: تأكد من صحة صيغة الملف', 'error')
    except Exception as e:
        db.session.rollback()
        flash(f'حدث خطأ أثناء الاستيراد: {str(e)}', 'error')
    
    return redirect(url_for('backlog'))

def init_db():
    with app.app_context():
        db.create_all()
        print("Database tables created successfully!")
        
        # Run production migration for new columns
        try:
            migrate_task_columns()
        except Exception as e:
            print(f"Migration warning: {str(e)}")

def migrate_task_columns():
    """Add new columns to existing Task table if they don't exist"""
    import sqlite3
    
    # Get database path
    db_path = app.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', '')
    
    # Handle Fly.io volume path
    if '/data/' in os.environ.get('DATABASE_URL', ''):
        db_path = '/data/team_planning.db'
    elif not os.path.exists(db_path) and os.path.exists('/data/team_planning.db'):
        db_path = '/data/team_planning.db'
    
    if os.path.exists(db_path):
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check current columns
        cursor.execute("PRAGMA table_info(task)")
        columns = [column[1] for column in cursor.fetchall()]
        
        # Add missing columns
        new_columns = [
            ('tags', 'VARCHAR(500)'),
            ('updated_at', 'DATETIME'),
            ('completed_at', 'DATETIME')
        ]
        
        for column_name, column_type in new_columns:
            if column_name not in columns:
                print(f"Adding missing column: {column_name}")
                cursor.execute(f"ALTER TABLE task ADD COLUMN {column_name} {column_type}")
                
                # Set default value for updated_at
                if column_name == 'updated_at':
                    cursor.execute("UPDATE task SET updated_at = created_at WHERE updated_at IS NULL")
                    
        # Update completed_at for completed tasks
        cursor.execute("""
            UPDATE task 
            SET completed_at = COALESCE(updated_at, created_at)
            WHERE status = 'completed' AND completed_at IS NULL
        """)
        
        conn.commit()
        conn.close()
        print("Database migration completed!")


# Admin Panel Routes (Super Admin Only)
@app.route('/admin/workspaces')
@superadmin_required
def admin_workspaces():
    """List all workspaces"""
    workspaces = Workspace.query.all()
    return render_template('admin_workspaces.html', workspaces=workspaces)

@app.route('/admin/workspace/new', methods=['GET', 'POST'])
@superadmin_required
def admin_workspace_new():
    """Create a new workspace"""
    if request.method == 'POST':
        workspace_id = request.form.get('workspace_id', '').strip().lower()
        name = request.form.get('name')
        description = request.form.get('description', '')
        
        # Validate workspace ID format
        if not workspace_id:
            flash('يجب إدخال معرف الـ workspace', 'error')
            return render_template('admin_workspace_form.html', workspace=None)
        
        if not workspace_id.startswith('ws-'):
            flash('يجب أن يبدأ معرف الـ workspace بـ "ws-"', 'error')
            return render_template('admin_workspace_form.html', workspace=None)
        
        # Validate only contains lowercase letters, numbers, and hyphens
        if not re.match(r'^ws-[a-z0-9-]+$', workspace_id):
            flash('معرف الـ workspace يجب أن يحتوي على أحرف إنجليزية صغيرة وأرقام وشرطات فقط', 'error')
            return render_template('admin_workspace_form.html', workspace=None)
        
        # Check if workspace already exists
        if Workspace.query.get(workspace_id):
            flash(f'Workspace بهذا المعرف موجود بالفعل: {workspace_id}', 'error')
            return render_template('admin_workspace_form.html', workspace=None)
        
        workspace = Workspace(
            id=workspace_id,
            name=name,
            description=description
        )
        db.session.add(workspace)
        db.session.commit()
        
        flash(f'تم إنشاء workspace بنجاح: {name}', 'success')
        return redirect(url_for('admin_workspaces'))
    
    return render_template('admin_workspace_form.html', workspace=None)

@app.route('/admin/workspace/<workspace_id>/edit', methods=['GET', 'POST'])
@superadmin_required
def admin_workspace_edit(workspace_id):
    """Edit a workspace"""
    print("\n" + "="*80)
    print(f"🔵 ROUTE ACCESSED: /admin/workspace/{workspace_id}/edit")
    print(f"🔵 Request Method: {request.method}")
    print(f"🔵 Request URL: {request.url}")
    print(f"🔵 THIS SHOULD ALWAYS PRINT IF ROUTE IS HIT!")
    print("="*80)
    
    # Query workspace directly
    print(f"🔎 Querying workspace with id: '{workspace_id}'")
    workspace = Workspace.query.filter_by(id=workspace_id).first()
    print(f"✅ Workspace query completed: {workspace is not None}")
    
    if not workspace:
        print(f"⚠️ Workspace not found, redirecting to admin_workspaces")
        flash('Workspace not found', 'error')
        return redirect(url_for('admin_workspaces'))
    
    if request.method == 'POST':
        print(f"📝 Processing POST request")
        workspace.name = request.form.get('name')
        workspace.description = request.form.get('description', '')
        db.session.commit()
        
        # Update session if user is currently in this workspace
        if session.get('current_workspace_id') == workspace_id:
            session['current_workspace_name'] = workspace.name
        
        flash(f'تم تحديث workspace بنجاح: {workspace.name}', 'success')
        return redirect(url_for('admin_workspaces'))
    
    # GET request - render form
    print(f"📄 Rendering form template for GET request")
    rendered = render_template('admin_workspace_form.html', workspace=workspace)
    print(f"✅ Template rendered successfully (length: {len(rendered)} chars)")
    
    response = make_response(rendered)
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    # Don't send Arabic text in headers - HTTP headers must be ASCII only
    response.headers['X-Workspace-Id'] = workspace.id
    
    print(f"🚀 Returning response")
    print("="*80 + "\n")
    return response

@app.route('/admin/workspace/<workspace_id>/delete', methods=['POST'])
@superadmin_required
def admin_workspace_delete(workspace_id):
    """Delete a workspace"""
    if workspace_id == 'ws-general':
        flash('لا يمكن حذف workspace الرئيسي (ws-general)', 'error')
        return redirect(url_for('admin_workspaces'))
    
    workspace = Workspace.query.get_or_404(workspace_id)
    
    # Check if there are users assigned to this workspace
    user_count = UserWorkspace.query.filter_by(workspace_id=workspace_id).count()
    if user_count > 0:
        flash(f'لا يمكن حذف workspace يحتوي على {user_count} مستخدم(ين)', 'error')
        return redirect(url_for('admin_workspaces'))
    
    db.session.delete(workspace)
    db.session.commit()
    
    flash(f'تم حذف workspace: {workspace.name}', 'success')
    return redirect(url_for('admin_workspaces'))

@app.route('/admin/users')
@superadmin_required
def admin_users():
    """List all users"""
    users = User.query.all()
    return render_template('admin_users.html', users=users, current_user=get_current_user())

@app.route('/admin/user/new', methods=['GET', 'POST'])
@superadmin_required
def admin_user_new():
    """Create a new user"""
    workspaces = Workspace.query.all()
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        is_superadmin = request.form.get('is_superadmin') == 'on'
        workspace_ids = request.form.getlist('workspaces')
        
        # Check if username already exists
        if User.query.filter_by(username=username).first():
            flash(f'اسم المستخدم موجود بالفعل: {username}', 'error')
            return render_template('admin_user_form.html', user=None, workspaces=workspaces)
        
        # Create user
        user = User(
            username=username,
            is_superadmin=is_superadmin
        )
        user.set_password(password)
        db.session.add(user)
        db.session.flush()  # Get user ID
        
        # Assign workspaces
        for workspace_id in workspace_ids:
            user_workspace = UserWorkspace(
                user_id=user.id,
                workspace_id=workspace_id
            )
            db.session.add(user_workspace)
        
        # Set first workspace as default
        if workspace_ids:
            user.last_workspace_id = workspace_ids[0]
        
        db.session.commit()
        
        flash(f'تم إنشاء المستخدم بنجاح: {username}', 'success')
        return redirect(url_for('admin_users'))
    
    return render_template('admin_user_form.html', user=None, workspaces=workspaces)

@app.route('/admin/user/<int:user_id>/edit', methods=['GET', 'POST'])
@superadmin_required
def admin_user_edit(user_id):
    """Edit a user"""
    user = User.query.get_or_404(user_id)
    current_user = get_current_user()
    workspaces = Workspace.query.all()
    user_workspace_ids = [uw.workspace_id for uw in user.workspaces]
    
    if request.method == 'POST':
        # Check if editing yourself - only allow password changes
        if user.id == current_user.id:
            password = request.form.get('password')
            if password:  # Only update password if provided
                user.set_password(password)
                flash(f'✅ تم تحديث كلمة المرور الخاصة بك', 'success')
            else:
                flash('⚠️ لم يتم إجراء أي تغييرات', 'info')
        else:
            # Editing another user - allow all changes
            user.username = request.form.get('username')
            password = request.form.get('password')
            if password:  # Only update password if provided
                user.set_password(password)
            
            user.is_superadmin = request.form.get('is_superadmin') == 'on'
            workspace_ids = request.form.getlist('workspaces')
            
            # Update workspace assignments
            # Remove old assignments
            UserWorkspace.query.filter_by(user_id=user.id).delete()
            
            # Add new assignments
            for workspace_id in workspace_ids:
                user_workspace = UserWorkspace(
                    user_id=user.id,
                    workspace_id=workspace_id
                )
                db.session.add(user_workspace)
            
            # Update last workspace if needed
            if workspace_ids and user.last_workspace_id not in workspace_ids:
                user.last_workspace_id = workspace_ids[0]
            
            flash(f'تم تحديث المستخدم بنجاح: {user.username}', 'success')
        
        db.session.commit()
        return redirect(url_for('admin_users'))
    
    return render_template('admin_user_form.html', user=user, workspaces=workspaces, user_workspace_ids=user_workspace_ids, current_user=current_user)

@app.route('/admin/user/<int:user_id>/delete', methods=['POST'])
@superadmin_required
def admin_user_delete(user_id):
    """Delete a user"""
    user = User.query.get_or_404(user_id)
    current_user = get_current_user()
    
    # Prevent deleting yourself
    if user.id == current_user.id:
        flash('❌ لا يمكنك حذف حسابك الخاص', 'error')
        return redirect(url_for('admin_users'))
    
    username = user.username
    db.session.delete(user)
    db.session.commit()
    
    flash(f'تم حذف المستخدم: {username}', 'success')
    return redirect(url_for('admin_users'))

if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 5000))
    host = '0.0.0.0' if port != 5000 else '127.0.0.1'
    
    # Enable threaded mode to handle multiple requests
    print("🚀 Starting Flask server...")
    print(f"   - Host: {host}")
    print(f"   - Port: {port}")
    print(f"   - Debug: True")
    print(f"   - Threaded: True")
    print("="*80)
    
    app.run(debug=True, host=host, port=port, threaded=True, use_reloader=True) 