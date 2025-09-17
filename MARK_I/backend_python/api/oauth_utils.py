"""
OAuth utility functions for managing app connections and token refresh
"""
import asyncio
import aiohttp
from datetime import datetime, timedelta
from typing import Dict, Any, Tuple, Optional
from .db_client import get_supabase_anon_client
from .crypto_utils import decrypt_credentials, encrypt_credentials, is_token_expired
import os

# OAuth configurations for token refresh
OAUTH_CONFIGS = {
    "hubspot": {
        "token_url": "https://api.hubapi.com/oauth/v1/token",
        "client_id": os.getenv("HUBSPOT_CLIENT_ID"),
        "client_secret": os.getenv("HUBSPOT_CLIENT_SECRET")
    },
    "google_calendar": {
        "token_url": "https://oauth2.googleapis.com/token",
        "client_id": os.getenv("GOOGLE_CLIENT_ID"),
        "client_secret": os.getenv("GOOGLE_CLIENT_SECRET")
    },
    "calendly": {
        "token_url": "https://auth.calendly.com/oauth/token",
        "client_id": os.getenv("CALENDLY_CLIENT_ID"),
        "client_secret": os.getenv("CALENDLY_CLIENT_SECRET")
    },
    "salesforce": {
        "token_url": "https://login.salesforce.com/services/oauth2/token",
        "client_id": os.getenv("SALESFORCE_CLIENT_ID"),
        "client_secret": os.getenv("SALESFORCE_CLIENT_SECRET")
    },
    "slack": {
        "token_url": "https://slack.com/api/oauth.v2.access",
        "client_id": os.getenv("SLACK_CLIENT_ID"),
        "client_secret": os.getenv("SLACK_CLIENT_SECRET")
    }
}

