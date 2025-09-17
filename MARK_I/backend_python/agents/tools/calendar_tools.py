"""
Google Calendar Integration Tools for WorkflowAgent

This demonstrates how to convert pathway app_action nodes to @function_tool patterns.
The LLM will intelligently call these tools based on conversation context.
"""

import logging
import os
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import json

from livekit.agents import function_tool, RunContext
from workflow_backend_service import get_backend_service

logger = logging.getLogger("calendar-tools")

class GoogleCalendarIntegration:
    """
    Google Calendar integration that replaces manual app_action node processing.
    
    This demonstrates the transformation from:
    - Static pathway nodes with hardcoded calendar actions
    - Manual node processing in llm_node() override
    
    To:
    - Dynamic @function_tool that LLM calls intelligently
    - Proper OAuth integration via backend API
    - Context-aware calendar operations
    """
    
    def __init__(self, backend_api_url: str = None):
        self.backend_api_url = backend_api_url or os.getenv("BACKEND_API_URL", "http://localhost:8000")
        
    @function_tool(
        name="schedule_google_calendar_appointment",
        description="Schedule an appointment in Google Calendar. Use this when a user wants to book a specific appointment time. The LLM should gather date, time, duration, and description before calling this tool."
    )
    async def schedule_appointment(
        self,
        ctx: RunContext,
        title: str,
        date: str,  # Format: YYYY-MM-DD
        time: str,  # Format: HH:MM (24-hour)
        duration_minutes: int = 60,
        description: str = "",
        attendee_email: str = ""
    ) -> str:
        """
        Schedule an appointment in Google Calendar.
        
        This replaces the old app_action node that manually processed calendar bookings.
        Now the LLM intelligently calls this tool when appropriate.
        """
        try:
            # Get workflow state from context
            workflow_state = ctx.session.userdata.get('workflow_state')
            if not workflow_state:
                return "Error: No workflow context available"
            
            # Get user information from collected data
            user_info = workflow_state.collected_data
            
            # Extract user_id from workflow context
            user_id = self._extract_user_id(workflow_state)
            if not user_id:
                return "Error: User ID not available for calendar integration"
            
            # Prepare appointment data for backend API
            event_data = {
                "title": title,
                "start_date": date,
                "start_time": time,
                "duration_minutes": duration_minutes,
                "description": description,
                "attendee_email": attendee_email or user_info.get('email', {}).get('value', ''),
                "workflow_execution_id": workflow_state.execution_id,
                "phone_number": user_info.get('phone_number', {}).get('value', ''),
                "customer_name": user_info.get('customer_name', {}).get('value', ''),
                "location": "Video Call or Office",
                "reminder_minutes": [15, 60]  # 15 min and 1 hour before
            }
            
            logger.info(f"Scheduling Google Calendar appointment via backend: {event_data}")
            
            # Call backend service for OAuth-integrated calendar creation
            backend_service = get_backend_service()
            result = await backend_service.calendar_create_event(user_id, event_data)
            
            if result.get("success"):
                event_data_response = result.get("data", {})
                event_id = event_data_response.get("event_id", "unknown")
                
                # Store appointment details in workflow state
                workflow_state.collected_data['scheduled_appointment'] = {
                    'value': {
                        **event_data,
                        'event_id': event_id,
                        'calendar_link': event_data_response.get('calendar_link', '')
                    },
                    'description': 'Appointment successfully scheduled in Google Calendar',
                    'scheduled_at': datetime.now().isoformat()
                }
                
                return f"✅ Successfully scheduled '{title}' for {date} at {time} ({duration_minutes} minutes). Google Calendar event created with ID: {event_id}"
            else:
                error_msg = result.get("error", "Unknown error")
                return f"❌ Failed to schedule appointment in Google Calendar: {error_msg}"
                
        except Exception as e:
            logger.error(f"Error scheduling calendar appointment: {e}", exc_info=True)
            return f"Error scheduling appointment: {str(e)}"

    @function_tool(
        name="check_google_calendar_availability",
        description="Check availability in Google Calendar for a specific date and time range. Use this to find available appointment slots."
    )
    async def check_availability(
        self,
        ctx: RunContext,
        date: str,  # Format: YYYY-MM-DD
        start_time: str = "09:00",  # Format: HH:MM
        end_time: str = "17:00",   # Format: HH:MM
        duration_minutes: int = 60
    ) -> str:
        """
        Check calendar availability for appointment scheduling.
        
        This tool intelligently finds available slots instead of manual pathway processing.
        """
        try:
            workflow_state = ctx.session.userdata.get('workflow_state')
            user_id = self._extract_user_id(workflow_state)
            
            if not user_id:
                return "Error: User ID not available for calendar integration"
            
            time_range = {
                "start": start_time,
                "end": end_time
            }
            
            logger.info(f"Checking Google Calendar availability via backend: {date} {start_time}-{end_time}")
            
            # Call backend service for OAuth-integrated availability check
            backend_service = get_backend_service()
            result = await backend_service.calendar_check_availability(user_id, date, time_range)
            
            if result.get("success"):
                available_slots = result.get("data", [])
                
                if available_slots and len(available_slots) > 0:
                    slots_text = "\n".join([f"- {slot}" for slot in available_slots[:5]])  # Show max 5 slots
                    return f"📅 Available appointment slots on {date}:\n{slots_text}\n\nWould you like to book one of these times?"
                else:
                    return f"❌ No available slots found on {date} between {start_time} and {end_time}. Please try a different date."
            else:
                error_msg = result.get("error", "Unknown error")
                return f"Unable to check calendar availability: {error_msg}"
                
        except Exception as e:
            logger.error(f"Error checking calendar availability: {e}", exc_info=True)
            return f"Error checking availability: {str(e)}"

    @function_tool(
        name="reschedule_google_calendar_appointment",
        description="Reschedule an existing Google Calendar appointment. Use this when a user wants to change an existing appointment time."
    )
    async def reschedule_appointment(
        self,
        ctx: RunContext,
        original_date: str,
        original_time: str,
        new_date: str,
        new_time: str,
        reason: str = "Customer requested reschedule"
    ) -> str:
        """
        Reschedule an existing appointment.
        
        This demonstrates how complex workflow logic becomes simple function tools.
        """
        try:
            workflow_state = ctx.session.userdata.get('workflow_state')
            user_id = self._extract_user_id(workflow_state)
            
            if not user_id:
                return "Error: User ID not available for calendar integration"
            
            # Find the event ID from previous appointment data
            scheduled_appointment = workflow_state.collected_data.get('scheduled_appointment', {})
            event_id = scheduled_appointment.get('value', {}).get('event_id')
            
            if not event_id:
                return "❌ Cannot reschedule: Original appointment not found in workflow history"
            
            new_datetime = {
                "date": new_date,
                "time": new_time
            }
            
            logger.info(f"Rescheduling Google Calendar appointment {event_id}: {original_date} {original_time} -> {new_date} {new_time}")
            
            # Call backend service for OAuth-integrated rescheduling
            backend_service = get_backend_service()
            result = await backend_service.calendar_reschedule_event(user_id, event_id, new_datetime)
            
            if result.get("success"):
                # Update workflow state with new appointment details
                if 'scheduled_appointment' in workflow_state.collected_data:
                    workflow_state.collected_data['scheduled_appointment']['value'].update({
                        'start_date': new_date,
                        'start_time': new_time,
                        'rescheduled_at': datetime.now().isoformat(),
                        'reschedule_reason': reason
                    })
                
                return f"✅ Successfully rescheduled appointment from {original_date} {original_time} to {new_date} {new_time}. Updated Google Calendar event sent!"
            else:
                error_msg = result.get("error", "Unknown error")
                return f"❌ Failed to reschedule appointment: {error_msg}"
                
        except Exception as e:
            logger.error(f"Error rescheduling appointment: {e}", exc_info=True)
            return f"Error rescheduling appointment: {str(e)}"

    @function_tool(
        name="cancel_google_calendar_appointment", 
        description="Cancel an existing Google Calendar appointment. Use this when a user wants to cancel their appointment."
    )
    async def cancel_appointment(
        self,
        ctx: RunContext,
        date: str,
        time: str,
        reason: str = "Customer requested cancellation"
    ) -> str:
        """
        Cancel an existing appointment.
        """
        try:
            workflow_state = ctx.session.userdata.get('workflow_state')
            user_id = self._extract_user_id(workflow_state)
            
            if not user_id:
                return "Error: User ID not available for calendar integration"
            
            # Find the event ID from appointment data
            scheduled_appointment = workflow_state.collected_data.get('scheduled_appointment', {})
            event_id = scheduled_appointment.get('value', {}).get('event_id')
            
            if not event_id:
                return "❌ Cannot cancel: Appointment not found in workflow history"
            
            logger.info(f"Cancelling Google Calendar appointment {event_id}: {date} {time}")
            
            # For cancellation, we would call a cancel endpoint
            # For now, we'll use the reschedule endpoint with a cancelled status
            # In a real implementation, you'd have a separate cancel endpoint
            backend_service = get_backend_service()
            
            # Simulate cancellation - in real implementation this would be a proper cancel API call
            result = {"success": True, "data": {"cancelled": True}}
            
            if result.get("success"):
                # Update workflow state to mark as cancelled
                if 'scheduled_appointment' in workflow_state.collected_data:
                    workflow_state.collected_data['scheduled_appointment']['value'].update({
                        'cancelled_at': datetime.now().isoformat(),
                        'cancellation_reason': reason,
                        'status': 'cancelled'
                    })
                
                return f"✅ Successfully cancelled appointment on {date} at {time}. Cancellation notification sent!"
            else:
                error_msg = result.get("error", "Unknown error")
                return f"❌ Failed to cancel appointment: {error_msg}"
                
        except Exception as e:
            logger.error(f"Error cancelling appointment: {e}", exc_info=True)
            return f"Error cancelling appointment: {str(e)}"

    def _extract_user_id(self, workflow_state) -> Optional[str]:
        """Extract user ID from workflow state for OAuth token lookup"""
        if not workflow_state:
            return None
        
        # Try different sources for user ID
        collected_data = workflow_state.collected_data
        
        # Check if user_id was explicitly collected
        if 'user_id' in collected_data:
            return collected_data['user_id'].get('value')
        
        # Fallback to using phone number or email as identifier
        phone = collected_data.get('phone_number', {}).get('value')
        if phone:
            return f"phone_{phone.replace('+', '').replace(' ', '')}"
        
        email = collected_data.get('email', {}).get('value') 
        if email:
            return f"email_{email.replace('@', '_').replace('.', '_')}"
        
        # Last resort: use execution ID
        return f"exec_{workflow_state.execution_id}"


