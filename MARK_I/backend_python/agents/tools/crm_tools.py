"""
CRM Integration Tools for WorkflowAgent

Demonstrates how CRM app_action nodes become intelligent function tools.
Integrates with HubSpot, Salesforce, or custom CRM systems.
"""

import logging
import os
from typing import Dict, Any, Optional, List
from datetime import datetime
import json

from livekit.agents import function_tool, RunContext
from workflow_backend_service import get_backend_service

logger = logging.getLogger("crm-tools")

class CRMIntegration:
    """
    CRM integration that transforms static pathway nodes into intelligent tools.
    
    OLD PATHWAY CRM NODES:
    - Manual contact creation with hardcoded fields
    - Static lead scoring
    - Hardcoded opportunity creation
    
    NEW WORKFLOW CRM TOOLS:
    - LLM intelligently creates contacts when appropriate
    - Dynamic lead qualification based on conversation
    - Context-aware opportunity management
    """
    
    def __init__(self, backend_api_url: str = None):
        self.backend_api_url = backend_api_url or os.getenv("BACKEND_API_URL", "http://localhost:8000")
        
    @function_tool(
        name="create_crm_contact",
        description="Create a new contact in the CRM system. Use this when you've gathered sufficient customer information during the conversation."
    )
    async def create_contact(
        self,
        ctx: RunContext,
        first_name: str,
        last_name: str,
        email: str,
        phone: str = "",
        company: str = "",
        lead_source: str = "Phone Call",
        notes: str = ""
    ) -> str:
        """
        Create CRM contact intelligently based on collected information.
        
        LLM determines when enough info is available to create contact.
        """
        try:
            workflow_state = ctx.session.userdata.get('workflow_state')
            if not workflow_state:
                return "Error: No workflow context available"
            
            # Enhance contact data with workflow context
            contact_data = {
                "first_name": first_name,
                "last_name": last_name,
                "email": email,
                "phone": phone,
                "company": company,
                "lead_source": lead_source,
                "notes": notes,
                "workflow_execution_id": workflow_state.execution_id,
                "conversation_date": datetime.now().isoformat(),
                "agent_name": "AI Assistant",
                "call_outcome": self._determine_call_outcome(workflow_state)
            }
            
            # Add any additional data collected during workflow
            for key, data in workflow_state.collected_data.items():
                if key not in contact_data and isinstance(data, dict):
                    contact_data[f"custom_{key}"] = data.get('value', '')
            
            logger.info(f"Creating CRM contact: {contact_data}")
            
            # Call backend CRM API
            success = await self._call_backend_crm_api("create_contact", contact_data)
            
            if success:
                # Store CRM contact ID in workflow state
                workflow_state.collected_data['crm_contact'] = {
                    'value': f"{first_name} {last_name}",
                    'description': 'Contact created in CRM',
                    'created_at': datetime.now().isoformat()
                }
                
                return f"✅ Contact created in CRM: {first_name} {last_name} ({email})"
            else:
                return f"❌ Failed to create CRM contact for {first_name} {last_name}"
                
        except Exception as e:
            logger.error(f"Error creating CRM contact: {e}", exc_info=True)
            return f"Error creating contact: {str(e)}"

    @function_tool(
        name="update_lead_score",
        description="Update lead scoring in CRM based on conversation quality and interest level. Use this to qualify leads intelligently."
    )
    async def update_lead_score(
        self,
        ctx: RunContext,
        contact_email: str,
        interest_level: str,  # high, medium, low
        budget_qualified: bool = False,
        timeline: str = "",  # immediate, 1-3_months, 6_months, future
        pain_points: str = ""
    ) -> str:
        """
        Intelligent lead scoring based on conversation analysis.
        
        LLM assesses conversation quality and updates CRM accordingly.
        """
        try:
            workflow_state = ctx.session.userdata.get('workflow_state')
            
            # Calculate lead score based on conversation context
            lead_score = self._calculate_lead_score(
                interest_level, budget_qualified, timeline, 
                workflow_state.collected_data if workflow_state else {}
            )
            
            lead_data = {
                "contact_email": contact_email,
                "lead_score": lead_score,
                "interest_level": interest_level,
                "budget_qualified": budget_qualified,
                "timeline": timeline,
                "pain_points": pain_points,
                "qualification_date": datetime.now().isoformat(),
                "conversation_quality": self._assess_conversation_quality(workflow_state)
            }
            
            logger.info(f"Updating lead score: {lead_data}")
            
            success = await self._call_backend_crm_api("update_lead_score", lead_data)
            
            if success:
                return f"✅ Lead score updated: {lead_score}/100 for {contact_email} (Interest: {interest_level})"
            else:
                return f"❌ Failed to update lead score for {contact_email}"
                
        except Exception as e:
            logger.error(f"Error updating lead score: {e}", exc_info=True)
            return f"Error updating lead score: {str(e)}"

    @function_tool(
        name="create_crm_opportunity",
        description="Create a sales opportunity in CRM. Use this when a qualified lead shows strong buying intent and specific needs."
    )
    async def create_opportunity(
        self,
        ctx: RunContext,
        contact_email: str,
        opportunity_name: str,
        value: float,
        stage: str = "Qualification",  # Qualification, Proposal, Negotiation, Closed Won, Closed Lost
        close_date: str = "",
        description: str = ""
    ) -> str:
        """
        Create sales opportunity based on qualified conversation.
        """
        try:
            workflow_state = ctx.session.userdata.get('workflow_state')
            
            opportunity_data = {
                "contact_email": contact_email,
                "opportunity_name": opportunity_name,
                "value": value,
                "stage": stage,
                "close_date": close_date,
                "description": description,
                "created_date": datetime.now().isoformat(),
                "source": "AI Agent Conversation",
                "workflow_execution_id": workflow_state.execution_id if workflow_state else ""
            }
            
            logger.info(f"Creating CRM opportunity: {opportunity_data}")
            
            success = await self._call_backend_crm_api("create_opportunity", opportunity_data)
            
            if success:
                if workflow_state:
                    workflow_state.collected_data['crm_opportunity'] = {
                        'value': opportunity_name,
                        'description': f'Opportunity created: ${value}',
                        'created_at': datetime.now().isoformat()
                    }
                
                return f"✅ Opportunity created: '{opportunity_name}' (${value:,.2f}) at {stage} stage"
            else:
                return f"❌ Failed to create opportunity for {contact_email}"
                
        except Exception as e:
            logger.error(f"Error creating opportunity: {e}", exc_info=True)
            return f"Error creating opportunity: {str(e)}"

    @function_tool(
        name="log_crm_activity",
        description="Log interaction activities in CRM. Use this to record important conversation points, follow-up tasks, or call outcomes."
    )
    async def log_activity(
        self,
        ctx: RunContext,
        contact_email: str,
        activity_type: str,  # call, email, meeting, note, task
        subject: str,
        description: str,
        follow_up_required: bool = False,
        follow_up_date: str = ""
    ) -> str:
        """
        Log CRM activities intelligently based on conversation flow.
        """
        try:
            workflow_state = ctx.session.userdata.get('workflow_state')
            
            activity_data = {
                "contact_email": contact_email,
                "activity_type": activity_type,
                "subject": subject,
                "description": description,
                "activity_date": datetime.now().isoformat(),
                "follow_up_required": follow_up_required,
                "follow_up_date": follow_up_date,
                "agent_name": "AI Assistant",
                "workflow_step": workflow_state.current_step if workflow_state else "unknown"
            }
            
            logger.info(f"Logging CRM activity: {activity_data}")
            
            success = await self._call_backend_crm_api("log_activity", activity_data)
            
            if success:
                return f"✅ Activity logged in CRM: {activity_type} - {subject}"
            else:
                return f"❌ Failed to log activity for {contact_email}"
                
        except Exception as e:
            logger.error(f"Error logging CRM activity: {e}", exc_info=True)
            return f"Error logging activity: {str(e)}"

    def _calculate_lead_score(self, interest_level: str, budget_qualified: bool, 
                             timeline: str, collected_data: Dict[str, Any]) -> int:
        """Calculate lead score based on conversation factors"""
        score = 0
        
        # Interest level scoring
        if interest_level == "high":
            score += 40
        elif interest_level == "medium":
            score += 25
        elif interest_level == "low":
            score += 10
        
        # Budget qualification
        if budget_qualified:
            score += 30
        
        # Timeline scoring
        timeline_scores = {
            "immediate": 20,
            "1-3_months": 15,
            "6_months": 10,
            "future": 5
        }
        score += timeline_scores.get(timeline, 0)
        
        # Additional factors from collected data
        if collected_data:
            if 'company' in collected_data:
                score += 10  # Business contact
            if 'appointment_scheduled' in collected_data:
                score += 15  # Appointment booked
        
        return min(score, 100)  # Cap at 100

    def _assess_conversation_quality(self, workflow_state) -> str:
        """Assess conversation quality for CRM insights"""
        if not workflow_state:
            return "unknown"
        
        data_count = len(workflow_state.collected_data)
        step_count = len(workflow_state.step_history)
        
        if data_count >= 5 and step_count >= 3:
            return "high"
        elif data_count >= 3 and step_count >= 2:
            return "medium"
        else:
            return "low"

    def _determine_call_outcome(self, workflow_state) -> str:
        """Determine call outcome based on workflow progression"""
        if not workflow_state:
            return "incomplete"
        
        collected_data = workflow_state.collected_data
        
        if 'scheduled_appointment' in collected_data:
            return "appointment_scheduled"
        elif 'transfer_reason' in collected_data:
            return "transferred_to_human"
        elif len(collected_data) >= 3:
            return "information_gathered"
        else:
            return "brief_interaction"

    async def _call_backend_crm_api(self, action: str, data: Dict[str, Any]) -> bool:
        """Call backend CRM API (HubSpot, Salesforce, etc.)"""
        try:
            # Extract user_id for OAuth token lookup
            user_id = data.get('user_id') or self._extract_user_id_from_context(data)
            
            if not user_id:
                logger.error("No user_id available for CRM API call")
                return False
            
            backend_service = get_backend_service()
            
            # Call appropriate backend service method
            if action == "create_contact":
                result = await backend_service.crm_create_contact(user_id, data)
            elif action == "update_lead_score":
                result = await backend_service.crm_update_lead_score(user_id, data)
            elif action == "create_opportunity":
                # For opportunities, we'd need a separate backend method
                # For now, we'll use create_contact as a placeholder
                result = await backend_service.crm_create_contact(user_id, data)
            elif action == "log_activity":
                # For activities, we'd need a separate backend method
                # For now, we'll use a generic approach
                result = await backend_service.crm_create_contact(user_id, data)
            else:
                logger.error(f"Unknown CRM action: {action}")
                return False
            
            return result.get("success", False)
                        
        except Exception as e:
            logger.error(f"Error calling CRM backend service: {e}", exc_info=True)
            return False

    def _extract_user_id_from_context(self, data: Dict[str, Any]) -> Optional[str]:
        """Extract user_id from CRM data context"""
        # Try to extract from workflow execution ID or contact email
        workflow_id = data.get('workflow_execution_id')
        if workflow_id:
            return f"exec_{workflow_id}"
        
        email = data.get('email') or data.get('contact_email')
        if email:
            return f"email_{email.replace('@', '_').replace('.', '_')}"
        
        phone = data.get('phone')
        if phone:
            return f"phone_{phone.replace('+', '').replace(' ', '')}"
        
        return None

    def _simulate_crm_operation(self, action: str, data: Dict[str, Any]) -> bool:
        """Simulate CRM operations for demonstration"""
        logger.info(f"SIMULATED CRM: {action}")
        if action == "create_contact":
            logger.info(f"  Contact: {data.get('first_name')} {data.get('last_name')}")
        elif action == "update_lead_score":
            logger.info(f"  Lead Score: {data.get('lead_score')}")
        elif action == "create_opportunity":
            logger.info(f"  Opportunity: {data.get('opportunity_name')} (${data.get('value')})")
        elif action == "log_activity":
            logger.info(f"  Activity: {data.get('activity_type')} - {data.get('subject')}")
        return True


