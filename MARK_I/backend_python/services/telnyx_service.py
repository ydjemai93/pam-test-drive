import os
import httpx
import logging
from typing import Optional, List, Dict, Any
import asyncio
import json

# Configure logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

TELNYX_API_KEY = os.getenv("TELNYX_API_KEY")
TELNYX_API_BASE_URL = "https://api.telnyx.com/v2"

# Custom Exceptions
class TelnyxServiceError(Exception):
    """Base exception for Telnyx service errors."""
    def __init__(self, message: str, status_code: Optional[int] = None, telnyx_errors: Optional[List[Dict[str, Any]]] = None):
        super().__init__(message)
        self.status_code = status_code
        self.telnyx_errors = telnyx_errors if telnyx_errors else []

class NumberNotFoundError(TelnyxServiceError):
    """Custom error for when a number or resource is not found (404)."""
    pass

class NumberAlreadyReservedError(TelnyxServiceError):
    """Custom error for when Telnyx indicates a number is already reserved (error code 85006)."""
    pass

class TelnyxPurchaseError(TelnyxServiceError):
    """Exception raised for errors during Telnyx number purchase, including reservation issues."""
    pass

class TelnyxReservationError(TelnyxPurchaseError): # Inherits from TelnyxPurchaseError
    """Specific exception for errors during the reservation step of a purchase."""
    pass

