"""
App action handlers for executing integrations within pathways
"""
import asyncio
import aiohttp
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from .oauth_utils import get_user_connection_with_valid_creds, make_authenticated_request
from .db_client import get_supabase_anon_client
import json

class AppActionError(Exception):
    """Custom exception for app action errors"""
    def __init__(self, message: str, app_name: str, action_type: str, details: Optional[Dict[str, Any]] = None):
        self.message = message
        self.app_name = app_name
        self.action_type = action_type
        self.details = details or {}
        super().__init__(self.message)

async def execute_pathway_app_action(
    pathway_app_action: Dict[str, Any],
    call_context: Dict[str, Any],
    pathway_variables: Dict[str, Any] = None
) -> Dict[str, Any]:
    """
    Execute an app action from a pathway
    
    Args:
        pathway_app_action: Database record from pathway_app_actions table
        call_context: Context data from the current call
        pathway_variables: Current pathway variables
        
    Returns:
        Dictionary containing action results
    """
    try:
        app_name = pathway_app_action["app_integrations"]["name"]
        action_type = pathway_app_action["action_type"]
        action_config = pathway_app_action.get("action_config", {})
        field_mappings = pathway_app_action.get("field_mappings", {})
        
        # Get user connection
        connection_id = pathway_app_action["user_connection_id"]
        user_id = call_context.get("user_id")
        
        if not user_id:
            raise AppActionError("No user_id in call context", app_name, action_type)
        
        # Map call context variables to action parameters
        action_data = map_fields(call_context, field_mappings, pathway_variables)
        action_data.update(action_config)
        
        # Execute based on app type
        if app_name == "hubspot":
            result = await execute_hubspot_action(connection_id, user_id, action_type, action_data)
        elif app_name == "google_calendar":
            result = await execute_google_calendar_action(connection_id, user_id, action_type, action_data)
        elif app_name == "slack":
            result = await execute_slack_action(connection_id, user_id, action_type, action_data)
        elif app_name == "zapier":
            result = await execute_zapier_action(connection_id, user_id, action_type, action_data)
        else:
            raise AppActionError(f"Unsupported app: {app_name}", app_name, action_type)
        
        # Log successful execution
        await log_app_action_execution(pathway_app_action["id"], "success", result)
        
        return {
            "status": "success",
            "app_name": app_name,
            "action_type": action_type,
            "result": result
        }
        
    except Exception as e:
        error_details = {
            "error": str(e),
            "app_name": app_name if 'app_name' in locals() else "unknown",
            "action_type": action_type if 'action_type' in locals() else "unknown"
        }
        
        # Log failed execution
        if 'pathway_app_action' in locals():
            await log_app_action_execution(pathway_app_action["id"], "error", error_details)
        
        raise AppActionError(f"App action failed: {str(e)}", 
                           error_details["app_name"], 
                           error_details["action_type"], 
                           error_details)

