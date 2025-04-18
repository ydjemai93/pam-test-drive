import requests
from fastapi import HTTPException, status

from app.core.config import settings

async def verify_xano_token(token: str) -> dict:
    """Calls Xano's /auth/me endpoint to validate the token and get user details."""
    # --- Use settings again (but ensure it's correct) --- 
    auth_me_url = f"{settings.XANO_API_BASE_URL}/auth/me"
    # --- REMOVED DEBUG PRINTS ---
    headers = {
        "Authorization": f"Bearer {token}",
        # Note: We don't need the backend's XANO_API_KEY here, 
        # as we are authenticating as the user.
    }
    # --- REMOVED DEBUG PRINTS ---
    # print(f"[DEBUG] Calling Xano /auth/me URL: '{auth_me_url}'")
    # print(f"[DEBUG] Using Authorization Header: '{headers['Authorization']}'")
    # --- END REMOVED ---

    try:
        response = requests.get(auth_me_url, headers=headers)
        response.raise_for_status() # Raise an exception for bad status codes (4xx or 5xx)
        
        user_data = response.json()
        if not user_data or 'id' not in user_data:
             raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid user data received from Xano",
            )
        return user_data # Should contain user id, email, etc.

    except requests.exceptions.RequestException as e:
        # Log the error details for debugging?
        print(f"Error verifying Xano token: {e}") 
        if e.response is not None:
            if e.response.status_code == 401:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid or expired token",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            else:
                 raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=f"Error communicating with authentication service: {e.response.status_code}",
                )
        else:
            # Network error or other issue
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Could not connect to authentication service",
            ) 

# --- Agent CRUD Operations ---

def _get_xano_backend_headers() -> dict:
    """Returns headers for backend-to-Xano authentication."""
    return {
        "Authorization": f"Bearer {settings.XANO_API_KEY}",
        "Content-Type": "application/json"
    }

def _handle_xano_error(e: requests.exceptions.RequestException, operation: str):
    """Generic handler for Xano request errors."""
    print(f"Xano API Error ({operation}): {e}")
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    detail = f"Error communicating with data service during {operation}"
    if e.response is not None:
        status_code = e.response.status_code # Use Xano's status if available
        try:
            # Try to get a more specific error from Xano response
            xano_error = e.response.json()
            detail = xano_error.get('message', detail)
        except requests.exceptions.JSONDecodeError:
            pass # Keep the generic detail
        # Special case for not found during get/update/delete
        if status_code == 404 and operation != 'create':
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Agent not found")

    raise HTTPException(status_code=status_code, detail=detail)


async def create_agent_in_xano(agent_data: dict, user_id: int) -> dict:
    """Creates an agent record in Xano."""
    # create_url = f"{settings.XANO_API_BASE_URL}/agents"
    create_url = "https://x8ki-letl-twmt.n7.xano.io/api:BylZxBJT/agents" # FORCE CORRECT URL
    headers = _get_xano_backend_headers()
    payload = agent_data.copy()
    payload['user_id'] = user_id # Add the owner ID

    try:
        response = requests.post(create_url, headers=headers, json=payload)
        response.raise_for_status()
        return response.json() # Return the created agent data from Xano
    except requests.exceptions.RequestException as e:
        _handle_xano_error(e, "create agent")

async def get_agents_from_xano(user_id: int) -> list[dict]:
    """Retrieves agents for a specific user from Xano."""
    # get_url = f"{settings.XANO_API_BASE_URL}/agents"
    get_url = "https://x8ki-letl-twmt.n7.xano.io/api:BylZxBJT/agents" # FORCE CORRECT URL
    headers = _get_xano_backend_headers()
    # IMPORTANT: Assuming Xano endpoint is configured to filter by user_id based on backend auth
    # OR that it accepts a filter parameter like `?user_id={user_id}`.
    # If Xano filters based on the calling user (via backend key), we might not need to send user_id.
    # Let's assume for now Xano needs a filter. Adjust if necessary.
    params = {"user_id_filter": user_id} # Example param name, ADJUST BASED ON YOUR XANO ENDPOINT

    try:
        # You might need to adjust how you filter by user_id depending on your Xano API setup.
        # Common ways in Xano:
        # 1. Modify Endpoint Logic: Add logic to filter by user_id if provided in params/body.
        # 2. Specific Endpoint: Create an endpoint like `/my_agents` that automatically filters.
        # 3. Standard Query Params: Use Xano's built-in query features if enabled.
        response = requests.get(get_url, headers=headers, params=params)
        response.raise_for_status()
        return response.json() # Returns a list of agents
    except requests.exceptions.RequestException as e:
        _handle_xano_error(e, "get agents")

async def get_agent_by_id_from_xano(agent_id: int, user_id: int) -> dict | None:
    """Retrieves a specific agent by ID from Xano, ensuring user ownership."""
    # get_url = f"{settings.XANO_API_BASE_URL}/agents/{agent_id}"
    get_url = f"https://x8ki-letl-twmt.n7.xano.io/api:BylZxBJT/agents/{agent_id}" # FORCE CORRECT URL
    headers = _get_xano_backend_headers()

    try:
        response = requests.get(get_url, headers=headers)
        response.raise_for_status()
        agent = response.json()
        # SECURITY CHECK: Verify the agent belongs to the requesting user
        if agent.get('user_id') != user_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found") # Or 403 Forbidden
        return agent
    except requests.exceptions.RequestException as e:
        _handle_xano_error(e, "get agent by id")

