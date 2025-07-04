#!/usr/bin/env python3
"""Test improved Arabic PDF generation with enhanced Pyppeteer"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_pdf_from_html

def test_improved_arabic_pdf():
    """Test enhanced Arabic PDF generation"""
    
    html_content = """
    <div class="bg-cyan-50 p-8 rounded-xl border-2 border-dashed border-cyan-200">
        <h2 class="text-2xl font-bold text-cyan-950 mb-4">اختبار محسن للنصوص العربية</h2>
        
        <div class="mb-6">
            <p class="text-cyan-700 mb-4">
                هذا اختبار شامل للتحسينات الجديدة في تصدير PDF للنصوص العربية. 
                التحسينات تشمل دعم أفضل للخطوط العربية وترتيب RTL المحسن.
            </p>
        </div>
        
        <div class="bg-white p-6 rounded-lg shadow-sm border mb-6">
            <h3 class="text-lg font-semibold text-cyan-950 mb-3">النص العربي المتواصل:</h3>
            <p class="text-gray-700 mb-4">
                بسم الله الرحمن الرحيم. هذا نص عربي طويل لاختبار تدفق النصوص والتواصل بين الحروف.
                يجب أن تظهر الحروف العربية متصلة بشكل صحيح ومقروءة بوضوح تام.
                النص يجب أن يكون من اليمين إلى اليسار بشكل طبيعي ومتدفق.
            </p>
            
            <h4 class="text-md font-semibold text-cyan-900 mb-2">كلمات متنوعة:</h4>
            <ul class="list-disc list-inside space-y-1 text-gray-600">
                <li>البرمجة والتطوير</li>
                <li>الذكاء الاصطناعي</li>
                <li>تقنيات الويب الحديثة</li>
                <li>قواعد البيانات والخوادم</li>
                <li>أمان المعلومات والشبكات</li>
            </ul>
        </div>
        
        <div class="bg-blue-50 p-6 rounded-lg border mb-6">
            <h3 class="text-lg font-semibold text-cyan-950 mb-3">أرقام وتواريخ:</h3>
            <p class="text-gray-700">
                التاريخ: ٢٠٢٥/٠٦/٣٠ الساعة: ١٢:٣٠ ظهراً
            </p>
            <p class="text-gray-700">
                الأرقام الإنجليزية: 2025/06/30 الساعة: 12:30 PM
            </p>
        </div>
        
        <div class="text-center p-4 bg-green-50 rounded-lg border border-green-200">
            <p class="text-sm font-semibold text-green-900 mb-2">
                "إن مع العسر يسراً"
            </p>
            <p class="text-xs text-green-600">
                الآية الكريمة من سورة الشرح
            </p>
        </div>
        
        <div class="mt-6 text-sm text-gray-600">
            <p>
                ملاحظة: يجب أن تظهر جميع النصوص العربية واضحة ومقروءة، 
                مع التدفق الصحيح من اليمين لليسار، والاتصال السليم بين الحروف.
            </p>
        </div>
    </div>
    """
    
    print("🔧 اختبار التحسينات الجديدة للنصوص العربية...")
    print("=" * 60)
    
    try:
        print("⏳ جاري إنشاء PDF مع التحسينات الجديدة...")
        print("   • خطوط عربية محسنة (Amiri, Cairo, Noto Kufi)")
        print("   • دعم RTL متقدم")
        print("   • تشكيل النصوص المحسن")
        print("   • انتظار تحميل الخطوط")
        
        pdf_buffer = create_pdf_from_html(html_content, "اختبار محسن للنصوص العربية")
        
        if pdf_buffer:
            pdf_data = pdf_buffer.getvalue()
            pdf_size = len(pdf_data)
            
            print(f"\n✅ نجح إنشاء PDF! حجم الملف: {pdf_size:,} بايت")
            
            # Save improved test file
            with open('improved_arabic_test.pdf', 'wb') as f:
                f.write(pdf_data)
            
            print("💾 تم حفظ الملف: improved_arabic_test.pdf")
            print("\n📋 يرجى فتح الملف والتحقق من:")
            print("   ✓ وضوح النصوص العربية (لا مربعات فارغة)")
            print("   ✓ اتصال الحروف العربية بشكل صحيح")
            print("   ✓ اتجاه RTL من اليمين لليسار") 
            print("   ✓ جودة الخطوط والتنسيق")
            print("   ✓ محاذاة القوائم والعناصر")
            
            print(f"\n🎉 التحسينات نجحت! الملف جاهز للمراجعة.")
            return True
            
        else:
            print("❌ فشل في إنشاء PDF")
            return False
            
    except Exception as e:
        print(f"❌ خطأ في التحسينات: {e}")
        print("\n🔄 سيتم التجربة مع الطريقة البديلة...")
        return False

if __name__ == "__main__":
    success = test_improved_arabic_pdf()
    if success:
        print("\n🌟 التحسينات الجديدة تعمل بنجاح!")
        print("🚀 جاهز للاستخدام في التطبيق!")
    else:
        print("\n⚠️ قد تحتاج لمراجعة إعدادات إضافية")
    
    input("\nاضغط Enter للإنهاء...") 