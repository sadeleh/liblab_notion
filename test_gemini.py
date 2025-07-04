#!/usr/bin/env python3
"""
Test script for Gemini AI API
Run this script to verify your Gemini API key is working correctly before using the Smart Notions feature.
"""

import os
import sys
import google.generativeai as genai

def test_gemini_api():
    """Test Gemini API connection and model availability"""
    
    # Check if API key is set
    api_key = os.environ.get('GEMINI_API_KEY', '')
    if not api_key:
        print("❌ GEMINI_API_KEY environment variable is not set")
        print("Please set it with: export GEMINI_API_KEY='your-api-key-here'")
        print("Get your API key from: https://makersuite.google.com/app/apikey")
        return False
    
    try:
        # Configure Gemini
        genai.configure(api_key=api_key)
        print("✅ API key configured successfully")
        
        # List available models
        print("\n📋 Available models:")
        models = genai.list_models()
        generation_models = []
        
        for model in models:
            if 'generateContent' in model.supported_generation_methods:
                generation_models.append(model.name)
                print(f"  - {model.name}")
        
        if not generation_models:
            print("❌ No models available for content generation")
            return False
        
        # Select best model (prioritize newer 2.5 models)
        preferred_models = [
            'models/gemini-2.5-pro',              # Latest 2.5 Pro model
            'models/gemini-2.5-pro-preview-06-05', # 2.5 Pro preview
            'models/gemini-2.5-flash',            # Latest 2.5 Flash
            'models/gemini-2.0-flash-exp',        # 2.0 Experimental
            'models/gemini-1.5-pro',              # Fallback to 1.5 Pro
            'models/gemini-1.5-flash',            # 1.5 Flash
            'models/gemini-pro',                  # Legacy fallback
            'models/gemini-1.0-pro'               # Oldest fallback
        ]
        
        selected_model = None
        for preferred in preferred_models:
            if preferred in generation_models:
                selected_model = preferred
                break
        
        if not selected_model:
            selected_model = generation_models[0]
        
        print(f"\n🎯 Selected model: {selected_model}")
        
        # Test content generation
        print("\n🧪 Testing content generation...")
        model = genai.GenerativeModel(selected_model)
        
        test_prompt = """
        أنشئ عنوان ترحيبي بسيط باللغة العربية لصفحة ويب، واجعل الرد في صيغة JSON يحتوي على:
        - "title": العنوان الرئيسي
        - "subtitle": العنوان الفرعي
        - "message": رسالة ترحيبية
        """
        
        response = model.generate_content(test_prompt)
        
        if response.text:
            print("✅ Content generation successful!")
            print(f"📝 Response preview: {response.text[:200]}...")
            return True
        else:
            print("❌ Empty response from model")
            return False
            
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return False

def main():
    """Main function"""
    print("🧠 Gemini AI API Test Script")
    print("=" * 40)
    
    success = test_gemini_api()
    
    print("\n" + "=" * 40)
    if success:
        print("🎉 All tests passed! Smart Notions feature is ready to use.")
        print("\nYou can now run the Flask app with: python app.py")
    else:
        print("❌ Tests failed. Please fix the issues above before using Smart Notions.")
        print("\nTroubleshooting:")
        print("1. Make sure your API key is correct")
        print("2. Check your internet connection")
        print("3. Verify the API key has the necessary permissions")
    
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main()) 