async def update_agent_in_xano(agent_id: int, update_data: dict, user_id: int) -> dict:
    """Updates an agent in Xano, ensuring user ownership."""
    # First, verify ownership by getting the agent
    await get_agent_by_id_from_xano(agent_id, user_id)
    
    # update_url = f"{settings.XANO_API_BASE_URL}/agents/{agent_id}"
    update_url = f"https://x8ki-letl-twmt.n7.xano.io/api:BylZxBJT/agents/{agent_id}" # FORCE CORRECT URL
    headers = _get_xano_backend_headers()
    payload = update_data.copy()

    try:
        response = requests.patch(update_url, headers=headers, json=payload) # Using PATCH for partial updates
        response.raise_for_status()
        return response.json() # Return the updated agent data
    except requests.exceptions.RequestException as e:
        _handle_xano_error(e, "update agent")

async def delete_agent_in_xano(agent_id: int, user_id: int) -> None:
    """Deletes an agent from Xano, ensuring user ownership."""
    # First, verify ownership
    await get_agent_by_id_from_xano(agent_id, user_id)

    # delete_url = f"{settings.XANO_API_BASE_URL}/agents/{agent_id}"
    delete_url = f"https://x8ki-letl-twmt.n7.xano.io/api:BylZxBJT/agents/{agent_id}" # FORCE CORRECT URL
    headers = _get_xano_backend_headers()

    try:
        response = requests.delete(delete_url, headers=headers)
        response.raise_for_status()
        # No content to return on successful delete
        return None
    except requests.exceptions.RequestException as e:
        _handle_xano_error(e, "delete agent")

# --- Call Log CRUD Operations ---

async def create_call_record_in_xano(call_data: dict) -> dict:
    """Creates a call record in Xano."""
    # Use the correct URL based on settings or hardcoded if needed
    # create_url = f"{settings.XANO_API_BASE_URL}/calls"
    create_url = "https://x8ki-letl-twmt.n7.xano.io/api:BylZxBJT/calls" # FORCE CORRECT URL for now
    headers = _get_xano_backend_headers()
    payload = call_data.copy()

    try:
        response = requests.post(create_url, headers=headers, json=payload)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        # Use the generic error handler, adjust if specific call errors needed
        _handle_xano_error(e, "create call record") 

async def update_call_record_in_xano(telnyx_call_control_id: str, update_data: dict) -> dict | None:
    """Updates a call record in Xano based on Telnyx Call Control ID."""
    # We need a way to find the Xano record ID from the Telnyx ID.
    # Option 1: Xano endpoint allows query by telnyx_call_control_id
    # Option 2: Xano endpoint allows update via telnyx_call_control_id (PATCH /calls?telnyx_id=...)
    # Option 3: We first query Xano for the record, get its ID, then PATCH by ID.
    
    # Let's assume Option 1 or 2 for now: Xano endpoint can find/update by Telnyx ID
    # This requires a specific Xano endpoint setup.
    # Example: PATCH /calls/by_telnyx_id/{telnyx_call_control_id}
    # update_url = f"{settings.XANO_API_BASE_URL}/calls/by_telnyx_id/{telnyx_call_control_id}" 
    # OR maybe PATCH /calls with a query param:
    # update_url = f"{settings.XANO_API_BASE_URL}/calls"
    # params = {"telnyx_call_control_id": telnyx_call_control_id} # Example

    # --- TEMPORARY: Assuming update via record ID (less efficient but works if GET exists) ---
    print(f"Attempting to update call record for Telnyx ID: {telnyx_call_control_id}")
    get_url = "https://x8ki-letl-twmt.n7.xano.io/api:BylZxBJT/calls" # FORCE CORRECT URL
    headers = _get_xano_backend_headers()
    params = {"telnyx_call_control_id_filter": telnyx_call_control_id} # ADJUST PARAM NAME
    xano_call_id = None
    try:
        get_response = requests.get(get_url, headers=headers, params=params)
        get_response.raise_for_status()
        results = get_response.json()
        if results and len(results) == 1:
            xano_call_id = results[0].get('id')
        else:
            print(f"WARN: Could not find unique call record in Xano for Telnyx ID {telnyx_call_control_id}. Found: {len(results)} results.")
            return None # Don't proceed with update if record not found
    except requests.exceptions.RequestException as e:
         _handle_xano_error(e, f"find call record for update (Telnyx ID: {telnyx_call_control_id})")
         return None # Don't proceed

    if not xano_call_id:
        return None

    # Now update by Xano ID
    update_url_by_id = f"https://x8ki-letl-twmt.n7.xano.io/api:BylZxBJT/calls/{xano_call_id}"
    try:
        response = requests.patch(update_url_by_id, headers=headers, json=update_data)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        _handle_xano_error(e, f"update call record (Xano ID: {xano_call_id})")
        return None
    # --- END TEMPORARY ---

async def get_calls_from_xano(user_id: int) -> list[dict]:
    """Retrieves call history for a specific user from Xano."""
    # get_url = f"{settings.XANO_API_BASE_URL}/calls"
    get_url = "https://x8ki-letl-twmt.n7.xano.io/api:BylZxBJT/calls" # FORCE CORRECT URL for now
    headers = _get_xano_backend_headers()
    # Assuming the /calls endpoint in Xano is configured to filter by user_id 
    # based on the backend API key, or requires a user_id param.
    params = {"user_id_filter": user_id} # Example param name, ADJUST BASED ON YOUR XANO ENDPOINT
    
    try:
        response = requests.get(get_url, headers=headers, params=params)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        _handle_xano_error(e, "get call history")
        return [] # Return empty list on error 