"""
Agent Management Routes

Handles all agent-related endpoints including CRUD operations,
agent configuration, and agent calls.
"""
import json
import os
import subprocess
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime

from fastapi import APIRouter, HTTPException, status, Header
from pydantic import BaseModel, Field

from ..config import get_user_id_from_token
from ..db_client import supabase_service_client
from ..agent_launcher import launch_outbound_agent

# Set up logging
logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/agents", tags=["agents"])

# --- Pydantic Models ---

class AgentCallRequest(BaseModel):
    agent_id: int
    phoneNumber: str
    lastName: str | None = None
    batch_campaign_id: Optional[str] = None
    batch_call_item_id: Optional[str] = None

class AgentCreateRequest(BaseModel):
    name: str
    system_prompt: str
    llm_provider: str = "openai"
    llm_model: str = "gpt-4o-mini"
    stt_provider: str = "deepgram"
    stt_model: str = "nova-2"
    tts_provider: str = "cartesia"
    tts_voice: str = "ab7c61f5-3daa-47dd-a23b-4ac0aac5f5c3"
    stt_language: str = "fr"
    tts_model: str = "sonic-2"
    status: str = "active"
    initial_greeting: str = "Bonjour, je suis votre assistant Pam. Comment puis-je vous aider?"
    phone_numbers_id: Optional[int] = None
    sip_trunk_id: Optional[str] = None
    
    # New PAM tier and advanced settings
    pam_tier: str = "core"
    wait_for_greeting: bool = False
    llm_temperature: float = 0.5
    interruption_threshold: int = 100
    vad_provider: str = "silero"
    
    # Call Handling & Behavior settings
    transfer_to: Optional[str] = None
    voicemail_detection: bool = False
    voicemail_hangup_immediately: bool = False
    voicemail_message: Optional[str] = None
    
    # Pathway Integration
    default_pathway_id: Optional[str] = None

class AgentUpdateRequest(BaseModel):
    name: Optional[str] = None
    system_prompt: Optional[str] = None
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None
    stt_provider: Optional[str] = None
    stt_model: Optional[str] = None
    tts_provider: Optional[str] = None
    tts_voice: Optional[str] = None
    stt_language: Optional[str] = None
    tts_model: Optional[str] = None
    status: Optional[str] = None
    initial_greeting: Optional[str] = None
    phone_numbers_id: Optional[int] = None
    sip_trunk_id: Optional[str] = None
    # Call Handling & Behavior settings
    transfer_to: Optional[str] = None
    voicemail_detection: Optional[bool] = None
    voicemail_hangup_immediately: Optional[bool] = None
    voicemail_message: Optional[str] = None
    
    # Pathway Integration  
    default_pathway_id: Optional[str] = None

# --- Route Endpoints ---

