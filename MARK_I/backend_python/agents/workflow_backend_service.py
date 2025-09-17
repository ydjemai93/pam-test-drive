"""
Backend Service Integration for WorkflowAgent

This service handles OAuth tokens, API calls, and backend integration
for all WorkflowAgent function tools. It replaces the hardcoded webhook calls
from the old PathwayAgent approach.
"""

import logging
import os
import json
import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime
import aiohttp
from urllib.parse import urljoin

logger = logging.getLogger("workflow-backend")

class WorkflowBackendService:
    """
    Centralized backend service for WorkflowAgent integrations.
    
    Handles OAuth tokens, API calls, and data persistence for:
    - Google Calendar integration
    - Email services (SendGrid/AWS SES)
    - CRM systems (HubSpot/Salesforce)
    - SMS services
    - Payment processing
    """
    
    def __init__(self, backend_api_url: str = None):
        self.backend_api_url = backend_api_url or os.getenv("BACKEND_API_URL", "http://localhost:8000")
        self.session: Optional[aiohttp.ClientSession] = None
        
    async def __aenter__(self):
        """Async context manager entry"""
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.session:
            await self.session.close()
    
    async def get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session"""
        if not self.session:
            self.session = aiohttp.ClientSession()
        return self.session
    
    # Google Calendar Integration
    async def calendar_create_event(self, user_id: str, event_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create Google Calendar event via backend API with OAuth"""
        try:
            session = await self.get_session()
            url = urljoin(self.backend_api_url, "/integrations/google_calendar/create_event")
            
            payload = {
                "user_id": user_id,
                "event": event_data
            }
            
            async with session.post(url, json=payload) as response:
                if response.status == 200:
                    result = await response.json()
                    logger.info(f"Calendar event created: {result.get('event_id')}")
                    return {"success": True, "data": result}
                else:
                    error_text = await response.text()
                    logger.error(f"Calendar API error: {response.status} - {error_text}")
                    return {"success": False, "error": error_text}
                    
        except Exception as e:
            logger.error(f"Error creating calendar event: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
    
    async def calendar_check_availability(self, user_id: str, date: str, time_range: Dict[str, str]) -> Dict[str, Any]:
        """Check Google Calendar availability"""
        try:
            session = await self.get_session()
            url = urljoin(self.backend_api_url, "/integrations/google_calendar/check_availability")
            
            payload = {
                "user_id": user_id,
                "date": date,
                "start_time": time_range.get("start", "09:00"),
                "end_time": time_range.get("end", "17:00")
            }
            
            async with session.post(url, json=payload) as response:
                if response.status == 200:
                    result = await response.json()
                    return {"success": True, "data": result.get("available_slots", [])}
                else:
                    return {"success": False, "error": await response.text()}
                    
        except Exception as e:
            logger.error(f"Error checking calendar availability: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
    
    async def calendar_reschedule_event(self, user_id: str, event_id: str, new_datetime: Dict[str, str]) -> Dict[str, Any]:
        """Reschedule Google Calendar event"""
        try:
            session = await self.get_session()
            url = urljoin(self.backend_api_url, f"/integrations/google_calendar/reschedule_event/{event_id}")
            
            payload = {
                "user_id": user_id,
                "new_date": new_datetime.get("date"),
                "new_time": new_datetime.get("time")
            }
            
            async with session.put(url, json=payload) as response:
                if response.status == 200:
                    result = await response.json()
                    return {"success": True, "data": result}
                else:
                    return {"success": False, "error": await response.text()}
                    
        except Exception as e:
            logger.error(f"Error rescheduling event: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
    
    # Email Integration
    async def email_send(self, user_id: str, email_data: Dict[str, Any]) -> Dict[str, Any]:
        """Send email via backend API (SendGrid/AWS SES)"""
        try:
            session = await self.get_session()
            url = urljoin(self.backend_api_url, "/integrations/email/send")
            
            payload = {
                "user_id": user_id,
                "email": email_data
            }
            
            async with session.post(url, json=payload) as response:
                if response.status == 200:
                    result = await response.json()
                    return {"success": True, "data": result}
                else:
                    return {"success": False, "error": await response.text()}
                    
        except Exception as e:
            logger.error(f"Error sending email: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
    
    async def email_send_template(self, user_id: str, template_data: Dict[str, Any]) -> Dict[str, Any]:
        """Send templated email"""
        try:
            session = await self.get_session()
            url = urljoin(self.backend_api_url, "/integrations/email/send_template")
            
            payload = {
                "user_id": user_id,
                "template": template_data
            }
            
            async with session.post(url, json=payload) as response:
                if response.status == 200:
                    result = await response.json()
                    return {"success": True, "data": result}
                else:
                    return {"success": False, "error": await response.text()}
                    
        except Exception as e:
            logger.error(f"Error sending template email: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
    
    # CRM Integration
    async def crm_create_contact(self, user_id: str, contact_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create CRM contact (HubSpot/Salesforce)"""
        try:
            session = await self.get_session()
            url = urljoin(self.backend_api_url, "/integrations/crm/create_contact")
            
            payload = {
                "user_id": user_id,
                "contact": contact_data
            }
            
            async with session.post(url, json=payload) as response:
                if response.status == 200:
                    result = await response.json()
                    return {"success": True, "data": result}
                else:
                    return {"success": False, "error": await response.text()}
                    
        except Exception as e:
            logger.error(f"Error creating CRM contact: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
    
    async def crm_update_lead_score(self, user_id: str, lead_data: Dict[str, Any]) -> Dict[str, Any]:
        """Update CRM lead score"""
        try:
            session = await self.get_session()
            url = urljoin(self.backend_api_url, "/integrations/crm/update_lead_score")
            
            payload = {
                "user_id": user_id,
                "lead": lead_data
            }
            
            async with session.put(url, json=payload) as response:
                if response.status == 200:
                    result = await response.json()
                    return {"success": True, "data": result}
                else:
                    return {"success": False, "error": await response.text()}
                    
        except Exception as e:
            logger.error(f"Error updating lead score: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
    
    # SMS Integration  
    async def sms_send(self, user_id: str, sms_data: Dict[str, Any]) -> Dict[str, Any]:
        """Send SMS via backend API"""
        try:
            session = await self.get_session()
            url = urljoin(self.backend_api_url, "/integrations/sms/send")
            
            payload = {
                "user_id": user_id,
                "sms": sms_data
            }
            
            async with session.post(url, json=payload) as response:
                if response.status == 200:
                    result = await response.json()
                    return {"success": True, "data": result}
                else:
                    return {"success": False, "error": await response.text()}
                    
        except Exception as e:
            logger.error(f"Error sending SMS: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
    
    # Workflow Data Persistence
    async def save_workflow_execution(self, execution_data: Dict[str, Any]) -> Dict[str, Any]:
        """Save workflow execution data to backend"""
        try:
            session = await self.get_session()
            url = urljoin(self.backend_api_url, "/workflows/executions")
            
            async with session.post(url, json=execution_data) as response:
                if response.status == 200:
                    result = await response.json()
                    return {"success": True, "data": result}
                else:
                    return {"success": False, "error": await response.text()}
                    
        except Exception as e:
            logger.error(f"Error saving workflow execution: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
    
    async def update_workflow_status(self, execution_id: str, status: str, step_data: Dict[str, Any] = None) -> Dict[str, Any]:
        """Update workflow execution status"""
        try:
            session = await self.get_session()
            url = urljoin(self.backend_api_url, f"/workflows/executions/{execution_id}/status")
            
            payload = {
                "status": status,
                "step_data": step_data or {},
                "updated_at": datetime.now().isoformat()
            }
            
            async with session.put(url, json=payload) as response:
                if response.status == 200:
                    result = await response.json()
                    return {"success": True, "data": result}
                else:
                    return {"success": False, "error": await response.text()}
                    
        except Exception as e:
            logger.error(f"Error updating workflow status: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
    
    # OAuth Token Management
    async def get_oauth_token(self, user_id: str, provider: str) -> Optional[str]:
        """Get OAuth token for user and provider"""
        try:
            session = await self.get_session()
            url = urljoin(self.backend_api_url, f"/integrations/oauth/{provider}/token/{user_id}")
            
            async with session.get(url) as response:
                if response.status == 200:
                    result = await response.json()
                    return result.get("access_token")
                else:
                    logger.warning(f"No OAuth token found for user {user_id}, provider {provider}")
                    return None
                    
        except Exception as e:
            logger.error(f"Error getting OAuth token: {e}", exc_info=True)
            return None
    
    async def refresh_oauth_token(self, user_id: str, provider: str) -> bool:
        """Refresh OAuth token"""
        try:
            session = await self.get_session()
            url = urljoin(self.backend_api_url, f"/integrations/oauth/{provider}/refresh/{user_id}")
            
            async with session.post(url) as response:
                return response.status == 200
                
        except Exception as e:
            logger.error(f"Error refreshing OAuth token: {e}", exc_info=True)
            return False

    # User Context Management
    async def get_user_context(self, user_id: str) -> Dict[str, Any]:
        """Get user context for workflow personalization"""
        try:
            session = await self.get_session()
            url = urljoin(self.backend_api_url, f"/users/{user_id}/context")
            
            async with session.get(url) as response:
                if response.status == 200:
                    result = await response.json()
                    return result
                else:
                    return {}
                    
        except Exception as e:
            logger.error(f"Error getting user context: {e}", exc_info=True)
            return {}

# Global service instance
_backend_service = None

def get_backend_service() -> WorkflowBackendService:
    """Get singleton backend service instance"""
    global _backend_service
    if _backend_service is None:
        _backend_service = WorkflowBackendService()
    return _backend_service

async def cleanup_backend_service():
    """Cleanup backend service on shutdown"""
    global _backend_service
    if _backend_service and _backend_service.session:
        await _backend_service.session.close()
        _backend_service = None 