def map_fields(call_context: Dict[str, Any], field_mappings: Dict[str, Any], pathway_variables: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Map call context and pathway variables to action parameters
    
    Args:
        call_context: Data from the current call
        field_mappings: Mapping configuration from pathway_app_actions
        pathway_variables: Current pathway execution variables
        
    Returns:
        Dictionary with mapped values
    """
    mapped_data = {}
    all_variables = {**(pathway_variables or {}), **call_context}
    
    for target_field, source_mapping in field_mappings.items():
        if isinstance(source_mapping, str):
            # Simple field mapping: "email" -> call_context["customer_email"]
            if source_mapping in all_variables:
                mapped_data[target_field] = all_variables[source_mapping]
        elif isinstance(source_mapping, dict):
            # Complex mapping with transformations
            if "source" in source_mapping:
                source_value = all_variables.get(source_mapping["source"])
                
                # Apply transformations
                if source_value and "transform" in source_mapping:
                    transform = source_mapping["transform"]
                    if transform == "uppercase":
                        source_value = source_value.upper()
                    elif transform == "lowercase":
                        source_value = source_value.lower()
                    elif transform == "phone_format":
                        # Format phone number to E.164
                        source_value = format_phone_number(source_value)
                
                mapped_data[target_field] = source_value
            elif "static" in source_mapping:
                # Static value
                mapped_data[target_field] = source_mapping["static"]
    
    return mapped_data

def format_phone_number(phone: str) -> str:
    """Format phone number to E.164 format"""
    if not phone:
        return phone
    
    # Remove all non-digit characters
    digits = ''.join(filter(str.isdigit, phone))
    
    # Add + prefix if not present
    if not digits.startswith('+'):
        if len(digits) == 10:  # US number
            digits = '+1' + digits
        elif len(digits) == 11 and digits.startswith('1'):  # US number with country code
            digits = '+' + digits
        else:
            digits = '+' + digits
    
    return digits

# HubSpot Actions
async def execute_hubspot_action(connection_id: str, user_id: str, action_type: str, action_data: Dict[str, Any]) -> Dict[str, Any]:
    """Execute HubSpot actions"""
    
    if action_type == "create_contact":
        return await hubspot_create_contact(connection_id, user_id, action_data)
    elif action_type == "update_contact":
        return await hubspot_update_contact(connection_id, user_id, action_data)
    elif action_type == "create_deal":
        return await hubspot_create_deal(connection_id, user_id, action_data)
    elif action_type == "add_note":
        return await hubspot_add_note(connection_id, user_id, action_data)
    elif action_type == "search_contacts":
        return await hubspot_search_contacts(connection_id, user_id, action_data)
    else:
        raise AppActionError(f"Unsupported HubSpot action: {action_type}", "hubspot", action_type)

async def hubspot_create_contact(connection_id: str, user_id: str, action_data: Dict[str, Any]) -> Dict[str, Any]:
    """Create a new contact in HubSpot"""
    
    # Prepare contact properties
    properties = {}
    
    # Map common fields
    field_mapping = {
        "email": "email",
        "firstname": "first_name",
        "lastname": "last_name", 
        "phone": "phone_number",
        "company": "company",
        "website": "website"
    }
    
    for hubspot_field, action_field in field_mapping.items():
        if action_field in action_data and action_data[action_field]:
            properties[hubspot_field] = action_data[action_field]
    
    # Add custom properties from action_data
    custom_properties = action_data.get("custom_properties", {})
    properties.update(custom_properties)
    
    # Add call-specific data
    if action_data.get("call_date"):
        properties["hs_lead_status"] = "NEW"
        properties["notes"] = f"Contact created from PAM call on {action_data.get('call_date')}"
    
    request_body = {"properties": properties}
    
    response = await make_authenticated_request(
        connection_id, user_id, "POST",
        "https://api.hubapi.com/crm/v3/objects/contacts",
        json=request_body
    )
    
    return {
        "contact_id": response["id"],
        "properties": response["properties"],
        "created_at": response["createdAt"]
    }

async def hubspot_create_deal(connection_id: str, user_id: str, action_data: Dict[str, Any]) -> Dict[str, Any]:
    """Create a new deal in HubSpot"""
    
    properties = {
        "dealname": action_data.get("deal_name", "New Deal from PAM"),
        "dealstage": action_data.get("deal_stage", "appointmentscheduled"),
        "amount": action_data.get("amount", "0"),
        "pipeline": action_data.get("pipeline", "default")
    }
    
    # Add custom properties
    custom_properties = action_data.get("custom_properties", {})
    properties.update(custom_properties)
    
    request_body = {"properties": properties}
    
    response = await make_authenticated_request(
        connection_id, user_id, "POST",
        "https://api.hubapi.com/crm/v3/objects/deals",
        json=request_body
    )
    
    return {
        "deal_id": response["id"],
        "properties": response["properties"],
        "created_at": response["createdAt"]
    }

# Google Calendar Actions
async def execute_google_calendar_action(connection_id: str, user_id: str, action_type: str, action_data: Dict[str, Any]) -> Dict[str, Any]:
    """Execute Google Calendar actions"""
    
    if action_type == "create_event":
        return await calendar_create_event(connection_id, user_id, action_data)
    elif action_type == "check_availability":
        return await calendar_check_availability(connection_id, user_id, action_data)
    elif action_type == "list_events":
        return await calendar_list_events(connection_id, user_id, action_data)
    elif action_type == "update_event":
        return await calendar_update_event(connection_id, user_id, action_data)
    elif action_type == "cancel_event":
        return await calendar_cancel_event(connection_id, user_id, action_data)
    else:
        raise AppActionError(f"Unsupported Google Calendar action: {action_type}", "google_calendar", action_type)

async def calendar_create_event(connection_id: str, user_id: str, action_data: Dict[str, Any]) -> Dict[str, Any]:
    """Create a calendar event"""
    
    # Default to 1 hour meeting if no end time specified
    start_time = action_data.get("start_time")
    end_time = action_data.get("end_time")
    
    if start_time and not end_time:
        start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
        end_dt = start_dt + timedelta(hours=1)
        end_time = end_dt.isoformat()
    
    event_data = {
        "summary": action_data.get("title", "Follow-up Meeting"),
        "description": action_data.get("description", "Meeting created from PAM call"),
        "start": {
            "dateTime": start_time,
            "timeZone": action_data.get("timezone", "UTC")
        },
        "end": {
            "dateTime": end_time,
            "timeZone": action_data.get("timezone", "UTC")
        }
    }
    
    # Add attendees if provided
    attendees = action_data.get("attendees", [])
    if attendees:
        event_data["attendees"] = [{"email": email} for email in attendees]
    
    calendar_id = action_data.get("calendar_id", "primary")
    
    response = await make_authenticated_request(
        connection_id, user_id, "POST",
        f"https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events",
        json=event_data
    )
    
    return {
        "event_id": response["id"],
        "summary": response["summary"],
        "start_time": response["start"]["dateTime"],
        "end_time": response["end"]["dateTime"],
        "html_link": response["htmlLink"]
    }

# Slack Actions
async def execute_slack_action(connection_id: str, user_id: str, action_type: str, action_data: Dict[str, Any]) -> Dict[str, Any]:
    """Execute Slack actions"""
    
    if action_type == "send_message":
        return await slack_send_message(connection_id, user_id, action_data)
    elif action_type == "send_dm":
        return await slack_send_dm(connection_id, user_id, action_data)
    elif action_type == "send_alert":
        return await slack_send_alert(connection_id, user_id, action_data)
    else:
        raise AppActionError(f"Unsupported Slack action: {action_type}", "slack", action_type)

async def slack_send_message(connection_id: str, user_id: str, action_data: Dict[str, Any]) -> Dict[str, Any]:
    """Send a message to a Slack channel"""
    
    message_data = {
        "channel": action_data.get("channel", "#general"),
        "text": action_data.get("message", "Message from PAM"),
        "username": action_data.get("username", "PAM Bot")
    }
    
    # Add rich formatting if provided
    if "blocks" in action_data:
        message_data["blocks"] = action_data["blocks"]
    
    response = await make_authenticated_request(
        connection_id, user_id, "POST",
        "https://slack.com/api/chat.postMessage",
        json=message_data
    )
    
    if not response.get("ok"):
        raise AppActionError(f"Slack API error: {response.get('error')}", "slack", "send_message")
    
    return {
        "message_ts": response["ts"],
        "channel": response["channel"],
        "message": response["message"]["text"]
    }

# Zapier Actions
async def execute_zapier_action(connection_id: str, user_id: str, action_type: str, action_data: Dict[str, Any]) -> Dict[str, Any]:
    """Execute Zapier webhook actions"""
    
    if action_type == "trigger_webhook":
        return await zapier_trigger_webhook(action_data)
    else:
        raise AppActionError(f"Unsupported Zapier action: {action_type}", "zapier", action_type)

async def zapier_trigger_webhook(action_data: Dict[str, Any]) -> Dict[str, Any]:
    """Trigger a Zapier webhook"""
    
    webhook_url = action_data.get("webhook_url")
    if not webhook_url:
        raise AppActionError("No webhook_url provided for Zapier action", "zapier", "trigger_webhook")
    
    # Prepare payload
    payload = {
        "trigger_source": "pam",
        "timestamp": datetime.utcnow().isoformat(),
        **action_data.get("data", {})
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post(webhook_url, json=payload) as response:
            if response.status >= 400:
                error_text = await response.text()
                raise AppActionError(f"Zapier webhook failed: {error_text}", "zapier", "trigger_webhook")
            
            response_data = await response.json() if response.headers.get('content-type', '').startswith('application/json') else {"status": "triggered"}
            
    return {
        "webhook_url": webhook_url,
        "status_code": response.status,
        "response": response_data
    }

async def log_app_action_execution(pathway_app_action_id: str, status: str, result: Dict[str, Any]):
    """Log app action execution for debugging and analytics"""
    try:
        supabase = get_supabase_anon_client()
        
        log_data = {
            "pathway_app_action_id": pathway_app_action_id,
            "execution_status": status,
            "execution_result": result,
            "executed_at": datetime.utcnow().isoformat()
        }
        
        # You might want to create an app_action_executions table for this
        # For now, we'll just print for debugging
        print(f"App action execution: {log_data}")
        
    except Exception as e:
        print(f"Failed to log app action execution: {str(e)}")

# Utility function to get available actions for an app
def get_available_actions_for_app(app_name: str) -> List[Dict[str, Any]]:
    """Get list of available actions for an app"""
    
    actions = {
        "hubspot": [
            {"action": "create_contact", "description": "Create a new contact", "required_fields": ["email"]},
            {"action": "update_contact", "description": "Update an existing contact", "required_fields": ["contact_id"]},
            {"action": "create_deal", "description": "Create a new deal", "required_fields": ["deal_name"]},
            {"action": "add_note", "description": "Add note to contact", "required_fields": ["contact_id", "note"]},
            {"action": "search_contacts", "description": "Search for contacts", "required_fields": ["query"]}
        ],
        "google_calendar": [
            {"action": "create_event", "description": "Create a calendar event", "required_fields": ["title", "start_time"]},
            {"action": "check_availability", "description": "Check calendar availability", "required_fields": ["start_time", "end_time"]},
            {"action": "list_events", "description": "List upcoming events", "required_fields": []},
            {"action": "update_event", "description": "Update an event", "required_fields": ["event_id"]},
            {"action": "cancel_event", "description": "Cancel an event", "required_fields": ["event_id"]}
        ],
        "slack": [
            {"action": "send_message", "description": "Send message to channel", "required_fields": ["channel", "message"]},
            {"action": "send_dm", "description": "Send direct message", "required_fields": ["user", "message"]},
            {"action": "send_alert", "description": "Send alert notification", "required_fields": ["message"]}
        ],
        "zapier": [
            {"action": "trigger_webhook", "description": "Trigger Zapier webhook", "required_fields": ["webhook_url"]}
        ]
    }
    
    return actions.get(app_name, []) 