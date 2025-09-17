"""
Email Integration Tools for WorkflowAgent

Demonstrates scalable @function_tool pattern for email app actions.
LLM intelligently sends emails based on conversation context.
"""

import logging
import os
from typing import Dict, Any, Optional, List
from datetime import datetime
import json

from livekit.agents import function_tool, RunContext
from workflow_backend_service import get_backend_service

logger = logging.getLogger("email-tools")

class EmailIntegration:
    """
    Email integration that converts email app_action nodes to intelligent function tools.
    
    OLD PATHWAY APPROACH:
    {
      "type": "app_action", 
      "config": {
        "action_type": "send_email",
        "parameters": {
          "to": "{{customer_email}}",
          "subject": "Appointment Confirmation",
          "template": "appointment_confirmation"
        }
      }
    }
    
    NEW WORKFLOW APPROACH:
    LLM intelligently calls send_email() tool when appropriate context exists.
    """
    
    def __init__(self, backend_api_url: str = None):
        self.backend_api_url = backend_api_url or os.getenv("BACKEND_API_URL", "http://localhost:8000")
        
    @function_tool(
        name="send_email",
        description="Send an email to a customer. Use this to send confirmations, follow-ups, or important information. Gather recipient email, subject, and message content before calling."
    )
    async def send_email(
        self,
        ctx: RunContext,
        to_email: str,
        subject: str,
        message: str,
        cc_email: str = "",
        template_name: str = "",
        priority: str = "normal"  # normal, high, low
    ) -> str:
        """
        Send an email intelligently based on conversation context.
        
        The LLM decides when to send emails rather than hardcoded pathway rules.
        """
        try:
            # Get workflow state for context
            workflow_state = ctx.session.userdata.get('workflow_state')
            if not workflow_state:
                return "Error: No workflow context available for email"
            
            # Get customer information from collected data
            user_info = workflow_state.collected_data
            
            # Prepare email data
            email_data = {
                "to_email": to_email,
                "subject": subject,
                "message": message,
                "cc_email": cc_email,
                "template_name": template_name,
                "priority": priority,
                "workflow_execution_id": workflow_state.execution_id,
                "customer_name": user_info.get('customer_name', {}).get('value', ''),
                "phone_number": user_info.get('phone_number', {}).get('value', ''),
                "sent_at": datetime.now().isoformat()
            }
            
            logger.info(f"Sending email via workflow: {email_data}")
            
            # Call backend API to send email
            success = await self._call_backend_email_api("send_email", email_data)
            
            if success:
                # Store email record in workflow state
                workflow_state.collected_data['sent_email'] = {
                    'value': email_data,
                    'description': f'Email sent to {to_email}',
                    'sent_at': datetime.now().isoformat()
                }
                
                return f"✅ Email sent successfully to {to_email} with subject: '{subject}'"
            else:
                return f"❌ Failed to send email to {to_email}. Please try again."
                
        except Exception as e:
            logger.error(f"Error sending email: {e}", exc_info=True)
            return f"Error sending email: {str(e)}"

    @function_tool(
        name="send_appointment_confirmation_email",
        description="Send an appointment confirmation email with calendar details. Use this after successfully scheduling an appointment."
    )
    async def send_appointment_confirmation(
        self,
        ctx: RunContext,
        customer_email: str,
        appointment_date: str,
        appointment_time: str,
        service_type: str = "Appointment",
        additional_notes: str = ""
    ) -> str:
        """
        Send appointment confirmation email with professional template.
        """
        try:
            workflow_state = ctx.session.userdata.get('workflow_state')
            customer_name = "Valued Customer"
            
            if workflow_state:
                customer_name = workflow_state.collected_data.get('customer_name', {}).get('value', customer_name)
            
            # Create professional appointment confirmation message
            confirmation_message = f"""
Dear {customer_name},

This email confirms your upcoming appointment:

📅 Date: {appointment_date}
🕐 Time: {appointment_time}
📋 Service: {service_type}

{additional_notes}

Please arrive 15 minutes early for check-in. If you need to reschedule or cancel, please contact us at least 24 hours in advance.

Thank you for choosing our services!

Best regards,
Wellness Partners Team
            """.strip()
            
            email_data = {
                "to_email": customer_email,
                "subject": f"Appointment Confirmation - {appointment_date} at {appointment_time}",
                "message": confirmation_message,
                "template_name": "appointment_confirmation",
                "priority": "high",
                "appointment_details": {
                    "date": appointment_date,
                    "time": appointment_time,
                    "service": service_type,
                    "customer_name": customer_name
                }
            }
            
            logger.info(f"Sending appointment confirmation email: {email_data}")
            
            success = await self._call_backend_email_api("send_template_email", email_data)
            
            if success:
                return f"✅ Appointment confirmation sent to {customer_email} for {appointment_date} at {appointment_time}"
            else:
                return f"❌ Failed to send confirmation email to {customer_email}"
                
        except Exception as e:
            logger.error(f"Error sending appointment confirmation: {e}", exc_info=True)
            return f"Error sending confirmation: {str(e)}"

    @function_tool(
        name="send_follow_up_email",
        description="Send a follow-up email to a customer. Use this for post-appointment follow-ups, survey requests, or continued engagement."
    )
    async def send_follow_up_email(
        self,
        ctx: RunContext,
        customer_email: str,
        follow_up_type: str,  # survey, thank_you, reminder, promotional
        message: str = "",
        days_after: int = 1
    ) -> str:
        """
        Send intelligent follow-up emails based on workflow context.
        """
        try:
            workflow_state = ctx.session.userdata.get('workflow_state')
            customer_name = "Valued Customer"
            
            if workflow_state:
                customer_name = workflow_state.collected_data.get('customer_name', {}).get('value', customer_name)
            
            # Generate follow-up content based on type
            if follow_up_type == "survey":
                subject = "How was your experience with us?"
                default_message = f"""
Dear {customer_name},

Thank you for choosing our services! We'd love to hear about your experience.

Please take a moment to share your feedback: [Survey Link]

Your input helps us continue providing excellent service.

Best regards,
Customer Experience Team
                """.strip()
            elif follow_up_type == "thank_you":
                subject = "Thank you for choosing our services!"
                default_message = f"""
Dear {customer_name},

Thank you for your recent visit! It was a pleasure serving you.

If you have any questions or need assistance, please don't hesitate to contact us.

We look forward to seeing you again soon!

Best regards,
Team
                """.strip()
            else:
                subject = f"Follow-up from your recent visit"
                default_message = message or f"Dear {customer_name}, thank you for your business!"
            
            final_message = message if message else default_message
            
            email_data = {
                "to_email": customer_email,
                "subject": subject,
                "message": final_message,
                "template_name": f"follow_up_{follow_up_type}",
                "priority": "normal",
                "follow_up_type": follow_up_type,
                "scheduled_days": days_after
            }
            
            logger.info(f"Sending follow-up email: {email_data}")
            
            success = await self._call_backend_email_api("send_follow_up", email_data)
            
            if success:
                return f"✅ {follow_up_type.title()} follow-up email sent to {customer_email}"
            else:
                return f"❌ Failed to send follow-up email to {customer_email}"
                
        except Exception as e:
            logger.error(f"Error sending follow-up email: {e}", exc_info=True)
            return f"Error sending follow-up: {str(e)}"

    async def _call_backend_email_api(self, action: str, data: Dict[str, Any]) -> bool:
        """
        Call the backend API for email operations.
        
        This handles email service integration (SendGrid, AWS SES, etc.)
        """
        try:
            # Extract user_id from email data
            user_id = data.get('user_id') or self._extract_user_id_from_context(data)
            
            if not user_id:
                logger.error("No user_id available for email API call")
                return False
            
            backend_service = get_backend_service()
            
            # Call appropriate backend service method
            if action == "send_email":
                result = await backend_service.email_send(user_id, data)
            elif action == "send_template_email":
                result = await backend_service.email_send_template(user_id, data)
            elif action == "send_follow_up":
                result = await backend_service.email_send_template(user_id, data)
            else:
                logger.error(f"Unknown email action: {action}")
                return False
            
            return result.get("success", False)
                        
        except Exception as e:
            logger.error(f"Error calling email backend service: {e}", exc_info=True)
            return False

    def _extract_user_id_from_context(self, data: Dict[str, Any]) -> Optional[str]:
        """Extract user_id from email data context"""
        # Try to extract from workflow execution ID or phone number
        workflow_id = data.get('workflow_execution_id')
        if workflow_id:
            return f"exec_{workflow_id}"
        
        phone = data.get('phone_number')
        if phone:
            return f"phone_{phone.replace('+', '').replace(' ', '')}"
        
        email = data.get('to_email')
        if email:
            return f"email_{email.replace('@', '_').replace('.', '_')}"
        
        return None

    def _simulate_email_send(self, action: str, data: Dict[str, Any]) -> bool:
        """Simulate email sending for demonstration"""
        logger.info(f"SIMULATED EMAIL: {action}")
        logger.info(f"  To: {data.get('to_email')}")
        logger.info(f"  Subject: {data.get('subject')}")
        logger.info(f"  Message: {data.get('message', '')[:100]}...")
        return True


