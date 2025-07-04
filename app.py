from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text
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

# Create upload directory for voice recordings
UPLOAD_FOLDER = os.path.join(app.instance_path, 'voice_recordings')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Ensure upload directory exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(app.instance_path, exist_ok=True)

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
    deleted_at = db.Column(db.DateTime, nullable=True)
    
class ChatConversation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    notion_id = db.Column(db.Integer, db.ForeignKey('smart_notion.id'), nullable=False)
    user_message = db.Column(db.Text, nullable=False)
    ai_response = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class VoiceNote(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    summary_html = db.Column(db.Text)  # Gemini-generated summary and insights
    created_by = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    deleted_at = db.Column(db.DateTime, nullable=True)
    
class VoiceRecording(db.Model):
    id = db.Column(db.Integer, primary_key=True)
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
    voice_note_id = db.Column(db.Integer, db.ForeignKey('voice_note.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    author = db.Column(db.String(100))
    comment_type = db.Column(db.String(20), default='text')  # 'text' or 'voice'
    recording_id = db.Column(db.Integer, db.ForeignKey('voice_recording.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class VoiceSummary(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    voice_note_id = db.Column(db.Integer, db.ForeignKey('voice_note.id'), nullable=False)
    summary_html = db.Column(db.Text, nullable=False)  # The generated summary content
    summary_version = db.Column(db.Integer, default=1)  # Version number for tracking
    transcripts_count = db.Column(db.Integer, default=0)  # Number of transcripts analyzed
    comments_count = db.Column(db.Integer, default=0)  # Number of comments analyzed
    model_used = db.Column(db.String(100))  # Which AI model was used
    created_by = db.Column(db.String(100))  # Who generated this summary
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_current = db.Column(db.Boolean, default=True)  # Flag for the current/latest summary

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

def has_deleted_at_column():
    """Check if deleted_at column exists in SmartNotion table"""
    try:
        # Try to access the column
        db.session.execute(text("SELECT deleted_at FROM smart_notion LIMIT 1"))
        return True
    except Exception:
        return False

@app.route('/smart_notion')
def smart_notion():
    try:
        # Check if deleted_at column exists
        if has_deleted_at_column():
            # Use new filtering with deleted_at
            notions = SmartNotion.query.filter(SmartNotion.deleted_at.is_(None)).order_by(SmartNotion.updated_at.desc()).all()
            total_notions = SmartNotion.query.filter(SmartNotion.deleted_at.is_(None)).count()
            today_count = SmartNotion.query.filter(
                SmartNotion.created_at >= datetime.now().replace(hour=0, minute=0, second=0, microsecond=0),
                SmartNotion.deleted_at.is_(None)
            ).count()
        else:
            # Use old filtering without deleted_at (backward compatibility)
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
        
    except Exception as e:
        # Fallback to basic query if there's any issue
        notions = SmartNotion.query.order_by(SmartNotion.updated_at.desc()).all()
        stats = {
            'total': len(notions),
            'today': len([n for n in notions if n.created_at.date() == datetime.now().date()])
        }
        return render_template('smart_notion.html', notions=notions, stats=stats)

@app.route('/smart_notion/new', methods=['GET', 'POST'])
def new_smart_notion():
    if request.method == 'POST':
        notion = SmartNotion(
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
def edit_smart_notion(notion_id):
    try:
        # Check if deleted_at column exists
        if has_deleted_at_column():
            # Only allow editing non-deleted notions
            notion = SmartNotion.query.filter_by(id=notion_id, deleted_at=None).first_or_404()
        else:
            # Backward compatibility - no deleted_at filtering
            notion = SmartNotion.query.filter_by(id=notion_id).first_or_404()
            
        conversations = ChatConversation.query.filter_by(notion_id=notion_id).order_by(ChatConversation.created_at.asc()).all()
        return render_template('smart_notion_edit.html', notion=notion, conversations=conversations)
        
    except Exception as e:
        # Fallback to basic query
        notion = SmartNotion.query.filter_by(id=notion_id).first_or_404()
        conversations = ChatConversation.query.filter_by(notion_id=notion_id).order_by(ChatConversation.created_at.asc()).all()
        return render_template('smart_notion_edit.html', notion=notion, conversations=conversations)

@app.route('/api/smart_notion/<int:notion_id>/delete', methods=['POST'])
def delete_smart_notion(notion_id):
    """Soft delete a smart notion"""
    try:
        # Check if deleted_at column exists
        if has_deleted_at_column():
            # Only allow deleting non-deleted notions
            notion = SmartNotion.query.filter_by(id=notion_id, deleted_at=None).first_or_404()
            
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
def smart_notion_chat(notion_id):
    try:
        # Check if deleted_at column exists
        if has_deleted_at_column():
            # Only allow chat with non-deleted notions
            notion = SmartNotion.query.filter_by(id=notion_id, deleted_at=None).first_or_404()
        else:
            # Backward compatibility - no deleted_at filtering
            notion = SmartNotion.query.filter_by(id=notion_id).first_or_404()
            
        user_message = request.json.get('message', '')
        preferred_model = request.json.get('model', None)
    except Exception as e:
        # Fallback to basic query
        notion = SmartNotion.query.filter_by(id=notion_id).first_or_404()
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
def voice_notes():
    """List all voice notes"""
    try:
        # Get all non-deleted voice notes
        voice_notes = VoiceNote.query.filter(VoiceNote.deleted_at.is_(None)).order_by(VoiceNote.updated_at.desc()).all()
        
        # Get statistics
        total_notes = VoiceNote.query.filter(VoiceNote.deleted_at.is_(None)).count()
        today_count = VoiceNote.query.filter(
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
def new_voice_note():
    """Create a new voice note"""
    if request.method == 'POST':
        voice_note = VoiceNote(
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
def edit_voice_note(note_id):
    """View and edit a voice note"""
    try:
        # Get non-deleted voice note
        voice_note = VoiceNote.query.filter_by(id=note_id, deleted_at=None).first_or_404()
    except Exception:
        # Fallback without deleted_at filtering
        voice_note = VoiceNote.query.filter_by(id=note_id).first_or_404()
    
    # Get all recordings for this note
    recordings = VoiceRecording.query.filter_by(voice_note_id=note_id).order_by(VoiceRecording.created_at.asc()).all()
    
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
def upload_voice_recording(note_id):
    """Upload a voice recording to a voice note"""
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
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
        
        # Save the file
        audio_file.save(file_path)
        
        # Get file size
        file_size = os.path.getsize(file_path)
        
        # Create recording record
        recording = VoiceRecording(
            voice_note_id=note_id,
            filename=unique_filename,
            original_name=audio_file.filename,
            file_size=file_size,
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
            'file_size': file_size
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'حدث خطأ أثناء رفع التسجيل: {str(e)}'
        }), 500

@app.route('/api/voice_notes/<int:note_id>/comment', methods=['POST'])
def add_voice_comment(note_id):
    """Add a text comment to a voice note"""
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
def delete_voice_note(note_id):
    """Soft delete a voice note"""
    try:
        # Try to get and soft delete the voice note
        try:
            voice_note = VoiceNote.query.filter_by(id=note_id, deleted_at=None).first_or_404()
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
def serve_voice_recording(filename):
    """Serve voice recording files"""
    try:
        # Security check - only allow files that exist in our upload folder
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        if not os.path.exists(file_path):
            return "File not found", 404
        
        # Check if filename contains only allowed characters
        import re
        if not re.match(r'^[a-zA-Z0-9\-_.]+$', filename):
            return "Invalid filename", 400
        
        from flask import send_from_directory
        return send_from_directory(app.config['UPLOAD_FOLDER'], filename)
        
    except Exception as e:
        return f"Error serving file: {str(e)}", 500

@app.route('/api/voice_recordings/<int:recording_id>/transcript', methods=['POST'])
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
        
        # Get the audio file path
        audio_file_path = os.path.join(app.config['UPLOAD_FOLDER'], recording.filename)
        
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
            
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'حدث خطأ أثناء تحويل التسجيل: {str(e)}'
        }), 500

@app.route('/api/voice_notes/<int:note_id>/generate_summary', methods=['POST'])
def generate_voice_note_summary(note_id):
    """Generate AI summary and insights for a voice note using Gemini with historical tracking"""
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

@app.route('/liblab_plan')
def liblab_plan():
    return render_template('liblab_plan.html')

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

def init_db():
    with app.app_context():
        db.create_all()
        print("Database tables created successfully!")

if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 5000))
    host = '0.0.0.0' if port != 5000 else '127.0.0.1'
    app.run(debug=True, host=host, port=port) 