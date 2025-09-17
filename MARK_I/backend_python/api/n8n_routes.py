"""
N8N Integration Routes

FastAPI routes for managing OAuth connections and app actions via n8n.
"""

from fastapi import APIRouter, HTTPException, Header, status, BackgroundTasks
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, HttpUrl
from datetime import datetime
import logging

from .n8n_integration import n8n_manager
from .config import get_user_id_from_token

router = APIRouter(prefix="/integrations/n8n", tags=["n8n-integration"])
logger = logging.getLogger("n8n-routes")

# Request/Response Models
class OAuthInitiateRequest(BaseModel):
    app_name: str
    redirect_url: Optional[str] = None

class OAuthInitiateResponse(BaseModel):
    authorization_url: str
    state: str
    message: str

class OAuthCallbackRequest(BaseModel):
    state: str
    code: str

class OAuthCallbackResponse(BaseModel):
    connection_id: str
    app_name: str
    status: str
    message: str

class AppActionRequest(BaseModel):
    app_name: str
    action_name: str
    action_data: Dict[str, Any]
    workflow_context: Optional[Dict[str, Any]] = None

class AppActionResponse(BaseModel):
    success: bool
    message: str
    result: Optional[Dict[str, Any]] = None
    execution_id: Optional[str] = None

class ConnectedAppResponse(BaseModel):
    connection_id: str
    app_name: str
    app_display_name: str
    supported_actions: List[Dict[str, Any]]
    connected_at: datetime
    last_used_at: Optional[datetime]

@router.post("/oauth/initiate", response_model=OAuthInitiateResponse)
async def initiate_oauth(
    request: OAuthInitiateRequest,
    authorization: str = Header(None, alias="Authorization")
):
    """
    Initiate OAuth flow via n8n webhook.
    
    This triggers an n8n workflow that handles the OAuth dance with the specified app.
    """
    try:
        user_id = get_user_id_from_token(authorization)
        
        result = await n8n_manager.initiate_oauth(
            user_id=user_id,
            app_name=request.app_name,
            redirect_url=request.redirect_url
        )
        
        return OAuthInitiateResponse(
            authorization_url=result["authorization_url"],
            state=result["state"],
            message=f"OAuth initiated for {request.app_name}"
        )
        
    except Exception as e:
        logger.error(f"Error initiating OAuth: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initiate OAuth: {str(e)}"
        )

@router.post("/oauth/callback", response_model=OAuthCallbackResponse)
async def handle_oauth_callback(
    request: OAuthCallbackRequest
):
    """
    Handle OAuth callback from provider.
    
    This completes the OAuth flow via n8n webhook and stores the connection.
    """
    try:
        result = await n8n_manager.handle_oauth_callback(
            state=request.state,
            code=request.code
        )
        
        return OAuthCallbackResponse(
            connection_id=result["connection_id"],
            app_name=result.get("app_name", "unknown"),
            status="connected",
            message="OAuth completed successfully"
        )
        
    except Exception as e:
        logger.error(f"Error handling OAuth callback: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"OAuth callback failed: {str(e)}"
        )

@router.get("/user-apps", response_model=List[ConnectedAppResponse])
async def get_user_connected_apps(
    authorization: str = Header(None, alias="Authorization")
):
    """
    Get list of apps that user has connected via n8n OAuth.
    
    Returns apps with their supported actions for use in pathway builder.
    """
    try:
        user_id = get_user_id_from_token(authorization)
        
        connected_apps = await n8n_manager.get_user_connected_apps(user_id)
        
        return [
            ConnectedAppResponse(
                connection_id=app["connection_id"],
                app_name=app["app_name"],
                app_display_name=app["app_display_name"],
                supported_actions=app["supported_actions"],
                connected_at=datetime.fromisoformat(app["connected_at"].replace("Z", "+00:00")),
                last_used_at=datetime.fromisoformat(app["last_used_at"].replace("Z", "+00:00")) if app["last_used_at"] else None
            )
            for app in connected_apps
        ]
        
    except Exception as e:
        logger.error(f"Error getting user connected apps: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get connected apps: {str(e)}"
        )

@router.post("/execute-action", response_model=AppActionResponse)
async def execute_app_action(
    request: AppActionRequest,
    authorization: str = Header(None, alias="Authorization"),
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    """
    Execute app action via n8n workflow.
    
    This is called by the LiveKit agent dynamic tools to perform actions
    in connected apps using n8n workflows.
    """
    try:
        user_id = get_user_id_from_token(authorization)
        
        result = await n8n_manager.execute_app_action(
            user_id=user_id,
            app_name=request.app_name,
            action_name=request.action_name,
            action_data=request.action_data,
            workflow_context=request.workflow_context
        )
        
        return AppActionResponse(
            success=True,
            message=f"Successfully executed {request.app_name}.{request.action_name}",
            result=result,
            execution_id=result.get("execution_id")
        )
        
    except Exception as e:
        logger.error(f"Error executing app action: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"App action execution failed: {str(e)}"
        )

@router.get("/apps/{app_name}/actions")
async def get_app_actions(
    app_name: str,
    authorization: str = Header(None, alias="Authorization")
):
    """
    Get available actions for a specific app.
    
    This helps the pathway builder show only valid actions for connected apps.
    """
    try:
        user_id = get_user_id_from_token(authorization)
        
        connected_apps = await n8n_manager.get_user_connected_apps(user_id)
        
        # Find the specific app
        app_info = next((app for app in connected_apps if app["app_name"] == app_name), None)
        
        if not app_info:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"App {app_name} not connected or not found"
            )
        
        return {
            "app_name": app_name,
            "app_display_name": app_info["app_display_name"],
            "supported_actions": app_info["supported_actions"]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting app actions: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get app actions: {str(e)}"
        )

@router.delete("/connections/{connection_id}")
async def disconnect_app(
    connection_id: str,
    authorization: str = Header(None, alias="Authorization")
):
    """
    Disconnect an app by deactivating the connection.
    
    This doesn't delete the connection record but marks it as inactive.
    """
    try:
        user_id = get_user_id_from_token(authorization)
        
        # Use supabase to deactivate the connection
        from .db_client import supabase_service_client
        supabase = supabase_service_client
        
        # Verify the connection belongs to the user
        connection_check = supabase.table("user_app_connections").select("user_id").eq("id", connection_id).execute()
        
        if not connection_check.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Connection not found"
            )
        
        if connection_check.data[0]["user_id"] != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to disconnect this app"
            )
        
        # Update connection status
        supabase.table("user_app_connections").update({
            "connection_status": "inactive",
            "updated_at": datetime.now().isoformat()
        }).eq("id", connection_id).execute()
        
        return {"message": "App disconnected successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error disconnecting app: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to disconnect app: {str(e)}"
        )

@router.get("/status")
async def get_n8n_status():
    """
    Check n8n integration status.
    
    Verifies that n8n is accessible and webhooks are working.
    """
    try:
        # Simple health check
        import aiohttp
        
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{n8n_manager.base_url}/healthz", timeout=5) as response:
                if response.status == 200:
                    return {
                        "status": "healthy",
                        "n8n_url": n8n_manager.base_url,
                        "message": "N8N integration is working"
                    }
                else:
                    return {
                        "status": "unhealthy", 
                        "n8n_url": n8n_manager.base_url,
                        "message": f"N8N returned status {response.status}"
                    }
        
    except Exception as e:
        logger.error(f"N8N health check failed: {e}")
        return {
            "status": "error",
            "n8n_url": n8n_manager.base_url,
            "message": f"N8N health check failed: {str(e)}"
        } 