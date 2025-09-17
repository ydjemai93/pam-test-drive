from fastapi import APIRouter, HTTPException, Header, status, BackgroundTasks
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, HttpUrl, validator
from datetime import datetime, timedelta
import os
import json
import asyncio
import aiohttp
from .db_client import get_supabase_anon_client
from .config import get_user_id_from_token
from .crypto_utils import decrypt_credentials, is_token_expired

router = APIRouter()

# Request/Response Models
class AppIntegrationResponse(BaseModel):
    id: str
    name: str
    display_name: str
    description: Optional[str]
    logo_url: Optional[str]
    auth_type: str
    supported_actions: List[Dict[str, Any]]
    is_active: bool
    created_at: datetime
    updated_at: datetime

class UserAppConnectionResponse(BaseModel):
    id: str
    app_integration_id: str
    app_name: str
    app_display_name: str
    connection_name: Optional[str]
    connection_status: str
    last_used_at: Optional[datetime]
    expires_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

class OAuthInitiateRequest(BaseModel):
    app_name: str
    connection_name: Optional[str] = None
    redirect_url: Optional[str] = None
    state: Optional[str] = None

class OAuthInitiateResponse(BaseModel):
    authorization_url: str
    state: str

class ConnectionTestRequest(BaseModel):
    connection_id: str

class ConnectionTestResponse(BaseModel):
    status: str
    message: str
    details: Optional[Dict[str, Any]] = None

# OAuth Configuration for supported apps
OAUTH_CONFIGS = {
    "hubspot": {
        "client_id": os.getenv("HUBSPOT_CLIENT_ID"),
        "client_secret": os.getenv("HUBSPOT_CLIENT_SECRET"),
        "auth_url": "https://app.hubspot.com/oauth/authorize",
        "token_url": "https://api.hubapi.com/oauth/v1/token",
        "scopes": ["contacts", "deals", "timeline", "crm.objects.contacts.write", "crm.objects.deals.write"]
    },
    "google_calendar": {
        "client_id": os.getenv("GOOGLE_CLIENT_ID"), 
        "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
        "auth_url": "https://accounts.google.com/o/oauth2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "scopes": ["https://www.googleapis.com/auth/calendar"]
    },
    "calendly": {
        "client_id": os.getenv("CALENDLY_CLIENT_ID"),
        "client_secret": os.getenv("CALENDLY_CLIENT_SECRET"),
        "auth_url": "https://auth.calendly.com/oauth/authorize",
        "token_url": "https://auth.calendly.com/oauth/token",
        "scopes": []  # Calendly doesn't use traditional scopes - OAuth grants full API access based on user permissions
    },
    "salesforce": {
        "client_id": os.getenv("SALESFORCE_CLIENT_ID"),
        "client_secret": os.getenv("SALESFORCE_CLIENT_SECRET"),
        "auth_url": "https://login.salesforce.com/services/oauth2/authorize",
        "token_url": "https://login.salesforce.com/services/oauth2/token",
        "scopes": ["api", "refresh_token", "web"]
    },
    "slack": {
        "client_id": os.getenv("SLACK_CLIENT_ID"),
        "client_secret": os.getenv("SLACK_CLIENT_SECRET"), 
        "auth_url": "https://slack.com/oauth/v2/authorize",
        "token_url": "https://slack.com/api/oauth.v2.access",
        "scopes": ["chat:write", "files:write", "channels:read", "users:read"]
    }
}

@router.get("/", response_model=List[AppIntegrationResponse])
async def list_app_integrations(
    active_only: bool = True
):
    """Get list of available app integrations"""
    try:
        # Use service role key to access app integrations table
        from .db_client import supabase_service_client
        supabase = supabase_service_client
        query = supabase.table("app_integrations").select("*")
        
        if active_only:
            query = query.eq("is_active", True)
            
        result = query.execute()
        
        return [
            AppIntegrationResponse(
                id=row["id"],
                name=row["name"],
                display_name=row["display_name"],
                description=row.get("description"),
                logo_url=row.get("logo_url"),
                auth_type=row["auth_type"],
                supported_actions=row.get("supported_actions", []),
                is_active=row["is_active"],
                created_at=row["created_at"],
                updated_at=row["updated_at"]
            )
            for row in result.data
        ]
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch app integrations: {str(e)}"
        )