@router.post("/call", summary="Initiate agent-based call")
async def initiate_agent_call(
    request: AgentCallRequest, 
    authorization: str | None = Header(None, alias="Authorization")
):
    agent_id = request.agent_id
    logger.info(f"Received call request for agent_id {agent_id} to number {request.phoneNumber}")

    # Extract JWT token from Authorization header
    jwt_token = None
    if authorization and authorization.startswith("Bearer "):
        jwt_token = authorization.replace("Bearer ", "")
        logger.info(f"✅ JWT token extracted successfully (length: {len(jwt_token)})")
    else:
        logger.warning(f"❌ No valid JWT token found in Authorization header")

    # Fetch agent configuration from Supabase
    agent_config = None
    logger.info(f"Attempting to fetch config for agent_id {agent_id} from Supabase.")

    try:
        select_query = "*" 
        agent_response = supabase_service_client.table("agents").select(select_query).eq("id", agent_id).single().execute()
        
        if agent_response.data:
            agent_config = agent_response.data
            logger.info(f"Configuration de l'agent {agent_id} récupérée depuis Supabase: {agent_config}")
        else:
            logger.error(f"Agent avec l'ID {agent_id} non trouvé dans Supabase.")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Agent with ID {agent_id} not found."
            )
            
    except Exception as e:
        logger.error(f"Erreur lors de la récupération de la configuration de l'agent depuis Supabase: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch agent configuration: {str(e)}"
        )

    # Validate phone number format
    phone_number = request.phoneNumber
    if not phone_number.startswith('+'):
        logger.warning(f"Phone number {phone_number} doesn't start with '+'. Adding +1 prefix.")
        phone_number = '+1' + phone_number

    # --- Get phone number details from the database for Caller ID ---
    phone_number_details = {}
    agent_caller_id_number = None  # Initialize here
    phone_numbers_id = agent_config.get("phone_numbers_id")
    
    if phone_numbers_id:
        try:
            # Fetch both the phone number and the SIP trunk ID
            pn_response = supabase_service_client.table("phone_numbers").select(
                "phone_number_e164, livekit_sip_trunk_id"
            ).eq("id", phone_numbers_id).single().execute()
            
            if pn_response.data:
                phone_number_details = pn_response.data
                # Correctly get the phone number to use as caller ID
                agent_caller_id_number = phone_number_details.get("phone_number_e164")
                logger.info(f"Retrieved phone number details for agent {agent_id}: {phone_number_details}")
                logger.info(f"Agent Caller ID Number: {agent_caller_id_number}")
        except Exception as e:
            logger.error(f"Failed to retrieve phone number details for agent {agent_id}: {e}")
    else:
        logger.info(f"Agent {agent_id} does not have a phone_numbers_id assigned. No Caller ID will be used.")

    # Create call record
    call_data = {
        "agent_id": agent_id,
        "to_phone_number": phone_number,
        "phone_number_e164": phone_number,
        "status": "initiating",
        "call_direction": "outbound",
        "user_id": agent_config.get("user_id"),
    }

    # Add batch campaign context if provided
    if request.batch_campaign_id:
        call_data["batch_campaign_id"] = request.batch_campaign_id
    if request.batch_call_item_id:
        call_data["batch_call_item_id"] = request.batch_call_item_id

    try:
        call_response = supabase_service_client.table("calls").insert(call_data).execute()
        
        if not call_response.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create call record"
            )
        
        call_record = call_response.data[0]
        call_id = call_record["id"]
        
        logger.info(f"Call record created with ID: {call_id}")

        # Generate room name and update the call record
        room_name = f"agent-call-{call_id}"
        update_response = supabase_service_client.table("calls").update({
            "room_name": room_name
        }).eq("id", call_id).execute()
        
        if update_response.data:
            call_record = update_response.data[0]  # Get updated record
            logger.info(f"Updated call record with room_name: {room_name}")
        else:
            logger.error(f"Failed to update call record with room_name")

        # Launch agent for the call
        success = await launch_outbound_agent(call_record, agent_id)
        
        if not success:
            # Update call status to failed
            supabase_service_client.table("calls").update({
                "status": "failed",
                "error_message": "Failed to launch agent"
            }).eq("id", call_id).execute()
            
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to launch agent for call"
            )

        # Give agent worker time to register with LiveKit
        import asyncio
        await asyncio.sleep(2)
        logger.info(f"Agent worker launched, waiting 2s for registration before dispatch")

        # CRITICAL FIX: Create LiveKit dispatch to assign agent to room
        # This is the missing piece that was causing calls to never initiate
        try:
            # Check if agent has pathway configured - if so, allow empty prompts/greetings
            has_pathway = agent_config.get("default_pathway_id") is not None
            
            # For pathway agents, only use fallbacks if explicitly provided
            if has_pathway:
                system_prompt = agent_config.get("system_prompt") if agent_config.get("system_prompt") else None
                initial_greeting = agent_config.get("initial_greeting") if agent_config.get("initial_greeting") else None
            else:
                # For non-pathway agents, use fallbacks as before
                system_prompt = agent_config.get("system_prompt", "You are a helpful assistant.")
                initial_greeting = agent_config.get("initial_greeting", "Hello, how can I help you?")
            
            # Prepare metadata for the dispatch
            metadata = {
                "firstName": "Valued Customer",
                "lastName": "",
                "dial_info": {
                    "agent_id": agent_id,
                    "call_direction": "outbound",
                    "room_name": room_name,
                    "supabase_call_id": call_id,
                    "telnyx_call_control_id": None,
                    "default_pathway_id": agent_config.get("default_pathway_id"),
                    "user_id": agent_config.get("user_id"),
                    "auth_token": jwt_token,  # ✅ ADD JWT TOKEN FOR BACKEND API CALLS
                    "phone_number": phone_number,
                    "sip_trunk_id": phone_number_details.get("livekit_sip_trunk_id") or agent_config.get("sip_trunk_id") or os.getenv("LIVEKIT_OUTBOUND_TRUNK_ID"),
                    "agent_caller_id_number": agent_caller_id_number # Add Caller ID number
                },
                "system_prompt": system_prompt,
                "initial_greeting": initial_greeting,
                "wait_for_greeting": agent_config.get("wait_for_greeting", False),
                "pam_tier": agent_config.get("pam_tier", "core"),
                "interruption_threshold": agent_config.get("interruption_threshold", 100),
                "ai_models": {
                    "vad": {"provider": "silero"},
                    "stt": {
                        "provider": agent_config.get("stt_provider", "deepgram"),
                        "language": agent_config.get("stt_language", "fr"),
                        "model": agent_config.get("stt_model", "nova-2")
                    },
                    "tts": {
                        "provider": agent_config.get("tts_provider", "cartesia"),
                        "model": agent_config.get("tts_model", "sonic-2"),
                        "voice_id": agent_config.get("tts_voice", "ab7c61f5-3daa-47dd-a23b-4ac0aac5f5c3")
                    },
                    "llm": {
                        "provider": agent_config.get("llm_provider", "openai"),
                        "model": agent_config.get("llm_model", "gpt-4o-mini")
                    }
                }
            }
            
            metadata_json = json.dumps(metadata)
            
            # First create the room with our specific name
            create_room_command = [
                "lk", "room", "create",
                "--name", room_name
            ]
            
            logger.info(f"Creating LiveKit room: {' '.join(create_room_command)}")
            
            try:
                room_result = subprocess.run(
                    create_room_command,
                    capture_output=True,
                    text=True,
                    check=True,
                    env=os.environ.copy()
                )
                logger.info(f"Room created successfully: {room_result.stdout}")
            except subprocess.CalledProcessError as e:
                logger.warning(f"Room creation failed (might already exist): {e.stderr}")
            
            # Then dispatch agent to the existing room
            command = [
                "lk", "dispatch", "create",
                "--room", room_name,
                "--agent-name", "outbound-caller", 
                "--metadata", metadata_json
            ]
            
            logger.info(f"Executing LiveKit dispatch command: {' '.join(command)}")
            
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=True,
                env=os.environ.copy()
            )
            
            logger.info(f"LiveKit dispatch successful: {result.stdout}")
            
            # Update call status to reflect dispatch
            supabase_service_client.table("calls").update({
                "status": "dispatched"
            }).eq("id", call_id).execute()
            
        except subprocess.CalledProcessError as e:
            logger.error(f"LiveKit dispatch failed: {e.stderr}")
            # Update call status to failed
            supabase_service_client.table("calls").update({
                "status": "failed",
                "error_message": f"LiveKit dispatch failed: {e.stderr}"
            }).eq("id", call_id).execute()
            
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to dispatch agent: {e.stderr}"
            )
        except Exception as e:
            logger.error(f"Unexpected error during dispatch: {e}")
            # Update call status to failed
            supabase_service_client.table("calls").update({
                "status": "failed", 
                "error_message": f"Dispatch error: {str(e)}"
            }).eq("id", call_id).execute()
            
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Unexpected dispatch error: {str(e)}"
            )

        return {
            "message": "Agent call initiated and dispatched successfully",
            "call_id": call_id,
            "agent_id": agent_id,
            "phone_number": phone_number,
            "room_name": room_name
        }

    except Exception as e:
        logger.error(f"Error initiating agent call: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initiate agent call: {str(e)}"
        )

