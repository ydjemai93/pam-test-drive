# Pathway Routes - Following PATHWAY_BACKEND_IMPLEMENTATION_PLAN.md

from fastapi import APIRouter, HTTPException, Header, status
from typing import Dict, Any, List, Optional
from datetime import datetime
import logging
from pydantic import BaseModel, Field

from .db_client import supabase_service_client
from .config import get_user_id_from_token

router = APIRouter(prefix="/pathways", tags=["Pathways"])
logger = logging.getLogger(__name__)

# ===== REQUEST/RESPONSE MODELS =====

class PathwayCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    config: Dict[str, Any] = Field(default_factory=dict)
    status: str = Field(default="draft")

class PathwayUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    status: Optional[str] = None

class PathwayResponse(BaseModel):
    id: str
    user_id: str
    name: str
    description: Optional[str]
    config: Dict[str, Any]
    status: str
    version: int
    is_default: bool
    created_at: datetime
    updated_at: datetime

# ===== UTILITY FUNCTIONS =====

async def verify_user_access_to_pathway(pathway_id: str, user_id: str) -> Dict[str, Any]:
    """Verify user has access to the pathway"""
    try:
        response = supabase_service_client.table("pathways").select("*").eq("id", pathway_id).eq("user_id", user_id).single().execute()
        
        if not response.data:
            raise HTTPException(status_code=404, detail="Pathway not found or access denied")
        
        return response.data
    except Exception as e:
        logger.error(f"Error verifying pathway access: {e}")
        raise HTTPException(status_code=500, detail="Error verifying pathway access")

# ===== PATHWAY CRUD ENDPOINTS =====

