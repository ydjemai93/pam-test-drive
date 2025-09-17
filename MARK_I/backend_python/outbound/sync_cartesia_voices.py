import os
import httpx
import asyncio
from dotenv import load_dotenv
import sys
from pathlib import Path

# Load environment variables from the outbound directory
current_dir = Path(__file__).parent
env_file = current_dir / '.env.local'
load_dotenv(env_file, encoding='utf-8')

# Add the api directory to path for imports
sys.path.append(str(current_dir.parent / 'api'))

# Import after setting up the path and environment
from supabase import create_client, Client

# Get environment variables
api_key = os.getenv('CARTESIA_API_KEY')
SUPABASE_URL = os.getenv("SUPABASE_URL") 
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
    print("Error: SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY not found in environment")
    print("Please make sure these are set in your .env.local file")
    exit(1)

# Create Supabase client
supabase_client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

async def sync_cartesia_voices():
    """Sync the voices table with actual voices available in your Cartesia account"""
    
    async with httpx.AsyncClient() as client:
        headers = {
            'X-API-Key': api_key,
            'Cartesia-Version': '2025-04-16'
        }
        
        # Get all voices from Cartesia
        all_voices = []
        next_page = None
        
        while True:
            url = 'https://api.cartesia.ai/voices'
            if next_page:
                url += f'?page={next_page}'
                
            response = await client.get(url, headers=headers)
            
            if response.status_code != 200:
                print(f"Error fetching voices: {response.status_code} - {response.text}")
                return
            
            data = response.json()
            all_voices.extend(data['data'])
            
            if not data.get('has_more', False):
                break
            next_page = data.get('next_page')
        
        print(f"Found {len(all_voices)} voices in your Cartesia account")
        
        # Clear existing voices and insert new ones
        print("Clearing existing voices...")
        delete_response = supabase_client.table("voices").delete().neq('id', '00000000-0000-0000-0000-000000000000').execute()
        print(f"Deleted {len(delete_response.data) if delete_response.data else 0} existing voices")
        
        # Insert new voices
        voices_to_insert = []
        for voice in all_voices:
            # Map gender
            gender = None
            if voice.get('gender') == 'feminine':
                gender = 'female'
            elif voice.get('gender') == 'masculine':
                gender = 'male'
            
            # Map language
            language_code = voice.get('language', 'en')
            language_name = 'English' if language_code == 'en' else 'French' if language_code == 'fr' else 'Spanish' if language_code == 'es' else 'Unknown'
            
            voice_data = {
                'cartesia_voice_id': voice['id'],
                'name': voice['name'],
                'language_code': language_code,
                'language_name': language_name,
                'gender': gender,
                'description': voice.get('description'),
                'cartesia_preview_url': f"https://api.cartesia.ai/voices/{voice['id']}/preview",
                'is_active': True,
                'provider': 'cartesia',
                'provider_model': 'sonic-2',
                'sample_rate': 44100
            }
            voices_to_insert.append(voice_data)
        
        # Insert in batches
        batch_size = 10
        for i in range(0, len(voices_to_insert), batch_size):
            batch = voices_to_insert[i:i+batch_size]
            insert_response = supabase_client.table("voices").insert(batch).execute()
            if insert_response.data:
                print(f"Inserted batch {i//batch_size + 1}: {len(insert_response.data)} voices")
            else:
                print(f"Error inserting batch {i//batch_size + 1}: {insert_response}")
        
        print(f"✅ Successfully synced {len(voices_to_insert)} voices!")
        
        # Test preview for first voice
        if voices_to_insert:
            first_voice = voices_to_insert[0]
            test_id = first_voice['cartesia_voice_id']
            preview_headers = {
                'X-API-Key': api_key,
                'Cartesia-Version': '2025-04-16',
                'Accept': 'audio/mpeg'
            }
            test_response = await client.get(
                f'https://api.cartesia.ai/voices/{test_id}/preview',
                headers=preview_headers
            )
            print(f"Preview test for {first_voice['name']}: {test_response.status_code}")

if __name__ == "__main__":
    asyncio.run(sync_cartesia_voices()) 