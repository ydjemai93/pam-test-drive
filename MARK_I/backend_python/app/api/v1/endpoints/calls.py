from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from fastapi.responses import PlainTextResponse
import uuid
import datetime
import requests
import asyncio # <-- Import asyncio for sleep

from app.api.v1.dependencies import get_current_user_id
from app.models.call import CallCreate, CallRead
from app.services import xano_service, telnyx_service
from app.core.config import settings

router = APIRouter()

@router.post("/initiate", response_model=CallRead)
async def initiate_call(
    call_in: CallCreate, 
    user_id: int = Depends(get_current_user_id)
):
    """Initiates an outbound call via Telnyx and records it."""
    # user_id is now directly available
    # if not user_id:
    #     raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User ID not found in token")

    # 1. Get Agent/Telnyx Credentials from Xano
    agent_id = call_in.agent_id
    try:
        agent_config = await xano_service.get_agent_by_id_from_xano(agent_id, user_id)
        if not agent_config:
             raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Agent with ID {agent_id} not found or not accessible.")
        
        telnyx_api_key = agent_config.get("telnyx_api_key")
        telnyx_connection_id = agent_config.get("telnyx_connection_id")
        telnyx_from_number = agent_config.get("telnyx_phone_number")
        livekit_sip_uri = agent_config.get("livekit_sip_uri")

        if not all([telnyx_api_key, telnyx_connection_id, telnyx_from_number, livekit_sip_uri]):
            missing = [k for k, v in {"API Key": telnyx_api_key, "Connection ID": telnyx_connection_id, "From Number": telnyx_from_number, "LiveKit SIP URI": livekit_sip_uri}.items() if not v]
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Agent {agent_id} is missing required Telnyx/LiveKit configuration: {', '.join(missing)}")

    except HTTPException as http_exc:
        raise http_exc # Re-raise exceptions from xano_service or validation
    except Exception as e:
        print(f"Error fetching agent config for agent {agent_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve agent configuration")

    # 2. Define Webhook URL
    # IMPORTANT: This URL must be publicly accessible
    # TODO: Get base URL from settings or environment
    base_url = "https://pam-test-drive-3hm7.onrender.com" # Correct Render URL
    telnyx_webhook_url = f"{base_url}/api/v1/calls/webhooks/telnyx/call_control"
    print(f"Using Telnyx webhook URL: {telnyx_webhook_url}")

    # 3. Initiate Call via Telnyx Service
    try:
        call_control_id, call_session_id = await telnyx_service.initiate_telnyx_call(
            api_key=telnyx_api_key,
            from_number=telnyx_from_number,
            to_number=call_in.to_phone_number,
            connection_id=telnyx_connection_id,
            webhook_url=telnyx_webhook_url
        )
        if not call_control_id:
            # Error already logged in service, raise generic error here
             raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Failed to initiate call via Telnyx.")
             
    except HTTPException as http_exc:
        raise http_exc # Propagate errors from telnyx_service
    except Exception as e:
         print(f"Unexpected error during Telnyx call initiation: {e}")
         raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Server error during call initiation.")

    # 4. Create Call Record in Xano
    call_record_payload = {
        "agent_id": agent_id,
        "user_id": user_id,
        "telnyx_call_control_id": call_control_id,
        "telnyx_call_session_id": call_session_id, # Include if available/needed
        "to_phone_number": call_in.to_phone_number,
        "from_phone_number": telnyx_from_number, # Store the number used
        "status": "initiating", # Initial status
        "initiated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "livekit_sip_uri": livekit_sip_uri # Store the target SIP URI for later use in webhook
    }
    
    try:
        created_call = await xano_service.create_call_record_in_xano(call_record_payload)
        print(f"Created call record in Xano: {created_call.get('id')}")
        
        # Map Xano response to Pydantic CallRead model
        # Ensure CallRead model matches the fields returned by Xano
        return CallRead(**created_call) 
        
    except HTTPException as http_exc:
        # If call initiated but DB record failed, we have an orphaned call!
        # Log this critical error. Maybe attempt cleanup?
        print(f"CRITICAL: Telnyx call {call_control_id} initiated but failed to create record in Xano: {http_exc.detail}")
        # Decide on response: Return error, or return success but log inconsistency?
        # For now, let's return an error, as the call cannot be properly tracked/bridged.
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Call initiated but failed to record in database.")
    except Exception as e:
        print(f"CRITICAL: Telnyx call {call_control_id} initiated but failed to create record in Xano due to unexpected error: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Call initiated but failed to record in database.")