@router.get("/connections", response_model=List[UserAppConnectionResponse])
async def list_user_connections(
    authorization: str = Header(None, alias="Authorization"),
    status_filter: Optional[str] = None
):
    """Get user's app connections with real-time token expiration checking"""
    try:
        user_id = get_user_id_from_token(authorization)
        # Use service client for admin access to join with app_integrations
        from .db_client import supabase_service_client
        supabase = supabase_service_client
        
        # Query user connections with app integration details
        query = supabase.table("user_app_connections").select("""
            *,
            app_integrations (
                name,
                display_name
            )
        """).eq("user_id", user_id)
        
        if status_filter:
            query = query.eq("connection_status", status_filter)
            
        result = query.execute()
        
        connections = []
        connections_to_update = []  # Track connections that need status updates
        
        for row in result.data:
            app_info = row.get("app_integrations")
            if app_info is None:
                app_info = {}
            
            # Check token expiration if connection is currently active
            current_status = row["connection_status"]
            should_include_connection = True
            
            if current_status == "active" and row.get("credentials"):
                try:
                    # Decrypt and check token expiration
                    credentials = decrypt_credentials(row["credentials"])
                    if is_token_expired(credentials):
                        print(f"🔄 Token expired for connection {row['id']} ({app_info.get('name', 'unknown')}) - excluding from connected apps")
                        current_status = "expired"
                        should_include_connection = False  # Don't show expired connections
                        # Mark for database update
                        connections_to_update.append({
                            "id": row["id"],
                            "status": "expired"
                        })
                except Exception as e:
                    print(f"⚠️ Error checking token expiration for connection {row['id']}: {e}")
                    # If we can't decrypt/check, mark as error and exclude
                    current_status = "error"
                    should_include_connection = False
                    connections_to_update.append({
                        "id": row["id"],
                        "status": "error"
                    })
            
            # Only include active connections (expired ones are filtered out)
            if should_include_connection and current_status == "active":
                connections.append(UserAppConnectionResponse(
                    id=row["id"],
                    app_integration_id=row["app_integration_id"], 
                    app_name=app_info.get("name", ""),
                    app_display_name=app_info.get("display_name", ""),
                    connection_name=row.get("connection_name"),
                    connection_status=current_status,
                    last_used_at=row.get("last_used_at"),
                    expires_at=row.get("expires_at"),
                    created_at=row["created_at"],
                    updated_at=row["updated_at"]
                ))
        
        # Update connection statuses in database if any were found to be expired
        if connections_to_update:
            print(f"📝 Updating {len(connections_to_update)} expired connection statuses in database")
            for conn_update in connections_to_update:
                try:
                    supabase.table("user_app_connections").update({
                        "connection_status": conn_update["status"],
                        "updated_at": datetime.utcnow().isoformat()
                    }).eq("id", conn_update["id"]).execute()
                except Exception as e:
                    print(f"⚠️ Failed to update connection {conn_update['id']} status: {e}")
            
        return connections
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch user connections: {str(e)}"
        )

@router.post("/oauth/initiate", response_model=OAuthInitiateResponse)
async def initiate_oauth_flow(
    request: OAuthInitiateRequest,
    authorization: str = Header(None, alias="Authorization")
):
    """Initiate OAuth flow for app connection"""
    try:
        user_id = get_user_id_from_token(authorization)
        app_name = request.app_name.lower()
        
        # Validate app is supported
        if app_name not in OAUTH_CONFIGS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"App '{app_name}' is not supported"
            )
            
        # Get app integration from database - use service client for admin access
        from .db_client import supabase_service_client
        supabase = supabase_service_client
        app_result = supabase.table("app_integrations").select("*").eq("name", app_name).execute()
        
        if not app_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"App integration '{app_name}' not found"
            )
            
        app_integration = app_result.data[0]
        oauth_config = OAUTH_CONFIGS[app_name]
        
        # Generate state parameter with user info
        import secrets
        state = f"{user_id}_{app_integration['id']}_{secrets.token_urlsafe(16)}"
        
        # Build authorization URL
        base_url = os.getenv("BASE_URL", "http://localhost:8000")
        redirect_uri = f"{base_url}/integrations/oauth/{app_name}/callback"
        
        if app_name == "slack":
            # Slack OAuth v2 format
            auth_url = (
                f"{oauth_config['auth_url']}?"
                f"client_id={oauth_config['client_id']}&"
                f"scope={','.join(oauth_config['scopes'])}&"
                f"redirect_uri={redirect_uri}&"
                f"state={state}&"
                f"response_type=code"
            )
        else:
            # Standard OAuth format (HubSpot, Google, Calendly)
            scope_param = ""
            if oauth_config['scopes']:  # Only add scope parameter if scopes exist
                scope_param = f"scope={' '.join(oauth_config['scopes'])}&"
            
            auth_url = (
                f"{oauth_config['auth_url']}?"
                f"client_id={oauth_config['client_id']}&"
                f"{scope_param}"
                f"redirect_uri={redirect_uri}&"
                f"state={state}&"
                f"response_type=code&"
                f"access_type=offline&"  # For refresh tokens
                f"prompt=consent"  # Force consent screen to appear
            )
            
        return OAuthInitiateResponse(
            authorization_url=auth_url,
            state=state
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initiate OAuth flow: {str(e)}"
        )

