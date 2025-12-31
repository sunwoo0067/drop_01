import asyncio
from app.db import SessionLocal
from app.models import APIKey
import google.generativeai as genai

async def test():
    with SessionLocal() as db:
        keys = db.query(APIKey.key).filter(APIKey.provider == "gemini", APIKey.is_active == True).all()
        keys = [k[0] for k in keys]
    
    if not keys:
        print("No Gemini keys found in DB")
        return
        
    print(f"Found {len(keys)} Gemini keys. Testing first one...")
    genai.configure(api_key=keys[0])
    
    try:
        model = genai.GenerativeModel("gemini-1.5-flash")
        response = await model.generate_content_async("Hi")
        print(f"Response: {response.text}")
    except Exception as e:
        print(f"Error for gemini-1.5-flash: {e}")
        
    try:
        print("Listing available models...")
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                print(f"- {m.name}")
    except Exception as e:
        print(f"Error listing models: {e}")

if __name__ == "__main__":
    asyncio.run(test())
