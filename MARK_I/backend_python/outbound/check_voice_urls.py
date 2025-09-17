import asyncio
import os
from supabase import create_client, Client
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

async def check_voice_urls():
    """Check what preview URLs are stored in the database"""
    
    # Initialize Supabase client
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_service_key = os.getenv("SUPABASE_SERVICE_KEY")
    
    if not supabase_url or not supabase_service_key:
        print("❌ Missing Supabase credentials")
        return
    
    supabase: Client = create_client(supabase_url, supabase_service_key)
    
    try:
        # Get all voices from database
        response = supabase.table("voices").select("id, name, cartesia_voice_id, cartesia_preview_url").execute()
        
        if not response.data:
            print("No voices found in database")
            return
        
        print(f"Found {len(response.data)} voices in database:")
        print("-" * 80)
        
        for voice in response.data:
            print(f"ID: {voice['id']}")
            print(f"Name: {voice['name']}")
            print(f"Cartesia Voice ID: {voice['cartesia_voice_id']}")
            print(f"Preview URL: {voice['cartesia_preview_url']}")
            print("-" * 80)
            
    except Exception as e:
        print(f"❌ Error checking voice URLs: {e}")

if __name__ == "__main__":
    asyncio.run(check_voice_urls()) 