@router.post("/", status_code=status.HTTP_201_CREATED, summary="Create new agent")
async def create_agent(
    request: AgentCreateRequest, 
    authorization: str = Header(None, alias="Authorization")
):
    user_id = get_user_id_from_token(authorization)
    
    agent_data = {
        "user_id": user_id,
        "name": request.name,
        "system_prompt": request.system_prompt,
        "llm_provider": request.llm_provider,
        "llm_model": request.llm_model,
        "stt_provider": request.stt_provider,
        "stt_model": request.stt_model,
        "tts_provider": request.tts_provider,
        "tts_voice": request.tts_voice,
        "stt_language": request.stt_language,
        "tts_model": request.tts_model,
        "status": request.status,
        "initial_greeting": request.initial_greeting,
        "phone_numbers_id": request.phone_numbers_id,
        "sip_trunk_id": request.sip_trunk_id,
        "pam_tier": request.pam_tier,
        "wait_for_greeting": request.wait_for_greeting,
        "llm_temperature": request.llm_temperature,
        "interruption_threshold": request.interruption_threshold,
        "vad_provider": request.vad_provider,
        "transfer_to": request.transfer_to,
        "voicemail_detection": request.voicemail_detection,
        "voicemail_hangup_immediately": request.voicemail_hangup_immediately,
        "voicemail_message": request.voicemail_message,
        "default_pathway_id": request.default_pathway_id
    }
    
    try:
        response = supabase_service_client.table("agents").insert(agent_data).execute()
        
        if response.data:
            logger.info(f"Agent created successfully with ID: {response.data[0]['id']}")
            return response.data[0]
        else:
            logger.error("Failed to create agent - no data returned")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create agent"
            )
            
    except Exception as e:
        logger.error(f"Error creating agent: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create agent: {str(e)}"
        )

