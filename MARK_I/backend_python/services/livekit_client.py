import os
import httpx
import logging
import json
from typing import List, Dict, Any, Optional
from livekit import api # Revert to using livekit.api for AccessToken and grants

# Try to import SIP service classes, but make it conditional for different LiveKit versions
try:
    from livekit.api.sip_service import SIPOutboundTrunkUpdate, UpdateSIPOutboundTrunkRequest
    LIVEKIT_SIP_UPDATE_AVAILABLE = True
except ImportError:
    # Fallback for older LiveKit versions that don't have these classes
    SIPOutboundTrunkUpdate = None
    UpdateSIPOutboundTrunkRequest = None
    LIVEKIT_SIP_UPDATE_AVAILABLE = False

# Import SIP inbound and dispatch rule classes for bidirectional support
try:
    from livekit.protocol.sip import (
        CreateSIPInboundTrunkRequest,
        CreateSIPDispatchRuleRequest,
        ListSIPInboundTrunkRequest,
        ListSIPDispatchRuleRequest,
        DeleteSIPDispatchRuleRequest,
        DeleteSIPTrunkRequest
    )
    LIVEKIT_SIP_INBOUND_AVAILABLE = True
except ImportError:
    # Fallback for older LiveKit versions
    LIVEKIT_SIP_INBOUND_AVAILABLE = False

# Ensure google.protobuf.json_format is available if api.MessageToJSON isn't found,
# but prioritize api.MessageToJSON based on user's previous comments.
# from google.protobuf.json_format import MessageToJSON as ProtoMessageToJSON # Fallback

# Configure logging
logger = logging.getLogger(__name__)
# Ensure logging is configured in your application's entry point or main module
# For example: logging.basicConfig(level=logging.INFO)

# Check if bidirectional calling is available
if not LIVEKIT_SIP_INBOUND_AVAILABLE:
    logger.warning("LiveKit SIP inbound classes not available. Bidirectional calling will not work. Please update LiveKit SDK.")

# LiveKit Server API details - typically loaded from environment variables
LIVEKIT_API_URL = os.getenv("LIVEKIT_URL") # e.g., "wss://project.livekit.cloud" or "http://localhost:7880"
LIVEKIT_API_KEY = os.getenv("LIVEKIT_API_KEY") # Starting with "APIK..."
LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET")

# Custom Exceptions
class LiveKitServiceError(Exception):
    """Base exception for LiveKit service errors."""
    def __init__(self, message: str, status_code: Optional[int] = None, details: Optional[str] = None):
        super().__init__(message)
        self.status_code = status_code
        self.details = details

class LiveKitConfigurationError(LiveKitServiceError):
    """Exception for configuration issues (e.g., missing API keys)."""
    pass

class LiveKitTrunkNotFoundError(LiveKitServiceError):
    """Exception when a specific SIP trunk is not found."""
    pass


# Note: LiveKit Server API often uses Twirp (Protobuf RPC framework over HTTP).
# Direct HTTP calls require specific headers and request/response structures (usually JSON).
# For more complex interactions or if using many LiveKit APIs, consider the official livekit-server-sdk (Python).
# The following _make_livekit_request is a simplified helper for direct JSON/HTTP POST requests,
# which is common for SIP management if not using the full SDK's RPC stubs.