@router.get("/oauth/{app_name}/callback")
async def oauth_callback(
    app_name: str,
    code: str,
    state: str,
    error: Optional[str] = None,
    error_description: Optional[str] = None
):
    """Handle OAuth callback and store tokens"""
    try:
        if error:
            # Return HTML with error message for popup flow
            frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
            error_html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>OAuth Error</title>
            </head>
            <body>
                <script>
                    if (window.opener) {{
                        window.opener.postMessage({{
                            type: 'OAUTH_ERROR',
                            message: '{error_description or error}'
                        }}, '{frontend_url}');
                        window.close();
                    }} else {{
                        window.location.href = '{frontend_url}/oauth-success?error={error}&error_description={error_description}';
                    }}
                </script>
                <div style="font-family: Arial, sans-serif; text-align: center; margin-top: 50px;">
                    <h2>Connection Failed</h2>
                    <p>Error: {error_description or error}</p>
                </div>
            </body>
            </html>
            """
            from fastapi.responses import HTMLResponse
            return HTMLResponse(content=error_html)
            
        # Normalize app name first
        app_name = app_name.lower()
        
        # Parse state to get user and app info
        try:
            state_parts = state.split("_")
            if len(state_parts) < 2:
                # Handle test state format like "pam-test-123"
                if state.startswith("pam-test"):
                    # For testing, use a default user ID and get app integration
                    from .db_client import supabase_service_client
                    supabase = supabase_service_client
                    app_result = supabase.table("app_integrations").select("id").eq("name", app_name).execute()
                    if not app_result.data:
                        raise HTTPException(
                            status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"App integration '{app_name}' not found"
                        )
                    user_id = "123e4567-e89b-12d3-a456-426614174000"  # Test UUID - you'll need to replace this with a real user ID
                    app_integration_id = app_result.data[0]["id"]
                else:
                    raise ValueError("Invalid state format")
            else:
                user_id = state_parts[0]
                app_integration_id = state_parts[1]
        except (IndexError, ValueError):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid OAuth state parameter: {state}"
            )
        if app_name not in OAUTH_CONFIGS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"App '{app_name}' is not supported"
            )
            
        oauth_config = OAUTH_CONFIGS[app_name]
        
        # Exchange code for tokens
        base_url = os.getenv("BASE_URL", "http://localhost:8000") 
        redirect_uri = f"{base_url}/integrations/oauth/{app_name}/callback"
        
        token_data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": oauth_config["client_id"],
            "client_secret": oauth_config["client_secret"]
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(oauth_config["token_url"], data=token_data) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Failed to exchange OAuth code: {error_text}"
                    )
                    
                token_response = await response.json()
                
        # Prepare credentials for storage
        credentials = {
            "access_token": token_response["access_token"],
            "token_type": token_response.get("token_type", "Bearer"),
            "scope": token_response.get("scope", " ".join(oauth_config["scopes"])),
            "obtained_at": datetime.utcnow().isoformat()
        }
        
        # Add refresh token if available
        if "refresh_token" in token_response:
            credentials["refresh_token"] = token_response["refresh_token"]
            
        # Calculate expiration
        expires_at = None
        if "expires_in" in token_response:
            expires_at = datetime.utcnow() + timedelta(seconds=int(token_response["expires_in"]))
            credentials["expires_at"] = expires_at.isoformat()
            
        # Encrypt credentials before storing
        from .crypto_utils import encrypt_credentials
        encrypted_credentials = encrypt_credentials(credentials)
        
        # Store connection in database
        supabase = get_supabase_anon_client()
        
        # Generate connection name if not provided
        app_result = supabase.table("app_integrations").select("display_name").eq("id", app_integration_id).execute()
        app_display_name = app_result.data[0]["display_name"] if app_result.data else app_name
        connection_name = f"My {app_display_name}"
        
        # Check if connection already exists
        existing_connection = supabase.table("user_app_connections").select("*").eq("user_id", user_id).eq("app_integration_id", app_integration_id).execute()
        
        connection_data = {
            "credentials": encrypted_credentials,
            "connection_status": "active",
            "expires_at": expires_at.isoformat() if expires_at else None,
            "updated_at": datetime.utcnow().isoformat()
        }
        
        if existing_connection.data:
            # Update existing connection
            result = supabase.table("user_app_connections").update(connection_data).eq("id", existing_connection.data[0]["id"]).execute()
            connection_id = existing_connection.data[0]["id"]
        else:
            # Create new connection
            connection_data.update({
                "user_id": user_id,
                "app_integration_id": app_integration_id,
                "connection_name": connection_name
            })
            result = supabase.table("user_app_connections").insert(connection_data).execute()
            connection_id = result.data[0]["id"] if result.data else None
        
        if not result.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to store app connection"
            )
            
        # Redirect to OAuth success page with connection info
        frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
        redirect_url = f"{frontend_url}/oauth-success?connected={app_name}&connection_id={connection_id}"
        
        # For popup flow, return HTML that posts message to parent
        html_response = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>OAuth Success</title>
        </head>
        <body>
            <script>
                if (window.opener) {{
                    window.opener.postMessage({{
                        type: 'OAUTH_SUCCESS',
                        app: '{app_name}',
                        connection_id: '{connection_id}'
                    }}, '{frontend_url}');
                    window.close();
                }} else {{
                    window.location.href = '{redirect_url}';
                }}
            </script>
            <div style="font-family: Arial, sans-serif; text-align: center; margin-top: 50px;">
                <h2>Connection Successful!</h2>
                <p>You have successfully connected to {app_name.replace('_', ' ').title()}.</p>
                <p>This window will close automatically...</p>
            </div>
        </body>
        </html>
        """
        
        from fastapi.responses import HTMLResponse
        return HTMLResponse(content=html_response)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"OAuth callback failed: {str(e)}"
        )

