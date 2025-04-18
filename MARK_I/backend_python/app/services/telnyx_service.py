import requests
import json
from fastapi import HTTPException, status

from app.core.config import settings # If base URL or other Telnyx settings are stored there

# Telnyx API V2 Base URL
TELNYX_API_V2_BASE = "https://api.telnyx.com/v2"

async def initiate_telnyx_call(
    api_key: str, 
    from_number: str, 
    to_number: str, 
    connection_id: str, 
    webhook_url: str
) -> tuple[str | None, str | None]:
    """Initiates an outbound call using Telnyx API V2.

    Args:
        api_key: The Telnyx V2 API key.
        from_number: The Telnyx phone number to call from (E.164 format).
        to_number: The destination phone number (E.164 format).
        connection_id: The Telnyx Connection ID (SIP Trunk) to use for the outbound call.
        webhook_url: The URL for Telnyx to send call control events.

    Returns:
        A tuple containing (call_control_id, call_session_id) or (None, None) on failure.
    """
    call_url = f"{TELNYX_API_V2_BASE}/calls"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    payload = {
        "connection_id": connection_id,
        "to": to_number,
        "from": from_number,
        "webhook_url": webhook_url,
        "webhook_url_method": "POST",
        # Add other options if needed, e.g., answering_machine_detection
    }
    print(f"Initiating Telnyx call: POST {call_url} Payload: {json.dumps(payload)}")

    try:
        response = requests.post(call_url, headers=headers, json=payload)
        
        # Telnyx might return 202 Accepted on success
        if response.status_code not in [200, 201, 202]: 
             print(f"Telnyx API Error (Initiate Call - Status {response.status_code}): {response.text}")
             response.raise_for_status() # Let requests library raise standard HTTP error

        response_data = response.json().get("data", {})
        call_control_id = response_data.get("call_control_id")
        call_session_id = response_data.get("call_session_id")
        
        if not call_control_id:
             print(f"Error: Telnyx response missing call_control_id. Response: {response.text}")
             return None, None
             
        print(f"Telnyx call initiated. call_control_id: {call_control_id}, call_session_id: {call_session_id}")
        return call_control_id, call_session_id

    except requests.exceptions.RequestException as e:
        print(f"Telnyx API RequestException (Initiate Call): {e}")
        # Handle specific errors if needed, e.g., 401 Unauthorized, 422 Unprocessable
        error_detail = f"Telnyx API error during call initiation"
        if e.response is not None:
             error_detail += f": {e.response.text}"
             raise HTTPException(status_code=e.response.status_code, detail=error_detail)
        else:
             raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=error_detail)
    except Exception as e:
        print(f"Unexpected error initiating Telnyx call: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected error initiating call with Telnyx")


async def bridge_telnyx_call(
    api_key: str, 
    call_control_id: str, 
    livekit_sip_uri: str
) -> bool:
    """Sends the bridge command to Telnyx for a specific call.

    Args:
        api_key: The Telnyx V2 API key.
        call_control_id: The call_control_id of the call to bridge.
        livekit_sip_uri: The SIP URI of the LiveKit inbound trunk.

    Returns:
        True if the bridge command was accepted by Telnyx, False otherwise.
    """
    bridge_url = f"{TELNYX_API_V2_BASE}/calls/{call_control_id}/actions/bridge"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    # IMPORTANT: Ensure the SIP URI format is exactly what LiveKit expects.
    # We might need to add ;transport=tls or port :5061 based on previous findings.
    # Let's start simple and assume Telnyx handles TLS based on trunk config.
    # We also need to consider authentication if LiveKit requires it (user/pass/headers).
    
    # Check LiveKit's authentication needs. If it requires credentials or specific headers,
    # they need to be added here in the `sip:` URI or potentially via `custom_headers`.
    # Example URI if user/pass needed: f"sip:user:pass@{livekit_sip_uri_domain}"
    # Example if transport needed: f"sip:{livekit_sip_uri_domain};transport=tls"
    
    target_sip_uri_to_send = livekit_sip_uri # Start simple
    
    # Add potential ;transport=tls and port :5061 based on our Twilio tests
    # target_sip_uri_to_send = f"{livekit_sip_uri}:5061;transport=tls" 
    
    payload = {
        "target": target_sip_uri_to_send,
        # "from": "Optional: Override caller ID for the SIP leg",
        # "custom_headers": [ # Example if LiveKit needs specific headers
        #     {"name": "X-LiveKit-Trunk-ID", "value": "your_lk_trunk_id"}
        # ],
        # "webhook_url": "Optional: URL for events specifically about the bridge attempt?"
    }
    print(f"Sending Telnyx Bridge command: POST {bridge_url} Payload: {json.dumps(payload)}")

    try:
        response = requests.post(bridge_url, headers=headers, json=payload)

        # Telnyx often returns 200 OK for successful action commands
        if response.status_code == 200:
             print(f"Telnyx Bridge command accepted for call_control_id: {call_control_id}")
             return True
        else:
             print(f"Telnyx API Error (Bridge Call - Status {response.status_code}): {response.text}")
             response.raise_for_status() 
             return False # Should not be reached if raise_for_status works

    except requests.exceptions.RequestException as e:
        print(f"Telnyx API RequestException (Bridge Call): {e}")
        error_detail = f"Telnyx API error during call bridge"
        if e.response is not None:
             error_detail += f": {e.response.text}"
        # Don't raise HTTPException here directly, let the caller handle failure
        return False 
    except Exception as e:
        print(f"Unexpected error bridging Telnyx call: {e}")
        return False 