async def _make_livekit_request(
    service: str, # e.g., "SIPService"
    method: str,  # e.g., "CreateSIPTrunk"
    payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Helper function to make requests to the LiveKit Server API (Twirp-style JSON over HTTP).
    This is a simplified version. The official SDK handles token generation and RPC calls.
    For direct HTTP, you would typically generate a JWT (access token) using API Key & Secret.
    """
    if not LIVEKIT_API_URL or not LIVEKIT_API_KEY or not LIVEKIT_API_SECRET:
        logger.error("LiveKit API URL, Key, or Secret is not configured.")
        raise LiveKitConfigurationError("LiveKit API credentials are not fully configured.")

    # Token generation (simplified example - SDK handles this robustly)
    # In a real scenario, you'd use the livekit.api.AccessToken or similar to create a grant
    # For direct API calls (not through SDK client), you might need a specific service token.
    # The /twirp/livekit.SIPService/MethodName endpoint usually expects this.
    # For simplicity, we'll assume a method that uses API Key/Secret directly or a pre-shared token if applicable.
    # However, most LiveKit service-to-service APIs expect a JWT.
    
    # Generate JWT for authentication
    admin_identity = "pam-backend-service"

    # Create the VideoGrant message
    video_grant_message = api.VideoGrants(room_admin=True)

    # Use the AccessToken class from livekit.api
    # This assumes api.AccessToken is the utility class with .to_jwt()
    access_token_generator = api.AccessToken(
        LIVEKIT_API_KEY, # Assuming positional arguments if api_key= not accepted
        LIVEKIT_API_SECRET, # Assuming positional arguments if api_secret= not accepted
    )
    # Use builder pattern
    access_token_generator = access_token_generator.with_identity(admin_identity)
    access_token_generator = access_token_generator.with_grants(video_grant_message) # Pass VideoGrants directly

    auth_token = access_token_generator.to_jwt()
    
    headers = {
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    logger.debug(f"LiveKit API Request: POST {LIVEKIT_API_URL.rstrip('/')}/twirp/livekit.{service}/{method} - Payload: {json.dumps(payload)}")

    async with httpx.AsyncClient(timeout=20.0) as client:
        try:
            # Twirp requests are typically POST
            response = await client.post(f"{LIVEKIT_API_URL.rstrip('/')}/twirp/livekit.{service}/{method}", json=payload if payload else {}, headers=headers)
            logger.debug(f"LiveKit API Response: Status {response.status_code} - Text: {response.text[:500]}")
            
            # Check for non-JSON "OK" response before attempting to parse
            # For create/update/delete operations, a plain "OK" is suspicious.
            is_mutating_operation = any(kw in method for kw in ["Create", "Update", "Delete", "Set", "Add", "Remove", "Patch"])
            if response.status_code == 200 and response.text.strip().upper() == "OK":
                if is_mutating_operation:
                    logger.warning(f"LiveKit API returned HTTP 200 with plain 'OK' for a mutating method {method} on {service}. Returning a special status.")
                    return {
                        "status": "success_plain_ok",
                        "message": f"LiveKit method {method} on {service} returned plain 'OK'. Assuming success but no data returned.",
                        "service": service,
                        "method": method
                    }
                else: # For non-mutating methods (e.g., Get, List), "OK" might be an empty success.
                    logger.info(f"LiveKit API returned HTTP 200 with 'OK' body for non-mutating method {method} on {service}. Treating as success with no data.")
                    return {"status": "success", "message": "Operation successful, empty response from server", "data": {}}

            response.raise_for_status() # For other 2xx that might have JSON, or any non-2xx
            return response.json()
        except httpx.HTTPStatusError as e:
            error_message = f"LiveKit API HTTP error: {e.response.status_code}"
            details_text = e.response.text
            try:
                error_json = e.response.json()
                # Twirp errors often have a specific JSON structure
                twirp_code = error_json.get("code")
                twirp_msg = error_json.get("msg")
                if twirp_code and twirp_msg:
                    error_message += f" - Twirp Code: {twirp_code} - Message: {twirp_msg}"
                    details_text = f"Twirp Error: {twirp_code} - {twirp_msg}. Full: {e.response.text[:500]}"
                else:
                    error_message += f" - Response: {e.response.text[:200]}"
            except json.JSONDecodeError:
                error_message += f" - Non-JSON response: {e.response.text[:200]}"
            
            logger.error(error_message, exc_info=True)
            if e.response.status_code == 404: # Or specific Twirp code for "not_found"
                raise LiveKitTrunkNotFoundError(f"LiveKit resource not found at {LIVEKIT_API_URL.rstrip('/')}/twirp/livekit.{service}/{method}. Detail: {error_message}", status_code=404, details=details_text)
            raise LiveKitServiceError(error_message, status_code=e.response.status_code, details=details_text)
        except httpx.RequestError as e:
            logger.error(f"LiveKit request error for POST {LIVEKIT_API_URL.rstrip('/')}/twirp/livekit.{service}/{method}: {e}", exc_info=True)
            raise LiveKitServiceError(f"LiveKit request error: {str(e)}", status_code=503)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to decode JSON response from LiveKit for POST {LIVEKIT_API_URL.rstrip('/')}/twirp/livekit.{service}/{method}: {e.doc[:200]}", exc_info=True)
            raise LiveKitServiceError(f"Invalid JSON response from LiveKit: {str(e)}", status_code=502)


async def create_sip_trunk(
    sip_trunk_id: Optional[str] = None, # Optional: LiveKit can generate one
    name: Optional[str] = None,
    outbound_addresses: Optional[List[str]] = None, # Telnyx SIP domain: sip.telnyx.com
    outbound_number: Optional[str] = None, # E.164 number for Caller ID
    inbound_numbers_e164: Optional[List[str]] = None, # Numbers routed to this trunk
    inbound_sip_username: Optional[str] = None, # For Telnyx, usually your SIP Connection username
    inbound_sip_password: Optional[str] = None, # For Telnyx, usually your SIP Connection password
    outbound_sip_username: Optional[str] = None,
    outbound_sip_password: Optional[str] = None,
    # metadata can be added if needed
) -> Dict[str, Any]:
    """
    Creates a SIP Trunk in LiveKit using the SDK.
    LiveKit will generate sip_trunk_id if not provided.
    """
    if not LIVEKIT_API_URL or not LIVEKIT_API_KEY or not LIVEKIT_API_SECRET:
        logger.error("LiveKit API URL, Key, or Secret is not configured.")
        raise LiveKitConfigurationError("LiveKit API credentials are not fully configured.")

    lk_api_client = None
    try:
        lk_api_client = api.LiveKitAPI(LIVEKIT_API_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET)

        # Prepare arguments for SIPOutboundTrunkInfo
        trunk_info_args: Dict[str, Any] = {}

        if sip_trunk_id: trunk_info_args["sip_outbound_trunk_id"] = sip_trunk_id
        if name: trunk_info_args["name"] = name
        
        # Credentials LiveKit uses to authenticate TO the provider (e.g., Telnyx)
        if outbound_sip_username: trunk_info_args["auth_username"] = outbound_sip_username
        if outbound_sip_password: trunk_info_args["auth_password"] = outbound_sip_password
        
        if outbound_addresses and len(outbound_addresses) > 0 and outbound_addresses[0]:
            trunk_info_args["address"] = outbound_addresses[0]
        else:
            # 'address' is a required field for SIPOutboundTrunkInfo.
            # If outbound_addresses is empty or None, this would cause an error.
            # The calling code in telnyx_routes.py provides ["sip.telnyx.com"], so this should be fine.
            logger.warning("outbound_addresses list was not provided or is empty; 'address' field for SIPOutboundTrunkInfo might be missing.")


        if inbound_numbers_e164: # List of E.164 numbers associated with this trunk
            trunk_info_args["numbers"] = inbound_numbers_e164
        
        logger.info(f"Constructing SIPOutboundTrunkInfo with args: {trunk_info_args}")
        # Create the SIPOutboundTrunkInfo object
        trunk_info_obj = api.SIPOutboundTrunkInfo(**trunk_info_args)

        # Create the CreateSIPOutboundTrunkRequest object
        create_request_obj = api.CreateSIPOutboundTrunkRequest(trunk=trunk_info_obj)
        
        logger.info(f"Calling create_sip_outbound_trunk with request: {create_request_obj}")
        response_proto = await lk_api_client.sip.create_sip_outbound_trunk(create_request_obj)
        
        response_json_str = ""
        # Check if api.MessageToJSON exists (from user's prior commented code)
        if hasattr(api, 'MessageToJSON') and callable(getattr(api, 'MessageToJSON')):
            response_json_str = api.MessageToJSON(response_proto)
        else:
            # Fallback to standard google.protobuf.json_format if LiveKit's own utility isn't found
            from google.protobuf.json_format import MessageToJson as ProtoMessageToJson
            logger.warning("livekit.api.MessageToJSON not found or not callable, using google.protobuf.json_format.MessageToJson.")
            response_json_str = ProtoMessageToJson(response_proto)
            
        response_dict = json.loads(response_json_str)
        
        logger.info(f"LiveKit SIP Trunk created successfully via SDK: {response_dict}")
        
        # The SDK returns with camelCase field names, but our code expects snake_case
        # Convert the sipTrunkId or sipOutboundTrunkId to the expected format
        if "sipOutboundTrunkId" in response_dict:
            response_dict["sipTrunkId"] = response_dict["sipOutboundTrunkId"]
        
        # Ensure the response has the expected fields for compatibility
        if "sipTrunkId" not in response_dict and response_dict.get("sipOutboundTrunkId"):
            response_dict["sipTrunkId"] = response_dict["sipOutboundTrunkId"]
            
        return response_dict

    except api.TwirpError as e:
        logger.error(f"LiveKit SDK TwirpError creating SIP Trunk: Code: {e.code}, Msg: {e.message}, Meta: {e.metadata}")
        details = f"Twirp Error: Code={e.code}, Message={e.message}, Metadata={e.metadata}"
        if e.code == "not_found" or e.status == 404 : # Map common not found scenarios
             raise LiveKitTrunkNotFoundError(f"LiveKit resource-related error: {e.message}", status_code=e.status, details=details)
        raise LiveKitServiceError(f"LiveKit SDK error: {e.message}", status_code=e.status, details=details)
    except Exception as e:
        logger.error(f"Unexpected error creating LiveKit SIP Trunk via SDK: {e}", exc_info=True)
        raise LiveKitServiceError(f"Unexpected SDK error while creating SIP trunk: {str(e)}")
    finally:
        if lk_api_client:
            await lk_api_client.aclose() # Ensure the client session is closed

async def update_sip_trunk_credentials(
    sip_trunk_id: str,
    new_auth_username: str,
    new_auth_password: str,
    # These are needed to reconstruct the SIPOutboundTrunkInfo for the update request
    current_name: str,
    current_outbound_address: str, 
    current_inbound_numbers: List[str]
) -> Dict[str, Any]:
    """
    Updates the authentication credentials (username and password) for a specific SIP Trunk in LiveKit.
    Other trunk details like name, address, and numbers are passed to ensure the update request is complete.
    """
    if not LIVEKIT_API_URL or not LIVEKIT_API_KEY or not LIVEKIT_API_SECRET:
        logger.error("LiveKit API URL, Key, or Secret is not configured for update operation.")
        raise LiveKitConfigurationError("LiveKit API credentials are not fully configured.")

    lk_api_client = None
    try:
        lk_api_client = api.LiveKitAPI(LIVEKIT_API_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET)

        # Prepare arguments specifically for UpdateSIPOutboundTrunkRequest
        # It likely only accepts the trunk ID and the fields to be updated.
        # As per docs (update_sip_outbound_trunk_fields), we need to create an SIPOutboundTrunkUpdate object.
        # update_payload = api.SIPOutboundTrunkUpdate(
        #     auth_username=new_auth_username,
        #     auth_password=new_auth_password
        # )
        
        # The following fields from current_trunk_info are not included here anymore
        # as they caused "has no field" errors, suggesting they are not direct updatable fields
        # or not needed if only credentials are changing:
        # "name": current_name,
        # "address": current_outbound_address, 
        # "numbers": current_inbound_numbers, 
        
        # logger.info(f"Constructing UpdateSIPOutboundTrunkRequest for trunk ID {sip_trunk_id} with update payload containing new credentials.")
        # update_request_obj = api.UpdateSIPOutboundTrunkRequest(
        #     sip_trunk_id=sip_trunk_id,
        #     update=update_payload
        # )
        
        # logger.info(f"Calling update_sip_outbound_trunk for trunk ID {sip_trunk_id} with request: {update_request_obj}")
        # response_proto = await lk_api_client.sip.update_sip_outbound_trunk(update_request_obj)

        logger.info(f"Calling update_sip_outbound_trunk_fields for trunk ID {sip_trunk_id} with new credentials.")
        response_proto = await lk_api_client.sip.update_sip_outbound_trunk_fields(
            trunk_id=sip_trunk_id,
            auth_username=new_auth_username,
            auth_password=new_auth_password
        )
        
        response_json_str = ""
        if hasattr(api, 'MessageToJSON') and callable(getattr(api, 'MessageToJSON')):
            response_json_str = api.MessageToJSON(response_proto)
        else:
            from google.protobuf.json_format import MessageToJson as ProtoMessageToJson
            logger.warning("livekit.api.MessageToJSON not found or not callable, using google.protobuf.json_format.MessageToJson for update response.")
            response_json_str = ProtoMessageToJson(response_proto)
            
        response_dict = json.loads(response_json_str)
        
        logger.info(f"LiveKit SIP Trunk {sip_trunk_id} credentials updated successfully via SDK: {response_dict}")
        return response_dict

    except api.TwirpError as e:
        logger.error(f"LiveKit SDK TwirpError updating SIP Trunk {sip_trunk_id}: Code: {e.code}, Msg: {e.message}, Meta: {e.metadata}")
        details = f"Twirp Error: Code={e.code}, Message={e.message}, Metadata={e.metadata}"
        if e.code == "not_found" or e.status == 404:
             raise LiveKitTrunkNotFoundError(f"LiveKit SIP Trunk {sip_trunk_id} not found for update. Detail: {e.message}", status_code=e.status, details=details)
        raise LiveKitServiceError(f"LiveKit SDK error updating SIP Trunk {sip_trunk_id}: {e.message}", status_code=e.status, details=details)
    except Exception as e:
        logger.error(f"Unexpected error updating LiveKit SIP Trunk {sip_trunk_id} via SDK: {e}", exc_info=True)
        raise LiveKitServiceError(f"Unexpected SDK error while updating SIP trunk credentials: {str(e)}")
    finally:
        if lk_api_client:
            await lk_api_client.aclose()

async def update_sip_trunk_credentials_simple(
    trunk_id: str,
    username: str,
    password: str
) -> Dict[str, Any]:
    """
    Simplified version of update_sip_trunk_credentials that only requires the essential parameters.
    This is used by the sync_livekit_trunk_credentials endpoint in telnyx_routes.py.
    """
    if not LIVEKIT_API_URL or not LIVEKIT_API_KEY or not LIVEKIT_API_SECRET:
        logger.error("LiveKit API URL, Key, or Secret is not configured for update operation.")
        raise LiveKitConfigurationError("LiveKit API credentials are not fully configured.")

    if not LIVEKIT_SIP_UPDATE_AVAILABLE:
        logger.error(f"LiveKit SIP update classes not available in this SDK version. Cannot update trunk {trunk_id} credentials.")
        raise LiveKitServiceError("LiveKit SDK version does not support SIP trunk credential updates via UpdateSIPOutboundTrunkRequest")

    lk_api_client = None
    try:
        lk_api_client = api.LiveKitAPI(LIVEKIT_API_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET)

        logger.info(f"Attempting to update SIP outbound trunk {trunk_id} credentials using UpdateSIPOutboundTrunkRequest.")
        
        # Create the SIPOutboundTrunkUpdate object with the new credentials
        trunk_update = SIPOutboundTrunkUpdate(
            auth_username=username,
            auth_password=password
        )
        
        # Create the UpdateSIPOutboundTrunkRequest object
        update_request = UpdateSIPOutboundTrunkRequest(
            sip_trunk_id=trunk_id,
            update=trunk_update
        )
        
        logger.info(f"Calling update_sip_outbound_trunk for trunk ID {trunk_id} with new credentials.")
        response_proto = await lk_api_client.sip.update_sip_outbound_trunk(update_request)
        
        response_json_str = ""
        if hasattr(api, 'MessageToJSON') and callable(getattr(api, 'MessageToJSON')):
            response_json_str = api.MessageToJSON(response_proto)
        else:
            from google.protobuf.json_format import MessageToJson as ProtoMessageToJson
            logger.warning("livekit.api.MessageToJSON not found or not callable, using google.protobuf.json_format.MessageToJson for update response.")
            response_json_str = ProtoMessageToJson(response_proto)
            
        response_dict = json.loads(response_json_str)
        
        logger.info(f"LiveKit SIP Trunk {trunk_id} credentials updated successfully via SDK: {response_dict}")
        return response_dict

    except api.TwirpError as e:
        logger.error(f"LiveKit SDK TwirpError updating SIP Trunk {trunk_id}: Code: {e.code}, Msg: {e.message}, Meta: {e.metadata}")
        details = f"Twirp Error: Code={e.code}, Message={e.message}, Metadata={e.metadata}"
        if e.code == "not_found" or e.status == 404:
             raise LiveKitTrunkNotFoundError(f"LiveKit SIP Trunk {trunk_id} not found for update. Detail: {e.message}", status_code=e.status, details=details)
        raise LiveKitServiceError(f"LiveKit SDK error updating SIP Trunk {trunk_id}: {e.message}", status_code=e.status, details=details)
    except Exception as e:
        logger.error(f"Unexpected error updating LiveKit SIP Trunk {trunk_id} via SDK: {e}", exc_info=True)
        raise LiveKitServiceError(f"Unexpected SDK error while updating SIP trunk credentials: {str(e)}")
    finally:
        if lk_api_client:
            await lk_api_client.aclose()

async def get_sip_trunk(sip_trunk_id: str) -> Optional[Dict[str, Any]]:
    """
    Gets a specific SIP Outbound Trunk from LiveKit by its ID by listing all outbound trunks
    and then filtering for the specified ID.
    """
    if not sip_trunk_id:
        raise ValueError("SIP Trunk ID is required.")

    if not LIVEKIT_API_URL or not LIVEKIT_API_KEY or not LIVEKIT_API_SECRET:
        logger.error("LiveKit API URL, Key, or Secret is not configured for get_sip_trunk.")
        raise LiveKitConfigurationError("LiveKit API credentials are not fully configured.")

    lk_api_client = None
    try:
        lk_api_client = api.LiveKitAPI(LIVEKIT_API_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
        
        logger.info(f"Attempting to find SIP Outbound Trunk ID: {sip_trunk_id} by listing all outbound trunks.")
        
        list_request_obj = api.ListSIPOutboundTrunkRequest()
        list_response_proto = await lk_api_client.sip.list_sip_outbound_trunk(list_request_obj)
        
        found_trunk_proto = None
        
        # The ListSIPOutboundTrunkResponse usually has a 'trunks' or 'items' field.
        # Based on typical LiveKit SDK patterns, 'trunks' is likely for typed responses.
        trunks_list = []
        if hasattr(list_response_proto, 'trunks'):
            trunks_list = list_response_proto.trunks
            logger.debug(f"Found 'trunks' attribute in ListSIPOutboundTrunkResponse, count: {len(trunks_list)}")
        elif hasattr(list_response_proto, 'items'): # Fallback for more generic list responses
            trunks_list = list_response_proto.items
            logger.debug(f"Found 'items' attribute in ListSIPOutboundTrunkResponse, count: {len(trunks_list)}")
        else:
            logger.warning("Could not find 'trunks' or 'items' attribute in ListSIPOutboundTrunkResponse. Unable to find specific trunk.")
            # If the response itself is the list (less common for protobufs but possible if SDK unwraps)
            if isinstance(list_response_proto, list):
                 logger.debug("ListSIPOutboundTrunkResponse appears to be a direct list.")
                 trunks_list = list_response_proto
            else:
                # Log the type and dir of the response to understand its structure if common fields are missing.
                logger.warning(f"ListSIPOutboundTrunkResponse type: {type(list_response_proto)}. Attributes: {dir(list_response_proto)}")


        for trunk_proto_item in trunks_list:
            # SIPOutboundTrunkInfo has a 'sip_trunk_id' field.
            if hasattr(trunk_proto_item, 'sip_trunk_id') and trunk_proto_item.sip_trunk_id == sip_trunk_id:
                found_trunk_proto = trunk_proto_item
                logger.debug(f"Matching trunk found: {trunk_proto_item.sip_trunk_id}")
                break
            elif hasattr(trunk_proto_item, 'sip_outbound_trunk_id') and trunk_proto_item.sip_outbound_trunk_id == sip_trunk_id: # Check alternative field name
                found_trunk_proto = trunk_proto_item
                logger.debug(f"Matching trunk found with sip_outbound_trunk_id: {trunk_proto_item.sip_outbound_trunk_id}")
                break
        
        if not found_trunk_proto:
            logger.warning(f"LiveKit SIP Outbound Trunk ID {sip_trunk_id} not found after listing all outbound trunks.")
            return None

        logger.info(f"Successfully found SIP Outbound Trunk {sip_trunk_id} by listing and filtering.")
        
        response_json_str = ""
        if hasattr(api, 'MessageToJSON') and callable(getattr(api, 'MessageToJSON')):
            response_json_str = api.MessageToJSON(found_trunk_proto)
        else:
            from google.protobuf.json_format import MessageToJson as ProtoMessageToJson
            logger.warning("livekit.api.MessageToJSON not found or not callable, using google.protobuf.json_format.MessageToJson for found trunk.")
            response_json_str = ProtoMessageToJson(found_trunk_proto)
            
        response_dict = json.loads(response_json_str)
        
        # The JSON field name is often camelCase, e.g., 'sipTrunkId'
        if response_dict and (response_dict.get("sipTrunkId") or response_dict.get("sipOutboundTrunkId")):
            logger.info(f"SIP Outbound Trunk {sip_trunk_id} (listed) details: {response_dict}")
            return response_dict
        else:
            logger.warning(f"Found SIP Outbound Trunk {sip_trunk_id} (listed) but conversion to dict or ID field ('sipTrunkId' or 'sipOutboundTrunkId') is missing. Response: {response_dict}")
            # Return the dict anyway if it exists, the caller might handle it
            return response_dict if response_dict else None

    except api.TwirpError as e:
        logger.error(f"LiveKit SDK TwirpError while listing SIP Outbound Trunks to find {sip_trunk_id}: Code: {e.code}, Msg: {e.message}, Meta: {e.metadata}")
        # This error means the listing itself failed.
        raise LiveKitServiceError(f"LiveKit SDK error listing SIP Outbound Trunks: {e.message}", status_code=e.status, details=f"Twirp Error: Code={e.code}, Message={e.message}, Metadata={e.metadata}")
    except Exception as e:
        logger.error(f"Unexpected error listing/finding LiveKit SIP Outbound Trunk {sip_trunk_id} via SDK: {e}", exc_info=True)
        raise LiveKitServiceError(f"Unexpected SDK error while listing/finding SIP outbound trunk: {str(e)}")
    finally:
        if lk_api_client:
            await lk_api_client.aclose()

async def list_sip_trunks() -> List[Dict[str, Any]]:
    """Lists all SIP Trunks in LiveKit."""
    # SDK: result = await lk_api.sip.list_sip_trunk(api.ListSIPTrunkRequest())
    # items = [json.loads(api.MessageToJSON(item)) for item in result.items]
    # return items
    logger.info("Listing all LiveKit SIP Trunks.")
    try:
        response = await _make_livekit_request(service="SIPService", method="ListSIPTrunk", payload={})
        return response.get("items", []) # ListSIPTrunkResponse has an 'items' field
    except LiveKitServiceError as e:
        logger.error(f"Error listing LiveKit SIP Trunks: {e}")
        raise
        return [] # Return empty list on error

async def delete_sip_trunk(sip_trunk_id: str) -> bool:
    """Deletes a SIP Trunk from LiveKit."""
    # SDK: await lk_api.sip.delete_sip_trunk(api.DeleteSIPTrunkRequest(sip_trunk_id=sip_trunk_id))
    # return True
    if not sip_trunk_id:
        raise ValueError("SIP Trunk ID for deletion is required.")
    payload = {"sip_trunk_id": sip_trunk_id}
    logger.info(f"Deleting LiveKit SIP Trunk ID: {sip_trunk_id}")
    try:
        await _make_livekit_request(service="SIPService", method="DeleteSIPTrunk", payload=payload)
        # DeleteSIPTrunk usually returns an empty response on success (e.g., {} or HTTP 200/204)
        logger.info(f"LiveKit SIP Trunk ID {sip_trunk_id} deleted successfully.")
        return True
    except LiveKitTrunkNotFoundError:
        logger.warning(f"LiveKit SIP Trunk ID {sip_trunk_id} not found for deletion.")
        return True # Idempotency: if not found, it's effectively deleted
    except LiveKitServiceError as e:
        logger.error(f"Error deleting LiveKit SIP Trunk {sip_trunk_id}: {e}")
        # Re-raise to indicate failure
        raise
        return False

# === INBOUND SIP TRUNK FUNCTIONS - FOLLOWING OUTBOUND PATTERNS ===

async def create_inbound_sip_trunk(
    sip_trunk_id: Optional[str] = None,  # Optional: LiveKit can generate one
    name: Optional[str] = None,
    inbound_addresses: Optional[List[str]] = None,  # Telnyx inbound SIP domains
    inbound_numbers_e164: Optional[List[str]] = None,  # Numbers that route TO this trunk
    auth_username: Optional[str] = None,  # Authentication for inbound calls
    auth_password: Optional[str] = None,  # Authentication password
    # metadata can be added if needed
) -> Dict[str, Any]:
    """
    Creates an Inbound SIP Trunk for receiving calls from Telnyx.
    This is the inbound equivalent of create_sip_trunk but specifically for incoming calls.
    
    Key differences from outbound:
    - Uses inbound_addresses instead of outbound_addresses
    - Configures authentication for incoming connections from Telnyx
    - Routes specific numbers TO this trunk rather than FROM
    """
    if not LIVEKIT_API_URL or not LIVEKIT_API_KEY or not LIVEKIT_API_SECRET:
        logger.error("LiveKit API URL, Key, or Secret is not configured for inbound SIP trunk creation.")
        raise LiveKitConfigurationError("LiveKit API credentials are not fully configured.")

    lk_api_client = None
    try:
        lk_api_client = api.LiveKitAPI(LIVEKIT_API_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
        
        # Generate SIP trunk ID if not provided
        if not sip_trunk_id:
            import uuid
            sip_trunk_id = f"inbound-trunk-{uuid.uuid4().hex[:8]}"
        
        # Generate name if not provided
        if not name:
            name = f"Inbound Trunk {sip_trunk_id}"
        
        logger.info(f"Creating Inbound SIP Trunk: {name} (ID: {sip_trunk_id})")
        
        # Create the inbound trunk info object
        inbound_trunk_info = api.SIPInboundTrunkInfo(
            sip_trunk_id=sip_trunk_id,
            name=name,
            metadata=""  # Can be customized as needed
        )
        
        # Add inbound addresses if provided (Telnyx SIP domains)
        if inbound_addresses:
            inbound_trunk_info.inbound_addresses = inbound_addresses
            logger.info(f"Configured inbound addresses: {inbound_addresses}")
        
        # Add allowed numbers if provided
        if inbound_numbers_e164:
            inbound_trunk_info.allowed_numbers = inbound_numbers_e164
            logger.info(f"Configured allowed inbound numbers: {inbound_numbers_e164}")
        
        # Configure authentication if provided
        if auth_username and auth_password:
            inbound_trunk_info.auth_username = auth_username
            inbound_trunk_info.auth_password = auth_password
            logger.info(f"Configured inbound authentication for user: {auth_username}")
        
        # Create the request
        create_request = api.CreateSIPInboundTrunkRequest(
            trunk=inbound_trunk_info
        )
        
        # Make the request
        response_proto = await lk_api_client.sip.create_sip_inbound_trunk(create_request)
        
        # Convert response to dict
        response_json_str = ""
        if hasattr(api, 'MessageToJSON') and callable(getattr(api, 'MessageToJSON')):
            response_json_str = api.MessageToJSON(response_proto)
        else:
            from google.protobuf.json_format import MessageToJson as ProtoMessageToJson
            logger.warning("livekit.api.MessageToJSON not found, using google.protobuf.json_format.MessageToJson for inbound trunk.")
            response_json_str = ProtoMessageToJson(response_proto)
            
        response_dict = json.loads(response_json_str)
        
        logger.info(f"Successfully created Inbound SIP Trunk: {response_dict}")
        return response_dict

    except api.TwirpError as e:
        logger.error(f"LiveKit SDK TwirpError creating Inbound SIP Trunk: Code: {e.code}, Msg: {e.message}, Meta: {e.metadata}")
        details = f"Twirp Error: Code={e.code}, Message={e.message}, Metadata={e.metadata}"
        raise LiveKitServiceError(f"LiveKit SDK error creating Inbound SIP Trunk: {e.message}", status_code=e.status, details=details)
    except Exception as e:
        logger.error(f"Unexpected error creating Inbound SIP Trunk via SDK: {e}", exc_info=True)
        raise LiveKitServiceError(f"Unexpected SDK error while creating inbound SIP trunk: {str(e)}")
    finally:
        if lk_api_client:
            await lk_api_client.aclose()

async def list_inbound_sip_trunks() -> List[Dict[str, Any]]:
    """
    Lists all Inbound SIP Trunks in LiveKit.
    Follows same pattern as list_sip_trunks but for inbound trunks.
    """
    if not LIVEKIT_API_URL or not LIVEKIT_API_KEY or not LIVEKIT_API_SECRET:
        logger.error("LiveKit API URL, Key, or Secret is not configured for listing inbound SIP trunks.")
        raise LiveKitConfigurationError("LiveKit API credentials are not fully configured.")

    lk_api_client = None
    try:
        lk_api_client = api.LiveKitAPI(LIVEKIT_API_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
        
        logger.info("Listing all LiveKit Inbound SIP Trunks.")
        
        list_request = api.ListSIPInboundTrunkRequest()
        list_response_proto = await lk_api_client.sip.list_sip_inbound_trunk(list_request)
        
        trunks_list = []
        if hasattr(list_response_proto, 'items'):
            trunks_list = list_response_proto.items
        elif hasattr(list_response_proto, 'trunks'):
            trunks_list = list_response_proto.trunks
        else:
            logger.warning("Could not find 'items' or 'trunks' in ListSIPInboundTrunkResponse")
            return []
        
        # Convert protobuf objects to dicts
        trunk_dicts = []
        for trunk_proto in trunks_list:
            if hasattr(api, 'MessageToJSON') and callable(getattr(api, 'MessageToJSON')):
                trunk_json_str = api.MessageToJSON(trunk_proto)
            else:
                from google.protobuf.json_format import MessageToJson as ProtoMessageToJson
                trunk_json_str = ProtoMessageToJson(trunk_proto)
            
            trunk_dict = json.loads(trunk_json_str)
            trunk_dicts.append(trunk_dict)
        
        logger.info(f"Found {len(trunk_dicts)} inbound SIP trunks")
        return trunk_dicts

    except api.TwirpError as e:
        logger.error(f"LiveKit SDK TwirpError listing Inbound SIP Trunks: Code: {e.code}, Msg: {e.message}, Meta: {e.metadata}")
        details = f"Twirp Error: Code={e.code}, Message={e.message}, Metadata={e.metadata}"
        raise LiveKitServiceError(f"LiveKit SDK error listing Inbound SIP Trunks: {e.message}", status_code=e.status, details=details)
    except Exception as e:
        logger.error(f"Unexpected error listing Inbound SIP Trunks via SDK: {e}", exc_info=True)
        raise LiveKitServiceError(f"Unexpected SDK error while listing inbound SIP trunks: {str(e)}")
    finally:
        if lk_api_client:
            await lk_api_client.aclose()

async def get_inbound_sip_trunk(sip_trunk_id: str) -> Optional[Dict[str, Any]]:
    """
    Gets a specific Inbound SIP Trunk from LiveKit by its ID.
    Follows same pattern as get_sip_trunk but for inbound trunks.
    """
    if not sip_trunk_id:
        raise ValueError("Inbound SIP Trunk ID is required.")

    if not LIVEKIT_API_URL or not LIVEKIT_API_KEY or not LIVEKIT_API_SECRET:
        logger.error("LiveKit API URL, Key, or Secret is not configured for get_inbound_sip_trunk.")
        raise LiveKitConfigurationError("LiveKit API credentials are not fully configured.")

    lk_api_client = None
    try:
        lk_api_client = api.LiveKitAPI(LIVEKIT_API_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
        
        logger.info(f"Attempting to find Inbound SIP Trunk ID: {sip_trunk_id}")
        
        # List all inbound trunks and find the matching one
        list_request = api.ListSIPInboundTrunkRequest()
        list_response_proto = await lk_api_client.sip.list_sip_inbound_trunk(list_request)
        
        found_trunk_proto = None
        
        trunks_list = []
        if hasattr(list_response_proto, 'items'):
            trunks_list = list_response_proto.items
        elif hasattr(list_response_proto, 'trunks'):
            trunks_list = list_response_proto.trunks
        else:
            logger.warning("Could not find 'items' or 'trunks' in ListSIPInboundTrunkResponse")
            return None

        for trunk_proto_item in trunks_list:
            if hasattr(trunk_proto_item, 'sip_trunk_id') and trunk_proto_item.sip_trunk_id == sip_trunk_id:
                found_trunk_proto = trunk_proto_item
                logger.debug(f"Matching inbound trunk found: {trunk_proto_item.sip_trunk_id}")
                break
        
        if not found_trunk_proto:
            logger.warning(f"LiveKit Inbound SIP Trunk ID {sip_trunk_id} not found.")
            return None

        logger.info(f"Successfully found Inbound SIP Trunk {sip_trunk_id}")
        
        # Convert to dict
        response_json_str = ""
        if hasattr(api, 'MessageToJSON') and callable(getattr(api, 'MessageToJSON')):
            response_json_str = api.MessageToJSON(found_trunk_proto)
        else:
            from google.protobuf.json_format import MessageToJson as ProtoMessageToJson
            response_json_str = ProtoMessageToJson(found_trunk_proto)
            
        response_dict = json.loads(response_json_str)
        
        logger.info(f"Inbound SIP Trunk {sip_trunk_id} details: {response_dict}")
        return response_dict

    except api.TwirpError as e:
        logger.error(f"LiveKit SDK TwirpError while finding Inbound SIP Trunk {sip_trunk_id}: Code: {e.code}, Msg: {e.message}, Meta: {e.metadata}")
        raise LiveKitServiceError(f"LiveKit SDK error finding Inbound SIP Trunk: {e.message}", status_code=e.status, details=f"Twirp Error: Code={e.code}, Message={e.message}, Metadata={e.metadata}")
    except Exception as e:
        logger.error(f"Unexpected error finding LiveKit Inbound SIP Trunk {sip_trunk_id} via SDK: {e}", exc_info=True)
        raise LiveKitServiceError(f"Unexpected SDK error while finding inbound SIP trunk: {str(e)}")
    finally:
        if lk_api_client:
            await lk_api_client.aclose()

async def update_sip_inbound_trunk(
    trunk_id: str,
    allowed_addresses: List[str] = None,
    numbers: List[str] = None
) -> Dict[str, Any]:
    """
    Updates an existing inbound SIP trunk with new allowed addresses and/or numbers.
    """
    if not trunk_id:
        raise ValueError("SIP Trunk ID is required.")
    
    if not LIVEKIT_API_URL or not LIVEKIT_API_KEY or not LIVEKIT_API_SECRET:
        logger.error("LiveKit API URL, Key, or Secret is not configured for update operation.")
        raise LiveKitConfigurationError("LiveKit API credentials are not fully configured.")
    
    lk_api_client = None
    try:
        lk_api_client = api.LiveKitAPI(LIVEKIT_API_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
        
        # Get current trunk details first
        current_trunk = await get_inbound_sip_trunk(trunk_id)
        if not current_trunk:
            raise LiveKitServiceError(f"Inbound SIP trunk {trunk_id} not found")
        
        # Use provided values or keep current ones
        final_allowed_addresses = allowed_addresses if allowed_addresses is not None else current_trunk.get("allowedAddresses", [])
        final_numbers = numbers if numbers is not None else current_trunk.get("numbers", [])
        
        logger.info(f"Updating inbound SIP trunk {trunk_id}")
        logger.info(f"  Allowed Addresses: {final_allowed_addresses}")
        logger.info(f"  Numbers: {final_numbers}")
        
        # Create the update request
        update_request = api.UpdateSIPInboundTrunkRequest(
            sip_trunk_id=trunk_id,
            allowed_addresses=final_allowed_addresses,
            numbers=final_numbers
        )
        
        response_proto = await lk_api_client.sip.update_sip_inbound_trunk(update_request)
        
        # Convert to dict
        response_json_str = ""
        if hasattr(api, 'MessageToJSON') and callable(getattr(api, 'MessageToJSON')):
            response_json_str = api.MessageToJSON(response_proto)
        else:
            from google.protobuf.json_format import MessageToJson as ProtoMessageToJson
            logger.warning("livekit.api.MessageToJSON not found or not callable, using google.protobuf.json_format.MessageToJson for update response.")
            response_json_str = ProtoMessageToJson(response_proto)
            
        response_dict = json.loads(response_json_str)
        
        logger.info(f"LiveKit Inbound SIP Trunk {trunk_id} updated successfully: {response_dict}")
        return response_dict
        
    except api.TwirpError as e:
        logger.error(f"LiveKit SDK TwirpError while updating Inbound SIP Trunk {trunk_id}: Code: {e.code}, Msg: {e.message}, Meta: {e.metadata}")
        raise LiveKitServiceError(f"LiveKit SDK error updating Inbound SIP Trunk: {e.message}", status_code=e.status, details=f"Twirp Error: Code={e.code}, Message={e.message}, Metadata={e.metadata}")
    except Exception as e:
        logger.error(f"Unexpected error updating LiveKit Inbound SIP Trunk {trunk_id} via SDK: {e}", exc_info=True)
        raise LiveKitServiceError(f"Unexpected SDK error while updating inbound SIP trunk: {str(e)}")
    finally:
        if lk_api_client:
            await lk_api_client.aclose()

async def delete_inbound_sip_trunk(sip_trunk_id: str) -> bool:
    """
    Deletes an Inbound SIP Trunk from LiveKit.
    Follows same pattern as delete_sip_trunk but for inbound trunks.
    """
    if not sip_trunk_id:
        raise ValueError("Inbound SIP Trunk ID for deletion is required.")
        
    if not LIVEKIT_API_URL or not LIVEKIT_API_KEY or not LIVEKIT_API_SECRET:
        logger.error("LiveKit API URL, Key, or Secret is not configured for deleting inbound SIP trunk.")
        raise LiveKitConfigurationError("LiveKit API credentials are not fully configured.")

    lk_api_client = None
    try:
        lk_api_client = api.LiveKitAPI(LIVEKIT_API_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
        
        logger.info(f"Deleting LiveKit Inbound SIP Trunk ID: {sip_trunk_id}")
        
        delete_request = api.DeleteSIPTrunkRequest(sip_trunk_id=sip_trunk_id)
        await lk_api_client.sip.delete_sip_trunk(delete_request)
        
        logger.info(f"LiveKit Inbound SIP Trunk ID {sip_trunk_id} deleted successfully.")
        return True

    except api.TwirpError as e:
        if e.code == "not_found" or e.status == 404:
            logger.warning(f"LiveKit Inbound SIP Trunk ID {sip_trunk_id} not found for deletion.")
            return True  # Idempotency: if not found, it's effectively deleted
        logger.error(f"LiveKit SDK TwirpError deleting Inbound SIP Trunk {sip_trunk_id}: Code: {e.code}, Msg: {e.message}, Meta: {e.metadata}")
        details = f"Twirp Error: Code={e.code}, Message={e.message}, Metadata={e.metadata}"
        raise LiveKitServiceError(f"LiveKit SDK error deleting Inbound SIP Trunk {sip_trunk_id}: {e.message}", status_code=e.status, details=details)
    except Exception as e:
        logger.error(f"Unexpected error deleting Inbound SIP Trunk {sip_trunk_id} via SDK: {e}", exc_info=True)
        raise LiveKitServiceError(f"Unexpected SDK error while deleting inbound SIP trunk: {str(e)}")
    finally:
        if lk_api_client:
            await lk_api_client.aclose()

async def update_inbound_sip_trunk_auth(
    trunk_id: str,
    username: str,
    password: str
) -> Dict[str, Any]:
    """
    Updates authentication credentials for an Inbound SIP Trunk.
    Follows same pattern as update_sip_trunk_credentials_simple but for inbound trunks.
    """
    if not trunk_id or not username or not password:
        raise ValueError("Trunk ID, username, and password are all required for inbound trunk auth update.")
        
    if not LIVEKIT_API_URL or not LIVEKIT_API_KEY or not LIVEKIT_API_SECRET:
        logger.error("LiveKit API URL, Key, or Secret is not configured for updating inbound SIP trunk auth.")
        raise LiveKitConfigurationError("LiveKit API credentials are not fully configured.")

    lk_api_client = None
    try:
        lk_api_client = api.LiveKitAPI(LIVEKIT_API_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
        
        logger.info(f"Attempting to update Inbound SIP trunk {trunk_id} authentication credentials.")
        
        # Create the inbound trunk update object with new credentials
        trunk_update = api.SIPInboundTrunkUpdate(
            auth_username=username,
            auth_password=password
        )
        
        # Create the update request
        update_request = api.UpdateSIPInboundTrunkRequest(
            sip_trunk_id=trunk_id,
            update=trunk_update
        )
        
        logger.info(f"Calling update_sip_inbound_trunk for trunk ID {trunk_id} with new credentials.")
        response_proto = await lk_api_client.sip.update_sip_inbound_trunk(update_request)
        
        # Convert response to dict
        response_json_str = ""
        if hasattr(api, 'MessageToJSON') and callable(getattr(api, 'MessageToJSON')):
            response_json_str = api.MessageToJSON(response_proto)
        else:
            from google.protobuf.json_format import MessageToJson as ProtoMessageToJson
            logger.warning("livekit.api.MessageToJSON not found, using google.protobuf.json_format.MessageToJson for inbound trunk update response.")
            response_json_str = ProtoMessageToJson(response_proto)
            
        response_dict = json.loads(response_json_str)
        
        logger.info(f"LiveKit Inbound SIP Trunk {trunk_id} credentials updated successfully: {response_dict}")
        return response_dict

    except api.TwirpError as e:
        logger.error(f"LiveKit SDK TwirpError updating Inbound SIP Trunk {trunk_id}: Code: {e.code}, Msg: {e.message}, Meta: {e.metadata}")
        details = f"Twirp Error: Code={e.code}, Message={e.message}, Metadata={e.metadata}"
        if e.code == "not_found" or e.status == 404:
             raise LiveKitTrunkNotFoundError(f"LiveKit Inbound SIP Trunk {trunk_id} not found for update. Detail: {e.message}", status_code=e.status, details=details)
        raise LiveKitServiceError(f"LiveKit SDK error updating Inbound SIP Trunk {trunk_id}: {e.message}", status_code=e.status, details=details)
    except Exception as e:
        logger.error(f"Unexpected error updating LiveKit Inbound SIP Trunk {trunk_id} via SDK: {e}", exc_info=True)
        raise LiveKitServiceError(f"Unexpected SDK error while updating inbound SIP trunk credentials: {str(e)}")
    finally:
        if lk_api_client:
            await lk_api_client.aclose()

# ===== LIVEKIT INBOUND INFRASTRUCTURE (Phase 2: Bidirectional Support) =====

async def create_sip_inbound_trunk(
    name: str,
    numbers: List[str],
    allowed_addresses: Optional[List[str]] = None,
    auth_username: Optional[str] = None,
    auth_password: Optional[str] = None,
    metadata: Optional[str] = None
) -> Dict[str, Any]:
    """
    Creates a LiveKit SIP inbound trunk for receiving calls from external sources.
    This is required for bidirectional calling to handle inbound calls.
    
    Args:
        name: Human-readable name for the trunk
        numbers: List of E.164 phone numbers that route to this trunk
        allowed_addresses: List of SIP addresses allowed to send calls (e.g., ["sip.telnyx.com"])
        auth_username: Username for SIP authentication 
        auth_password: Password for SIP authentication
        metadata: Optional metadata string
    
    Returns:
        Dict containing the created inbound trunk details
    """
    if not LIVEKIT_SIP_INBOUND_AVAILABLE:
        raise LiveKitServiceError("LiveKit SIP inbound classes not available. Please update LiveKit SDK.")
    
    if not LIVEKIT_API_URL or not LIVEKIT_API_KEY or not LIVEKIT_API_SECRET:
        logger.error("LiveKit API URL, Key, or Secret is not configured.")
        raise LiveKitConfigurationError("LiveKit API credentials are not fully configured.")
    
    lk_api_client = None
    try:
        lk_api_client = api.LiveKitAPI(LIVEKIT_API_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
        
        # Create the inbound trunk request
        trunk_request = CreateSIPInboundTrunkRequest()
        trunk_request.trunk.name = name
        trunk_request.trunk.metadata = metadata or f"Bidirectional inbound trunk for {', '.join(numbers)}"
        
        # Add phone numbers
        for number in numbers:
            trunk_request.trunk.numbers.append(number)
        
        # Add allowed addresses (typically ["sip.telnyx.com"])
        if allowed_addresses:
            for address in allowed_addresses:
                trunk_request.trunk.allowed_addresses.append(address)
        
        # Add authentication if provided
        if auth_username:
            trunk_request.trunk.auth_username = auth_username
        if auth_password:
            trunk_request.trunk.auth_password = auth_password
            
        logger.info(f"Creating LiveKit SIP inbound trunk '{name}' for numbers: {numbers}")
        trunk_response = await lk_api_client.sip.create_sip_inbound_trunk(trunk_request)
        
        # Convert response to JSON
        response_json_str = ""
        if hasattr(api, 'MessageToJSON') and callable(getattr(api, 'MessageToJSON')):
            response_json_str = api.MessageToJSON(trunk_response)
        else:
            from google.protobuf.json_format import MessageToJson as ProtoMessageToJson
            response_json_str = ProtoMessageToJson(trunk_response)
            
        response_dict = json.loads(response_json_str)
        trunk_id = trunk_response.sip_trunk_id
        
        logger.info(f"✅ Created LiveKit SIP inbound trunk with ID: {trunk_id}")
        logger.info(f"🔧 Auth - Username: {auth_username}")
        
        # Ensure compatibility with existing code expectations
        response_dict["sipTrunkId"] = trunk_id
        response_dict["sip_trunk_id"] = trunk_id
        
        return response_dict
        
    except Exception as e:
        logger.error(f"Error creating LiveKit SIP inbound trunk '{name}': {str(e)}")
        raise LiveKitServiceError(f"Failed to create SIP inbound trunk: {str(e)}")

async def create_sip_dispatch_rule(
    name: str,
    trunk_ids: List[str],
    agent_name: str,
    room_prefix: str = "call",
    metadata: Optional[str] = None
) -> Dict[str, Any]:
    """
    Creates a LiveKit SIP dispatch rule to route inbound calls to a specific agent.
    This connects inbound trunks to the bidirectional agent.
    
    Args:
        name: Human-readable name for the dispatch rule
        trunk_ids: List of SIP trunk IDs to route calls from
        agent_name: Name of the agent to handle calls (e.g., "bidirectional-agent")
        room_prefix: Prefix for room names (default: "call")
        metadata: Optional metadata string
    
    Returns:
        Dict containing the created dispatch rule details
    """
    if not LIVEKIT_SIP_INBOUND_AVAILABLE:
        raise LiveKitServiceError("LiveKit SIP inbound classes not available. Please update LiveKit SDK.")
    
    if not LIVEKIT_API_URL or not LIVEKIT_API_KEY or not LIVEKIT_API_SECRET:
        logger.error("LiveKit API URL, Key, or Secret is not configured.")
        raise LiveKitConfigurationError("LiveKit API credentials are not fully configured.")
    
    lk_api_client = None
    try:
        lk_api_client = api.LiveKitAPI(LIVEKIT_API_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
        
        # Create the dispatch rule request
        dispatch_request = CreateSIPDispatchRuleRequest()
        dispatch_request.rule.dispatch_rule_individual.room_prefix = room_prefix
        dispatch_request.name = name
        dispatch_request.metadata = metadata or f"Route inbound calls to {agent_name}"
        
        # Add trunk IDs
        for trunk_id in trunk_ids:
            dispatch_request.trunk_ids.append(trunk_id)
        
        # Configure individual dispatch rule with room prefix
        dispatch_request.rule.dispatch_rule_individual.room_prefix = room_prefix
        
        # Configure room with agent dispatch
        agent_config = dispatch_request.room_config.agents.add()
        agent_config.agent_name = agent_name
        if metadata:
            agent_config.metadata = metadata
        
        logger.info(f"Creating LiveKit SIP dispatch rule '{name}' for agent '{agent_name}'")
        logger.info(f"🔗 Routing from trunk IDs: {trunk_ids}")
        
        dispatch_response = await lk_api_client.sip.create_sip_dispatch_rule(dispatch_request)
        
        # Convert response to JSON
        response_json_str = ""
        if hasattr(api, 'MessageToJSON') and callable(getattr(api, 'MessageToJSON')):
            response_json_str = api.MessageToJSON(dispatch_response)
        else:
            from google.protobuf.json_format import MessageToJson as ProtoMessageToJson
            response_json_str = ProtoMessageToJson(dispatch_response)
            
        response_dict = json.loads(response_json_str)
        rule_id = dispatch_response.sip_dispatch_rule_id
        
        logger.info(f"✅ Created LiveKit SIP dispatch rule with ID: {rule_id}")
        
        # Ensure compatibility 
        response_dict["sipDispatchRuleId"] = rule_id
        response_dict["sip_dispatch_rule_id"] = rule_id
        
        return response_dict
        
    except Exception as e:
        logger.error(f"Error creating LiveKit SIP dispatch rule '{name}': {str(e)}")
        raise LiveKitServiceError(f"Failed to create SIP dispatch rule: {str(e)}")

async def list_sip_inbound_trunks() -> List[Dict[str, Any]]:
    """
    Lists all SIP inbound trunks in the LiveKit project.
    Useful for debugging and management.
    """
    if not LIVEKIT_SIP_INBOUND_AVAILABLE:
        raise LiveKitServiceError("LiveKit SIP inbound classes not available. Please update LiveKit SDK.")
    
    if not LIVEKIT_API_URL or not LIVEKIT_API_KEY or not LIVEKIT_API_SECRET:
        raise LiveKitConfigurationError("LiveKit API credentials are not fully configured.")
    
    try:
        lk_api_client = api.LiveKitAPI(LIVEKIT_API_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
        
        request = ListSIPInboundTrunkRequest()
        response = await lk_api_client.sip.list_sip_inbound_trunk(request)
        
        # Convert response to JSON
        response_json_str = ""
        if hasattr(api, 'MessageToJSON') and callable(getattr(api, 'MessageToJSON')):
            response_json_str = api.MessageToJSON(response)
        else:
            from google.protobuf.json_format import MessageToJson as ProtoMessageToJson
            response_json_str = ProtoMessageToJson(response)
            
        response_dict = json.loads(response_json_str)
        trunks = response_dict.get("items", [])
        
        logger.info(f"Found {len(trunks)} SIP inbound trunks")
        return trunks
        
    except Exception as e:
        logger.error(f"Error listing SIP inbound trunks: {str(e)}")
        raise LiveKitServiceError(f"Failed to list SIP inbound trunks: {str(e)}")

async def list_sip_dispatch_rules() -> List[Dict[str, Any]]:
    """
    Lists all SIP dispatch rules in the LiveKit project.
    Useful for debugging and management.
    """
    if not LIVEKIT_SIP_INBOUND_AVAILABLE:
        raise LiveKitServiceError("LiveKit SIP inbound classes not available. Please update LiveKit SDK.")
    
    if not LIVEKIT_API_URL or not LIVEKIT_API_KEY or not LIVEKIT_API_SECRET:
        raise LiveKitConfigurationError("LiveKit API credentials are not fully configured.")
    
    try:
        lk_api_client = api.LiveKitAPI(LIVEKIT_API_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
        
        request = ListSIPDispatchRuleRequest()
        response = await lk_api_client.sip.list_sip_dispatch_rule(request)
        
        # Convert response to JSON
        response_json_str = ""
        if hasattr(api, 'MessageToJSON') and callable(getattr(api, 'MessageToJSON')):
            response_json_str = api.MessageToJSON(response)
        else:
            from google.protobuf.json_format import MessageToJson as ProtoMessageToJson
            response_json_str = ProtoMessageToJson(response)
            
        response_dict = json.loads(response_json_str)
        rules = response_dict.get("items", [])
        
        logger.info(f"Found {len(rules)} SIP dispatch rules")
        return rules
        
    except Exception as e:
        logger.error(f"Error listing SIP dispatch rules: {str(e)}")
        raise LiveKitServiceError(f"Failed to list SIP dispatch rules: {str(e)}")

async def delete_sip_inbound_trunk(trunk_id: str) -> bool:
    """
    Deletes a SIP inbound trunk by ID.
    Used for cleanup during migration or removal.
    """
    if not LIVEKIT_SIP_INBOUND_AVAILABLE:
        raise LiveKitServiceError("LiveKit SIP inbound classes not available. Please update LiveKit SDK.")
    
    if not LIVEKIT_API_URL or not LIVEKIT_API_KEY or not LIVEKIT_API_SECRET:
        raise LiveKitConfigurationError("LiveKit API credentials are not fully configured.")
    
    try:
        lk_api_client = api.LiveKitAPI(LIVEKIT_API_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
        
        request = DeleteSIPTrunkRequest()
        request.sip_trunk_id = trunk_id
        await lk_api_client.sip.delete_sip_trunk(request)
        
        logger.info(f"✅ Deleted SIP inbound trunk: {trunk_id}")
        return True
        
    except Exception as e:
        logger.error(f"Error deleting SIP inbound trunk {trunk_id}: {str(e)}")
        raise LiveKitServiceError(f"Failed to delete SIP inbound trunk {trunk_id}: {str(e)}")

async def delete_sip_dispatch_rule(rule_id: str) -> bool:
    """
    Deletes a SIP dispatch rule by ID.
    Used for cleanup during migration or removal.
    """
    if not LIVEKIT_SIP_INBOUND_AVAILABLE:
        raise LiveKitServiceError("LiveKit SIP inbound classes not available. Please update LiveKit SDK.")
    
    if not LIVEKIT_API_URL or not LIVEKIT_API_KEY or not LIVEKIT_API_SECRET:
        raise LiveKitConfigurationError("LiveKit API credentials are not fully configured.")
    
    try:
        lk_api_client = api.LiveKitAPI(LIVEKIT_API_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
        
        request = DeleteSIPDispatchRuleRequest()
        request.sip_dispatch_rule_id = rule_id
        await lk_api_client.sip.delete_sip_dispatch_rule(request)
        
        logger.info(f"✅ Deleted SIP dispatch rule: {rule_id}")
        return True
        
    except Exception as e:
        logger.error(f"Error deleting SIP dispatch rule {rule_id}: {str(e)}")
        raise LiveKitServiceError(f"Failed to delete SIP dispatch rule {rule_id}: {str(e)}")

# ===== END INBOUND INFRASTRUCTURE =====

# Example of how you might call this if you were not using the SDK directly:
# async def main_example():
#     try:
#        # NOTE: LIVEKIT_API_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET must be in environment
#        trunks = await list_sip_trunks()
#        print("Existing trunks:", trunks)
#        
#        new_trunk_info = await create_sip_trunk(
#            name="MyTestTelnyxTrunk",
#            outbound_addresses=["sip.telnyx.com"],
#            outbound_number="+12345678900", # Your Telnyx number for outbound CID
#            inbound_sip_username="your_telnyx_sip_user",
#            inbound_sip_password="your_telnyx_sip_pass"
#        )
#        print("Created trunk:", new_trunk_info)
#        
#        if new_trunk_info and new_trunk_info.get('sip_trunk_id'):
#            await delete_sip_trunk(new_trunk_info['sip_trunk_id'])
#            print(f"Deleted trunk: {new_trunk_info['sip_trunk_id']}")
#            
#     except LiveKitServiceError as e:
#         print(f"LiveKit Service Error: {e.message} (Status: {e.status_code}) - Details: {e.details}")
#     except Exception as e:
#         print(f"An unexpected error occurred: {e}")

# if __name__ == "__main__":
#     import asyncio
#     logging.basicConfig(level=logging.INFO,
#                         format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
#     asyncio.run(main_example()) 