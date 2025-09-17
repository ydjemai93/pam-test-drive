"""
Call Management Routes

Handles all call-related endpoints including initiating calls,
status updates, and call history.
"""
import json
import os
import subprocess
import logging
from typing import Optional, Dict, Any
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, status, Header
from pydantic import BaseModel, Field

from ..config import get_user_id_from_token
from ..db_client import supabase_service_client

# Set up logging
logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/calls", tags=["calls"])

# --- Constants for AI Model Validation ---
SUPPORTED_VAD_PROVIDERS = {"silero"}
SUPPORTED_STT_PROVIDERS = {"deepgram"}
SUPPORTED_TTS_PROVIDERS = {"cartesia"}
SUPPORTED_LLM_PROVIDERS = {"openai"}

# --- Pydantic Models ---

class VADConfig(BaseModel):
    provider: str = "silero"

class STTConfig(BaseModel):
    provider: str = "deepgram"
    language: str = "fr"
    model: str = "nova-2"

class TTSConfig(BaseModel):
    provider: str = "cartesia"
    model: str = "sonic-2"
    voice_id: str = "65b25c5d-ff07-4687-a04c-da2f43ef6fa9"

class LLMConfig(BaseModel):
    provider: str = "openai"
    model: str = "gpt-4o-mini"

class AIModelConfig(BaseModel):
    vad: VADConfig = Field(default_factory=VADConfig)
    stt: STTConfig = Field(default_factory=STTConfig)
    tts: TTSConfig = Field(default_factory=TTSConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)

class CallRequest(BaseModel):
    firstName: str
    lastName: str
    phoneNumber: str
    system_prompt: str
    ai_models: AIModelConfig = Field(default_factory=AIModelConfig)

class AgentCallRequest(BaseModel):
    agent_id: int
    phoneNumber: str
    lastName: str | None = None
    batch_campaign_id: Optional[str] = None
    batch_call_item_id: Optional[str] = None

class CallStatusUpdateRequest(BaseModel):
    new_status: str
    supabase_call_id: str
    call_duration_seconds: Optional[int] = None
    telnyx_call_control_id: Optional[str] = None

# --- Helper Functions ---

def parse_lk_dispatch_output(output: str) -> tuple[str | None, str | None]:
    """
    Parse the output of 'lk dispatch create' command to extract room name and job ID.
    """
    logger.info(f"Parsing lk dispatch output: {output}")
    
    room_name = None
    job_id = None
    
    for line in output.strip().split('\n'):
        if 'room:' in line.lower():
            parts = line.split(':', 1)
            if len(parts) == 2:
                room_name = parts[1].strip()
        
        if 'id:' in line.lower():
            parts = line.split(':', 1)
            if len(parts) == 2:
                job_id = parts[1].strip()
    
    # Often, the room name itself contains the job/dispatch ID for dispatch-created rooms
    if room_name and room_name.startswith("RM_"):  # Default LiveKit room prefix
         pass  # Room name is usually sufficient reference initially

    logger.info(f"Parsed from lk output - Room: {room_name}")  # Removed Job ID for now
    return room_name, job_id  # Job ID might be None

# --- Route Endpoints ---