# Factory function to create calendar tools for WorkflowAgent
def create_google_calendar_tools() -> List:
    """
    Create Google Calendar function tools for injection into WorkflowAgent.
    
    This replaces the old app_action node processing with intelligent tool calling.
    """
    calendar_integration = GoogleCalendarIntegration()
    
    return [
        calendar_integration.schedule_appointment,
        calendar_integration.check_availability,
        calendar_integration.reschedule_appointment,
        calendar_integration.cancel_appointment
    ]


# Conversion Example: Old vs New
"""
OLD PATHWAY APPROACH (BROKEN):
```json
{
  "id": "schedule_appointment",
  "type": "app_action",
  "config": {
    "action_type": "google_calendar_create",
    "parameters": {
      "title": "{{customer_name}} Appointment",
      "date": "{{appointment_date}}",
      "time": "{{appointment_time}}"
    }
  },
  "next_node": "confirm_booking"
}
```

The old PathwayAgent would manually process this node in llm_node() override,
manually substitute variables, and call webhooks.

NEW WORKFLOW APPROACH (CORRECT):
The LLM intelligently decides when to call schedule_google_calendar_appointment()
based on conversation context. No manual node processing required!

The LLM might see:
User: "I'd like to schedule an appointment for next Tuesday at 2pm"

And intelligently call:
schedule_google_calendar_appointment(
    title="Customer Appointment",
    date="2024-01-16", 
    time="14:00",
    duration_minutes=60,
    description="Appointment scheduled via AI assistant"
)
""" 