@router.get("/", summary="Get user's agents")
async def get_agents(authorization: str = Header(None, alias="Authorization")):
    user_id = get_user_id_from_token(authorization)
    
    try:
        response = supabase_service_client.table("agents").select("*").eq("user_id", user_id).execute()
        
        if response.data:
            return {"agents": response.data}
        else:
            return {"agents": []}
            
    except Exception as e:
        logger.error(f"Error fetching agents for user {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch agents"
        )

@router.get("/{agent_id}", summary="Get specific agent")
async def get_agent(agent_id: int, authorization: str = Header(None, alias="Authorization")):
    user_id = get_user_id_from_token(authorization)
    
    try:
        response = supabase_service_client.table("agents").select("*").eq("id", agent_id).eq("user_id", user_id).single().execute()
        
        if response.data:
            return response.data
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Agent with ID {agent_id} not found"
            )
            
    except Exception as e:
        logger.error(f"Error fetching agent {agent_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch agent"
        )

@router.patch("/{agent_id}", summary="Update agent")
async def update_agent(
    agent_id: int, 
    request: AgentUpdateRequest, 
    authorization: str = Header(None, alias="Authorization")
):
    user_id = get_user_id_from_token(authorization)
    
    # Verify agent belongs to user
    try:
        existing_response = supabase_service_client.table("agents").select("id").eq("id", agent_id).eq("user_id", user_id).single().execute()
        if not existing_response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Agent with ID {agent_id} not found"
            )
    except Exception as e:
        logger.error(f"Error verifying agent ownership: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to verify agent"
        )
    
    # Prepare update data (only include non-None values)
    update_data = {}
    for field, value in request.model_dump().items():
        if value is not None:
            update_data[field] = value
    
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields provided for update"
        )
    
    update_data["updated_at"] = datetime.utcnow().isoformat()
    
    try:
        response = supabase_service_client.table("agents").update(update_data).eq("id", agent_id).execute()
        
        if response.data:
            logger.info(f"Agent {agent_id} updated successfully")
            return response.data[0]
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update agent"
            )
            
    except Exception as e:
        logger.error(f"Error updating agent {agent_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update agent: {str(e)}"
        )

@router.delete("/{agent_id}", summary="Delete agent")
async def delete_agent(agent_id: int, authorization: str = Header(None, alias="Authorization")):
    user_id = get_user_id_from_token(authorization)
    
    try:
        # Verify agent belongs to user and delete
        response = supabase_service_client.table("agents").delete().eq("id", agent_id).eq("user_id", user_id).execute()
        
        if response.data:
            logger.info(f"Agent {agent_id} deleted successfully")
            return {"message": f"Agent {agent_id} deleted successfully"}
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Agent with ID {agent_id} not found"
            )
            
    except Exception as e:
        logger.error(f"Error deleting agent {agent_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete agent"
        ) 