# Factory function for email tools
def create_email_tools() -> List:
    """
    Create email function tools for WorkflowAgent injection.
    
    Replaces hardcoded email app_action nodes with intelligent tool calling.
    """
    email_integration = EmailIntegration()
    
    return [
        email_integration.send_email,
        email_integration.send_appointment_confirmation,
        email_integration.send_follow_up_email
    ]


# Example: Converting Email App Action Nodes
"""
OLD PATHWAY EMAIL NODE (BROKEN):
```json
{
  "id": "send_confirmation",
  "type": "app_action",
  "config": {
    "action_type": "send_email",
    "parameters": {
      "to": "{{customer_email}}",
      "subject": "Appointment Confirmed",
      "template": "confirmation",
      "variables": {
        "name": "{{customer_name}}",
        "date": "{{appointment_date}}"
      }
    }
  },
  "next_node": "end_workflow"
}
```

Problems with old approach:
- Manual variable substitution
- Hardcoded email templates
- No intelligent timing
- Manual webhook calls
- No error handling

NEW WORKFLOW EMAIL APPROACH (INTELLIGENT):
The LLM sees conversation context like:
"Great! I've scheduled your appointment for Tuesday at 2pm"

And intelligently calls:
send_appointment_confirmation_email(
    customer_email="john@example.com",
    appointment_date="2024-01-16", 
    appointment_time="14:00",
    service_type="Consultation"
)

Benefits:
- LLM decides when to send emails
- Dynamic content based on conversation
- Professional templates with context
- Proper error handling
- Workflow state integration
""" 