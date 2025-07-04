from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os
import google.generativeai as genai
import json
import re

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///team_planning.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Database Models
class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    status = db.Column(db.String(20), default='pending')
    priority = db.Column(db.String(10), default='medium')
    assigned_to = db.Column(db.String(100))
    due_date = db.Column(db.Date)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    category = db.Column(db.String(50), default='general')

class Resource(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    url = db.Column(db.String(500))
    resource_type = db.Column(db.String(50))
    tags = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.String(100))

class BrainstormSession(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    status = db.Column(db.String(20), default='active')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.String(100))

class Idea(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    session_id = db.Column(db.Integer, db.ForeignKey('brainstorm_session.id'), nullable=False)
    author = db.Column(db.String(100))
    votes = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class SmartNotion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content_html = db.Column(db.Text, nullable=False)
    created_by = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
class ChatConversation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    notion_id = db.Column(db.Integer, db.ForeignKey('smart_notion.id'), nullable=False)
    user_message = db.Column(db.Text, nullable=False)
    ai_response = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# Gemini AI Configuration
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')
GEMINI_ENABLED = bool(GEMINI_API_KEY and GEMINI_API_KEY != 'your-gemini-api-key-here')

if GEMINI_ENABLED:
    genai.configure(api_key=GEMINI_API_KEY)

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

def get_gemini_response(user_input, context=""):
    if not GEMINI_ENABLED:
        return json.dumps({
            "action": "error",
            "html_content": "<div class='text-center p-8 bg-yellow-50 border border-yellow-200 rounded-lg'><h3 class='text-lg font-semibold text-yellow-800 mb-2'>⚠️ مطلوب إعداد مفتاح Gemini AI</h3><p class='text-yellow-700'>يرجى تكوين متغير البيئة GEMINI_API_KEY لاستخدام الملاحظات الذكية</p></div>",
            "explanation": "مطلوب إعداد مفتاح Gemini AI لاستخدام هذه الميزة"
        })
    
    try:
        model_name = get_best_gemini_model()
        if not model_name:
            raise Exception("No compatible Gemini models available")
            
        model = genai.GenerativeModel(model_name)
        
        system_prompt = f"""
        أنت مساعد ذكي لإنشاء وتعديل صفحات الملاحظات الذكية باللغة العربية. 
        
        المهام التي يمكنك القيام بها:
        1. إنشاء محتوى HTML جديد بناء على طلب المستخدم
        2. تعديل المحتوى الموجود
        3. إضافة أقسام جديدة
        
        قواعد مهمة:
        - استخدم HTML صحيح مع Tailwind CSS للتنسيق
        - اجعل التصميم متجاوب وجميل
        - استخدم الألوان المتناسقة مع موقعنا (cyan-950, etc.)
        - اكتب المحتوى باللغة العربية
        - اجعل النص يدعم RTL
        - لا تستخدم markdown (```json أو ```)
        
        السياق الحالي: {context}
        طلب المستخدم: {user_input}
        
        أرجع فقط JSON صحيح:
        {{
            "action": "نوع العملية",
            "html_content": "المحتوى HTML الجديد",
            "explanation": "شرح ما تم عمله"
        }}
        """
        
        response = model.generate_content(system_prompt)
        return response.text
    except Exception as e:
        return json.dumps({
            "action": "error",
            "html_content": f"<div class='text-center p-8 bg-red-50'>❌ خطأ: {str(e)}</div>",
            "explanation": f"خطأ في الاتصال: {str(e)}"
        })

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
        
        if html_content:
            html_content = html_content.replace('\\n', '\n')
            html_content = re.sub(r'\n\s*\n\s*\n+', '\n\n', html_content)
            html_content = html_content.strip()
        
        return html_content, explanation
        
    except json.JSONDecodeError as e:
        cleaned = re.sub(r'```json|```', '', ai_response).strip()
        return cleaned, f"تم استخراج المحتوى: {str(e)}"

# Routes
@app.route('/')
def index():
    recent_tasks = Task.query.order_by(Task.created_at.desc()).limit(5).all()
    recent_resources = Resource.query.order_by(Resource.created_at.desc()).limit(3).all()
    active_sessions = BrainstormSession.query.filter_by(status='active').limit(3).all()
    
    total_tasks = Task.query.count()
    completed_tasks = Task.query.filter_by(status='completed').count()
    pending_tasks = Task.query.filter_by(status='pending').count()
    in_progress_tasks = Task.query.filter_by(status='in_progress').count()
    
    stats = {
        'total': total_tasks,
        'completed': completed_tasks,
        'pending': pending_tasks,
        'in_progress': in_progress_tasks
    }
    
    return render_template('index.html', 
                         recent_tasks=recent_tasks,
                         recent_resources=recent_resources,
                         active_sessions=active_sessions,
                         stats=stats)

@app.route('/tasks')
def tasks():
    status_filter = request.args.get('status', 'all')
    category_filter = request.args.get('category', 'all')
    
    query = Task.query
    
    if status_filter != 'all':
        query = query.filter_by(status=status_filter)
    if category_filter != 'all':
        query = query.filter_by(category=category_filter)
    
    tasks = query.order_by(Task.created_at.desc()).all()
    categories = db.session.query(Task.category).distinct().all()
    
    return render_template('tasks.html', tasks=tasks, categories=categories,
                         current_status=status_filter, current_category=category_filter)

@app.route('/tasks/new', methods=['GET', 'POST'])
def new_task():
    if request.method == 'POST':
        task = Task(
            title=request.form['title'],
            description=request.form['description'],
            priority=request.form['priority'],
            assigned_to=request.form['assigned_to'],
            category=request.form['category'],
            due_date=datetime.strptime(request.form['due_date'], '%Y-%m-%d').date() if request.form['due_date'] else None
        )
        db.session.add(task)
        db.session.commit()
        flash('Task created successfully!', 'success')
        return redirect(url_for('tasks'))
    
    return render_template('task_form.html')

@app.route('/tasks/<int:task_id>/update_status')
def update_task_status(task_id):
    task = Task.query.get_or_404(task_id)
    new_status = request.args.get('status')
    
    if new_status in ['pending', 'in_progress', 'completed']:
        task.status = new_status
        db.session.commit()
        flash('Task status updated!', 'success')
    
    return redirect(url_for('tasks'))

@app.route('/resources')
def resources():
    resource_type = request.args.get('type', 'all')
    
    query = Resource.query
    if resource_type != 'all':
        query = query.filter_by(resource_type=resource_type)
    
    resources = query.order_by(Resource.created_at.desc()).all()
    resource_types = db.session.query(Resource.resource_type).distinct().all()
    
    return render_template('resources.html', resources=resources, 
                         resource_types=resource_types, current_type=resource_type)

@app.route('/resources/new', methods=['GET', 'POST'])
def new_resource():
    if request.method == 'POST':
        resource = Resource(
            title=request.form['title'],
            description=request.form['description'],
            url=request.form['url'],
            resource_type=request.form['resource_type'],
            tags=request.form['tags'],
            created_by=request.form['created_by']
        )
        db.session.add(resource)
        db.session.commit()
        flash('Resource added successfully!', 'success')
        return redirect(url_for('resources'))
    
    return render_template('resource_form.html')

@app.route('/brainstorm')
def brainstorm():
    sessions = BrainstormSession.query.order_by(BrainstormSession.created_at.desc()).all()
    return render_template('brainstorm.html', sessions=sessions)

@app.route('/brainstorm/new', methods=['GET', 'POST'])
def new_brainstorm_session():
    if request.method == 'POST':
        session = BrainstormSession(
            title=request.form['title'],
            description=request.form['description'],
            created_by=request.form['created_by']
        )
        db.session.add(session)
        db.session.commit()
        flash('Brainstorm session created!', 'success')
        return redirect(url_for('brainstorm_session', session_id=session.id))
    
    return render_template('brainstorm_form.html')

@app.route('/brainstorm/<int:session_id>')
def brainstorm_session(session_id):
    session = BrainstormSession.query.get_or_404(session_id)
    ideas = Idea.query.filter_by(session_id=session_id).order_by(Idea.votes.desc(), Idea.created_at.desc()).all()
    return render_template('brainstorm_session.html', session=session, ideas=ideas)

@app.route('/brainstorm/<int:session_id>/add_idea', methods=['POST'])
def add_idea(session_id):
    idea = Idea(
        content=request.form['content'],
        session_id=session_id,
        author=request.form['author']
    )
    db.session.add(idea)
    db.session.commit()
    flash('Idea added!', 'success')
    return redirect(url_for('brainstorm_session', session_id=session_id))

@app.route('/api/vote_idea/<int:idea_id>')
def vote_idea(idea_id):
    idea = Idea.query.get_or_404(idea_id)
    idea.votes += 1
    db.session.commit()
    return jsonify({'votes': idea.votes})

@app.route('/smart_notion')
def smart_notion():
    notions = SmartNotion.query.order_by(SmartNotion.updated_at.desc()).all()
    
    total_notions = SmartNotion.query.count()
    today_count = SmartNotion.query.filter(
        SmartNotion.created_at >= datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    ).count()
    
    stats = {
        'total': total_notions,
        'today': today_count
    }
    
    return render_template('smart_notion.html', notions=notions, stats=stats)

@app.route('/smart_notion/new', methods=['GET', 'POST'])
def new_smart_notion():
    if request.method == 'POST':
        notion = SmartNotion(
            title=request.form['title'],
            content_html='<div class="text-center p-8 bg-gradient-to-r from-cyan-50 to-blue-50 rounded-lg border border-cyan-200"><h2 class="text-2xl font-bold text-cyan-950 mb-4">🎉 مرحباً بك في ملاحظتك الذكية الجديدة!</h2><p class="text-gray-700 mb-6">استخدم نافذة الدردشة على اليمين لبدء إنشاء المحتوى</p></div>',
            created_by=request.form.get('created_by', 'مجهول')
        )
        db.session.add(notion)
        db.session.commit()
        flash('Smart Notion created successfully!', 'success')
        return redirect(url_for('edit_smart_notion', notion_id=notion.id))
    
    return render_template('smart_notion_form.html')

@app.route('/smart_notion/<int:notion_id>')
def edit_smart_notion(notion_id):
    notion = SmartNotion.query.get_or_404(notion_id)
    conversations = ChatConversation.query.filter_by(notion_id=notion_id).order_by(ChatConversation.created_at.asc()).all()
    return render_template('smart_notion_edit.html', notion=notion, conversations=conversations)

@app.route('/api/smart_notion/<int:notion_id>/chat', methods=['POST'])
def smart_notion_chat(notion_id):
    notion = SmartNotion.query.get_or_404(notion_id)
    user_message = request.json.get('message', '')
    
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
    
    ai_response = get_gemini_response(user_message, context)
    html_content, explanation = extract_html_from_response(ai_response)
    
    if html_content:
        notion.content_html = html_content
        notion.updated_at = datetime.utcnow()
        
        conversation = ChatConversation(
            notion_id=notion_id,
            user_message=user_message,
            ai_response=explanation
        )
        db.session.add(conversation)
        db.session.commit()
    
    return jsonify({
        'ai_response': explanation,
        'updated_content': html_content,
        'success': True
    })

@app.route('/liblab_plan')
def liblab_plan():
    return render_template('liblab_plan.html')

def init_db():
    with app.app_context():
        db.create_all()
        print("Database tables created successfully!")

if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 5000))
    host = '0.0.0.0' if port != 5000 else '127.0.0.1'
    app.run(debug=True, host=host, port=port) 