@router.post("/", response_model=PathwayResponse, status_code=status.HTTP_201_CREATED)
async def create_pathway(
    request: PathwayCreateRequest,
    authorization: str = Header(None, alias="Authorization")
):
    """Create a new pathway"""
    try:
        user_id = get_user_id_from_token(authorization)
        
        # Create basic pathway config if empty
        if not request.config:
            request.config = {
                "nodes": [],
                "edges": [],
                "entry_point": None,
                "variables": {}
            }
        
        # Insert into database
        insert_data = {
            "user_id": user_id,
            "name": request.name,
            "description": request.description,
            "config": request.config,
            "status": request.status
        }
        
        response = supabase_service_client.table("pathways").insert(insert_data).execute()
        
        if not response.data:
            raise HTTPException(status_code=500, detail="Failed to create pathway")
        
        pathway_data = response.data[0]
        
        return PathwayResponse(
            id=pathway_data["id"],
            user_id=pathway_data["user_id"],
            name=pathway_data["name"],
            description=pathway_data.get("description"),
            config=pathway_data.get("config", {}),
            status=pathway_data["status"],
            version=pathway_data.get("version", 1),
            is_default=pathway_data.get("is_default", False),
            created_at=pathway_data["created_at"],
            updated_at=pathway_data["updated_at"]
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating pathway: {e}")
        raise HTTPException(status_code=500, detail="Error creating pathway")

@router.get("/", response_model=List[PathwayResponse])
async def list_pathways(
    authorization: str = Header(None, alias="Authorization"),
    status_filter: Optional[str] = None,
    limit: int = 50,
    offset: int = 0
):
    """List pathways for the user"""
    try:
        user_id = get_user_id_from_token(authorization)
        
        query = supabase_service_client.table("pathways").select("*").eq("user_id", user_id)
        
        if status_filter:
            query = query.eq("status", status_filter)
        
        response = query.range(offset, offset + limit - 1).order("created_at", desc=True).execute()
        
        pathways = []
        for pathway_data in response.data:
            pathways.append(PathwayResponse(
                id=pathway_data["id"],
                user_id=pathway_data["user_id"],
                name=pathway_data["name"],
                description=pathway_data.get("description"),
                config=pathway_data.get("config", {}),
                status=pathway_data["status"],
                version=pathway_data.get("version", 1),
                is_default=pathway_data.get("is_default", False),
                created_at=pathway_data["created_at"],
                updated_at=pathway_data["updated_at"]
            ))
        
        return pathways
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing pathways: {e}")
        raise HTTPException(status_code=500, detail="Error listing pathways")

@router.get("/{pathway_id}", response_model=PathwayResponse)
async def get_pathway(
    pathway_id: str,
    authorization: str = Header(None, alias="Authorization")
):
    """Get pathway by ID"""
    try:
        user_id = get_user_id_from_token(authorization)
        
        pathway_data = await verify_user_access_to_pathway(pathway_id, user_id)
        
        return PathwayResponse(
            id=pathway_data["id"],
            user_id=pathway_data["user_id"],
            name=pathway_data["name"],
            description=pathway_data.get("description"),
            config=pathway_data.get("config", {}),
            status=pathway_data["status"],
            version=pathway_data.get("version", 1),
            is_default=pathway_data.get("is_default", False),
            created_at=pathway_data["created_at"],
            updated_at=pathway_data["updated_at"]
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting pathway: {e}")
        raise HTTPException(status_code=500, detail="Error getting pathway")

@router.patch("/{pathway_id}", response_model=PathwayResponse)
async def update_pathway(
    pathway_id: str,
    request: PathwayUpdateRequest,
    authorization: str = Header(None, alias="Authorization")
):
    """Update a pathway"""
    try:
        user_id = get_user_id_from_token(authorization)
        
        # Verify access
        await verify_user_access_to_pathway(pathway_id, user_id)
        
        # Build update data
        update_data = {}
        if request.name:
            update_data["name"] = request.name
        if request.description is not None:
            update_data["description"] = request.description
        if request.config is not None:
            update_data["config"] = request.config
        if request.status:
            update_data["status"] = request.status
        
        if update_data:
            update_data["updated_at"] = datetime.utcnow().isoformat()
            
        response = supabase_service_client.table("pathways").update(update_data).eq("id", pathway_id).execute()
        
        if not response.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pathway not found after update attempt.")

        return response.data[0]
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating pathway: {e}")
        raise HTTPException(status_code=500, detail="Error updating pathway")

@router.delete("/{pathway_id}")
async def delete_pathway(
    pathway_id: str,
    authorization: str = Header(None, alias="Authorization")
):
    """Delete a pathway"""
    user_id = get_user_id_from_token(authorization)
    
    try:
        # Verify user access
        await verify_user_access_to_pathway(pathway_id, user_id)
        
        # Delete the pathway
        response = supabase_service_client.table("pathways").delete().eq("id", pathway_id).eq("user_id", user_id).execute()
        
        if response.data:
            logger.info(f"Pathway deleted: {pathway_id}")
            return {"message": "Pathway deleted successfully"}
        else:
            raise HTTPException(status_code=404, detail="Pathway not found")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting pathway {pathway_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete pathway"
        )

@router.get("/templates", response_model=List[Dict[str, Any]])
async def get_pathway_templates():
    """Get available pathway templates for the pathway builder"""
    try:
        # Return built-in pathway templates
        templates = [
            {
                "id": "simple_conversation",
                "name": "Simple Conversation",
                "description": "Basic conversation flow with greeting and response",
                "category": "basic",
                "config": {
                    "entry_point": "greeting",
                    "nodes": [
                        {
                            "id": "greeting",
                            "type": "conversation",
                            "name": "Greeting",
                            "config": {
                                "prompt": "Hello! How can I help you today?",
                                "variables_to_extract": [
                                    {"name": "customer_name", "description": "Customer's name", "type": "string"},
                                    {"name": "inquiry_type", "description": "Type of inquiry", "type": "string"}
                                ]
                            }
                        },
                        {
                            "id": "response",
                            "type": "conversation", 
                            "name": "Response",
                            "config": {
                                "prompt": "Thank you {customer_name}, I understand you have a {inquiry_type} inquiry. Let me help you with that."
                            }
                        },
                        {
                            "id": "end",
                            "type": "end_call",
                            "name": "End Call",
                            "config": {
                                "final_message": "Thank you for calling! Have a great day!"
                            }
                        }
                    ],
                    "edges": [
                        {"source": "greeting", "target": "response", "condition": "success"},
                        {"source": "response", "target": "end", "condition": "success"}
                    ]
                }
            },
            {
                "id": "appointment_booking",
                "name": "Appointment Booking",
                "description": "Complete appointment booking flow with calendar integration",
                "category": "sales",
                "config": {
                    "entry_point": "greeting",
                    "nodes": [
                        {
                            "id": "greeting",
                            "type": "conversation",
                            "name": "Greeting & Information Gathering",
                            "config": {
                                "prompt": "Hello! I'm calling to help you schedule an appointment. May I have your name and what type of appointment you're looking for?",
                                "variables_to_extract": [
                                    {"name": "customer_name", "description": "Customer's full name", "type": "string"},
                                    {"name": "appointment_type", "description": "Type of appointment needed", "type": "string"},
                                    {"name": "preferred_date", "description": "Preferred appointment date", "type": "string"},
                                    {"name": "preferred_time", "description": "Preferred appointment time", "type": "string"}
                                ]
                            }
                        },
                        {
                            "id": "calendar_check",
                            "type": "app_action",
                            "name": "Check Calendar Availability",
                            "config": {
                                "app_name": "google_calendar",
                                "action_type": "check_availability",
                                "action_config": {
                                    "start_time": "{preferred_date} {preferred_time}",
                                    "duration": 60
                                }
                            }
                        },
                        {
                            "id": "book_appointment",
                            "type": "app_action",
                            "name": "Book Appointment",
                            "config": {
                                "app_name": "google_calendar",
                                "action_type": "create_event",
                                "action_config": {
                                    "title": "{appointment_type} - {customer_name}",
                                    "start_time": "{preferred_date} {preferred_time}",
                                    "attendees": ["{customer_email}"]
                                }
                            }
                        },
                        {
                            "id": "confirmation",
                            "type": "conversation",
                            "name": "Appointment Confirmation",
                            "config": {
                                "prompt": "Perfect! I've booked your {appointment_type} appointment for {preferred_date} at {preferred_time}. You'll receive a calendar invitation shortly. Is there anything else I can help you with?"
                            }
                        },
                        {
                            "id": "end",
                            "type": "end_call",
                            "name": "End Call",
                            "config": {
                                "final_message": "Thank you {customer_name}! We look forward to seeing you for your appointment. Have a great day!"
                            }
                        }
                    ],
                    "edges": [
                        {"source": "greeting", "target": "calendar_check", "condition": "success"},
                        {"source": "calendar_check", "target": "book_appointment", "condition": "success"},
                        {"source": "book_appointment", "target": "confirmation", "condition": "success"},
                        {"source": "confirmation", "target": "end", "condition": "success"}
                    ]
                }
            },
            {
                "id": "lead_qualification",
                "name": "Lead Qualification & CRM",
                "description": "Qualify leads and create records in CRM system",
                "category": "sales",
                "config": {
                    "entry_point": "introduction",
                    "nodes": [
                        {
                            "id": "introduction",
                            "type": "conversation",
                            "name": "Introduction",
                            "config": {
                                "prompt": "Hi! I'm calling from {company_name} regarding your interest in our services. Do you have a few minutes to discuss your needs?",
                                "variables_to_extract": [
                                    {"name": "is_interested", "description": "Whether prospect is interested", "type": "boolean"},
                                    {"name": "timing", "description": "When they're looking to implement", "type": "string"}
                                ]
                            }
                        },
                        {
                            "id": "qualification",
                            "type": "conversation",
                            "name": "Needs Assessment",
                            "config": {
                                "prompt": "Great! Can you tell me about your current challenges and what you're hoping to achieve? Also, what's your budget range for this type of solution?",
                                "variables_to_extract": [
                                    {"name": "company_name", "description": "Prospect's company name", "type": "string"},
                                    {"name": "company_size", "description": "Number of employees", "type": "string"},
                                    {"name": "budget_range", "description": "Budget range", "type": "string"},
                                    {"name": "pain_points", "description": "Main challenges", "type": "string"},
                                    {"name": "decision_maker", "description": "Are they the decision maker", "type": "boolean"}
                                ]
                            }
                        },
                        {
                            "id": "create_contact",
                            "type": "app_action",
                            "name": "Create CRM Contact",
                            "config": {
                                "app_name": "hubspot",
                                "action_type": "create_contact",
                                "action_config": {
                                    "first_name": "{customer_name}",
                                    "company": "{company_name}",
                                    "lifecycle_stage": "lead",
                                    "lead_status": "qualified"
                                }
                            }
                        },
                        {
                            "id": "followup_scheduling",
                            "type": "conversation",
                            "name": "Schedule Follow-up",
                            "config": {
                                "prompt": "Based on what you've told me, I think we can definitely help. I'd like to schedule a demo call where we can show you exactly how our solution addresses your {pain_points}. What's your availability next week?"
                            }
                        },
                        {
                            "id": "end",
                            "type": "end_call",
                            "name": "End Call",
                            "config": {
                                "final_message": "Perfect! I'll send you a calendar invite for our demo. Thank you for your time today!"
                            }
                        }
                    ],
                    "edges": [
                        {"source": "introduction", "target": "qualification", "condition": "success"},
                        {"source": "qualification", "target": "create_contact", "condition": "success"},
                        {"source": "create_contact", "target": "followup_scheduling", "condition": "success"},
                        {"source": "followup_scheduling", "target": "end", "condition": "success"}
                    ]
                }
            }
        ]
        
        logger.info(f"Returned {len(templates)} pathway templates")
        return templates
        
    except Exception as e:
        logger.error(f"Error fetching pathway templates: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch pathway templates"
        )

@router.post("/test/create-lead-qualification-pathway")
async def create_lead_qualification_pathway(authorization: str = Header(None, alias="Authorization")):
    """Create a comprehensive lead qualification pathway for testing all conversation flow aspects"""
    try:
        user_id = get_user_id_from_token(authorization)
        
        # Create comprehensive lead qualification pathway based on VAPI example
        pathway_config = {
            "name": "Lead Qualification Agent - Full Test",
            "description": "Comprehensive lead qualification pathway testing all conversation flow aspects",
            "config": {
                "entry_point": "introduction",
                "nodes": [
                    {
                        "id": "introduction",
                        "type": "conversation",
                        "name": "Introduction & Availability Check",
                        "prompt": "Hello, this is Morgan from GrowthPartners. We help businesses improve their operational efficiency through custom software solutions. Do you have a few minutes to chat about how we might be able to help your business?",
                        "variables_to_extract": [
                            {"name": "contact_name", "description": "Contact's name", "type": "string"},
                            {"name": "company_name", "description": "Company name", "type": "string"}
                        ]
                    },
                    {
                        "id": "need_discovery",
                        "type": "conversation", 
                        "name": "Need Discovery",
                        "prompt": "Conduct need discovery by asking about: 1) Their business and industry, 2) Current systems/processes they use, 3) Biggest challenges with current approach, 4) How challenges affect operations/bottom line, 5) Previous solutions tried. Ask one question at a time, listen actively, and acknowledge their responses. Keep responses under 30 words unless providing valuable information.",
                        "variables_to_extract": [
                            {"name": "industry", "description": "the user's industry or business type", "type": "string"},
                            {"name": "company_size", "description": "approximate number of employees or company size indicators", "type": "string"},
                            {"name": "pain_points", "description": "main business challenges or pain points mentioned", "type": "string"},
                            {"name": "current_systems", "description": "current systems or processes they use", "type": "string"}
                        ]
                    },
                    {
                        "id": "solution_alignment",
                        "type": "conversation",
                        "name": "Solution Alignment",
                        "prompt": "Based on their pain points ({pain_points}) and industry ({industry}), highlight relevant GrowthPartners capabilities. Mention specific solutions: OperationsOS for workflow automation, InsightAnalytics for data analysis, or CustomerConnect for client relationship management. Share a relevant success story from a similar company. Explain key differentiators like customization, implementation support, and integration capabilities. Be brief."
                    },
                    {
                        "id": "qualification_assessment",
                        "type": "conversation",
                        "name": "Qualification Assessment", 
                        "prompt": "Assess qualification by asking about: 1) Timeline for implementing a solution, 2) Budget allocation for this area, 3) Who else would be involved in evaluation, 4) How they would measure success. Listen for indicators that they meet our ideal customer profile: 50+ employees, $5M+ revenue, growth challenges, and willingness to invest in process improvement.",
                        "variables_to_extract": [
                            {"name": "timeline", "description": "their timeline for implementing a solution", "type": "string"},
                            {"name": "budget_status", "description": "information about budget allocation or financial capacity", "type": "string"},
                            {"name": "decision_makers", "description": "who else is involved in the decision process", "type": "string"},
                            {"name": "success_criteria", "description": "how they would measure success of a solution", "type": "string"}
                        ]
                    },
                    {
                        "id": "create_crm_contact",
                        "type": "app_action",
                        "name": "Create CRM Contact",
                        "data": {
                            "app_name": "hubspot",
                            "action_type": "create_contact",
                            "field_mappings": {
                                "firstname": "{contact_name}",
                                "company": "{company_name}",
                                "industry": "{industry}",
                                "lifecyclestage": "lead",
                                "lead_status": "new"
                            }
                        }
                    },
                    {
                        "id": "qualified_handoff",
                        "type": "conversation",
                        "name": "Qualified Lead Handoff",
                        "prompt": "Based on our conversation, I think it would be valuable to have you speak with our solutions specialist, who can provide a more tailored overview of how we could help with your {pain_points}. Would you be available for a 30-minute call this week?",
                        "variables_to_extract": [
                            {"name": "contact_email", "description": "user's email address", "type": "string"},
                            {"name": "preferred_meeting_time", "description": "their preferred time for the sales meeting", "type": "string"}
                        ]
                    },
                    {
                        "id": "schedule_meeting",
                        "type": "app_action",
                        "name": "Schedule Sales Meeting",
                        "data": {
                            "app_name": "google_calendar",
                            "action_type": "create_event",
                            "field_mappings": {
                                "summary": "Sales Meeting - {company_name}",
                                "description": "Follow-up meeting with {contact_name} from {company_name}. Pain points: {pain_points}",
                                "start": "{preferred_meeting_time}",
                                "duration": 30,
                                "attendees": ["{contact_email}"]
                            }
                        }
                    },
                    {
                        "id": "nurture_prospect",
                        "type": "conversation",
                        "name": "Nurture Prospect",
                        "prompt": "It sounds like the timing might not be ideal right now. Would it be helpful if I sent you some information about how we've helped similar businesses in your industry? Then perhaps we could reconnect in a few months?",
                        "variables_to_extract": [
                            {"name": "contact_email", "description": "user's email address for nurturing materials", "type": "string"},
                            {"name": "follow_up_timeframe", "description": "when they'd like to be contacted again", "type": "string"}
                        ]
                    },
                    {
                        "id": "unqualified_closure",
                        "type": "conversation",
                        "name": "Unqualified Lead Closure",
                        "prompt": "Based on what you've shared, it sounds like our solutions might not be the best fit for your current needs. We typically work best with companies that have 50+ employees and are experiencing significant growth challenges. To be respectful of your time, I won't suggest moving forward, but if your situation changes, please reach out."
                    },
                    {
                        "id": "reschedule_call",
                        "type": "conversation",
                        "name": "Reschedule Call",
                        "prompt": "I understand you're pressed for time. Would it be better to schedule a specific time for us to talk? I'd be happy to follow up when timing is better for you.",
                        "variables_to_extract": [
                            {"name": "callback_time", "description": "when they prefer to be called back", "type": "string"},
                            {"name": "contact_preference", "description": "their preferred contact method", "type": "string"}
                        ]
                    },
                    {
                        "id": "human_transfer_request",
                        "type": "conversation",
                        "name": "Human Transfer Request",
                        "prompt": "I understand you'd like to speak with a human. Let me confirm what you'd like to discuss and connect you with the right person."
                    },
                    {
                        "id": "transfer_call",
                        "type": "transfer",
                        "name": "Transfer to Human",
                        "transfer_to": "+15551234567",
                        "transfer_message": "Transferring to sales specialist"
                    },
                    {
                        "id": "send_slack_notification",
                        "type": "app_action",
                        "name": "Notify Sales Team",
                        "data": {
                            "app_name": "slack",
                            "action_type": "send_message",
                            "field_mappings": {
                                "channel": "#sales-leads",
                                "text": "🔥 New qualified lead: {contact_name} from {company_name} in {industry}. Pain points: {pain_points}. Meeting scheduled for {preferred_meeting_time}."
                            }
                        }
                    },
                    {
                        "id": "end_call_qualified",
                        "type": "end_call",
                        "name": "End Call - Qualified",
                        "final_message": "Perfect! I've scheduled your meeting and you'll receive a calendar invitation shortly. Our specialist will be well-prepared to discuss your {pain_points}. Thank you for your time today!"
                    },
                    {
                        "id": "end_call_nurture",
                        "type": "end_call", 
                        "name": "End Call - Nurture",
                        "final_message": "Thank you for your time today. I'll send you some relevant information and we'll reconnect in {follow_up_timeframe}. Have a great day!"
                    },
                    {
                        "id": "end_call_unqualified",
                        "type": "end_call",
                        "name": "End Call - Unqualified", 
                        "final_message": "Thank you for taking the time to chat today. Have a great day!"
                    },
                    {
                        "id": "end_call_reschedule",
                        "type": "end_call",
                        "name": "End Call - Reschedule",
                        "final_message": "Perfect! I'll call you back at {callback_time}. Thank you and have a great day!"
                    }
                ],
                "edges": [
                    {
                        "source": "introduction",
                        "target": "need_discovery",
                        "condition": {
                            "type": "ai",
                            "prompt": "User agreed to chat and shows interest in learning more"
                        }
                    },
                    {
                        "source": "introduction", 
                        "target": "reschedule_call",
                        "condition": {
                            "type": "ai",
                            "prompt": "User said they're too busy right now but seems potentially interested"
                        }
                    },
                    {
                        "source": "introduction",
                        "target": "human_transfer_request", 
                        "condition": {
                            "type": "ai",
                            "prompt": "User wants to speak to a human"
                        }
                    },
                    {
                        "source": "introduction",
                        "target": "end_call_unqualified",
                        "condition": {
                            "type": "ai",
                            "prompt": "User was not interested or wants to end the call"
                        }
                    },
                    {
                        "source": "need_discovery",
                        "target": "solution_alignment",
                        "condition": {
                            "type": "ai",
                            "prompt": "Sufficient information gathered about their business, industry, pain points, and current systems"
                        }
                    },
                    {
                        "source": "solution_alignment",
                        "target": "qualification_assessment", 
                        "condition": {
                            "type": "ai",
                            "prompt": "User showed interest in the solutions presented and wants to learn more"
                        }
                    },
                    {
                        "source": "qualification_assessment",
                        "target": "create_crm_contact",
                        "condition": {
                            "type": "ai",
                            "prompt": "User met qualification criteria: has timeline within 3-6 months, budget capacity, decision authority or influence, and clear need for our solutions"
                        }
                    },
                    {
                        "source": "create_crm_contact",
                        "target": "qualified_handoff",
                        "condition": "success"
                    },
                    {
                        "source": "qualified_handoff",
                        "target": "schedule_meeting",
                        "condition": {
                            "type": "ai", 
                            "prompt": "User agreed to schedule a meeting and provided contact information"
                        }
                    },
                    {
                        "source": "schedule_meeting",
                        "target": "send_slack_notification",
                        "condition": "success"
                    },
                    {
                        "source": "send_slack_notification",
                        "target": "end_call_qualified",
                        "condition": "success"
                    },
                    {
                        "source": "qualification_assessment",
                        "target": "nurture_prospect",
                        "condition": {
                            "type": "ai",
                            "prompt": "User has potential but timing isn't right, budget unclear, or needs more information before moving forward"
                        }
                    },
                    {
                        "source": "nurture_prospect", 
                        "target": "end_call_nurture",
                        "condition": {
                            "type": "ai",
                            "prompt": "Email obtained and follow-up expectations set"
                        }
                    },
                    {
                        "source": "qualification_assessment",
                        "target": "unqualified_closure",
                        "condition": {
                            "type": "ai",
                            "prompt": "User didn't meet ideal customer profile (too small, no budget, no authority, no clear need, or very long timeline)"
                        }
                    },
                    {
                        "source": "unqualified_closure",
                        "target": "end_call_unqualified",
                        "condition": {
                            "type": "ai",
                            "prompt": "User responded or acknowledged"
                        }
                    },
                    {
                        "source": "reschedule_call",
                        "target": "end_call_reschedule",
                        "condition": {
                            "type": "ai",
                            "prompt": "Callback time and contact information obtained, or user decides not to reschedule"
                        }
                    },
                    {
                        "source": "human_transfer_request",
                        "target": "transfer_call",
                        "condition": {
                            "type": "ai",
                            "prompt": "User confirmed they want to speak to a human"
                        }
                    }
                ],
                "variables": {}
            },
            "status": "active"
        }
        
        # Insert the pathway
        insert_data = {
            "user_id": user_id,
            "name": pathway_config["name"],
            "description": pathway_config["description"], 
            "config": pathway_config["config"],
            "status": pathway_config["status"]
        }
        
        response = supabase_service_client.table("pathways").insert(insert_data).execute()
        
        if not response.data:
            raise HTTPException(status_code=500, detail="Failed to create lead qualification pathway")
        
        pathway_data = response.data[0]
        
        logger.info(f"Created comprehensive lead qualification pathway: {pathway_data['id']}")
        
        return {
            "message": "Lead qualification pathway created successfully",
            "pathway_id": pathway_data["id"],
            "name": pathway_data["name"],
            "nodes_count": len(pathway_config["config"]["nodes"]),
            "edges_count": len(pathway_config["config"]["edges"]),
            "features_tested": [
                "AI Conditions (VAPI-style affirmative statements)",
                "Variable Extraction",
                "App Integrations (HubSpot, Google Calendar, Slack)",
                "Call Transfer",
                "Multiple End Points", 
                "Complex Routing Logic",
                "CRM Contact Creation",
                "Meeting Scheduling",
                "Team Notifications",
                "Lead Qualification Logic"
            ]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating lead qualification pathway: {e}")
        raise HTTPException(status_code=500, detail="Error creating lead qualification pathway")

logger.info("Pathway Routes loaded successfully") 