async def _make_telnyx_request(
    method: str,
    endpoint: str,
    api_key: Optional[str] = None, # Allows using a user-specific key
    json_data: Optional[Dict[str, Any]] = None,
    params: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Helper function to make requests to the Telnyx API.
    Handles authentication, request formation, and basic error handling.
    """
    request_api_key = api_key if api_key else TELNYX_API_KEY
    
    if not request_api_key:
        logger.error("Telnyx API key is not available (neither specific nor Pam's main key).")
        raise TelnyxServiceError("Telnyx API key is not configured or provided.", status_code=500)

    headers = {
        "Authorization": f"Bearer {request_api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    
    # Robust URL construction
    clean_base_url = TELNYX_API_BASE_URL.rstrip('/')
    clean_endpoint = endpoint.lstrip('/')
    url = f"{clean_base_url}/{clean_endpoint}"

    logger.info(f"[DEBUG_URL_CONSTRUCTION] Original TELNYX_API_BASE_URL: '{TELNYX_API_BASE_URL}', Original endpoint: '{endpoint}'")
    logger.info(f"[DEBUG_URL_CONSTRUCTION] Cleaned Base: '{clean_base_url}', Cleaned Endpoint: '{clean_endpoint}', Final Constructed URL: '{url}'")

    async with httpx.AsyncClient(timeout=20.0) as client: # Default timeout of 20s for Telnyx requests
        try:
            response = await client.request(
                method.upper(),
                url,
                json=json_data,
                params=params,
                headers=headers
            )
            
            logger.debug(f"Telnyx API Response: Status {response.status_code} - Text: {response.text[:500]}...") # Log snippet of response
            
            response.raise_for_status() # Raises HTTPStatusError for 4xx/5xx responses
            return response.json()
        
        except httpx.HTTPStatusError as e:
            error_message = f"Telnyx API HTTP error: {e.response.status_code}"
            telnyx_api_errors = []
            try:
                error_details = e.response.json()
                telnyx_api_errors = error_details.get("errors", [])
                if telnyx_api_errors:
                    first_error = telnyx_api_errors[0]
                    error_message += f" - Code: {first_error.get('code')} - Title: {first_error.get('title')} - Detail: {first_error.get('detail', '')}"
                else:
                    error_message += f" - Response: {e.response.text[:200]}" # Show part of raw response if no structured error
            except json.JSONDecodeError:
                error_message += f" - Non-JSON response: {e.response.text[:200]}"

            logger.error(error_message, exc_info=True)

            if e.response.status_code == 404:
                raise NumberNotFoundError(f"Resource not found at {endpoint}. Detail: {error_message}", status_code=404, telnyx_errors=telnyx_api_errors)
            
            # Check for specific Telnyx error codes within the response body for already reserved
            if telnyx_api_errors:
                for err in telnyx_api_errors:
                    if err.get("code") == 85006: # "phone_number.already_reserved"
                        raise NumberAlreadyReservedError(f"Phone number is already reserved. Detail: {error_message}", status_code=e.response.status_code, telnyx_errors=telnyx_api_errors)
            
            # General purchase or reservation error
            if "number_orders" in endpoint or "number_reservations" in endpoint:
                 if e.response.status_code == 422: # Often validation errors
                     raise TelnyxPurchaseError(f"Telnyx validation error during purchase/reservation. Detail: {error_message}", status_code=422, telnyx_errors=telnyx_api_errors)
                 raise TelnyxPurchaseError(f"Telnyx API error during purchase/reservation. Detail: {error_message}", status_code=e.response.status_code, telnyx_errors=telnyx_api_errors)

            raise TelnyxServiceError(error_message, status_code=e.response.status_code, telnyx_errors=telnyx_api_errors)
        
        except httpx.RequestError as e: # Network errors, timeouts other than HTTPStatusError
            logger.error(f"Telnyx request error for {method} {url}: {e}", exc_info=True)
            raise TelnyxServiceError(f"Telnyx request error: {str(e)}", status_code=503) # 503 for service unavailable type errors
        
        except json.JSONDecodeError as e:
            logger.error(f"Failed to decode JSON response from Telnyx for {method} {url}: {e.doc[:200]}...", exc_info=True)
            # This case should be rare if raise_for_status() is working, but good for robustness
            raise TelnyxServiceError(f"Invalid JSON response from Telnyx: {str(e)}", status_code=502) # 502 for bad gateway type errors

async def list_available_numbers(
    country_code: str,
    localities: Optional[List[str]] = None,
    area_code: Optional[str] = None,
    number_type: str = "local", # Parameter for default number type
    features: Optional[List[str]] = None, # Parameter for features
    limit_per_locality: int = 5,
    limit_general: int = 20 # Parameter for general limit, matches request model default but can be overridden
) -> List[Dict[str, Any]]:
    """
    Searches for available phone numbers on Telnyx.
    Enhanced to handle multiple localities or a general area code, and more filters.
    """
    all_numbers: List[Dict[str, Any]] = []
    seen_numbers = set() # To avoid duplicates if localities overlap or general search overlaps

    if not TELNYX_API_KEY:
        logger.error("TELNYX_API_KEY is not set in environment.")
        raise TelnyxServiceError("Telnyx API key is not configured on the server.", 500)

    base_filter_params: Dict[str, Any] = {
        "filter[country_code]": country_code,
        "filter[number_type]": number_type,
    }
    if features:
        base_filter_params["filter[features]"] = ",".join(features) # Telnyx expects comma-separated string

    async def fetch_and_add_numbers(current_params: Dict[str, Any]):
        nonlocal all_numbers, seen_numbers
        try:
            logger.info(f"Querying Telnyx available_phone_numbers with params: {current_params}")
            response_data = await _make_telnyx_request("GET", "/available_phone_numbers", params=current_params)
            numbers_found = response_data.get("data", [])
            count = 0
            for num_data in numbers_found:
                if num_data.get("phone_number") not in seen_numbers:
                    all_numbers.append(num_data)
                    seen_numbers.add(num_data["phone_number"])
                    count += 1
            logger.info(f"Added {count} new unique numbers. Total unique now: {len(all_numbers)}.")
        except TelnyxServiceError as e:
            # Log specific errors but don't let one failed locality search stop others.
            logger.error(f"Telnyx API error while searching with params {current_params}: {e}")
        except Exception as e:
            logger.error(f"Unexpected error while searching with params {current_params}: {e}")

    if localities:
        logger.info(f"Searching numbers by localities: {localities} with base filters: {base_filter_params}")
        for locality_name in localities:
            locality_params = {
                **base_filter_params,
                "filter[locality]": locality_name,
                "page[size]": limit_per_locality, # Telnyx uses page[size]
            }
            await fetch_and_add_numbers(locality_params)
    
    # Perform general search if no localities specified, or if localities yielded few results (optional)
    # For now, only if localities is not primary search.
    elif area_code: 
        logger.info(f"Searching numbers by area code: {area_code} with base filters: {base_filter_params}")
        general_params = {
            **base_filter_params,
            # For US/CA, national_destination_code is area code. Other countries might vary.
            "filter[national_destination_code]": area_code, 
            "page[size]": limit_general,
        }
        if "filter[features]" not in general_params: # Ensure voice is requested if not already specified
            general_params["filter[features]"] = "voice"
        elif "voice" not in general_params["filter[features]"]:
            general_params["filter[features]"] += ",voice"
            
        await fetch_and_add_numbers(general_params)
    else:
        # Fallback: if neither localities nor area_code
        logger.info(f"Performing broad search for country {country_code}.")
        
        # Start with essential params for any broad search
        common_broad_params = {
            "filter[country_code]": country_code,
            "page[size]": limit_general # Use the limit_general parameter from function arguments
        }
        
        # Ensure 'voice' feature is included, or use provided features.
        # If features is None from args, default to ["voice"].
        # If features is provided, ensure "voice" is in it if not already.
        effective_features = features.copy() if features is not None else ["voice"]
        if "voice" not in effective_features:
            effective_features.append("voice")
        
        if effective_features: # Only add the filter if there are features
             common_broad_params["filter[features]"] = ",".join(effective_features)

        if country_code == "FR":
            # For France, attempt to find 'national' numbers.
            params_fr_national = common_broad_params.copy()
            params_fr_national["filter[number_type]"] = "national" # Explicitly set to national
            logger.info(f"For FR, attempting broad search with specific params: {params_fr_national}")
            await fetch_and_add_numbers(params_fr_national)
            
            # To be thorough, also search for 'local' numbers in France.
            params_fr_local = common_broad_params.copy()
            params_fr_local["filter[number_type]"] = "local" # Explicitly set to local
            logger.info(f"For FR, also attempting broad search with specific params: {params_fr_local}")
            await fetch_and_add_numbers(params_fr_local)
        else:
            # For other countries, use the number_type passed to the function
            params_other_country = common_broad_params.copy()
            # `number_type` here is the argument to list_available_numbers
            params_other_country["filter[number_type]"] = number_type 
            logger.info(f"For {country_code}, performing broad search with number_type='{number_type}' using params: {params_other_country}")
            await fetch_and_add_numbers(params_other_country)
            
    return all_numbers

async def _create_number_reservation(phone_number_e164: str) -> Optional[str]:
    """
    Creates a number reservation on Telnyx and returns the reservation ID.
    Returns None if reservation fails.
    Raises NumberAlreadyReservedError if Telnyx reports the number is already reserved.
    """
    payload = {"phone_numbers": [{"phone_number": phone_number_e164}]}
    logger.info(f"Attempting to reserve Telnyx number: {phone_number_e164}")
    try:
        response = await _make_telnyx_request("POST", "/number_reservations", json_data=payload)
        reservation_data = response.get("data")
        if reservation_data and isinstance(reservation_data, dict):
            reservation_id = reservation_data.get("id")
            status = reservation_data.get("status")
            reserved_numbers = reservation_data.get("phone_numbers", [])
            
            if reservation_id and status == "success" and reserved_numbers:
                # Check if the specific number is in the reservation and its status is also "success"
                is_reserved = any(
                    pn.get("phone_number") == phone_number_e164 and pn.get("status") == "success"
                    for pn in reserved_numbers
                )
                if is_reserved:
                    logger.info(f"Telnyx number {phone_number_e164} reserved successfully with status 'success'. Reservation ID: {reservation_id}")
                    return reservation_id
                else:
                    logger.warning(f"Telnyx number {phone_number_e164} not found with 'success' status in reservation {reservation_id}. Reserved numbers: {reserved_numbers}")
            else:
                logger.warning(f"Telnyx number reservation for {phone_number_e164} was not successful or has unexpected status/content. Status: {status}, Reservation ID: {reservation_id}, Response: {response}")
        else:
            logger.error(f"Unexpected reservation response structure from Telnyx for {phone_number_e164}: {response}")
    except httpx.HTTPStatusError as e:
        # Specifically handle cases where the number might not be reservable (e.g., 404 or 422 if not found/available)
        logger.error(f"Telnyx API HTTP error during number reservation for {phone_number_e164}: {e.response.status_code} - {e.response.text}")
        
        parsed_telnyx_error_code = None
        parsed_telnyx_error_detail = "Unknown Telnyx error detail"
        try:
            error_details_json = e.response.json()
            if error_details_json and "errors" in error_details_json and error_details_json["errors"]:
                parsed_telnyx_error_code = error_details_json["errors"][0].get("code")
                parsed_telnyx_error_detail = error_details_json["errors"][0].get("detail", parsed_telnyx_error_detail)
        except json.JSONDecodeError:
            logger.warning(f"Could not parse JSON from Telnyx error response: {e.response.text}")

        if parsed_telnyx_error_code == "85006": # Number already reserved by you or another process
            raise NumberAlreadyReservedError(f"Phone number is already reserved. Detail: {parsed_telnyx_error_detail}", status_code=e.response.status_code, telnyx_errors=[{"code": parsed_telnyx_error_code, "detail": parsed_telnyx_error_detail}])
        elif e.response.status_code == 422 and parsed_telnyx_error_code == "10027":
            logger.warning(f"Telnyx returned error 10027 ('issue with the number_reservation') for {phone_number_e164}. Detail: '{parsed_telnyx_error_detail}'. Will attempt purchase without reservation ID.")
            return None # Non-blocking for this specific error, will try purchase without reservation
        else:
            # For other HTTP errors, raise a general TelnyxReservationError
            raise TelnyxReservationError(f"Telnyx API error during reservation for {phone_number_e164}: {e.response.status_code} - {parsed_telnyx_error_detail} - Full: {e.response.text}", status_code=e.response.status_code, telnyx_errors=[{"code": parsed_telnyx_error_code, "detail": parsed_telnyx_error_detail}])
            
    except Exception as e: # Catch any other unexpected errors
        logger.error(f"Unexpected error during number reservation for {phone_number_e164}: {e}")
        # Optional: re-raise a TelnyxReservationError or let it propagate if it's critical
    return None

async def purchase_number(phone_number_e164: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Attempts to reserve and then purchase a phone number from Telnyx.
    If reservation fails with a '10027' error (issue with reservation), it attempts to purchase directly.
    Returns the details of the actual phone number resource from Telnyx (obtained via get_number_details after order), or None if purchase/fetch fails.
    """
    if not phone_number_e164:
        raise ValueError("phone_number_e164 must be provided to purchase a number.")

    reservation_id = None
    try:
        reservation_id = await _create_number_reservation(phone_number_e164)
        if reservation_id:
            logger.info(f"Successfully obtained reservation ID {reservation_id} for {phone_number_e164}.")
        else:
            logger.info(f"No reservation ID obtained for {phone_number_e164}. Proceeding to attempt purchase directly.")
    except NumberAlreadyReservedError as nare:
        logger.error(f"Cannot purchase number {phone_number_e164} because it's already reserved (85006): {nare}")
        raise
    except TelnyxReservationError as tre:
        logger.error(f"Failed to reserve Telnyx number {phone_number_e164} due to: {tre}. Purchase cannot proceed.")
        raise TelnyxPurchaseError(f"Failed to reserve Telnyx number {phone_number_e164}. Details: {tre}", status_code=tre.status_code, telnyx_errors=tre.telnyx_errors) from tre
    
    order_payload = {
        "phone_numbers": [{"phone_number": phone_number_e164}]
    }

    if reservation_id:
        logger.info(f"Attempting to order Telnyx number {phone_number_e164} (reservation ID {reservation_id} was obtained) with payload: {order_payload}")
    else:
        logger.info(f"Attempting to order Telnyx number {phone_number_e164} directly (no reservation ID) with payload: {order_payload}")

    try:
        response_data = await _make_telnyx_request("POST", "/number_orders", json_data=order_payload)
        
        order_details = response_data.get("data")
        if not order_details or not isinstance(order_details, dict):
            logger.error(f"Telnyx order response for {phone_number_e164} is missing 'data' or has an unexpected structure: {response_data}")
            raise TelnyxPurchaseError(f"Telnyx order response for {phone_number_e164} is malformed.", status_code=500)

        ordered_numbers_info = order_details.get("phone_numbers", [])
        order_status = order_details.get("status")
        order_id = order_details.get("id")

        logger.info(f"Telnyx number order for {phone_number_e164} placed. Status: {order_status}. Order ID: {order_id}.")
        
        if ordered_numbers_info and isinstance(ordered_numbers_info, list) and len(ordered_numbers_info) > 0:
            number_order_phone_id = ordered_numbers_info[0].get("id")
            logger.info(f"ID from number_order.phone_numbers[0]: {number_order_phone_id} for {phone_number_e164}")
        else:
            logger.warning(f"Could not extract ID from number_order.phone_numbers for order {order_id}.")

        if order_status in ["pending", "complete"]:
            logger.info(f"Number order {order_id} for {phone_number_e164} is {order_status}. Attempting to fetch actual phone number resource details.")
            # Attempt to fetch the definitive phone number resource details
            # Add a small delay to improve chances of Telnyx API consistency
            await asyncio.sleep(5) # 5 second delay
            actual_phone_number_resource = await get_number_details(phone_number_e164=phone_number_e164)
            
            if actual_phone_number_resource and actual_phone_number_resource.get("id"):
                logger.info(f"Successfully fetched actual Telnyx phone number resource for {phone_number_e164}. Resource ID: {actual_phone_number_resource.get('id')}")
                # THIS is the object that should be returned and its ID stored in Xano.
                return actual_phone_number_resource 
            else:
                logger.error(f"Failed to fetch actual phone number resource details for {phone_number_e164} after order was {order_status}. Order ID: {order_id}")
                # Even if fetching the final resource fails, if the order had some info, maybe return that with a warning?
                # For now, strict failure if we can't get the final resource ID.
                raise TelnyxPurchaseError(f"Order {order_status}, but could not fetch final phone number resource for {phone_number_e164}. Order ID: {order_id}", status_code=500)
        
        elif order_status in ["failed", "cancelled", "rejected"]:
            logger.error(f"Telnyx number order {order_id} for {phone_number_e164} has status: {order_status}. Errors: {order_details.get('errors')}")
            telnyx_order_errors = order_details.get('errors', [])
            error_msg_detail = f"Telnyx order failed with status '{order_status}'."
            if telnyx_order_errors:
                error_msg_detail += f" Details: {telnyx_order_errors[0].get('title', '')} - {telnyx_order_errors[0].get('detail', '')}"
            raise TelnyxPurchaseError(error_msg_detail, status_code=500, telnyx_errors=telnyx_order_errors)
            
        else: # Any other unexpected status
            logger.warning(f"Telnyx number order {order_id} for {phone_number_e164} has an unexpected status: {order_status}. Full response: {response_data}")
            # This case should be treated as an error if it's not explicitly handled as success.
            raise TelnyxPurchaseError(f"Order for {phone_number_e164} has unexpected status '{order_status}'. Order ID: {order_id}", status_code=500)

    except httpx.HTTPStatusError as e:
        logger.error(f"Telnyx API HTTP error during number purchase for {phone_number_e164}: {e.response.status_code} - {e.response.text}")
        error_detail_msg = f"Telnyx API error during purchase for {phone_number_e164}: {e.response.text}"
        try:
            error_json = e.response.json()
            if error_json and "errors" in error_json and error_json["errors"]:
                error_detail_msg = f"Telnyx API Error: {error_json['errors'][0].get('title', '')} - {error_json['errors'][0].get('detail', '')}"
        except json.JSONDecodeError:
            pass 
        raise TelnyxPurchaseError(error_detail_msg, status_code=e.response.status_code) from e
    except TelnyxPurchaseError: 
        raise
    except Exception as e:
        logger.error(f"Unexpected error during number purchase for {phone_number_e164}: {e}", exc_info=True)
        raise TelnyxPurchaseError(f"Unexpected error during Telnyx number purchase: {str(e)}", status_code=500) from e

    # Fallback, should ideally not be reached if logic above is complete
    return None

async def get_number_details(phone_number_e164: str, api_key: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Retrieves details of a phone number already owned on the Telnyx account.
    This uses the "List Phone Numbers" endpoint with a filter.
    Accepts an optional api_key to use a specific user's Telnyx account.
    """
    params = {"filter[phone_number]": phone_number_e164}
    logger.info(f"Getting details for number: {phone_number_e164}")
    response = await _make_telnyx_request("GET", "/phone_numbers", api_key=api_key, params=params)
    logger.info(f"Raw Telnyx response for {phone_number_e164} details: {response}")
    numbers = response.get("data", [])
    if numbers:
        logger.info(f"Found {len(numbers)} number(s) in 'data' for {phone_number_e164}. First one: {numbers[0]}")
        return numbers[0]
    else:
        logger.warning(f"No numbers found in 'data' field for {phone_number_e164}. 'data' field content: {response.get('data')}")
    return None

async def get_number_details_by_e164(phone_number_e164: str, api_key: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Alias for get_number_details - retrieves details of a phone number by E164.
    This is needed by the telnyx_routes.py for register_existing_telnyx_number function.
    """
    return await get_number_details(phone_number_e164=phone_number_e164, api_key=api_key)

async def update_number_connection(
    phone_number_id: str, 
    connection_id: str, 
    friendly_name: Optional[str] = None,
    api_key: Optional[str] = None # Added api_key
) -> Dict[str, Any]:
    """
    Updates a phone_number's configuration, e.g., to assign it to a SIP connection (for voice).
    `phone_number_id` here is Telnyx's internal ID for an *owned* number.
    """
    endpoint = f"/phone_numbers/{phone_number_id}"
    payload = {
        "connection_id": connection_id # Assigns to a specific SIP Connection or other connection type
    }
    if friendly_name: # You can also update the friendly name
        payload["tags"] = [friendly_name] # Telnyx uses tags for friendly names sometimes, or a direct field. Check docs.
        # Or payload["friendly_name"] = friendly_name if available.
        # Based on PUT /v2/phone_numbers/{id}, it seems 'connection_id' is correct.
        # For friendly_name, Telnyx often uses `tags` or it's part of the initial purchase.
        # The API allows updating 'connection_id'.

    logger.info(f"Updating number {phone_number_id} with connection {connection_id}")
    response = await _make_telnyx_request("PATCH", endpoint, json_data=payload, api_key=api_key) # Pass api_key
    return response.get("data", {})

async def release_number(phone_number_id: str) -> bool:
    """
    Releases/deletes a phone number from the Telnyx account.
    `phone_number_id` is Telnyx's internal ID for an *owned* number.
    """
    endpoint = f"/phone_numbers/{phone_number_id}"
    logger.info(f"Releasing number ID: {phone_number_id}")
    try:
        await _make_telnyx_request("DELETE", endpoint)
        return True # Telnyx DELETE usually returns 204 No Content on success
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404: # Already deleted or doesn't exist
            logger.warning(f"Number {phone_number_id} not found for release, might be already released.")
            return True # Idempotency
        raise
    return False

# Placeholder for linking to LiveKit SIP Trunk if needed directly via Telnyx API
# This is usually done by configuring the Telnyx number to point to LiveKit's SIP URI
# or by LiveKit managing the number if ported in.
# For numbers purchased via API and used with LiveKit SIP Trunk, you'd:
# 1. Purchase number via Telnyx API.
# 2. Get the phone_number_id (Telnyx's ID for the owned number).
# 3. Update the number (using update_number_connection) to point to your Telnyx SIP Connection
#    that is configured to route to LiveKit (e.g., using Telnyx Voice API or connection settings).
#    Or, if LiveKit provides a SIP Trunk ID that Telnyx understands directly.

# The `telnyx_connection_id` in your `phone_numbers` Xano table might refer to
# the Telnyx "Connection ID" (previously "SIP Connection ID" or "Credential Connection ID")
# to which this number should be assigned for voice traffic.

async def configure_number_for_voice(
    phone_number_telnyx_id: str, # This is Telnyx's own ID for the number, e.g., "123-abc-456"
    telnyx_sip_connection_id: str, # The ID of your SIP Connection in Telnyx (e.g., that routes to LiveKit)
    api_key: Optional[str] = None # Added api_key
) -> Dict[str, Any]:
    """
    Ensures a number is configured for voice by assigning it to a specific voice-enabled SIP Connection.
    """
    logger.info(f"Configuring Telnyx number {phone_number_telnyx_id} for voice with SIP Connection {telnyx_sip_connection_id}")
    return await update_number_connection(
        phone_number_id=phone_number_telnyx_id, 
        connection_id=telnyx_sip_connection_id,
        api_key=api_key # Pass api_key
    )

# You might also need functions to:
# - List your owned numbers on Telnyx
# - Get details of a specific SIP connection
# - etc.

async def list_owned_numbers(limit: int = 100, api_key: Optional[str] = None) -> List[Dict[str, Any]]:
    """List phone numbers owned by the Telnyx account (using provided API key if given)."""
    params = {"filter[limit]": limit}
    logger.info(f"Listing owned Telnyx numbers with params: {params}")
    response_data = await _make_telnyx_request("GET", "/phone_numbers", api_key=api_key, params=params)
    return response_data.get("data", [])

async def create_sip_connection(
    connection_name: str, 
    api_key: Optional[str] = None, 
    credential_username: Optional[str] = None,
    credential_password: Optional[str] = None,
    outbound_voice_profile_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Creates a new Credential Connection on Telnyx.
    These credentials are what Telnyx expects from a SIP client (e.g., LiveKit) connecting to it.
    Can optionally assign an Outbound Voice Profile ID during creation.
    Returns the created credential connection details.
    """
    if not credential_username or not credential_password:
        raise ValueError("Both credential_username and credential_password must be provided for a credential connection.")

    payload: Dict[str, Any] = {
        "active": True,
        "connection_name": connection_name,
        "user_name": credential_username,
        "password": credential_password,
    }

    # Include OVP ID in the outbound section during creation
    if outbound_voice_profile_id:
        payload["outbound"] = {
            "outbound_voice_profile_id": int(outbound_voice_profile_id)  # Ensure it's an integer
        }
        logger.info(f"Including Outbound Voice Profile ID {outbound_voice_profile_id} in Credential Connection creation.")

    logger.info(f"Creating Telnyx Credential Connection '{connection_name}' with username: {credential_username}")
    try:
        # Use the /credential_connections endpoint
        response = await _make_telnyx_request("POST", "/credential_connections", api_key=api_key, json_data=payload)
        connection_data = response.get("data")
        if not connection_data:
            raise TelnyxServiceError("Telnyx Credential Connection created but no data returned.")

        logger.info(f"Telnyx Credential Connection '{connection_name}' created: {connection_data.get('id')}")
        return response # Returns {"data": {...connection_details...}}
    except TelnyxServiceError as e:
        logger.error(f"Error creating Telnyx Credential Connection '{connection_name}': {e}")
        raise

async def list_sip_connections( 
    api_key: Optional[str] = None,
    params: Optional[Dict[str, Any]] = None # e.g., {"filter[connection_name][eq]": "my_connection_name"}
) -> List[Dict[str, Any]]:
    """
    Lists Credential Connections on Telnyx.
    Allows filtering via params.
    """
    logger.info(f"Listing Telnyx Credential Connections with params: {params}")
    try:
        # Use the /credential_connections endpoint
        response = await _make_telnyx_request("GET", "/credential_connections", api_key=api_key, params=params)
        connections = response.get("data", [])
        logger.info(f"Found {len(connections)} Credential Connections.")
        return connections
    except NumberNotFoundError: 
        logger.info(f"No Telnyx Credential Connections found matching params: {params}. Returning empty list.")
        return []
    except TelnyxServiceError as e:
        logger.error(f"Error listing Telnyx Credential Connections: {e}")
        raise

async def get_sip_connection_details( 
    sip_connection_id: str, # This should be the ID of a credential_connection
    api_key: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Retrieves details for a specific Credential Connection on Telnyx.
    """
    if not sip_connection_id:
        raise ValueError("sip_connection_id must be provided")
    logger.info(f"Getting details for Telnyx Credential Connection ID: {sip_connection_id}")
    try:
        # Use the /credential_connections endpoint
        response = await _make_telnyx_request("GET", f"/credential_connections/{sip_connection_id}", api_key=api_key)
        connection_data = response.get("data")
        if connection_data:
            logger.info(f"Successfully fetched details for Telnyx Credential Connection {sip_connection_id}")
            return connection_data
        else:
            logger.warning(f"Telnyx Credential Connection ID {sip_connection_id} found, but response structure unexpected (missing 'data' field): {response}")
            return None
    except NumberNotFoundError: 
        logger.warning(f"Telnyx Credential Connection ID {sip_connection_id} not found.")
        return None
    except TelnyxServiceError as e:
        logger.error(f"Error getting Telnyx Credential Connection {sip_connection_id} details: {e}")
        raise

async def update_sip_connection_outbound_auth( 
    sip_connection_id: str, # ID of the credential_connection
    new_username: Optional[str] = None, 
    new_password: Optional[str] = None, 
    new_connection_name: Optional[str] = None,
    is_active: Optional[bool] = None,
    api_key: Optional[str] = None,
    outbound_voice_profile_id: Optional[str] = None  # New parameter for OVP assignment
) -> Dict[str, Any]:
    """
    Updates a specific Credential Connection on Telnyx.
    Can update username, password, connection_name, active status, and outbound voice profile.
    Telnyx expects 'user_name' for username in the payload.
    """
    if not sip_connection_id:
        raise ValueError("sip_connection_id must be provided")

    payload: Dict[str, Any] = {}
    if new_username:
        payload["user_name"] = new_username # Telnyx API uses 'user_name' for PATCH /credential_connections
    if new_password:
        payload["password"] = new_password
    if new_connection_name:
        payload["connection_name"] = new_connection_name
    if is_active is not None:
        payload["active"] = is_active
    
    # Add outbound voice profile to the outbound section
    if outbound_voice_profile_id:
        payload["outbound"] = {
            "outbound_voice_profile_id": int(outbound_voice_profile_id)  # Ensure it's an integer
        }
        logger.info(f"Including Outbound Voice Profile ID {outbound_voice_profile_id} in Credential Connection update.")
    
    if not payload:
        raise ValueError("At least one field (new_username, new_password, new_connection_name, is_active, outbound_voice_profile_id) must be provided for update.")

    logger.info(f"Updating Telnyx Credential Connection ID: {sip_connection_id} with payload: {payload}")
    try:
        # Use the /credential_connections endpoint for PATCH
        response = await _make_telnyx_request(
            "PATCH",
            f"/credential_connections/{sip_connection_id}",
            api_key=api_key,
            json_data=payload
        )
        connection_data = response.get("data")
        if connection_data:
            logger.info(f"Successfully updated Telnyx Credential Connection {sip_connection_id}.")
            # Log the outbound section to verify OVP assignment
            outbound_section = connection_data.get("outbound", {})
            if outbound_section and outbound_voice_profile_id:
                assigned_ovp_id = outbound_section.get("outbound_voice_profile_id")
                if str(assigned_ovp_id) == str(outbound_voice_profile_id):
                    logger.info(f"✅ Successfully assigned OVP {outbound_voice_profile_id} to Connection {sip_connection_id}")
                else:
                    logger.warning(f"⚠️  OVP assignment may have failed. Expected: {outbound_voice_profile_id}, Got: {assigned_ovp_id}")
            return connection_data
        else:
            logger.warning(f"Telnyx Credential Connection {sip_connection_id} update response missing 'data': {response}")
            return response # Return the raw response if 'data' is missing but no HTTP error
    except TelnyxServiceError as e:
        logger.error(f"Error updating Telnyx Credential Connection {sip_connection_id}: {e}")
        raise

async def create_call_control_application(
    application_name: str,
    webhook_event_url: str,
    api_key: Optional[str] = None,
    active: bool = True,
    anchorsite_override: str = "Latency", # "Latency" or specific site like "Chicago, IL"
    webhook_api_version: str = "2", # "1" or "2"
    # Add other optional parameters as needed from Telnyx docs
    first_sip_contact_only: Optional[bool] = None, # example optional param
    dtmf_type: str = "RFC 2833" # example optional param with default
) -> Dict[str, Any]:
    """
    Creates a Call Control Application (Voice API Application) on Telnyx.
    https://developers.telnyx.com/api/call-control/create-call-control-application
    """
    payload = {
        "application_name": application_name,
        "webhook_event_url": webhook_event_url,
        "active": active,
        "anchorsite_override": anchorsite_override,
        "webhook_api_version": webhook_api_version,
        "dtmf_type": dtmf_type
    }
    if first_sip_contact_only is not None:
        payload["first_sip_contact_only"] = first_sip_contact_only
    
    # Add more specific fields based on your screenshots or detailed needs
    # For example, "outbound.outbound_voice_profile_id" can be set here if you want to default it for the app

    logger.info(f"Creating Telnyx Call Control Application '{application_name}' with webhook URL {webhook_event_url}")
    try:
        response = await _make_telnyx_request("POST", "/call_control_applications", api_key=api_key, json_data=payload)
        # The response structure for create usually has a "data" object containing the created resource
        app_data = response.get("data")
        if not app_data:
            raise TelnyxServiceError(f"Telnyx Call Control Application '{application_name}' created but no 'data' in response.")
        
        logger.info(f"Telnyx Call Control Application '{application_name}' created successfully: ID {app_data.get('id')}")
        return response # Return the full response which includes {"data": {...}}
    except TelnyxServiceError as e:
        logger.error(f"Error creating Telnyx Call Control Application '{application_name}': {e}")
        raise

async def create_outbound_voice_profile(
    name: str,
    api_key: Optional[str] = None,
    usage_payment_method: str = "rate-deck", # Default as per Telnyx docs
    # Common optional parameters (refer to Telnyx docs for all)
    allowed_destinations: Optional[List[str]] = None, # e.g., ["US", "CA", "FR"]
    traffic_type: str = "conversational", # P2P or Conversational usually
    service_plan: str = "global", # Or other plans if you have them
    concurrent_call_limit: Optional[int] = None,
    enabled: bool = True
) -> Dict[str, Any]:
    """
    Creates an Outbound Voice Profile on Telnyx.
    https://developers.telnyx.com/api/outbound-voice-profiles/create-voice-profile
    """
    payload: Dict[str, Any] = {
        "name": name,
        "usage_payment_method": usage_payment_method,
        "traffic_type": traffic_type,
        "service_plan": service_plan,
        "enabled": enabled
    }

    if allowed_destinations is not None: # Telnyx API expects a list of country codes
        payload["whitelisted_destinations"] = allowed_destinations 
        # Updated to use correct field name from Telnyx API documentation

    if concurrent_call_limit is not None:
        payload["concurrent_call_limit"] = concurrent_call_limit

    logger.info(f"Creating Telnyx Outbound Voice Profile '{name}'")
    try:
        response = await _make_telnyx_request("POST", "/outbound_voice_profiles", api_key=api_key, json_data=payload)
        profile_data = response.get("data")
        if not profile_data:
            raise TelnyxServiceError(f"Telnyx Outbound Voice Profile '{name}' created but no 'data' in response.")
        
        logger.info(f"Telnyx Outbound Voice Profile '{name}' created successfully: ID {profile_data.get('id')}")
        return response # Return the full response
    except TelnyxServiceError as e:
        logger.error(f"Error creating Telnyx Outbound Voice Profile '{name}': {e}")
        raise

async def assign_connection_to_outbound_profile(
    outbound_voice_profile_id: str,
    connection_id: str, # This is the ID of the Credential Connection
    api_key: Optional[str] = None
) -> Dict[str, Any]:
    """
    Assigns a Credential Connection to an Outbound Voice Profile on Telnyx.
    This typically involves updating the Outbound Voice Profile to include the connection ID.
    Ref: https://developers.telnyx.com/api/outbound-voice-profiles/update-outbound-voice-profile
    The exact payload structure for 'assigned_connections' needs to be precise.
    It's often a list of objects, e.g., [{"connection_id": "uuid", "app_type": "credential_connection"}]
    """
    # First, we might need to GET the current profile to see existing assigned connections
    # if the PATCH operation for assigned_connections replaces the entire list.
    # For simplicity, if the API allows adding without knowing the existing ones, or if we assume
    # this is for a new profile, we can try a direct PATCH.
    # Let's assume we need to provide the full list of connections to assign.
    # A robust implementation would GET, append, then PATCH.
    # For this initial version, we'll PATCH with just the new connection.
    # This might overwrite existing connections if not handled carefully by the API or by fetching first.

    # The `update-outbound-voice-profile` doc shows `assigned_connections` as a field.
    # It doesn't explicitly detail the structure of each item in the array for PATCH.
    # Let's infer from common patterns and the GET response structure (if available).
    # Typically, it's an array of objects, where each object identifies the connection.
    # The type of connection might also be needed if the profile can be assigned to different kinds of apps/connections.
    
    # Based on typical Telnyx patterns for associating resources, 
    # the `assigned_connections` field in the PATCH payload for an Outbound Voice Profile
    # likely expects a list of objects, where each object contains at least the `connection_id`.
    # It might also require `app_type` or `record_type` to specify it's a 'credential_connection'.

    # For safety, let's assume we need to specify the type if known.
    # The Telnyx dashboard screenshots show "Type" for assigned connections (e.g., "FQDN Connection", "Voice API App").
    # So, it's plausible `app_type` or a similar field is needed.
    # If `create_sip_connection` creates a `credential_connection`, then that would be the type.

    assigned_connection_payload_item = {
        "id": connection_id,
        "record_type": "credential_connection" # Assuming this is the record_type for connections from create_sip_connection
    }

    payload = {
        # We are updating the assigned_connections field of the outbound_voice_profile_id
        "assigned_connections": [assigned_connection_payload_item] # Ensure this is a list containing the object
    }

    logger.info(f"Assigning Connection ID {connection_id} to Outbound Voice Profile ID {outbound_voice_profile_id}. Payload: {json.dumps(payload)}")
    try:
        response = await _make_telnyx_request(
            "PATCH", 
            f"/outbound_voice_profiles/{outbound_voice_profile_id}", 
            api_key=api_key, 
            json_data=payload
        )
        # More detailed logging of the raw response
        logger.info(f"Raw response from assigning Connection {connection_id} to OVP {outbound_voice_profile_id}. Status: {response.status_code if hasattr(response, 'status_code') else 'N/A'}. Body: {response.text if hasattr(response, 'text') else response}")

        updated_profile_data = response.get("data")
        if not updated_profile_data:
            logger.warning(f"Assigning connection to OVP {outbound_voice_profile_id} returned a response without 'data'. Raw Response was logged above.")
            return response 
        
        logger.info(f"Successfully assigned Connection to OVP. Updated OVP data ID: {updated_profile_data.get('id')}")
        # Log the assigned_connections field from the response
        assigned_connections_from_response = updated_profile_data.get("assigned_connections")
        if assigned_connections_from_response is not None: # Check for None explicitly
            logger.info(f"Telnyx OVP {outbound_voice_profile_id} - Assigned Connections from response: {json.dumps(assigned_connections_from_response, indent=2)}")
        else:
            logger.warning(f"Telnyx OVP {outbound_voice_profile_id} - 'assigned_connections' field IS NULL or MISSING in response data. Full data: {json.dumps(updated_profile_data, indent=2)}")
        
        return response # Return the full response
    except TelnyxServiceError as e:
        logger.error(f"Error assigning Connection {connection_id} to OVP {outbound_voice_profile_id}: {e}")
        raise

async def assign_number_to_call_control_application(
    phone_number_telnyx_id: str, # Telnyx ID of the phone number resource
    call_control_application_id: str, # Telnyx ID of the Call Control Application
    api_key: Optional[str] = None
) -> bool:
    """
    Assigns a phone number to a Call Control Application for inbound call routing.
    This is effectively updating the phone number's 'connection_id' to be the Call Control App ID.
    Ref: https://developers.telnyx.com/api/numbers/update-phone-number (see connection_id)
    """
    logger.info(f"Assigning Telnyx Phone Number ID {phone_number_telnyx_id} to Call Control Application ID {call_control_application_id}")
    try:
        # Use the existing update_number_connection, where the connection_id field
        # on a phone number can also point to a call_control_application_id for routing.
        updated_number_data = await update_number_connection(
            phone_number_id=phone_number_telnyx_id,
            connection_id=call_control_application_id, # Telnyx uses this field for app assignment too
            api_key=api_key
        )
        # Check if the update was successful, e.g., by verifying the response
        if updated_number_data and updated_number_data.get("id") == phone_number_telnyx_id and updated_number_data.get("connection_id") == call_control_application_id:
            logger.info(f"Successfully assigned Phone Number {phone_number_telnyx_id} to Call Control App {call_control_application_id}.")
            return True
        else:
            logger.warning(f"Assigning Phone Number {phone_number_telnyx_id} to Call Control App {call_control_application_id} completed, but response verification failed or was unexpected. Response: {updated_number_data}")
            return False # Or True if a 2xx response is considered success regardless of detailed content match
    except TelnyxServiceError as e:
        logger.error(f"Error assigning Phone Number {phone_number_telnyx_id} to Call Control App {call_control_application_id}: {e}")
        # Re-raise the error so the calling function knows it failed.
        raise 
    return False # Should not be reached if exceptions are handled

async def update_call_control_application_outbound_settings(
    call_control_application_id: str,
    outbound_voice_profile_id: str,
    api_key: Optional[str] = None
) -> Dict[str, Any]:
    """
    Updates an existing Call Control Application to use a specific Outbound Voice Profile
    for its outbound calls.
    """
    endpoint = f"/call_control_applications/{call_control_application_id}"
    payload = {
        "outbound": {
            "outbound_voice_profile_id": outbound_voice_profile_id
        }
    }
    logger.info(f"Updating Call Control Application {call_control_application_id} to use Outbound Voice Profile {outbound_voice_profile_id}")
    try:
        response_data = await _make_telnyx_request(
            method="PATCH", 
            endpoint=endpoint, 
            json_data=payload, 
            api_key=api_key
        )
        logger.info(f"Successfully updated CCA {call_control_application_id} with OVP {outbound_voice_profile_id}.")
        return response_data.get("data", {}) # Return the 'data' part of the response
    except httpx.HTTPStatusError as hse:
        logger.error(f"Telnyx API error updating Call Control Application {call_control_application_id}: {hse.response.status_code} - {hse.response.text}")
        raise TelnyxServiceError(
            message=f"Failed to update Call Control Application {call_control_application_id}",
            status_code=hse.response.status_code,
            telnyx_errors=hse.response.json().get("errors") if hse.response.content else None
        )
    except Exception as e:
        logger.error(f"Unexpected error updating Call Control Application {call_control_application_id}: {e}", exc_info=True)
        raise TelnyxServiceError(f"Unexpected error: {str(e)}")

async def delete_sip_connection(connection_id: str, api_key: Optional[str] = None) -> bool:
    """Deletes a SIP connection from Telnyx."""
    endpoint = f"/credential_connections/{connection_id}"
    logger.info(f"Attempting to delete SIP Connection ID: {connection_id}")
    try:
        await _make_telnyx_request(method="DELETE", endpoint=endpoint, api_key=api_key)
        logger.info(f"Successfully deleted SIP Connection ID: {connection_id}")
        return True
    except httpx.HTTPStatusError as hse:
        if hse.response.status_code == 404:
            logger.warning(f"SIP Connection {connection_id} not found for deletion (already deleted?).")
            return True # Treat as success if already gone
        logger.error(f"Telnyx API error deleting SIP Connection {connection_id}: {hse.response.status_code} - {hse.response.text}")
        raise TelnyxServiceError(
            message=f"Failed to delete SIP Connection {connection_id}",
            status_code=hse.response.status_code,
            telnyx_errors=hse.response.json().get("errors") if hse.response.content else None
        )
    except Exception as e:
        logger.error(f"Unexpected error deleting SIP Connection {connection_id}: {e}", exc_info=True)
        raise TelnyxServiceError(f"Unexpected error: {str(e)}")

async def delete_outbound_voice_profile(profile_id: str, api_key: Optional[str] = None) -> bool:
    """Deletes an Outbound Voice Profile from Telnyx."""
    endpoint = f"/outbound_voice_profiles/{profile_id}"
    logger.info(f"Attempting to delete Outbound Voice Profile ID: {profile_id}")
    try:
        await _make_telnyx_request(method="DELETE", endpoint=endpoint, api_key=api_key)
        logger.info(f"Successfully deleted Outbound Voice Profile ID: {profile_id}")
        return True
    except httpx.HTTPStatusError as hse:
        if hse.response.status_code == 404:
            logger.warning(f"Outbound Voice Profile {profile_id} not found for deletion (already deleted?).")
            return True # Treat as success if already gone
        logger.error(f"Telnyx API error deleting OVP {profile_id}: {hse.response.status_code} - {hse.response.text}")
        raise TelnyxServiceError(
            message=f"Failed to delete Outbound Voice Profile {profile_id}",
            status_code=hse.response.status_code,
            telnyx_errors=hse.response.json().get("errors") if hse.response.content else None
        )
    except Exception as e:
        logger.error(f"Unexpected error deleting OVP {profile_id}: {e}", exc_info=True)
        raise TelnyxServiceError(f"Unexpected error: {str(e)}")

async def delete_call_control_application(app_id: str, api_key: Optional[str] = None) -> bool:
    """Deletes a Call Control Application from Telnyx."""
    endpoint = f"/call_control_applications/{app_id}"
    logger.info(f"Attempting to delete Call Control Application ID: {app_id}")
    try:
        await _make_telnyx_request(method="DELETE", endpoint=endpoint, api_key=api_key)
        logger.info(f"Successfully deleted Call Control Application ID: {app_id}")
        return True
    except httpx.HTTPStatusError as hse:
        if hse.response.status_code == 404:
            logger.warning(f"Call Control Application {app_id} not found for deletion (already deleted?).")
            return True # Treat as success if already gone
        logger.error(f"Telnyx API error deleting CCA {app_id}: {hse.response.status_code} - {hse.response.text}")
        raise TelnyxServiceError(
            message=f"Failed to delete Call Control Application {app_id}",
            status_code=hse.response.status_code,
            telnyx_errors=hse.response.json().get("errors") if hse.response.content else None
        )
    except Exception as e:
        logger.error(f"Unexpected error deleting CCA {app_id}: {e}", exc_info=True)
        raise TelnyxServiceError(f"Unexpected error: {str(e)}")

# === INBOUND FUNCTIONS - FOLLOWING OUTBOUND PATTERNS ===

async def create_inbound_voice_profile(
    name: str,
    api_key: Optional[str] = None,
    # Same parameters as outbound profile for consistency
    usage_payment_method: str = "rate-deck",
    allowed_destinations: Optional[List[str]] = None,
    traffic_type: str = "conversational", 
    service_plan: str = "global",
    concurrent_call_limit: Optional[int] = None,
    enabled: bool = True
) -> Dict[str, Any]:
    """
    Creates an Inbound Voice Profile for handling incoming calls.
    Follows the same pattern as create_outbound_voice_profile but for inbound routing.
    """
    endpoint = "/inbound_voice_profiles"  # Note: different from outbound
    
    payload = {
        "name": name,
        "usage_payment_method": usage_payment_method,
        "traffic_type": traffic_type,
        "service_plan": service_plan,
        "enabled": enabled
    }
    
    # Add optional parameters if provided
    if allowed_destinations:
        payload["allowed_destinations"] = allowed_destinations
    if concurrent_call_limit is not None:
        payload["concurrent_call_limit"] = concurrent_call_limit
    
    logger.info(f"Creating Inbound Voice Profile: {name}")
    
    try:
        response_data = await _make_telnyx_request(
            method="POST",
            endpoint=endpoint,
            json_data=payload,
            api_key=api_key
        )
        
        profile_data = response_data.get("data")
        if not profile_data:
            raise TelnyxServiceError("No data returned when creating inbound voice profile")
        
        profile_id = profile_data.get("id")
        logger.info(f"Successfully created Inbound Voice Profile: {profile_id}")
        
        return profile_data
        
    except httpx.HTTPStatusError as hse:
        logger.error(f"Telnyx API error creating inbound voice profile: {hse.response.status_code} - {hse.response.text}")
        raise TelnyxServiceError(
            message=f"Failed to create inbound voice profile {name}",
            status_code=hse.response.status_code,
            telnyx_errors=hse.response.json().get("errors") if hse.response.content else None
        )
    except Exception as e:
        logger.error(f"Unexpected error creating inbound voice profile {name}: {e}", exc_info=True)
        raise TelnyxServiceError(f"Unexpected error: {str(e)}")

async def create_dispatch_rule(
    phone_number: str,
    inbound_voice_profile_id: str, 
    destination: str,  # LiveKit SIP trunk endpoint
    api_key: Optional[str] = None,
    rule_name: Optional[str] = None
) -> Dict[str, Any]:
    """
    Creates a Dispatch Rule to route incoming calls from a specific number to a destination.
    This is the inbound equivalent of outbound voice profile assignment.
    """
    endpoint = "/dispatch_rules"
    
    # Generate a rule name if not provided
    if not rule_name:
        rule_name = f"Inbound rule for {phone_number}"
    
    payload = {
        "name": rule_name,
        "match": {
            "from": phone_number  # Match calls TO this number (inbound)
        },
        "destination": destination,  # Where to route the call (LiveKit SIP trunk)
        "inbound_voice_profile_id": inbound_voice_profile_id
    }
    
    logger.info(f"Creating Dispatch Rule for number {phone_number} -> {destination}")
    
    try:
        response_data = await _make_telnyx_request(
            method="POST",
            endpoint=endpoint,
            json_data=payload,
            api_key=api_key
        )
        
        rule_data = response_data.get("data")
        if not rule_data:
            raise TelnyxServiceError("No data returned when creating dispatch rule")
        
        rule_id = rule_data.get("id")
        logger.info(f"Successfully created Dispatch Rule: {rule_id}")
        
        return rule_data
        
    except httpx.HTTPStatusError as hse:
        logger.error(f"Telnyx API error creating dispatch rule: {hse.response.status_code} - {hse.response.text}")
        raise TelnyxServiceError(
            message=f"Failed to create dispatch rule for {phone_number}",
            status_code=hse.response.status_code,
            telnyx_errors=hse.response.json().get("errors") if hse.response.content else None
        )
    except Exception as e:
        logger.error(f"Unexpected error creating dispatch rule for {phone_number}: {e}", exc_info=True)
        raise TelnyxServiceError(f"Unexpected error: {str(e)}")

async def configure_number_for_inbound(
    phone_number_telnyx_id: str,
    inbound_voice_profile_id: str,
    api_key: Optional[str] = None
) -> Dict[str, Any]:
    """
    Configures a phone number for inbound calls by assigning it to an inbound voice profile.
    This is the inbound equivalent of configure_number_for_voice.
    """
    endpoint = f"/phone_numbers/{phone_number_telnyx_id}"
    
    payload = {
        "inbound_voice_profile_id": inbound_voice_profile_id,
        "call_forwarding_enabled": True,  # Enable call forwarding for inbound
        "call_recording_enabled": False   # Can be configured as needed
    }
    
    logger.info(f"Configuring number {phone_number_telnyx_id} for inbound with profile {inbound_voice_profile_id}")
    
    try:
        response_data = await _make_telnyx_request(
            method="PATCH",
            endpoint=endpoint,
            json_data=payload,
            api_key=api_key
        )
        
        number_data = response_data.get("data")
        if not number_data:
            raise TelnyxServiceError("No data returned when configuring number for inbound")
        
        logger.info(f"Successfully configured number for inbound: {phone_number_telnyx_id}")
        
        return number_data
        
    except httpx.HTTPStatusError as hse:
        logger.error(f"Telnyx API error configuring number for inbound: {hse.response.status_code} - {hse.response.text}")
        raise TelnyxServiceError(
            message=f"Failed to configure number {phone_number_telnyx_id} for inbound",
            status_code=hse.response.status_code,
            telnyx_errors=hse.response.json().get("errors") if hse.response.content else None
        )
    except Exception as e:
        logger.error(f"Unexpected error configuring number for inbound {phone_number_telnyx_id}: {e}", exc_info=True)
        raise TelnyxServiceError(f"Unexpected error: {str(e)}")

async def list_inbound_voice_profiles(api_key: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Lists all inbound voice profiles.
    Follows same pattern as list_owned_numbers.
    """
    endpoint = "/inbound_voice_profiles"
    
    logger.info("Fetching inbound voice profiles")
    
    try:
        response_data = await _make_telnyx_request(
            method="GET",
            endpoint=endpoint,
            api_key=api_key
        )
        
        profiles = response_data.get("data", [])
        logger.info(f"Found {len(profiles)} inbound voice profiles")
        
        return profiles
        
    except httpx.HTTPStatusError as hse:
        logger.error(f"Telnyx API error listing inbound voice profiles: {hse.response.status_code} - {hse.response.text}")
        raise TelnyxServiceError(
            message="Failed to list inbound voice profiles",
            status_code=hse.response.status_code,
            telnyx_errors=hse.response.json().get("errors") if hse.response.content else None
        )
    except Exception as e:
        logger.error(f"Unexpected error listing inbound voice profiles: {e}", exc_info=True)
        raise TelnyxServiceError(f"Unexpected error: {str(e)}")

async def list_dispatch_rules(api_key: Optional[str] = None, phone_number_filter: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Lists dispatch rules, optionally filtered by phone number.
    Follows same pattern as list_sip_connections.
    """
    endpoint = "/dispatch_rules"
    params = {}
    
    if phone_number_filter:
        params["filter[from]"] = phone_number_filter
    
    logger.info(f"Fetching dispatch rules{f' for number {phone_number_filter}' if phone_number_filter else ''}")
    
    try:
        response_data = await _make_telnyx_request(
            method="GET",
            endpoint=endpoint,
            params=params if params else None,
            api_key=api_key
        )
        
        rules = response_data.get("data", [])
        logger.info(f"Found {len(rules)} dispatch rules")
        
        return rules
        
    except httpx.HTTPStatusError as hse:
        logger.error(f"Telnyx API error listing dispatch rules: {hse.response.status_code} - {hse.response.text}")
        raise TelnyxServiceError(
            message="Failed to list dispatch rules",
            status_code=hse.response.status_code,
            telnyx_errors=hse.response.json().get("errors") if hse.response.content else None
        )
    except Exception as e:
        logger.error(f"Unexpected error listing dispatch rules: {e}", exc_info=True)
        raise TelnyxServiceError(f"Unexpected error: {str(e)}")

async def delete_inbound_voice_profile(profile_id: str, api_key: Optional[str] = None) -> bool:
    """
    Deletes an Inbound Voice Profile from Telnyx.
    Follows same pattern as delete_outbound_voice_profile.
    """
    endpoint = f"/inbound_voice_profiles/{profile_id}"
    logger.info(f"Attempting to delete Inbound Voice Profile ID: {profile_id}")
    
    try:
        await _make_telnyx_request(method="DELETE", endpoint=endpoint, api_key=api_key)
        logger.info(f"Successfully deleted Inbound Voice Profile ID: {profile_id}")
        return True
        
    except httpx.HTTPStatusError as hse:
        if hse.response.status_code == 404:
            logger.warning(f"Inbound Voice Profile {profile_id} not found for deletion (already deleted?).")
            return True  # Treat as success if already gone
        logger.error(f"Telnyx API error deleting IVP {profile_id}: {hse.response.status_code} - {hse.response.text}")
        raise TelnyxServiceError(
            message=f"Failed to delete Inbound Voice Profile {profile_id}",
            status_code=hse.response.status_code,
            telnyx_errors=hse.response.json().get("errors") if hse.response.content else None
        )
    except Exception as e:
        logger.error(f"Unexpected error deleting IVP {profile_id}: {e}", exc_info=True)
        raise TelnyxServiceError(f"Unexpected error: {str(e)}")

async def delete_dispatch_rule(rule_id: str, api_key: Optional[str] = None) -> bool:
    """
    Deletes a Dispatch Rule from Telnyx.
    Follows same pattern as delete_call_control_application.
    """
    endpoint = f"/dispatch_rules/{rule_id}"
    logger.info(f"Attempting to delete Dispatch Rule ID: {rule_id}")
    
    try:
        await _make_telnyx_request(method="DELETE", endpoint=endpoint, api_key=api_key)
        logger.info(f"Successfully deleted Dispatch Rule ID: {rule_id}")
        return True
        
    except httpx.HTTPStatusError as hse:
        if hse.response.status_code == 404:
            logger.warning(f"Dispatch Rule {rule_id} not found for deletion (already deleted?).")
            return True  # Treat as success if already gone
        logger.error(f"Telnyx API error deleting Dispatch Rule {rule_id}: {hse.response.status_code} - {hse.response.text}")
        raise TelnyxServiceError(
            message=f"Failed to delete Dispatch Rule {rule_id}",
            status_code=hse.response.status_code,
            telnyx_errors=hse.response.json().get("errors") if hse.response.content else None
        )
    except Exception as e:
        logger.error(f"Unexpected error deleting Dispatch Rule {rule_id}: {e}", exc_info=True)
        raise TelnyxServiceError(f"Unexpected error: {str(e)}")

# ===== FQDN SIP CONNECTION FUNCTIONS (Phase 1: Bidirectional Support) =====

async def create_fqdn_sip_connection(
    connection_name: str,
    sip_subdomain: Optional[str] = None,
    api_key: Optional[str] = None
) -> Dict[str, Any]:
    """
    Creates a new FQDN-based SIP Connection on Telnyx for bidirectional calling.
    Unlike credential connections, FQDN connections can handle both inbound and outbound.
    
    Returns the created FQDN connection details including the specified SIP subdomain.
    """
    # Generate a unique SIP subdomain if not provided
    if not sip_subdomain:
        import uuid
        sip_subdomain = f"pam{uuid.uuid4().hex[:8]}"
    
    payload = {
        "connection_name": connection_name,
        "sip_subdomain": sip_subdomain,  # Add SIP subdomain during creation
        "sip_subdomain_receive_settings": "from_anyone",  # Enable SIP subdomain to receive calls from anyone
        "active": True,
        "anchorsite_override": "Latency",
        "transport_protocol": "TCP",
        "inbound": {
            "ani_number_format": "+E.164",
            "dnis_number_format": "+e164",
            "sip_subdomain": sip_subdomain,  # SIP subdomain for inbound
            "sip_subdomain_receive_settings": "from_anyone"  # Enable receiving from anyone
        }
    }
    
    logger.info(f"Creating Telnyx FQDN Connection '{connection_name}' with payload: {payload}")
    try:
        # Use the /fqdn_connections endpoint
        response = await _make_telnyx_request("POST", "/fqdn_connections", api_key=api_key, json_data=payload)
        connection_data = response.get("data")
        if not connection_data:
            raise TelnyxServiceError("Telnyx FQDN Connection created but no data returned.")
        
        connection_id = connection_data.get("id")
        # Extract the SIP subdomain from the response (it's in the inbound section)
        inbound_data = connection_data.get("inbound", {})
        response_sip_subdomain = inbound_data.get("sip_subdomain")
        
        logger.info(f"Telnyx FQDN Connection '{connection_name}' created successfully: ID {connection_id}")
        logger.info(f"SIP subdomain: {response_sip_subdomain}")
        logger.info(f"Full FQDN connection response: {connection_data}")
        
        # Check if SIP subdomain was actually set (look in inbound section)
        if not response_sip_subdomain and sip_subdomain:
            logger.error(f"❌ SIP SUBDOMAIN NOT SET! Requested: {sip_subdomain}, Got: {response_sip_subdomain}")
            logger.error(f"Inbound section: {inbound_data}")
        elif response_sip_subdomain:
            logger.info(f"✅ SIP subdomain confirmed: {response_sip_subdomain}")
        else:
            logger.info("ℹ️ No SIP subdomain requested")
        
        return response # Returns {"data": {...connection_details...}}
    except TelnyxServiceError as e:
        logger.error(f"Error creating Telnyx FQDN Connection '{connection_name}': {e}")
        raise

async def create_fqdn_record(
    fqdn_connection_id: str,
    fqdn: str,  # LiveKit SIP URI (e.g., "your-project.livekit.cloud")
    port: int = 5060,
    dns_record_type: str = "a",
    api_key: Optional[str] = None
) -> Dict[str, Any]:
    """
    Creates an FQDN record for the FQDN connection to route inbound calls to LiveKit.
    This tells Telnyx where to send inbound SIP calls.
    """
    payload = {
        "connection_id": fqdn_connection_id,
        "fqdn": fqdn,
        "dns_record_type": dns_record_type,
        "port": port
    }
    
    logger.info(f"Creating FQDN record for connection {fqdn_connection_id}: {fqdn}:{port}")
    try:
        response = await _make_telnyx_request("POST", "/fqdns", api_key=api_key, json_data=payload)
        fqdn_data = response.get("data")
        if not fqdn_data:
            raise TelnyxServiceError("Telnyx FQDN record created but no data returned.")
        
        fqdn_id = fqdn_data.get("id")
        logger.info(f"FQDN record created successfully: ID {fqdn_id} for {fqdn}:{port}")
        return response
    except TelnyxServiceError as e:
        logger.error(f"Error creating FQDN record for connection {fqdn_connection_id}: {e}")
        raise

async def configure_fqdn_inbound_settings(
    fqdn_connection_id: str,
    sip_subdomain: str,  # Add SIP subdomain parameter
    ani_number_format: str = "+E.164",  # Valid Telnyx format
    dnis_number_format: str = "+e164", # Valid Telnyx format 
    sip_region: str = "europe",
    transport_protocol: str = "TCP",
    api_key: Optional[str] = None
) -> Dict[str, Any]:
    """
    Configures inbound settings for FQDN connection.
    Sets number formats, SIP region, and transport protocol for inbound calls.
    """
    endpoint = f"/fqdn_connections/{fqdn_connection_id}"
    payload = {
        "inbound": {
            "ani_number_format": ani_number_format,
            "dnis_number_format": dnis_number_format,
            "sip_region": sip_region,
            "sip_transport_protocol": transport_protocol.lower(),
            "sip_subdomain": sip_subdomain,  # Set SIP subdomain for inbound
            "sip_subdomain_receive_settings": "from_anyone"  # Enable receiving from anyone
        }
    }
    
    logger.info(f"Configuring inbound settings for FQDN Connection {fqdn_connection_id}")
    logger.info(f"  ANI/DNIS format: {ani_number_format}, Region: {sip_region}, Protocol: {transport_protocol}")
    logger.info(f"  Payload: {payload}")
    try:
        response = await _make_telnyx_request("PATCH", endpoint, api_key=api_key, json_data=payload)
        logger.info(f"Successfully configured inbound settings for FQDN Connection {fqdn_connection_id}")
        response_data = response.get("data", {})
        logger.info(f"Inbound settings response: {response_data}")
        return response_data
    except TelnyxServiceError as e:
        logger.error(f"Error configuring inbound settings for FQDN Connection {fqdn_connection_id}: {e}")
        raise

async def configure_fqdn_outbound_settings(
    fqdn_connection_id: str,
    outbound_voice_profile_id: str,
    auth_username: str,
    auth_password: str,
    api_key: Optional[str] = None
) -> Dict[str, Any]:
    """
    Configures outbound settings for FQDN connection.
    Assigns outbound voice profile and sets authentication credentials.
    """
    endpoint = f"/fqdn_connections/{fqdn_connection_id}"
    payload = {
        "outbound": {
            "outbound_voice_profile_id": outbound_voice_profile_id,
            "ani_override_type": "always",
            "generate_ringback_tone": False,
            "fqdn_authentication_method": "credential-authentication"  # Outbound uses credential auth
        },
        # Credential authentication requires username/password for outbound calls
        "user_name": auth_username,
        "password": auth_password
    }
    
    logger.info(f"Configuring outbound settings for FQDN Connection {fqdn_connection_id}")
    logger.info(f"  OVP ID: {outbound_voice_profile_id}, Username: {auth_username}")
    logger.info(f"  Payload: {payload}")
    try:
        response = await _make_telnyx_request("PATCH", endpoint, api_key=api_key, json_data=payload)
        logger.info(f"Successfully configured outbound settings for FQDN Connection {fqdn_connection_id}")
        return response.get("data", {})
    except TelnyxServiceError as e:
        logger.error(f"Error configuring outbound settings for FQDN Connection {fqdn_connection_id}: {e}")
        raise

async def assign_number_to_fqdn_connection(
    phone_number_telnyx_id: str,
    fqdn_connection_id: str,
    api_key: Optional[str] = None
) -> Dict[str, Any]:
    """
    Assigns a phone number to an FQDN connection for bidirectional routing.
    This replaces the number assignment to Call Control Applications.
    """
    endpoint = f"/phone_numbers/{phone_number_telnyx_id}"
    payload = {
        "connection_id": fqdn_connection_id
    }
    
    logger.info(f"Assigning phone number {phone_number_telnyx_id} to FQDN Connection {fqdn_connection_id}")
    try:
        response = await _make_telnyx_request("PATCH", endpoint, api_key=api_key, json_data=payload)
        updated_number_data = response.get("data")
        
        if updated_number_data and updated_number_data.get("connection_id") == fqdn_connection_id:
            logger.info(f"Successfully assigned phone number {phone_number_telnyx_id} to FQDN Connection {fqdn_connection_id}")
            return updated_number_data
        else:
            logger.warning(f"Number assignment completed but response verification failed. Response: {updated_number_data}")
            return updated_number_data or {}
    except TelnyxServiceError as e:
        logger.error(f"Error assigning phone number {phone_number_telnyx_id} to FQDN Connection {fqdn_connection_id}: {e}")
        raise

async def update_fqdn_sip_subdomain(
    fqdn_connection_id: str,
    sip_subdomain: str,
    api_key: Optional[str] = None
) -> Dict[str, Any]:
    """
    Updates an FQDN connection to enable SIP subdomain using the official Telnyx API.
    Reference: https://developers.telnyx.com/api/connections/update-fqdn-connection
    
    PATCH /fqdn_connections/{id} - Updates settings of an existing FQDN connection.
    """
    logger.info(f"Updating FQDN Connection {fqdn_connection_id} to enable SIP subdomain: {sip_subdomain}")
    
    try:
        endpoint = f"/fqdn_connections/{fqdn_connection_id}"
        
        # Payload structure based on Telnyx FQDN connection update API
        payload = {
            "sip_subdomain": sip_subdomain,
            "sip_subdomain_receive_settings": "from_anyone"
        }
        
        logger.info(f"🔄 PATCH {endpoint}")
        logger.info(f"📤 Update payload: {payload}")
        
        # Make the PATCH request to update the FQDN connection
        response = await _make_telnyx_request("PATCH", endpoint, api_key=api_key, json_data=payload)
        
        # Check the response (SIP subdomain is in the inbound section)
        updated_data = response.get("data")
        if updated_data:
            inbound_data = updated_data.get("inbound", {})
            response_sip_subdomain = inbound_data.get("sip_subdomain")
            sip_subdomain_receive_settings = inbound_data.get("sip_subdomain_receive_settings")
            
            logger.info(f"📥 Update response received:")
            logger.info(f"   - SIP subdomain: {response_sip_subdomain}")
            logger.info(f"   - SIP subdomain receive settings: {sip_subdomain_receive_settings}")
            logger.info(f"   - Full response data: {updated_data}")
            
            if response_sip_subdomain:
                logger.info(f"✅ SIP subdomain successfully updated: {response_sip_subdomain}")
            else:
                logger.warning(f"⚠️ SIP subdomain not found in inbound section. Inbound data: {inbound_data}")
        else:
            logger.warning(f"⚠️ No data in update response: {response}")
        
        return response
        
    except TelnyxServiceError as e:
        logger.error(f"❌ Telnyx API error updating FQDN Connection {fqdn_connection_id}: {e}")
        raise
    except Exception as e:
        logger.error(f"❌ Unexpected error updating FQDN Connection {fqdn_connection_id}: {str(e)}")
        raise TelnyxServiceError(f"Failed to update FQDN connection: {str(e)}")

async def get_fqdn_connection_details(
    fqdn_connection_id: str,
    api_key: Optional[str] = None
) -> Dict[str, Any]:
    """
    Retrieves detailed information about an FQDN Connection including the generated SIP subdomain.
    """
    logger.info(f"Retrieving details for FQDN Connection: {fqdn_connection_id}")
    try:
        endpoint = f"/fqdn_connections/{fqdn_connection_id}"
        response = await _make_telnyx_request("GET", endpoint, api_key=api_key)
        connection_data = response.get("data")
        if not connection_data:
            raise TelnyxServiceError(f"FQDN Connection {fqdn_connection_id} not found or no data returned.")
        
        # Extract SIP subdomain from the response
        logger.info(f"FQDN Connection response data: {connection_data}")
        sip_subdomain = connection_data.get("sip_subdomain") or connection_data.get("fqdn")
        if sip_subdomain:
            logger.info(f"FQDN Connection {fqdn_connection_id} SIP subdomain: {sip_subdomain}")
        else:
            logger.warning(f"No SIP subdomain found in FQDN connection response. Available fields: {list(connection_data.keys())}")
        
        return connection_data
    except TelnyxServiceError as e:
        logger.error(f"Error retrieving FQDN Connection {fqdn_connection_id}: {e}")
        raise

async def list_fqdn_connections(
    api_key: Optional[str] = None,
    params: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """
    Lists FQDN Connections on Telnyx.
    Allows filtering via params.
    """
    logger.info(f"Listing Telnyx FQDN Connections with params: {params}")
    try:
        response = await _make_telnyx_request("GET", "/fqdn_connections", api_key=api_key, params=params)
        connections = response.get("data", [])
        logger.info(f"Found {len(connections)} FQDN Connections.")
        return connections
    except TelnyxServiceError as e:
        logger.info(f"No Telnyx FQDN Connections found matching params: {params}. Returning empty list.")
        return []

async def delete_fqdn_connection(
    fqdn_connection_id: str,
    api_key: Optional[str] = None
) -> bool:
    """
    Deletes an FQDN Connection from Telnyx.
    Used for cleanup during migration or when removing bidirectional support.
    """
    endpoint = f"/fqdn_connections/{fqdn_connection_id}"
    logger.info(f"Attempting to delete FQDN Connection ID: {fqdn_connection_id}")
    try:
        await _make_telnyx_request(method="DELETE", endpoint=endpoint, api_key=api_key)
        logger.info(f"Successfully deleted FQDN Connection ID: {fqdn_connection_id}")
        return True
    except httpx.HTTPStatusError as hse:
        if hse.response.status_code == 404:
            logger.warning(f"FQDN Connection {fqdn_connection_id} not found for deletion (already deleted?).")
            return True # Treat as success if already gone
        logger.error(f"Telnyx API error deleting FQDN Connection {fqdn_connection_id}: {hse.response.status_code} - {hse.response.text}")
        raise TelnyxServiceError(
            message=f"Failed to delete FQDN Connection {fqdn_connection_id}",
            status_code=hse.response.status_code,
            telnyx_errors=hse.response.json().get("errors") if hse.response.content else None
        )
    except Exception as e:
        logger.error(f"Unexpected error deleting FQDN Connection {fqdn_connection_id}: {e}", exc_info=True)
        raise TelnyxServiceError(f"Unexpected error: {str(e)}")

# ===== END FQDN FUNCTIONS ===== 