"""
N8N Integration Module for OAuth and App Actions

Handles OAuth connections via n8n and executes app actions using n8n workflows.
This replaces the direct OAuth implementation with n8n-based OAuth management.
"""

import asyncio
import aiohttp
import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from .db_client import supabase_service_client
from .crypto_utils import encrypt_credentials, decrypt_credentials
import os

logger = logging.getLogger("n8n-integration")

# N8N Configuration
N8N_BASE_URL = os.getenv("N8N_WEBHOOK_URL", "http://localhost:5678")
N8N_API_KEY = os.getenv("N8N_API_KEY")  # If using n8n API authentication

class N8NOAuthManager:
    """
    Manages OAuth connections via n8n workflows.
    
    n8n handles the OAuth dance and stores tokens securely.
    We call n8n webhooks to initiate OAuth and execute app actions.
    """
    
    def __init__(self):
        self.base_url = N8N_BASE_URL
        self.api_key = N8N_API_KEY
        
    async def initiate_oauth(self, user_id: str, app_name: str, redirect_url: str = None) -> Dict[str, Any]:
        """
        Initiate OAuth flow via n8n webhook.
        
        Args:
            user_id: User identifier
            app_name: Name of the app to connect (hubspot, google_calendar, etc.)
            redirect_url: Optional redirect URL after OAuth completion
            
        Returns:
            Dict with authorization_url and state
        """
        try:
            # Call n8n OAuth initiation webhook
            webhook_url = f"{self.base_url}/webhook/oauth/initiate/{app_name}"
            
            payload = {
                "user_id": user_id,
                "app_name": app_name,
                "redirect_url": redirect_url,
                "timestamp": datetime.now().isoformat()
            }
            
            async with aiohttp.ClientSession() as session:
                headers = self._get_headers()
                
                async with session.post(webhook_url, json=payload, headers=headers) as response:
                    if response.status == 200:
                        result = await response.json()
                        
                        # Store OAuth session in database for tracking
                        await self._store_oauth_session(
                            user_id=user_id,
                            app_name=app_name,
                            state=result.get("state"),
                            n8n_execution_id=result.get("execution_id")
                        )
                        
                        logger.info(f"OAuth initiated for user {user_id} app {app_name}")
                        return result
                    else:
                        error_text = await response.text()
                        raise Exception(f"N8N OAuth initiation failed: {response.status} - {error_text}")
                        
        except Exception as e:
            logger.error(f"Error initiating OAuth: {e}")
            raise
    
    async def handle_oauth_callback(self, state: str, code: str) -> Dict[str, Any]:
        """
        Handle OAuth callback via n8n webhook.
        
        Args:
            state: OAuth state parameter
            code: Authorization code from OAuth provider
            
        Returns:
            Dict with connection details
        """
        try:
            # Get OAuth session from database
            oauth_session = await self._get_oauth_session(state)
            if not oauth_session:
                raise Exception(f"OAuth session not found for state: {state}")
            
            # Call n8n OAuth completion webhook
            webhook_url = f"{self.base_url}/webhook/oauth/callback/{oauth_session['app_name']}"
            
            payload = {
                "state": state,
                "code": code,
                "user_id": oauth_session["user_id"],
                "app_name": oauth_session["app_name"]
            }
            
            async with aiohttp.ClientSession() as session:
                headers = self._get_headers()
                
                async with session.post(webhook_url, json=payload, headers=headers) as response:
                    if response.status == 200:
                        result = await response.json()
                        
                        # Store the connection in database
                        connection_id = await self._store_app_connection(
                            user_id=oauth_session["user_id"],
                            app_name=oauth_session["app_name"],
                            connection_data=result
                        )
                        
                        # Update OAuth session
                        await self._update_oauth_session(state, "completed", connection_id)
                        
                        logger.info(f"OAuth completed for user {oauth_session['user_id']} app {oauth_session['app_name']}")
                        return {"connection_id": connection_id, **result}
                    else:
                        error_text = await response.text()
                        await self._update_oauth_session(state, "failed", error=error_text)
                        raise Exception(f"N8N OAuth callback failed: {response.status} - {error_text}")
                        
        except Exception as e:
            logger.error(f"Error handling OAuth callback: {e}")
            raise
    
    async def execute_app_action(
        self, 
        user_id: str, 
        app_name: str, 
        action_name: str, 
        action_data: Dict[str, Any],
        workflow_context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Execute app action via n8n workflow.
        
        Args:
            user_id: User identifier
            app_name: App name (hubspot, google_calendar, etc.)
            action_name: Action to execute (create_contact, create_event, etc.)
            action_data: Data for the action
            workflow_context: Additional workflow context
            
        Returns:
            Dict with action execution results
        """
        try:
            # Check if user has active connection for this app
            connection = await self._get_user_app_connection(user_id, app_name)
            if not connection:
                raise Exception(f"No active connection found for {app_name}")
            
            # Call n8n app action webhook
            webhook_url = f"{self.base_url}/webhook/app-action/{app_name}/{action_name}"
            
            payload = {
                "user_id": user_id,
                "app_name": app_name,
                "action_name": action_name,
                "connection_id": connection["id"],
                "action_data": action_data,
                "workflow_context": workflow_context or {},
                "timestamp": datetime.now().isoformat()
            }
            
            async with aiohttp.ClientSession() as session:
                headers = self._get_headers()
                
                async with session.post(webhook_url, json=payload, headers=headers, timeout=30) as response:
                    if response.status == 200:
                        result = await response.json()
                        
                        # Log the execution
                        await self._log_app_execution(
                            user_id=user_id,
                            connection_id=connection["id"],
                            app_name=app_name,
                            action_name=action_name,
                            input_data=action_data,
                            output_data=result,
                            status="success"
                        )
                        
                        logger.info(f"App action executed: {app_name}.{action_name} for user {user_id}")
                        return result
                    else:
                        error_text = await response.text()
                        
                        # Log the failed execution
                        await self._log_app_execution(
                            user_id=user_id,
                            connection_id=connection["id"],
                            app_name=app_name,
                            action_name=action_name,
                            input_data=action_data,
                            status="failed",
                            error_message=error_text
                        )
                        
                        raise Exception(f"N8N app action failed: {response.status} - {error_text}")
                        
        except Exception as e:
            logger.error(f"Error executing app action: {e}")
            raise
    
    async def get_user_connected_apps(self, user_id: str) -> List[Dict[str, Any]]:
        """
        Get list of apps that user has connected via n8n OAuth.
        
        Args:
            user_id: User identifier
            
        Returns:
            List of connected app details
        """
        try:
            supabase = supabase_service_client
            
            # Get user's app connections with integration details
            result = supabase.table("user_app_connections").select("""
                *,
                app_integrations (
                    name,
                    display_name,
                    supported_actions
                )
            """).eq("user_id", user_id).eq("connection_status", "active").execute()
            
            connected_apps = []
            for row in result.data:
                app_info = row.get("app_integrations")
                connected_apps.append({
                    "connection_id": row["id"],
                    "app_name": app_info["name"],
                    "app_display_name": app_info["display_name"], 
                    "supported_actions": app_info["supported_actions"],
                    "connected_at": row["created_at"],
                    "last_used_at": row["last_used_at"]
                })
            
            return connected_apps
            
        except Exception as e:
            logger.error(f"Error getting user connected apps: {e}")
            raise
    
    def _get_headers(self) -> Dict[str, str]:
        """Get headers for n8n requests"""
        headers = {"Content-Type": "application/json"}
        
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
            
        return headers
    
    async def _store_oauth_session(self, user_id: str, app_name: str, state: str, n8n_execution_id: str = None):
        """Store OAuth session in database"""
        try:
            supabase = supabase_service_client
            
            session_data = {
                "user_id": user_id,
                "app_id": app_name,
                "app_name": app_name,
                "state": state,
                "status": "pending",
                "oauth_type": "n8n_oauth",
                "additional_params": {"n8n_execution_id": n8n_execution_id} if n8n_execution_id else {}
            }
            
            result = supabase.table("oauth_sessions").insert(session_data).execute()
            return result.data[0]["id"]
            
        except Exception as e:
            logger.error(f"Error storing OAuth session: {e}")
            raise
    
    async def _get_oauth_session(self, state: str) -> Optional[Dict[str, Any]]:
        """Get OAuth session by state"""
        try:
            supabase = supabase_service_client
            
            result = supabase.table("oauth_sessions").select("*").eq("state", state).execute()
            
            if result.data:
                return result.data[0]
            return None
            
        except Exception as e:
            logger.error(f"Error getting OAuth session: {e}")
            return None
    
    async def _update_oauth_session(self, state: str, status: str, connection_id: str = None, error: str = None):
        """Update OAuth session status"""
        try:
            supabase = supabase_service_client
            
            update_data = {"status": status}
            if connection_id:
                update_data["connection_id"] = connection_id
            if error:
                update_data["error"] = error
                
            supabase.table("oauth_sessions").update(update_data).eq("state", state).execute()
            
        except Exception as e:
            logger.error(f"Error updating OAuth session: {e}")
    
    async def _store_app_connection(self, user_id: str, app_name: str, connection_data: Dict[str, Any]) -> str:
        """Store app connection in database"""
        try:
            supabase = supabase_service_client
            
            # Get app integration ID
            app_result = supabase.table("app_integrations").select("id").eq("name", app_name).execute()
            if not app_result.data:
                raise Exception(f"App integration not found: {app_name}")
            
            app_integration_id = app_result.data[0]["id"]
            
            # Encrypt sensitive credentials
            encrypted_credentials = encrypt_credentials(connection_data.get("credentials", {}))
            
            connection_record = {
                "user_id": user_id,
                "app_integration_id": app_integration_id,
                "connection_name": f"{app_name}_connection_{datetime.now().strftime('%Y%m%d')}",
                "credentials": encrypted_credentials,
                "connection_status": "active"
            }
            
            result = supabase.table("user_app_connections").insert(connection_record).execute()
            return result.data[0]["id"]
            
        except Exception as e:
            logger.error(f"Error storing app connection: {e}")
            raise
    
    async def _get_user_app_connection(self, user_id: str, app_name: str) -> Optional[Dict[str, Any]]:
        """Get user's app connection"""
        try:
            supabase = supabase_service_client
            
            result = supabase.table("user_app_connections").select("""
                *,
                app_integrations!inner (name)
            """).eq("user_id", user_id).eq("app_integrations.name", app_name).eq("connection_status", "active").execute()
            
            if result.data:
                return result.data[0]
            return None
            
        except Exception as e:
            logger.error(f"Error getting user app connection: {e}")
            return None
    
    async def _log_app_execution(
        self, 
        user_id: str, 
        connection_id: str, 
        app_name: str, 
        action_name: str, 
        input_data: Dict[str, Any],
        output_data: Dict[str, Any] = None,
        status: str = "pending",
        error_message: str = None
    ):
        """Log app action execution"""
        try:
            supabase = supabase_service_client
            
            execution_record = {
                "user_id": user_id,
                "app_connection_id": connection_id,
                "action_id": f"{app_name}.{action_name}",
                "action_name": action_name,
                "execution_status": status,
                "input_data": input_data,
                "output_data": output_data or {},
                "error_message": error_message,
                "triggered_by": "pathway"
            }
            
            supabase.table("app_executions").insert(execution_record).execute()
            
        except Exception as e:
            logger.error(f"Error logging app execution: {e}")

# Global n8n manager instance
n8n_manager = N8NOAuthManager() 