async def get_user_connection_with_valid_creds(connection_id: str, user_id: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Get user connection with valid credentials (refresh if needed)
    
    Args:
        connection_id: ID of the user's app connection
        user_id: ID of the user (for security verification)
        
    Returns:
        Tuple of (connection_data, valid_credentials)
    """
    supabase = get_supabase_anon_client()
    
    # Get connection with app integration details
    result = supabase.table("user_app_connections").select("""
        *,
        app_integrations!inner (
            name,
            display_name,
            auth_type
        )
    """).eq("id", connection_id).eq("user_id", user_id).execute()
    
    if not result.data:
        raise Exception("Connection not found or access denied")
        
    connection = result.data[0]
    
    # Decrypt credentials
    encrypted_credentials = connection["credentials"]
    credentials = decrypt_credentials(encrypted_credentials)
    
    # Check if token needs refresh
    app_name = connection["app_integrations"]["name"]
    
    if is_token_expired(credentials) and credentials.get("refresh_token"):
        print(f"Token expired for {app_name}, refreshing...")
        credentials = await refresh_oauth_token(connection)
    
    return connection, credentials

async def refresh_oauth_token(connection: Dict[str, Any]) -> Dict[str, Any]:
    """
    Refresh OAuth token for a connection
    
    Args:
        connection: User app connection data from database
        
    Returns:
        Updated credentials dictionary
    """
    # Defensive check for app_integrations data
    app_integrations = connection.get("app_integrations")
    if not app_integrations:
        raise Exception(f"No app integration data found for connection {connection.get('id', 'unknown')}")
    
    app_name = app_integrations.get("name")
    if not app_name:
        raise Exception(f"No app name found in integration data for connection {connection.get('id', 'unknown')}")
    
    if app_name not in OAUTH_CONFIGS:
        raise Exception(f"Token refresh not supported for app: {app_name}")
        
    oauth_config = OAUTH_CONFIGS[app_name]
    current_credentials = decrypt_credentials(connection["credentials"])
    
    if not current_credentials.get("refresh_token"):
        raise Exception(f"No refresh token available for {app_name} connection")
    
    # Prepare refresh request
    refresh_data = {
        "grant_type": "refresh_token",
        "refresh_token": current_credentials["refresh_token"],
        "client_id": oauth_config["client_id"],
        "client_secret": oauth_config["client_secret"]
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(oauth_config["token_url"], data=refresh_data) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Token refresh failed for {app_name}: {error_text}")
                    
                token_response = await response.json()
                
        # Update credentials with new tokens
        updated_credentials = {
            **current_credentials,
            "access_token": token_response["access_token"],
            "token_type": token_response.get("token_type", "Bearer"),
            "obtained_at": datetime.utcnow().isoformat()
        }
        
        # Update refresh token if provided (some services rotate refresh tokens)
        if "refresh_token" in token_response:
            updated_credentials["refresh_token"] = token_response["refresh_token"]
            
        # Update expiration
        if "expires_in" in token_response:
            expires_at = datetime.utcnow() + timedelta(seconds=int(token_response["expires_in"]))
            updated_credentials["expires_at"] = expires_at.isoformat()
        
        # Encrypt and store updated credentials
        encrypted_credentials = encrypt_credentials(updated_credentials)
        
        supabase = get_supabase_anon_client()
        update_result = supabase.table("user_app_connections").update({
            "credentials": encrypted_credentials,
            "connection_status": "active",
            "updated_at": datetime.utcnow().isoformat()
        }).eq("id", connection["id"]).execute()
        
        if not update_result.data:
            raise Exception("Failed to update credentials in database")
            
        print(f"✅ Token refreshed successfully for {app_name}")
        return updated_credentials
        
    except Exception as e:
        # Mark connection as expired
        supabase = get_supabase_anon_client()
        supabase.table("user_app_connections").update({
            "connection_status": "expired"
        }).eq("id", connection["id"]).execute()
        
        raise Exception(f"Failed to refresh token for {app_name}: {str(e)}")

async def check_and_refresh_expiring_tokens():
    """
    Background task to check and refresh expiring tokens
    Run this periodically (e.g., every 30 minutes)
    """
    try:
        supabase = get_supabase_anon_client()
        
        # Get connections that expire in the next hour
        one_hour_from_now = (datetime.utcnow() + timedelta(hours=1)).isoformat()
        
        result = supabase.table("user_app_connections").select("""
            *,
            app_integrations!inner (
                name,
                display_name
            )
        """).eq("connection_status", "active").lt("expires_at", one_hour_from_now).execute()
        
        if not result.data:
            print("No tokens need refreshing")
            return
            
        print(f"Found {len(result.data)} connections with expiring tokens")
        
        for connection in result.data:
            try:
                # Get app integration info safely
                app_integrations = connection.get("app_integrations")
                if not app_integrations:
                    print(f"Skipping connection {connection.get('id', 'unknown')}: No app integration data")
                    continue
                
                app_name = app_integrations.get("name", "Unknown")
                print(f"Refreshing token for {app_name}...")
                
                await refresh_oauth_token(connection)
                
            except Exception as e:
                print(f"Failed to refresh token for connection {connection.get('id', 'unknown')}: {str(e)}")
                continue
                
        print("✅ Token refresh check completed")
        
    except Exception as e:
        print(f"Error in token refresh task: {str(e)}")

async def revoke_oauth_token(connection_id: str, user_id: str) -> bool:
    """
    Revoke OAuth token and mark connection as revoked
    
    Args:
        connection_id: ID of the connection to revoke
        user_id: ID of the user (for security verification)
        
    Returns:
        True if revocation was successful
    """
    try:
        connection, credentials = await get_user_connection_with_valid_creds(connection_id, user_id)
        app_name = connection["app_integrations"]["name"]
        
        # Try to revoke token with the service (if supported)
        revoked = False
        
        if app_name == "google_calendar":
            # Google supports token revocation
            revoke_url = f"https://oauth2.googleapis.com/revoke?token={credentials['access_token']}"
            async with aiohttp.ClientSession() as session:
                async with session.post(revoke_url) as response:
                    revoked = response.status == 200
                    
        elif app_name == "slack":
            # Slack supports token revocation
            async with aiohttp.ClientSession() as session:
                async with session.post("https://slack.com/api/auth.revoke", 
                                      headers={"Authorization": f"Bearer {credentials['access_token']}"}) as response:
                    if response.status == 200:
                        data = await response.json()
                        revoked = data.get("ok", False)
        
        # Mark connection as revoked in database regardless of service revocation
        supabase = get_supabase_anon_client()
        supabase.table("user_app_connections").update({
            "connection_status": "revoked",
            "updated_at": datetime.utcnow().isoformat()
        }).eq("id", connection_id).execute()
        
        print(f"Connection {connection_id} marked as revoked. Service revocation: {revoked}")
        return True
        
    except Exception as e:
        print(f"Failed to revoke connection {connection_id}: {str(e)}")
        return False

async def get_app_integration_by_name(app_name: str) -> Optional[Dict[str, Any]]:
    """
    Get app integration configuration by name
    
    Args:
        app_name: Name of the app integration
        
    Returns:
        App integration data or None if not found
    """
    try:
        supabase = get_supabase_anon_client()
        result = supabase.table("app_integrations").select("*").eq("name", app_name.lower()).execute()
        
        return result.data[0] if result.data else None
        
    except Exception as e:
        print(f"Failed to get app integration {app_name}: {str(e)}")
        return None

async def get_user_connections_for_app(user_id: str, app_name: str) -> list:
    """
    Get all user connections for a specific app
    
    Args:
        user_id: ID of the user
        app_name: Name of the app
        
    Returns:
        List of user connections for the app
    """
    try:
        supabase = get_supabase_anon_client()
        
        # First get the app integration ID
        app_integration = await get_app_integration_by_name(app_name)
        if not app_integration:
            return []
            
        # Get user connections for this app
        result = supabase.table("user_app_connections").select("*").eq("user_id", user_id).eq("app_integration_id", app_integration["id"]).execute()
        
        return result.data
        
    except Exception as e:
        print(f"Failed to get user connections for {app_name}: {str(e)}")
        return []

# Utility functions for specific app API calls
async def make_authenticated_request(
    connection_id: str, 
    user_id: str, 
    method: str, 
    url: str, 
    **kwargs
) -> Dict[str, Any]:
    """
    Make an authenticated API request using stored credentials
    
    Args:
        connection_id: ID of the app connection
        user_id: ID of the user
        method: HTTP method (GET, POST, etc.)
        url: API endpoint URL
        **kwargs: Additional arguments for aiohttp request
        
    Returns:
        API response as dictionary
    """
    connection, credentials = await get_user_connection_with_valid_creds(connection_id, user_id)
    
    # Add authorization header
    headers = kwargs.get("headers", {})
    headers["Authorization"] = f"Bearer {credentials['access_token']}"
    kwargs["headers"] = headers
    
    # Update last_used_at
    supabase = get_supabase_anon_client()
    supabase.table("user_app_connections").update({
        "last_used_at": datetime.utcnow().isoformat()
    }).eq("id", connection_id).execute()
    
    # Make the request
    async with aiohttp.ClientSession() as session:
        async with session.request(method, url, **kwargs) as response:
            if response.status >= 400:
                error_text = await response.text()
                raise Exception(f"API request failed ({response.status}): {error_text}")
                
            return await response.json() 