@router.post("/webhooks/telnyx/call_control")
async def handle_telnyx_webhook(request: Request):
    """Receives call control events from Telnyx."""
    try:
        payload = await request.json()
    except Exception as e:
        print(f"Error decoding Telnyx webhook JSON: {e}")
        # Return 400 Bad Request if JSON is invalid
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON payload")

    event_data = payload.get("data", {})
    event_type = event_data.get("event_type")
    call_control_id = event_data.get("payload", {}).get("call_control_id")

    print(f"Received Telnyx Webhook: Event Type = {event_type}, Call Control ID = {call_control_id}")

    if not call_control_id:
        print("WARN: Telnyx webhook received without call_control_id.")
        return Response(status_code=status.HTTP_200_OK) # Acknowledge, but do nothing

    # Handle 'call.answered' event
    if event_type == "call.answered":
        print(f"Call answered event for {call_control_id}")
        
        call_record = None
        agent_config = None
        livekit_sip_uri = None
        telnyx_api_key = None
        max_retries = 3
        retry_delay_seconds = 1

        for attempt in range(max_retries):
            print(f"Attempt {attempt + 1}/{max_retries} to fetch call record for {call_control_id}...")
            try:
                get_url = "https://x8ki-letl-twmt.n7.xano.io/api:BylZxBJT/calls" # FIXME: Use settings
                headers = xano_service._get_xano_backend_headers() 
                params = {"telnyx_call_control_id_filter": call_control_id} # ADJUST PARAM NAME if needed
                
                get_response = requests.get(get_url, headers=headers, params=params)
                get_response.raise_for_status()
                results = get_response.json()
                
                if results and len(results) == 1:
                    call_record = results[0]
                    print(f"Successfully fetched call record on attempt {attempt + 1}")
                    break # Found the record, exit retry loop
                else:
                    print(f"Call record not found or not unique on attempt {attempt + 1}. Results: {len(results)}")

            except Exception as e:
                print(f"Error fetching call record on attempt {attempt + 1}: {e}")
            
            # Wait before retrying if not the last attempt
            if attempt < max_retries - 1:
                print(f"Waiting {retry_delay_seconds}s before next attempt...")
                await asyncio.sleep(retry_delay_seconds)
            else:
                 print(f"Error: Could not find unique call record in Xano for call_control_id {call_control_id} after {max_retries} attempts.")
                 return Response(status_code=status.HTTP_200_OK) # Acknowledge Telnyx, but log final error

        # --- Proceed only if call_record was found --- 
        if call_record:
            try: 
                agent_id = call_record.get('agent_id')
                livekit_sip_uri = call_record.get('livekit_sip_uri')
                user_id = call_record.get('user_id')
                
                if not all([agent_id, livekit_sip_uri, user_id]):
                     print(f"Error: Missing agent_id, livekit_sip_uri, or user_id in fetched call record for {call_control_id}")
                     return Response(status_code=status.HTTP_200_OK)
                
                agent_config = await xano_service.get_agent_by_id_from_xano(agent_id, user_id)
                if not agent_config:
                    print(f"Error: Could not find agent config for agent {agent_id} associated with call {call_control_id}")
                    return Response(status_code=status.HTTP_200_OK)
                    
                telnyx_api_key = agent_config.get("telnyx_api_key")
                if not telnyx_api_key:
                     print(f"Error: Missing Telnyx API Key for agent {agent_id} on call {call_control_id}")
                     return Response(status_code=status.HTTP_200_OK)

                # Now, Bridge the call!
                print(f"Attempting to bridge call {call_control_id} to {livekit_sip_uri}")
                bridge_success = await telnyx_service.bridge_telnyx_call(
                    api_key=telnyx_api_key,
                    call_control_id=call_control_id,
                    livekit_sip_uri=livekit_sip_uri
                )
                
                if bridge_success:
                    print(f"Bridge command successful for {call_control_id}. Updating status.")
                    # Update call status in Xano to 'bridged' or 'answered'
                    await xano_service.update_call_record_in_xano(
                        telnyx_call_control_id=call_control_id,
                        update_data={"status": "answered"} # Or 'bridged'
                    )
                else:
                     print(f"Error: Bridge command failed for {call_control_id}. Call likely dropped.")
                     # Update call status in Xano to 'failed' or similar
                     await xano_service.update_call_record_in_xano(
                        telnyx_call_control_id=call_control_id,
                        update_data={"status": "failed", "ended_reason": "bridge_failed"}
                     )
            except Exception as e:
                # Catch-all for processing after fetch
                print(f"Error processing Telnyx 'call.answered' webhook after fetching record for {call_control_id}: {e}")

    # Handle other events (optional)
    elif event_type == "call.hangup":
        print(f"Call hangup event for {call_control_id}")
        # Update call status to 'completed' or based on hangup cause
        hangup_cause = event_data.get("payload", {}).get("hangup_cause")
        sip_hangup_cause = event_data.get("payload", {}).get("sip_hangup_cause")
        try:
            await xano_service.update_call_record_in_xano(
                telnyx_call_control_id=call_control_id,
                update_data={
                    "status": "completed", 
                    "ended_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "ended_reason": hangup_cause,
                    # Add sip_hangup_cause if relevant field exists
                }
            )
        except Exception as e:
             print(f"Error updating Xano record on hangup for {call_control_id}: {e}")

    # Always acknowledge Telnyx
    # It's crucial to respond quickly to webhooks, even if processing fails
    return Response(status_code=status.HTTP_200_OK) 