@router.post("/connections/{connection_id}/test", response_model=ConnectionTestResponse)
async def test_connection(
    connection_id: str,
    authorization: str = Header(None, alias="Authorization")
):
    """Test an app connection to verify it's working"""
    try:
        user_id = get_user_id_from_token(authorization)
        
        # Get connection details
        from .oauth_utils import get_user_connection_with_valid_creds
        connection, credentials = await get_user_connection_with_valid_creds(connection_id, user_id)
        
        # Test based on app type
        app_name = connection["app_integrations"]["name"]
        
        if app_name == "hubspot":
            result = await test_hubspot_connection(credentials)
        elif app_name == "google_calendar":
            result = await test_google_calendar_connection(credentials)
        elif app_name == "slack":
            result = await test_slack_connection(credentials)
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Testing not implemented for app: {app_name}"
            )
            
        # Update last_used_at
        supabase = get_supabase_anon_client()
        supabase.table("user_app_connections").update({
            "last_used_at": datetime.utcnow().isoformat()
        }).eq("id", connection_id).execute()
        
        return ConnectionTestResponse(
            status="success",
            message=f"{app_name.title()} connection is working",
            details=result
        )
        
    except HTTPException:
        raise
    except Exception as e:
        return ConnectionTestResponse(
            status="error",
            message=f"Connection test failed: {str(e)}"
        )

@router.delete("/connections/{connection_id}")
async def delete_connection(
    connection_id: str,
    authorization: str = Header(None, alias="Authorization")
):
    """Delete an app connection"""
    try:
        user_id = get_user_id_from_token(authorization)
        supabase = get_supabase_anon_client()
        
        # Verify connection belongs to user
        connection_result = supabase.table("user_app_connections").select("*").eq("id", connection_id).eq("user_id", user_id).execute()
        
        if not connection_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Connection not found"
            )
            
        # Delete connection
        delete_result = supabase.table("user_app_connections").delete().eq("id", connection_id).execute()
        
        if not delete_result.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete connection"
            )
            
        return {"message": "Connection deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete connection: {str(e)}"
        )

# Test functions for different apps
async def test_hubspot_connection(credentials: dict) -> dict:
    """Test HubSpot connection"""
    headers = {"Authorization": f"Bearer {credentials['access_token']}"}
    
    async with aiohttp.ClientSession() as session:
        async with session.get("https://api.hubapi.com/crm/v3/objects/contacts?limit=1", headers=headers) as response:
            if response.status == 200:
                data = await response.json()
                return {"contacts_accessible": True, "total_contacts": data.get("total", 0)}
            else:
                error_text = await response.text()
                raise Exception(f"HubSpot API error: {error_text}")

async def test_google_calendar_connection(credentials: dict) -> dict:
    """Test Google Calendar connection"""
    headers = {"Authorization": f"Bearer {credentials['access_token']}"}
    
    async with aiohttp.ClientSession() as session:
        async with session.get("https://www.googleapis.com/calendar/v3/calendars/primary", headers=headers) as response:
            if response.status == 200:
                data = await response.json()
                return {"calendar_accessible": True, "calendar_id": data.get("id")}
            else:
                error_text = await response.text()
                raise Exception(f"Google Calendar API error: {error_text}")

async def test_slack_connection(credentials: dict) -> dict:
    """Test Slack connection"""
    headers = {"Authorization": f"Bearer {credentials['access_token']}"}
    
    async with aiohttp.ClientSession() as session:
        async with session.get("https://slack.com/api/auth.test", headers=headers) as response:
            if response.status == 200:
                data = await response.json()
                if data.get("ok"):
                    return {"user_id": data.get("user_id"), "team": data.get("team")}
                else:
                    raise Exception(f"Slack API error: {data.get('error')}")
            else:
                error_text = await response.text()
                raise Exception(f"Slack API error: {error_text}") 