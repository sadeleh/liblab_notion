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
    status = db.Column(db.String(20), default='pending')  # pending, in_progress, completed
    priority = db.Column(db.String(10), default='medium')  # low, medium, high
    assigned_to = db.Column(db.String(100))
    due_date = db.Column(db.Date)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    category = db.Column(db.String(50), default='general')

class Resource(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    url = db.Column(db.String(500))
    resource_type = db.Column(db.String(50))  # document, link, file, note
    tags = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.String(100))

class BrainstormSession(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    status = db.Column(db.String(20), default='active')  # active, completed, archived
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
    """Test Gemini AI connection and return available models"""
    if not GEMINI_ENABLED:
        return False, "API key not configured"
    
    try:
        # List available models to check connection
        models = genai.list_models()
        available_models = []
        for model in models:
            if 'generateContent' in model.supported_generation_methods:
                available_models.append(model.name)
        
        return True, available_models
    except Exception as e:
        return False, str(e)

def get_best_gemini_model():
    """Get the best available Gemini model"""
    if not GEMINI_ENABLED:
        return None
    
    # Preferred models in order of preference (newest first)
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
        
        # Return the first preferred model that's available
        for preferred in preferred_models:
            if preferred in available_models:
                return preferred
                
        # If no preferred model found, return the first available one
        if available_models:
            return available_models[0]
            
        return None
    except Exception:
        return 'models/gemini-1.5-pro'  # Default fallback

def print_gemini_model_info():
    """Print detailed information about Gemini model selection and availability"""
    if not GEMINI_ENABLED:
        print("❌ Gemini AI not enabled - GEMINI_API_KEY not configured")
        return
    
    try:
        print("🧠 Gemini AI Model Information:")
        print("=" * 50)
        
        # Get connection status
        connection_ok, result = test_gemini_connection()
        print(f"📡 Connection Status: {'✅ Connected' if connection_ok else '❌ Failed'}")
        
        if connection_ok:
            available_models = result
            selected_model = get_best_gemini_model()
            
            print(f"🎯 Selected Model: {selected_model}")
            print(f"📊 Total Available Models: {len(available_models)}")
            
            print("\n🏆 Model Priority Order:")
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
            
            for i, model in enumerate(preferred_models, 1):
                status = "✅ AVAILABLE" if model in available_models else "❌ Not Available"
                marker = "👑 SELECTED" if model == selected_model else ""
                print(f"  {i}. {model} - {status} {marker}")
            
            print(f"\n📋 All Available Models ({len(available_models)}):")
            for model in available_models[:15]:  # Show first 15
                print(f"  • {model}")
            if len(available_models) > 15:
                print(f"  ... and {len(available_models) - 15} more")
        else:
            print(f"❌ Connection Error: {result}")
    
    except Exception as e:
        print(f"❌ Error getting model info: {e}")

def get_gemini_response(user_input, context=""):
    """Get response from Gemini AI for smart notion creation/modification"""
    if not GEMINI_ENABLED:
        return json.dumps({
            "action": "error",
            "html_content": "<div class='text-center p-8 bg-yellow-50 border border-yellow-200 rounded-lg'><h3 class='text-lg font-semibold text-yellow-800 mb-2'>⚠️ مطلوب إعداد مفتاح Gemini AI</h3><p class='text-yellow-700'>يرجى تكوين متغير البيئة GEMINI_API_KEY لاستخدام الملاحظات الذكية</p><p class='text-sm text-yellow-600 mt-2'>احصل على مفتاح API من: https://makersuite.google.com/app/apikey</p></div>",
            "explanation": "مطلوب إعداد مفتاح Gemini AI لاستخدام هذه الميزة"
        })
    
    try:
        # Get the best available model
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
        4. تنسيق وتصميم المحتوى
        5. إنشاء قوائم وجداول ومخططات
        
        قواعد مهمة:
        - استخدم HTML صحيح مع Tailwind CSS للتنسيق
        - اجعل التصميم متجاوب وجميل
        - استخدم الألوان المتناسقة مع موقعنا (cyan-950, etc.)
        - اكتب المحتوى باللغة العربية
        - اجعل النص يدعم RTL
        - لا تضع أي تعليقات أو شروحات خارج JSON
        - لا تستخدم markdown (```json أو ```)
        
        السياق الحالي: {context}
        
        طلب المستخدم: {user_input}
        
        IMPORTANT: أرجع فقط JSON صحيح بدون أي markdown أو تعليقات إضافية:
        {{
            "action": "نوع العملية (create, modify, add_section, style)",
            "html_content": "المحتوى HTML الجديد أو المحدث",
            "explanation": "شرح مختصر ما تم عمله باللغة العربية"
        }}
        """
        
        response = model.generate_content(system_prompt)
        return response.text
    except Exception as e:
        return json.dumps({
            "action": "error",
            "html_content": f"<div class='text-center p-8 bg-red-50 border border-red-200 rounded-lg'><h3 class='text-lg font-semibold text-red-800 mb-2'>❌ خطأ في الاتصال</h3><p class='text-red-700'>حدث خطأ في الاتصال مع المساعد الذكي</p><p class='text-sm text-red-600 mt-2'>رسالة الخطأ: {str(e)}</p><p class='text-xs text-red-500 mt-1'>النموذج المستخدم: {model_name if 'model_name' in locals() else 'غير محدد'}</p></div>",
            "explanation": f"خطأ في الاتصال مع Gemini AI: {str(e)}"
        })

def extract_html_from_response(ai_response):
    """Extract HTML content from AI response and clean it properly"""
    try:
        # Remove markdown code blocks if present
        cleaned_response = ai_response.strip()
        
        # Remove ```json and ``` wrappers
        if cleaned_response.startswith('```json'):
            cleaned_response = cleaned_response[7:]  # Remove ```json
        if cleaned_response.startswith('```'):
            cleaned_response = cleaned_response[3:]   # Remove ```
        if cleaned_response.endswith('```'):
            cleaned_response = cleaned_response[:-3]  # Remove trailing ```
        
        cleaned_response = cleaned_response.strip()
        
        # Try to parse as JSON
        response_data = json.loads(cleaned_response)
        
        html_content = response_data.get("html_content", "")
        explanation = response_data.get("explanation", "")
        
        # Clean up the HTML content
        if html_content:
            # Replace literal \n with actual newlines, then remove extra whitespace
            html_content = html_content.replace('\\n', '\n')
            # Remove excessive newlines and whitespace
            html_content = re.sub(r'\n\s*\n\s*\n+', '\n\n', html_content)
            html_content = re.sub(r'^\s+|\s+$', '', html_content, flags=re.MULTILINE)
            html_content = html_content.strip()
        
        return html_content, explanation
        
    except json.JSONDecodeError as e:
        # If JSON parsing fails, try to extract HTML using regex
        html_match = re.search(r'```html\n(.*?)\n```', ai_response, re.DOTALL)
        if html_match:
            return html_match.group(1), ai_response
        
        # Last resort: return cleaned response
        cleaned = re.sub(r'```json|```', '', ai_response).strip()
        return cleaned, f"تم استخراج المحتوى بدون تحليل JSON: {str(e)}"

# Routes
@app.route('/')
def index():
    recent_tasks = Task.query.order_by(Task.created_at.desc()).limit(5).all()
    recent_resources = Resource.query.order_by(Resource.created_at.desc()).limit(3).all()
    active_sessions = BrainstormSession.query.filter_by(status='active').limit(3).all()
    
    # Task statistics
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
    
    # Calculate statistics
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
            content_html='<div class="text-center p-8 bg-gradient-to-r from-cyan-50 to-blue-50 rounded-lg border border-cyan-200"><h2 class="text-2xl font-bold text-cyan-950 mb-4">🎉 مرحباً بك في ملاحظتك الذكية الجديدة!</h2><p class="text-gray-700 mb-6">استخدم نافذة الدردشة على اليمين لبدء إنشاء المحتوى</p><div class="bg-white p-4 rounded-lg shadow-sm border border-cyan-100"><h3 class="font-semibold text-cyan-800 mb-2">💡 أمثلة على ما يمكنك طلبه:</h3><ul class="text-right space-y-1 text-gray-600"><li>• "أنشئ قائمة مهام لمشروع جديد"</li><li>• "اكتب خطة عمل لثلاثة أشهر"</li><li>• "أضف جدول للمواعيد الأسبوعية"</li><li>• "أنشئ قسم للملاحظات والأفكار"</li></ul></div></div>',
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
    
    # Build context for Gemini
    context_parts = []
    
    # Add current notion content
    context_parts.append(f"المحتوى الحالي للملاحظة:\n{notion.content_html}")
    
    # Add recent conversation history
    recent_conversations = ChatConversation.query.filter_by(notion_id=notion_id)\
        .order_by(ChatConversation.created_at.desc()).limit(5).all()
    
    if recent_conversations:
        context_parts.append("\nتاريخ المحادثة الأخير:")
        for conv in reversed(recent_conversations):  # Reverse to show chronological order
            context_parts.append(f"المستخدم: {conv.user_message}")
            context_parts.append(f"المساعد: {conv.ai_response}")
    
    context = "\n".join(context_parts)
    
    # Get AI response
    ai_response = get_gemini_response(user_message, context)
    html_content, explanation = extract_html_from_response(ai_response)
    
    if html_content:
        # Update notion content
        notion.content_html = html_content
        notion.updated_at = datetime.utcnow()
        
        # Save conversation
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

@app.route('/api/ai-status')
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

@app.route('/api/debug-gemini')
def debug_gemini():
    """Debug endpoint to show Gemini model and interaction details"""
    if not GEMINI_ENABLED:
        return jsonify({
            'success': False,
            'error': 'API key not configured',
            'model_info': None
        })
    
    try:
        # Get model information
        best_model = get_best_gemini_model()
        connection_ok, available_models = test_gemini_connection()
        
        # Test with context example
        sample_context = """المحتوى الحالي للملاحظة:
<div class="text-center p-8">
    <h2>مرحباً بكم في ملاحظتي</h2>
    <p>هذا مثال على المحتوى الموجود</p>
</div>

تاريخ المحادثة:
المستخدم: أضف قسم جديد
المساعد: تم إضافة قسم جديد بنجاح"""
        
        sample_request = "أضف قائمة مهام بثلاث مهام"
        
        # Get sample response
        sample_response = get_gemini_response(sample_request, sample_context)
        html_content, explanation = extract_html_from_response(sample_response)
        
        return jsonify({
            'success': True,
            'model_info': {
                'selected_model': best_model,
                'connection_status': 'connected' if connection_ok else 'failed',
                'available_models': available_models[:10] if connection_ok else [],
                'total_models': len(available_models) if connection_ok else 0
            },
            'context_example': {
                'user_request': sample_request,
                'context_used': sample_context,
                'raw_response': sample_response[:500] + "..." if len(sample_response) > 500 else sample_response,
                'extracted_html': html_content[:300] + "..." if len(html_content) > 300 else html_content,
                'explanation': explanation
            },
            'prompt_structure': {
                'system_prompt_includes': [
                    "Arabic language instructions",
                    "HTML/Tailwind CSS formatting rules",
                    "RTL text support",
                    "Current context from notion",
                    "Chat history (last 5 conversations)",
                    "JSON response format requirements"
                ]
            }
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'model_info': {
                'selected_model': get_best_gemini_model() if get_best_gemini_model() else 'unknown',
                'error_details': str(e)
            }
        })

@app.route('/liblab_plan')
def liblab_plan():
    return render_template('liblab_plan.html')

@app.route('/api/model-info')
def get_model_info():
    """Get Gemini model information as JSON and print to console"""
    if not GEMINI_ENABLED:
        return jsonify({'enabled': False, 'error': 'API key not configured'})
    
    try:
        best_model = get_best_gemini_model()
        connection_ok, available_models = test_gemini_connection()
        
        # Print to console/logs for debugging
        print_gemini_model_info()
        
        return jsonify({
            'enabled': True,
            'selected_model': best_model,
            'connection_ok': connection_ok,
            'available_models': available_models,
            'total_models': len(available_models) if connection_ok else 0,
            'preferred_order': [
                'models/gemini-2.5-flash', 
                'models/gemini-2.5-pro',
                'models/gemini-2.5-pro-preview-06-05',
                'models/gemini-2.0-flash-exp',
                'models/gemini-1.5-pro',
                'models/gemini-1.5-flash',
                'models/gemini-pro',
                'models/gemini-1.0-pro'
            ]
        })
    except Exception as e:
        return jsonify({
            'enabled': False,
            'error': str(e)
        })

def init_db():
    """Initialize database tables"""
    with app.app_context():
        db.create_all()
        print("Database tables created successfully!")

if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 5000))
    host = '0.0.0.0' if port != 5000 else '127.0.0.1'
    app.run(debug=True, host=host, port=port) 