@router.post("/", summary="Initiate a basic call")
async def initiate_call(request: CallRequest):
    logger.info(f"Received call request for {request.firstName} {request.lastName} at {request.phoneNumber} with custom prompt.")

    # Validation supplémentaire pour s'assurer que le prompt n'est pas vide
    if not request.system_prompt or not request.system_prompt.strip():
        logger.error("Validation Error: system_prompt cannot be empty.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The 'system_prompt' field cannot be empty."
        )

    # --- Validation de la configuration AI --- 
    ai_config = request.ai_models
    if ai_config.vad.provider not in SUPPORTED_VAD_PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported VAD provider: '{ai_config.vad.provider}'. Supported: {list(SUPPORTED_VAD_PROVIDERS)}"
        )
    if ai_config.stt.provider not in SUPPORTED_STT_PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported STT provider: '{ai_config.stt.provider}'. Supported: {list(SUPPORTED_STT_PROVIDERS)}"
        )
    if ai_config.tts.provider not in SUPPORTED_TTS_PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported TTS provider: '{ai_config.tts.provider}'. Supported: {list(SUPPORTED_TTS_PROVIDERS)}"
        )
    if ai_config.llm.provider not in SUPPORTED_LLM_PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported LLM provider: '{ai_config.llm.provider}'. Supported: {list(SUPPORTED_LLM_PROVIDERS)}"
        )

    # --- Environment validation ---
    livekit_url = os.getenv("LIVEKIT_URL")
    livekit_api_key = os.getenv("LIVEKIT_API_KEY")
    livekit_api_secret = os.getenv("LIVEKIT_API_SECRET")

    logger.info(f"Vérification Env Vars: URL={livekit_url}, Key Exists={'Oui' if livekit_api_key else 'Non'}, Secret Exists={'Oui' if livekit_api_secret else 'Non'}")

    if not all([livekit_url, livekit_api_key, livekit_api_secret]):
        logger.error("ERREUR CRITIQUE: Une ou plusieurs variables d'environnement LiveKit (URL, KEY, SECRET) sont manquantes ou vides!")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Configuration serveur LiveKit incomplète."
        )

    # Create call log in Supabase before dispatching
    supabase_call_id = None
    try:
        call_log_payload = {
            "to_phone_number": request.phoneNumber,
            "status": "initiating",
        }
        logger.info(f"Attempting to insert call log into Supabase 'calls' table: {call_log_payload}")
        call_log_response = supabase_service_client.table("calls").insert(call_log_payload).execute()
        if call_log_response.data and len(call_log_response.data) > 0:
            supabase_call_id = call_log_response.data[0].get("id")
            logger.info(f"Successfully logged call initiation to Supabase 'calls' table. Supabase Call ID: {supabase_call_id}")
        else:
            error_detail = "No data returned from Supabase after call log insert."
            if hasattr(call_log_response, 'error') and call_log_response.error:
                error_detail = f"DB Error: {call_log_response.error.message if hasattr(call_log_response.error, 'message') else call_log_response.error}"
            logger.error(f"Failed to log call to Supabase 'calls' table. {error_detail}")
            raise HTTPException(status_code=500, detail=f"Could not create call log in database. {error_detail}")
    except Exception as log_e:
        logger.error(f"Error occurred while trying to log call to Supabase 'calls' table: {log_e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Could not create call log in database: {str(log_e)}")

    if not supabase_call_id:
        raise HTTPException(status_code=500, detail="Failed to obtain Supabase Call ID after logging attempt.")

    metadata = {
        "firstName": request.firstName,
        "lastName": request.lastName,
        "phoneNumber": request.phoneNumber,
        "system_prompt": request.system_prompt,
        "ai_models": request.ai_models.model_dump(),
        "supabase_call_id": str(supabase_call_id)
    }

    metadata_json = json.dumps(metadata)

    # Construct the lk dispatch command
    command = [
        "lk",
        "dispatch",
        "create",
        "--new-room",
        "--agent-name", "outbound-caller",
        "--metadata", metadata_json
    ]

    try:
        logger.info(f"Executing command: {' '.join(command)}")
        process_env = os.environ.copy()
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=True,
            shell=False,
            env=process_env
        )

        logger.info(f"lk dispatch command output: {result.stdout}")
        logger.info(f"lk dispatch command stderr: {result.stderr}")

        if "Dispatch created" not in result.stdout and "id: " not in result.stdout:
             logger.warning("Dispatch command executed but success message/ID not found in output.")

        return {"message": "Call initiated successfully", "dispatch_details": result.stdout}

    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to execute lk dispatch command: {e}")
        logger.error(f"Command output (stdout): {e.stdout}")
        logger.error(f"Command output (stderr): {e.stderr}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initiate call: {e.stderr or e.stdout or 'Unknown error'}",
        )
    except FileNotFoundError:
        logger.error("Error: 'lk' command not found. Make sure LiveKit CLI is installed and in PATH.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="'lk' command not found. Server configuration issue."
        )
    except Exception as e:
        logger.exception("An unexpected error occurred")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred: {str(e)}",
        )

@router.get("/", summary="Get call history")
async def get_calls(authorization: str = Header(None, alias="Authorization")):
    user_id = get_user_id_from_token(authorization)
    
    try:
        response = supabase_service_client.table("calls").select("*").eq("user_id", user_id).order("created_at", desc=True).execute()
        
        if response.data:
            return {"calls": response.data}
        else:
            return {"calls": []}
            
    except Exception as e:
        logger.error(f"Error fetching calls for user {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch calls"
        )

@router.patch("/room/{room_name}/status", summary="Update call status by room")
async def update_call_status_by_room(
    room_name: str,
    status_update: CallStatusUpdateRequest,
    x_agent_token: str | None = Header(None, alias="X-Agent-Token")
):
    # Validate agent token if required
    expected_token = os.getenv("AGENT_INTERNAL_TOKEN")
    if expected_token and x_agent_token != expected_token:
        logger.error(f"Invalid or missing agent token for room {room_name}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid agent authentication token"
        )
    
    supabase_call_id = status_update.supabase_call_id
    new_status = status_update.new_status
    call_duration_seconds = status_update.call_duration_seconds
    telnyx_call_control_id = status_update.telnyx_call_control_id
    
    logger.info(f"Updating call status for room {room_name}, Supabase Call ID: {supabase_call_id}, New Status: {new_status}")
    
    # Prepare update data
    update_data = {
        "status": new_status,
        "room_name": room_name,
        "updated_at": datetime.utcnow().isoformat()
    }
    
    if call_duration_seconds is not None:
        update_data["duration_seconds"] = call_duration_seconds
        
    if telnyx_call_control_id:
        update_data["call_control_id"] = telnyx_call_control_id
    
    if new_status in ["completed", "failed", "cancelled"]:
        update_data["ended_at"] = datetime.utcnow().isoformat()
    
    try:
        response = supabase_service_client.table("calls").update(update_data).eq("id", supabase_call_id).execute()
        
        if response.data:
            logger.info(f"Successfully updated call status for Supabase Call ID: {supabase_call_id}")
            return {"message": "Call status updated successfully", "call": response.data[0]}
        else:
            error_msg = f"No call found with Supabase Call ID: {supabase_call_id}"
            logger.error(error_msg)
            raise HTTPException(status_code=404, detail=error_msg)
            
    except Exception as e:
        logger.error(f"Failed to update call status for Supabase Call ID {supabase_call_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update call status: {str(e)}"
        ) 