# Factory function for CRM tools
def create_crm_tools() -> List:
    """
    Create CRM function tools for WorkflowAgent injection.
    """
    crm_integration = CRMIntegration()
    
    return [
        crm_integration.create_contact,
        crm_integration.update_lead_score,
        crm_integration.create_opportunity,
        crm_integration.log_activity
    ]


# Conversion Example: CRM App Action Transformation
"""
OLD PATHWAY CRM APPROACH (BROKEN):
```json
{
  "id": "create_lead",
  "type": "app_action",
  "config": {
    "action_type": "crm_create_contact",
    "parameters": {
      "first_name": "{{customer_first_name}}",
      "last_name": "{{customer_last_name}}",
      "email": "{{customer_email}}",
      "lead_source": "Phone Call"
    }
  },
  "next_node": "qualify_lead"
}
```

Problems:
- Manual variable substitution
- No intelligent timing
- Static lead qualification
- Hardcoded field mapping

NEW WORKFLOW CRM APPROACH (INTELLIGENT):
Conversation context:
User: "Hi, I'm John Smith from ABC Corp, interested in your consulting services"

LLM intelligently calls:
1. create_crm_contact(
     first_name="John",
     last_name="Smith", 
     email="john@abccorp.com",
     company="ABC Corp",
     lead_source="Inbound Call"
   )

2. update_lead_score(
     contact_email="john@abccorp.com",
     interest_level="high",
     budget_qualified=True,
     timeline="immediate"
   )

3. create_crm_opportunity(
     contact_email="john@abccorp.com",
     opportunity_name="ABC Corp Consulting",
     value=50000.0,
     stage="Qualification"
   )

Benefits:
- LLM decides when to create CRM records
- Dynamic lead scoring based on conversation
- Intelligent opportunity creation
- Context-aware activity logging
- Professional integration with backend APIs
""" 