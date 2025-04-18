#!/usr/bin/env python
import asyncio
import os
from dotenv import load_dotenv

# Import the main API entrypoint
from livekit import api as livekit_api

async def find_and_display_trunk():
    """Finds the existing LiveKit SIP Inbound Trunk and displays its URI."""
    load_dotenv(dotenv_path="backend_python/app/.env") 

    livekit_url = os.getenv("LIVEKIT_URL")
    livekit_api_key = os.getenv("LIVEKIT_API_KEY")
    livekit_api_secret = os.getenv("LIVEKIT_API_SECRET")

    if not all([livekit_url, livekit_api_key, livekit_api_secret]):
        print("Error: LIVEKIT_URL, LIVEKIT_API_KEY, and LIVEKIT_API_SECRET must be set in backend_python/app/.env")
        return

    print(f"Connecting to LiveKit API at: {livekit_url}")
    lkapi = livekit_api.LiveKitAPI(livekit_url, livekit_api_key, livekit_api_secret)

    target_trunk_name = "telnyx-inbound-trunk-mark-i"
    target_trunk_id = "ST_frx58YngzoSi" # The ID from the error message
    found_trunk = None

    print(f"\nSearching for existing trunk ID: {target_trunk_id} or Name: {target_trunk_name}...")

    try:
        list_request = livekit_api.ListSIPInboundTrunkRequest()
        all_trunks = await lkapi.sip.list_sip_inbound_trunk(list_request)
        
        for trunk in all_trunks.items:
            # Prefer matching by ID if available
            if trunk.sip_trunk_id == target_trunk_id:
                found_trunk = trunk
                break
            # Fallback to matching by name
            if trunk.name == target_trunk_name:
                 found_trunk = trunk # Found by name, continue loop in case ID matches later
        
        if found_trunk and hasattr(found_trunk, 'inbound_endpoint') and found_trunk.inbound_endpoint:
             print("\n--- SUCCESS! Found Existing Trunk Info --- ")
             print(f"Trunk ID: {found_trunk.sip_trunk_id}")
             print(f"Name: {found_trunk.name}")
             print(f"Inbound Numbers Configured: {found_trunk.numbers}")
             print(f"Authentication: User={found_trunk.auth_username}")
             
             # THIS IS THE CRUCIAL URI WE NEED FOR TELNYX:
             print(f"\n>>> Inbound SIP Endpoint URI: {found_trunk.inbound_endpoint} <<<")
             print("\nPlease add this URI to your backend_python/app/.env file as LIVEKIT_INBOUND_SIP_URI")
        elif found_trunk:
             print(f"\n--- WARNING: Found trunk {found_trunk.sip_trunk_id} but it lacks a valid inbound_endpoint. ---")
             print(f"Retrieved info: {found_trunk}")
        else:
             print(f"\n--- ERROR: Trunk with ID '{target_trunk_id}' or Name '{target_trunk_name}' not found. ---")
             print("You might need to run the creation part of the script again if it was deleted.")

    except Exception as e:
        print(f"\n--- ERROR During Trunk Listing Operation --- ")
        print(f"Error: {e}")
    finally:
        await lkapi.aclose()
        print("\nLiveKit API connection closed.")

if __name__ == "__main__":
    asyncio.run(find_and_display_trunk()) 