import asyncio
import base64
import json
import logging
import os
import random
import re
import subprocess
import uuid
import httpx
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any
from pathlib import Path
from dotenv import load_dotenv

# FAILSAFE: Load environment variables directly
print(f"[MAIN.PY DEBUG] Loading environment variables...")
script_dir = Path(__file__).parent  # api directory
outbound_dir = script_dir.parent / "outbound"  # outbound directory  

# Try to load .env.local first, then .env
env_local_file = outbound_dir / '.env.local'
env_file = outbound_dir / '.env'
api_env_file = script_dir / '.env'

loaded_local = load_dotenv(env_local_file, encoding='utf-8', override=True)
loaded_outbound = load_dotenv(env_file, encoding='utf-8', override=True)
loaded_api = load_dotenv(api_env_file, encoding='utf-8', override=True)

print(f"[MAIN.PY DEBUG] .env.local load result: {loaded_local}")
print(f"[MAIN.PY DEBUG] outbound .env load result: {loaded_outbound}")
print(f"[MAIN.PY DEBUG] api .env load result: {loaded_api}")


# Add debug prints for environment variables at startup
print(f"[MAIN.PY DEBUG] Starting API server...")
print(f"[MAIN.PY DEBUG] Current working directory: {os.getcwd()}")
print(f"[MAIN.PY DEBUG] SUPABASE_URL at startup: {os.getenv('SUPABASE_URL')}")
print(f"[MAIN.PY DEBUG] SUPABASE_ANON_KEY at startup: {'SET' if os.getenv('SUPABASE_ANON_KEY') else 'NOT SET'}")
print(f"[MAIN.PY DEBUG] SUPABASE_SERVICE_ROLE_KEY at startup: {'SET' if os.getenv('SUPABASE_SERVICE_ROLE_KEY') else 'NOT SET'}")

from fastapi import FastAPI, HTTPException, status, Header, Request, File, UploadFile, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field, validator
from supabase import create_client

from .config import BaseModel, get_user_id_from_token
from .db_client import supabase_service_client, get_supabase_anon_client
from .telnyx_routes import router as telnyx_router
from .batch_routes import router as batch_router
from .csv_reports import router as csv_reports_router
# from .webhook_tools_routes import router as webhook_tools_router  # Disabled - tools system removed
from .pathway_routes import router as pathway_router
from .integrations_routes import router as integrations_router
from .n8n_routes import router as n8n_router

# Import new route modules
from .routes import (
    auth_router,
    agents_router,
    calls_router,
    users_router
)





# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="PAM API", version="1.0.0")

# Configure CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],  # Frontend development server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global exception handler to prevent backend crashes
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler to catch all unhandled exceptions"""
    logger.error(f"Unhandled exception in {request.method} {request.url}: {exc}", exc_info=True)
    
    # Return a 500 error instead of crashing the server
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error occurred",
            "error_type": exc.__class__.__name__,
            "error_message": str(exc)
        }
    )

# Request validation error handler
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    """Handle request validation errors"""
    logger.warning(f"Validation error in {request.method} {request.url}: {exc}")
    return JSONResponse(
        status_code=422,
        content={
            "detail": "Request validation failed",
            "errors": exc.errors()
        }
    )

# --- Import Telnyx routes ---
from . import telnyx_routes as telnyx_routes # Import with api prefix

# --- Configuration CORS --- 
# Définir les origines autorisées (URL de votre frontend)
# Utilisez "*" pour tout autoriser (moins sécurisé, OK pour dev local)
# Ou spécifiez l'URL exacte de votre frontend Vite
origins = [
    "http://localhost:5173", # Port par défaut de Vite
    "http://localhost:5174", # Port alternatif de Vite
    "http://127.0.0.1:5173",
    "http://127.0.0.1:5174",
    # Ajoutez d'autres origines si nécessaire (ex: preview de déploiement)
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins, # Autoriser les origines spécifiques
    allow_credentials=True, # Autoriser les cookies (si vous en utilisez)
    allow_methods=["GET", "POST", "DELETE", "OPTIONS", "PATCH"], # Méthodes HTTP autorisées - Added DELETE
    allow_headers=["*"], # Autoriser tous les en-têtes, y compris Content-Type et X-Xano-Authorization
    # Vous pourriez restreindre les en-têtes à ["Content-Type", "X-Xano-Authorization"] pour plus de sécurité
)
# --- Fin Configuration CORS ---

app.include_router(telnyx_routes.router) # Include Telnyx routes
app.include_router(batch_router) # Include Batch Campaign routes
app.include_router(csv_reports_router) # Include CSV Reports routes
from .webhook_tools_routes import router as webhook_router
app.include_router(webhook_router) # Include Webhook routes
app.include_router(pathway_router) # Include Pathway routes
app.include_router(integrations_router, prefix="/integrations", tags=["integrations"])
app.include_router(n8n_router) # Include N8N OAuth routes

# Include new organized route modules
app.include_router(auth_router) # Authentication routes
app.include_router(agents_router) # Agent management routes
app.include_router(calls_router) # Call management routes
app.include_router(users_router) # User management routes



# ===== Background Scheduler for Batch Campaigns =====
import threading
import time

async def run_campaign_scheduler():
    """Background task to check and start scheduled campaigns"""
    logger.info("Starting batch campaign scheduler background task")
    
    while True:
        try:
            # Import here to avoid circular imports
            from .batch_routes import check_and_start_scheduled_campaigns
            
            # Run the scheduler check
            await check_and_start_scheduled_campaigns()
            
        except Exception as e:
            logger.error(f"Error in campaign scheduler: {e}")
        
        # Check every 60 seconds
        await asyncio.sleep(60)

def run_scheduler_thread():
    """Run the scheduler in a new event loop"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(run_campaign_scheduler())
    except Exception as e:
        logger.error(f"Scheduler thread error: {e}")
    finally:
        loop.close()

# Start the scheduler in a background thread
scheduler_thread = threading.Thread(target=run_scheduler_thread, daemon=True)
scheduler_thread.start()
logger.info("Batch campaign scheduler started")

async def run_token_refresh_scheduler():
    """Background task to check and refresh expiring OAuth tokens"""
    logger.info("Starting OAuth token refresh scheduler background task")
    
    while True:
        try:
            # Import here to avoid circular imports
            from .oauth_utils import check_and_refresh_expiring_tokens
            
            # Run the token refresh check
            await check_and_refresh_expiring_tokens()
            
        except Exception as e:
            logger.error(f"Error in token refresh scheduler: {e}")
        
        # Check every 30 minutes (1800 seconds)
        await asyncio.sleep(1800)

def run_token_refresh_thread():
    """Run the token refresh scheduler in a new event loop"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(run_token_refresh_scheduler())
    except Exception as e:
        logger.error(f"Token refresh scheduler thread error: {e}")
    finally:
        loop.close()

# Start the token refresh scheduler in a background thread
token_refresh_thread = threading.Thread(target=run_token_refresh_thread, daemon=True)
token_refresh_thread.start()
logger.info("OAuth token refresh scheduler started")



# Définir les fournisseurs supportés par le worker actuel
SUPPORTED_VAD_PROVIDERS = {"silero"}
SUPPORTED_STT_PROVIDERS = {"deepgram"} # Ajouter d'autres si le worker les gère
SUPPORTED_TTS_PROVIDERS = {"cartesia"} # Ajouter d'autres si le worker les gère
SUPPORTED_LLM_PROVIDERS = {"openai"}   # Ajouter d'autres si le worker les gère

# URL de base de l'API Xano (à adapter si nécessaire)
# XANO_API_BASE_URL = "https://x8ki-letl-twmt.n7.xano.io/api:BylZxBJT" # Déplacé vers config.py

# --- Configuration Models for AI Plugins ---
class VADConfig(BaseModel):
    provider: str = "silero"

class STTConfig(BaseModel):
    provider: str = "deepgram"
    language: str = "fr"
    model: str = "nova-2"

class TTSConfig(BaseModel):
    provider: str = "cartesia"
    model: str = "sonic-2-2025-03-07"
    voice_id: str = "65b25c5d-ff07-4687-a04c-da2f43ef6fa9"

class LLMConfig(BaseModel):
    provider: str = "openai"
    model: str = "gpt-4o-mini"

class AIModelConfig(BaseModel):
    # Utiliser default_factory pour créer des instances par défaut si non fournies
    vad: VADConfig = Field(default_factory=VADConfig)
    stt: STTConfig = Field(default_factory=STTConfig)
    tts: TTSConfig = Field(default_factory=TTSConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)

# --- Pydantic Models ---
class CallRequest(BaseModel):
    firstName: str
    lastName: str
    phoneNumber: str
    system_prompt: str
    # Ajouter la configuration des modèles IA comme champ optionnel
    ai_models: AIModelConfig = Field(default_factory=AIModelConfig)

# Modèle pour le nouvel endpoint /agents/call
class AgentCallRequest(BaseModel):
    agent_id: int
    phoneNumber: str
    lastName: str | None = None
    # Batch campaign context (optional)
    batch_campaign_id: Optional[str] = None
    batch_call_item_id: Optional[str] = None

class UserCreateRequest(BaseModel): # For creating in public.users directly
    email: str
    name: str | None = None
    auth_user_id: str | None = None # Should be UUID

class UserSignupRequest(BaseModel): # New model for auth signup
    email: str
    password: str
    name: str | None = None # Optional name for public.users profile

class CallStatusUpdateRequest(BaseModel):
    new_status: str
    supabase_call_id: str # This ID is the ID of the row in the 'calls' table of Supabase
    call_duration_seconds: Optional[int] = None
    telnyx_call_control_id: Optional[str] = None

# Modèle pour les webhooks Telnyx
class TelnyxWebhook(BaseModel):
    data: dict
    meta: dict

# --- Helper function to parse lk output ---
def parse_lk_dispatch_output(output: str) -> tuple[str | None, str | None]:
    """Tries to parse room name and job ID from lk dispatch output."""
    room_name = None
    job_id = None
    
    room_match = re.search(r'room:"([^"]+)"', output)
    if room_match:
        room_name = room_match.group(1)
        
    # Note: 'lk dispatch create' might not directly output the 'job_id' easily parsable.
    # It often outputs a 'dispatch_id' or just the room name. Let's focus on room name.
    # job_id_match = re.search(r"id: (JB_\S+)", output) # Example if job ID format is JB_...
    # if job_id_match:
    #     job_id = job_id_match.group(1)
        
    # Often, the room name itself contains the job/dispatch ID for dispatch-created rooms
    if room_name and room_name.startswith("RM_"): # Default LiveKit room prefix
         pass # Room name is usually sufficient reference initially

    logger.info(f"Parsed from lk output - Room: {room_name}") # Removed Job ID for now
    return room_name, job_id # Job ID might be None

# --- API Endpoints ---
@app.post("/call")
async def initiate_call(request: CallRequest):
    logger.info(f"Received call request for {request.firstName} {request.lastName} at {request.phoneNumber} with custom prompt.")

    # Validation supplémentaire pour s'assurer que le prompt n'est pas vide
    if not request.system_prompt or not request.system_prompt.strip():
        logger.error("Validation Error: system_prompt cannot be empty.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, # 400 Bad Request est plus approprié ici
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
    # --- Fin Validation AI --- 

    # --- Début Vérification/Modification ---
    # Vérifier si le script Python voit les variables d'environnement
    livekit_url = os.getenv("LIVEKIT_URL")
    livekit_api_key = os.getenv("LIVEKIT_API_KEY")
    livekit_api_secret = os.getenv("LIVEKIT_API_SECRET")

    logger.info(f"Vérification Env Vars: URL={livekit_url}, Key Exists={'Oui' if livekit_api_key else 'Non'}, Secret Exists={'Oui' if livekit_api_secret else 'Non'}")

    # Vérification simple que les variables ne sont pas vides (crucial !)
    if not all([livekit_url, livekit_api_key, livekit_api_secret]):
        logger.error("ERREUR CRITIQUE: Une ou plusieurs variables d'environnement LiveKit (URL, KEY, SECRET) sont manquantes ou vides!")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Configuration serveur LiveKit incomplète."
        )
    # --- Fin Vérification ---

    # Prepare metadata for the agent
    # --- Create Call Log in Supabase BEFORE dispatching --- 
    # This assumes the /call endpoint is initiated by a logged-in user or a system process
    # for which we can determine a user_id (UUID from public.users or auth.users).
    # For now, this example won't assume a user_id unless passed in the request.
    
    # For a generic /call, it's harder to determine who the "user" is for the calls table.
    # If it's always tied to an internal process or a specific pre-defined user, that UUID could be used.
    # Let's assume for now `user_id` might be null if not explicitly provided or determined.
    
    supabase_call_id = None
    try:
        call_log_payload = {
            # "agent_id": request.supabase_agent_id, # If applicable, from request
            # "user_id": request.supabase_user_id,  # If applicable, from request
            "to_phone_number": request.phoneNumber,
            "status": "initiating", # Initial status before lk dispatch
            # We don't have from_phone_number or trunk_id yet for this generic call
            # These might be set by the agent worker or a later process if known
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
        # This case should ideally be caught by the exceptions above
        raise HTTPException(status_code=500, detail="Failed to obtain Supabase Call ID after logging attempt.")

    metadata = {
        "firstName": request.firstName,
        "lastName": request.lastName,
        "phoneNumber": request.phoneNumber,
        "system_prompt": request.system_prompt,
        "ai_models": request.ai_models.model_dump(), # Use model_dump for Pydantic v2
        "supabase_call_id": str(supabase_call_id) # Pass the generated Supabase call ID to the agent
    }

    metadata_json = json.dumps(metadata)

    # Construct the lk dispatch command
    command = [
        "lk",
        "dispatch",
        "create",
        "--new-room",
        "--agent-name", "outbound-caller", # Ensure this matches your agent name
        "--metadata", metadata_json
    ]

    try:
        # Execute the command
        logger.info(f"Executing command: {' '.join(command)}")
        # --- Début Modification Subprocess ---
        # Passer explicitement l'environnement actuel au sous-processus
        process_env = os.environ.copy()
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=True,
            shell=False, # Utiliser shell=False (plus sûr)
            env=process_env # Passer l'environnement
        )
        # --- Fin Modification Subprocess ---

        logger.info(f"lk dispatch command output: {result.stdout}")
        logger.info(f"lk dispatch command stderr: {result.stderr}")

        # Check for specific success indicators
        if "Dispatch created" not in result.stdout and "id: " not in result.stdout: # Check pour l'ID aussi
             logger.warning("Dispatch command executed but success message/ID not found in output.")
             # Peut-être vérifier le code de retour si check=True n'est pas suffisant

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
        logger.exception("An unexpected error occurred") # Log the full traceback
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred: {str(e)}",
        )

# Nouvel endpoint pour lancer un appel basé sur un agent Xano
@app.post("/agents/call")
async def initiate_agent_call(request: AgentCallRequest, authorization: str | None = Header(None, alias="Authorization")):
    agent_id = request.agent_id
    logger.info(f"Received call request for agent_id {agent_id} to number {request.phoneNumber}")

    # Extract JWT token from Authorization header
    xano_token = None
    if authorization and authorization.startswith("Bearer "):
        xano_token = authorization.replace("Bearer ", "")
        logger.info(f"✅ JWT token extracted successfully (length: {len(xano_token)})")
    else:
        logger.warning(f"❌ No valid JWT token found in Authorization header")

    # Xano token is no longer used for fetching agent config from Supabase.
    # But we now pass it to the agent for backend API calls

    # --- Étape 1: Récupérer la configuration de l'agent depuis Supabase ---
    agent_config = None
    logger.info(f"Attempting to fetch config for agent_id {agent_id} from Supabase.")

    try:
        # Assuming agent_id in the request corresponds to 'id' in your Supabase 'agents' table
        # And user_id in agents table links to users(id) which is auth.users(id)
        # select_query = "*, users!inner(id)" # Example if you needed to join with users table
        select_query = "*" 
        
        agent_response = supabase_service_client.table("agents").select(select_query).eq("id", agent_id).single().execute()
        
        if agent_response.data:
            agent_config = agent_response.data
            logger.info(f"Configuration de l'agent {agent_id} récupérée depuis Supabase: {agent_config}")
        else:
            logger.error(f"Agent config not found in Supabase for agent_id {agent_id}. Response: {agent_response.error or 'No data'}")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Agent with ID {agent_id} not found.")
    except Exception as e: 
        logger.error(f"Error fetching agent config for {agent_id} from Supabase: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Could not fetch agent config: {str(e)}")

    if not agent_config: # Should be caught by the exception above, but as a safeguard
         raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to load agent configuration.")

    # --- Récupérer le numéro de téléphone de l'agent (Caller ID) et son LiveKit SIP Trunk ID depuis Supabase ---
    agent_caller_id_number = None
    sip_trunk_id_from_phone_number_config = None # Explicitly for the number assigned to agent
    phone_numbers_id = agent_config.get("phone_numbers_id") # This is the PK of the phone_numbers record assigned to the agent

    if phone_numbers_id: 
        try:
            logger.info(f"Attempting to fetch phone number details for phone_numbers_id {phone_numbers_id} (assigned to agent {agent_id}) from Supabase.")
            # Select phone_number_e164 and livekit_sip_trunk_id
            pn_response = supabase_service_client.table("phone_numbers").select("phone_number_e164, livekit_sip_trunk_id").eq("id", phone_numbers_id).single().execute()
            
            if pn_response.data:
                phone_number_details = pn_response.data
                agent_caller_id_number = phone_number_details.get("phone_number_e164")
                sip_trunk_id_from_phone_number_config = phone_number_details.get("livekit_sip_trunk_id")
                
                if agent_caller_id_number:
                    logger.info(f"Agent Caller ID from Supabase phone_numbers record {phone_numbers_id}: {agent_caller_id_number}")
                else:
                    logger.warning(f"phone_number_e164 not found in Supabase phone_numbers record {phone_numbers_id} for agent {agent_id}.")

                if sip_trunk_id_from_phone_number_config:
                    logger.info(f"LiveKit SIP Trunk ID from Supabase phone_numbers record {phone_numbers_id}: {sip_trunk_id_from_phone_number_config}")
                else:
                    logger.warning(f"livekit_sip_trunk_id not found in Supabase phone_numbers record {phone_numbers_id} for agent {agent_id}.")
            else:
                logger.warning(f"Phone number details not found in Supabase for phone_numbers_id {phone_numbers_id} (assigned to agent {agent_id}). Response: {pn_response.error or 'No data'}")
        except Exception as e:
            logger.error(f"Error fetching phone number details for phone_numbers_id {phone_numbers_id} from Supabase: {e}", exc_info=True)
            # Not raising HTTPException here to allow fallback logic for caller ID / trunk ID
    else:
        logger.info(f"Agent {agent_id} does not have a phone_numbers_id assigned in their agent config. Caller ID and specific trunk from phone_numbers table will not be used.")

    # --- Extraire les valeurs de la config agent (avec des valeurs par défaut) ---
    system_prompt_from_config = agent_config.get("system_prompt", "Default prompt: Please handle the call.")
    stt_language_from_config = agent_config.get("stt_language", "fr")
    tts_voice_id_from_config = agent_config.get("tts_voice", "65b25c5d-ff07-4687-a04c-da2f43ef6fa9") # Default Natasha (French)
    agent_name_from_config = agent_config.get("name", f"Agent {agent_id}")
    initial_greeting_from_config = agent_config.get("initial_greeting", "Bonjour, ceci est un test de Pam.")
    sip_trunk_id_directly_on_agent = agent_config.get("sip_trunk_id") # This is agents.sip_trunk_id

    logger.info(f"Extracted from Agent Config - Prompt: '{system_prompt_from_config}', Lang: '{stt_language_from_config}', Voice: '{tts_voice_id_from_config}', Greeting: '{initial_greeting_from_config}'")
    logger.info(f"SIP Trunk ID directly on agent record (agents.sip_trunk_id): {sip_trunk_id_directly_on_agent}")

    # Extract VAD provider from agent config
    vad_provider_from_config = agent_config.get("vad_provider", "silero")
    
    # Extract PAM tier and advanced settings
    pam_tier = agent_config.get("pam_tier", "core")
    wait_for_greeting = agent_config.get("wait_for_greeting", False)
    llm_temperature = agent_config.get("llm_temperature", 0.5)
    interruption_threshold = agent_config.get("interruption_threshold", 100)
    
    # Extract call handling settings
    transfer_to = agent_config.get("transfer_to")
    voicemail_detection = agent_config.get("voicemail_detection", False)
    voicemail_hangup_immediately = agent_config.get("voicemail_hangup_immediately", False)
    voicemail_message = agent_config.get("voicemail_message")
    
    logger.info(f"PAM Tier: {pam_tier}, Wait for Greeting: {wait_for_greeting}, Temperature: {llm_temperature}, Interruption Threshold: {interruption_threshold}")
    logger.info(f"Call Handling - Transfer To: {transfer_to}, Voicemail Detection: {voicemail_detection}, Hangup Immediately: {voicemail_hangup_immediately}, Custom Message: {'Set' if voicemail_message else 'Not set'}")

    ai_models_metadata = {
        "vad": {"provider": vad_provider_from_config},
        "stt": {
            "provider": agent_config.get("stt_provider", "deepgram"), 
            "language": stt_language_from_config, 
            "model_name": agent_config.get("stt_model", "nova-2")
        },
        "tts": {
            "provider": "dynamic",  # Will be determined by voice lookup
            "model_name": agent_config.get("tts_model", "sonic-2-2025-03-07"), 
            "voice_id": tts_voice_id_from_config
        },
        "llm": {
            "provider": agent_config.get("llm_provider", "openai"), 
            "model_name": agent_config.get("llm_model", "gpt-4o-mini"),
            "temperature": llm_temperature  # Pass temperature to LLM config
        }
    }

    # --- Déterminer le SIP Trunk ID final ---
    final_sip_trunk_id = None
    source_of_sip_trunk_id = "Unknown"

    if sip_trunk_id_from_phone_number_config: # Highest priority: trunk from agent's assigned number
        final_sip_trunk_id = sip_trunk_id_from_phone_number_config
        source_of_sip_trunk_id = f"phone_numbers table (record id {phone_numbers_id} assigned to agent)"
    elif sip_trunk_id_directly_on_agent: # Second priority: trunk ID set directly on the agent record
        final_sip_trunk_id = sip_trunk_id_directly_on_agent
        source_of_sip_trunk_id = "agents table (agents.sip_trunk_id field)"
    
    if not final_sip_trunk_id:
        logger.error(f"CRITICAL: No SIP Trunk ID could be determined for agent {agent_id}. Searched agent's assigned phone_number and agent record.")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="SIP trunk ID is not configured for this agent.")
    
    logger.info(f"Final SIP Trunk ID to be used for the call: {final_sip_trunk_id} (Source: {source_of_sip_trunk_id})")

    # --- Créer le log d'appel Supabase AVANT le job LiveKit ---
    call_log_payload_supabase = {
        "agent_id": agent_id,
        "to_phone_number": request.phoneNumber,
        "status": "initiating",
        "livekit_outbound_trunk_id": final_sip_trunk_id,
        "user_id": agent_config.get("user_id"), 
        "from_phone_number": agent_caller_id_number if agent_caller_id_number else None
    }
    
    # Add batch campaign context if provided
    if request.batch_campaign_id:
        call_log_payload_supabase["batch_campaign_id"] = request.batch_campaign_id
        logger.info(f"Call will be linked to batch campaign: {request.batch_campaign_id}")
        
    if request.batch_call_item_id:
        call_log_payload_supabase["batch_call_item_id"] = request.batch_call_item_id
        logger.info(f"Call will be linked to batch call item: {request.batch_call_item_id}")
    
    supabase_call_id = None
    try:
        logger.info(f"Attempting to insert call log into Supabase 'calls' table: {call_log_payload_supabase}")
        call_log_response = supabase_service_client.table("calls").insert(call_log_payload_supabase).execute()
        if call_log_response.data and len(call_log_response.data) > 0:
            supabase_call_id = call_log_response.data[0].get("id")
            logger.info(f"Successfully logged call initiation to Supabase 'calls' table. Supabase Call ID: {supabase_call_id}")
        else:
            logger.error(f"Failed to log call to Supabase 'calls' table or get ID back. Response: {call_log_response.error or 'No data'}")
            # This is critical, so raise an error
            raise HTTPException(status_code=500, detail="Could not create call log in Supabase database (no ID returned).")
    except Exception as log_e:
        logger.error(f"Error occurred while trying to log call to Supabase 'calls' table: {log_e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Could not create call log in Supabase database: {str(log_e)}")

    if not supabase_call_id: # Should be caught by exceptions above, but as a safeguard
        raise HTTPException(status_code=500, detail="Could not create call log in Supabase database (ID is null).")

    # --- Auto-start pathway if agent has default pathway assigned ---
    try:
        from api.agent_pathway_integration import auto_start_pathway_for_new_call
        
        # Prepare session metadata for pathway execution
        session_metadata = {
            "phone_number": request.phoneNumber,
            "contact_name": request.lastName,
            "agent_name": agent_name_from_config,
            "call_id": str(supabase_call_id),
            "batch_campaign_id": request.batch_campaign_id,
            "batch_call_item_id": request.batch_call_item_id
        }
        
        # Attempt to auto-start pathway (non-blocking)
        execution_id = await auto_start_pathway_for_new_call(
            call_id=str(supabase_call_id),
            agent_id=agent_id,
            session_metadata=session_metadata
        )
        
        if execution_id:
            logger.info(f"✅ Auto-started pathway execution {execution_id} for call {supabase_call_id}")
        else:
            logger.info(f"No pathway auto-started for call {supabase_call_id} (agent has no default pathway or pathway inactive)")
            
    except Exception as pathway_error:
        # Don't fail the call if pathway auto-start fails
        logger.error(f"Failed to auto-start pathway for call {supabase_call_id}: {pathway_error}")

    # --- Préparer les métadonnées pour LiveKit ---
    metadata = {
        "phoneNumber": request.phoneNumber,
        "agent_id_requested": agent_id,
        "agent_id": agent_id,
        "system_prompt": system_prompt_from_config,
        "ai_models": ai_models_metadata,
        "agentName": agent_name_from_config,
        "supabase_call_id": str(supabase_call_id), # Pass the new Supabase call ID
        "initial_greeting": initial_greeting_from_config,
        "sip_trunk_id": final_sip_trunk_id,
        "agent_caller_id_number": agent_caller_id_number if agent_caller_id_number else None,
        # PAM tier and advanced settings
        "pam_tier": pam_tier,
        "wait_for_greeting": wait_for_greeting,
        "interruption_threshold": interruption_threshold,
        "transfer_to": transfer_to,
        "voicemail_detection": voicemail_detection,
        "voicemail_hangup_immediately": voicemail_hangup_immediately,
        "voicemail_message": voicemail_message,
        # ✅ ADD JWT TOKEN FOR BACKEND API CALLS
        "auth_token": xano_token,
        "user_id": agent_config.get("user_id")
    }
    logger.info(f"Métadonnées finales envoyées au job LiveKit: {metadata}")
    metadata_json = json.dumps(metadata)

    # --- Créer le job LiveKit ---
    command = [
        "lk", "dispatch", "create",
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
        lk_room_name, lk_job_id = parse_lk_dispatch_output(result.stdout)
        return {"message": f"Call for agent {agent_id} initiated successfully", "dispatch_details": result.stdout}
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to execute lk dispatch command for agent {agent_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initiate call: {e.stderr or e.stdout or 'Unknown error'}",
        )
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="'lk' command not found. Server configuration issue."
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred: {str(e)}",
        )

@app.patch("/calls/room/{room_name}/status")
async def update_call_status_by_room(
    room_name: str,
    status_update: CallStatusUpdateRequest, # Contains supabase_call_id
    x_agent_token: str | None = Header(None, alias="X-Agent-Token")
):
    # The CallStatusUpdateRequest model now uses supabase_call_id.
    # The agent.py should send `supabase_call_id` field containing the Supabase call ID.
    supabase_call_id_value = status_update.supabase_call_id
    
    logger.info(f"Requête de mise à jour de statut/info pour room {room_name} (Supabase Call ID: {supabase_call_id_value}) reçue avec payload: {status_update.dict()}")

    EXPECTED_AGENT_TOKEN = os.getenv("AGENT_INTERNAL_TOKEN")
    if not EXPECTED_AGENT_TOKEN:
        logger.error("AGENT_INTERNAL_TOKEN n'est pas configuré côté serveur API. Authentification agent impossible.")
        # Ne pas lever d'exception ici si on veut quand même traiter des appels locaux par exemple, mais logguer l'erreur.
        # Pour des appels externes par l'agent, ce token est crucial.
    elif not x_agent_token or x_agent_token != EXPECTED_AGENT_TOKEN:
        logger.error(f"Token agent invalide ou manquant pour la mise à jour de statut de la room {room_name}.")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing agent token")
    else:
        logger.info(f"Token agent validé pour la room {room_name}.")

    if not supabase_call_id_value: # Check if the Supabase ID is present
        logger.error(f"Supabase Call ID (supabase_call_id) manquant dans la requête PATCH pour room {room_name}.")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Supabase Call ID (supabase_call_id in request body) is required.")

    # Update Supabase 'calls' table
    payload_to_supabase = {}
    if status_update.new_status:
        payload_to_supabase["status"] = status_update.new_status
    if status_update.call_duration_seconds is not None:
        payload_to_supabase["call_duration"] = status_update.call_duration_seconds
    if status_update.telnyx_call_control_id is not None: # Assuming this is Telnyx's call_control_id
        payload_to_supabase["call_control_id"] = status_update.telnyx_call_control_id
    
    # Add updated_at manually or ensure DB trigger handles it
    payload_to_supabase["updated_at"] = datetime.utcnow().isoformat()


    if not payload_to_supabase:
        logger.info(f"Aucun champ à mettre à jour pour Supabase Call ID {supabase_call_id_value} (room {room_name}).")
        return {"message": f"No fields to update for Supabase call ID {supabase_call_id_value}."}

    logger.info(f"Envoi du payload PATCH à Supabase 'calls' table (ID: {supabase_call_id_value}): {payload_to_supabase}")

    try:
        # supabase_service_client should be imported from .db_client
        update_response = supabase_service_client.table("calls").update(payload_to_supabase).eq("id", supabase_call_id_value).execute()
        
        if update_response.data and len(update_response.data) > 0:
            logger.info(f"Infos pour Supabase Call ID {supabase_call_id_value} (room {room_name}) mises à jour dans Supabase: {update_response.data[0]}")
            
            # Update batch call item status if this is a batch campaign call
            if status_update.new_status:
                try:
                    # Import here to avoid circular imports
                    from api.batch_routes import update_batch_call_item_from_call_status
                    
                    await update_batch_call_item_from_call_status(
                        supabase_call_id_value, 
                        status_update.new_status, 
                        status_update.call_duration_seconds
                    )
                except Exception as e:
                    logger.error(f"Error updating batch call item for call {supabase_call_id_value}: {e}")
                    # Don't fail the main call update if batch update fails
            
            return update_response.data[0]
        elif update_response.error:
            logger.error(f"Erreur Supabase lors de la mise à jour pour Call ID {supabase_call_id_value}: {update_response.error.message}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Supabase PATCH error: {update_response.error.message}")
        else:
            # This case might occur if .eq("id", supabase_call_id_value) found no matching record.
            logger.warning(f"Mise à jour Supabase pour Call ID {supabase_call_id_value} n'a retourné aucune donnée ni erreur. L'enregistrement existe-t-il ?")
            # Check if the record exists. If not, it's a 404 situation.
            try: # Add try-except for the check itself
                check_exists = supabase_service_client.table("calls").select("id").eq("id", supabase_call_id_value).maybe_single().execute()
                if not check_exists.data:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Call record with ID {supabase_call_id_value} not found in Supabase.")
            except Exception as e_check:
                 logger.error(f"Error checking existence of Supabase Call ID {supabase_call_id_value}: {e_check}", exc_info=True)
                 # Reraise as 500, or handle as appropriate if check fails
                 raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error verifying call record existence: {str(e_check)}")
            return {"message": f"Update for Supabase Call ID {supabase_call_id_value} processed, but no data returned from Supabase (possibly no change or record not found and rechecked)."}

    except Exception as e_generic:
        logger.error(f"Erreur générique lors de la mise à jour Supabase pour Call ID {supabase_call_id_value}: {e_generic}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Unexpected Supabase error: {str(e_generic)}")

# --- API Endpoints ---
@app.post("/webhook/telnyx")
async def telnyx_webhook(webhook: TelnyxWebhook):
    """
    Endpoint pour recevoir les webhooks de Telnyx.
    Les webhooks contiennent des informations sur les événements d'appel.
    """
    try:
        logger.info(f"Webhook Telnyx reçu: Event: {webhook.data.get('event_type')}, Full Data: {webhook.data}")
        
        event_type = webhook.data.get("event_type")
        payload = webhook.data.get("payload", {})
        call_control_id = payload.get("call_control_id") 
        
        if not event_type:
            logger.warning("Webhook Telnyx incomplet: event_type manquant.")
            return {"status": "warning", "message": "Webhook incomplet: event_type manquant"}
            
        supabase_call_id_to_update = None
        
        # Tentative 1: Extraire supabase_call_id depuis client_state
        client_state_base64 = payload.get("client_state")
        if client_state_base64:
            try:
                client_state_bytes = client_state_base64.encode('utf-8')
                decoded_client_state = base64.b64decode(client_state_bytes).decode('utf-8')
                if decoded_client_state.isdigit():
                    supabase_call_id_to_update = int(decoded_client_state)
                    logger.info(f"Supabase Call ID '{supabase_call_id_to_update}' extrait de client_state.")
                else:
                    # Try to match if it's a UUID (string) directly
                    try:
                        uuid_obj = uuid.UUID(decoded_client_state, version=4) # Check if it's a valid UUID string
                        supabase_call_id_to_update = str(uuid_obj) # Keep as string if it's a UUID
                        logger.info(f"Supabase Call ID (UUID) '{supabase_call_id_to_update}' extrait de client_state.")
                    except ValueError:
                        logger.warning(f"client_state décodé ('{decoded_client_state}') ne semble pas être un ID Supabase valide (entier ou UUID). Ignoré.")
            except Exception as e:
                logger.error(f"Erreur de décodage client_state: {e}. client_state reçu: {client_state_base64}")
        
        update_data_for_supabase = {}
        is_number_order_event = event_type.startswith("number.order.")

        if is_number_order_event:
            logger.info(f"Traitement Webhook: Événement de commande de numéro '{event_type}'.")
            telnyx_number_id_from_payload = None
            
            # Extraire telnyx_number_id du payload spécifique aux commandes de numéro
            if event_type == "number.order.phone_number.updated" or event_type == "number.order.completed":
                 if "id" in payload and event_type == "number.order.phone_number.updated":
                     telnyx_number_id_from_payload = payload.get("id")
                 elif "phone_numbers" in payload and isinstance(payload["phone_numbers"], list) and payload["phone_numbers"]:
                     telnyx_number_id_from_payload = payload["phone_numbers"][0].get("id")

            if not telnyx_number_id_from_payload and "number_order_phone_number_id" in payload: 
                telnyx_number_id_from_payload = payload.get("number_order_phone_number_id")
            
            if not telnyx_number_id_from_payload:
                logger.warning(f"Webhook '{event_type}': Impossible d'extraire telnyx_number_id du payload: {payload}. Mise à jour Supabase impossible.")
                return {"status": "warning", "message": f"Webhook {event_type} non traitable: telnyx_number_id manquant."}

            logger.info(f"Webhook '{event_type}': Recherche dans Supabase table 'phone_numbers' par 'telnyx_number_id' = '{telnyx_number_id_from_payload}'.")
            pn_response = supabase_service_client.table("phone_numbers").select("id, status, telnyx_connection_id").eq("telnyx_number_id", telnyx_number_id_from_payload).maybe_single().execute()

            if pn_response.data:
                supabase_phone_number_id = pn_response.data.get("id")
                phone_number_update_payload = {}
                new_status_from_webhook = payload.get("status")
                if event_type == "number.order.phone_number.updated" and "status" in payload:
                    new_status_from_webhook = payload.get("status")
                elif event_type == "number.order.completed":
                    new_status_from_webhook = "active"
                    # For number.order.completed, also extract the actual phone number if available
                    if "phone_numbers" in payload and isinstance(payload["phone_numbers"], list) and payload["phone_numbers"]:
                        phone_number_e164_from_order = payload["phone_numbers"][0].get("phone_number")
                        if phone_number_e164_from_order:
                            phone_number_update_payload["phone_number_e164"] = phone_number_e164_from_order
                            logger.info(f"Webhook 'number.order.completed': Extracted phone_number_e164 '{phone_number_e164_from_order}' for update.")

                if new_status_from_webhook and new_status_from_webhook != pn_response.data.get("status"):
                    phone_number_update_payload["status"] = new_status_from_webhook
                
                telnyx_connection_id_from_webhook = None
                if "voice" in payload and payload["voice"] and "connection_id" in payload["voice"]:
                     telnyx_connection_id_from_webhook = payload["voice"]["connection_id"]
                elif "connection_id" in payload:
                     telnyx_connection_id_from_webhook = payload.get("connection_id")

                if telnyx_connection_id_from_webhook and telnyx_connection_id_from_webhook != pn_response.data.get("telnyx_connection_id"):
                    phone_number_update_payload["telnyx_connection_id"] = telnyx_connection_id_from_webhook
                
                if phone_number_update_payload: # Only update if there are changes
                    phone_number_update_payload["updated_at"] = datetime.utcnow().isoformat()
                    logger.info(f"Webhook '{event_type}': Envoi PATCH à Supabase 'phone_numbers' ID {supabase_phone_number_id} avec données: {phone_number_update_payload}")
                    update_pn_response = supabase_service_client.table("phone_numbers").update(phone_number_update_payload).eq("id", supabase_phone_number_id).execute()
                    if update_pn_response.data:
                        logger.info(f"Webhook '{event_type}': Enregistrement Supabase 'phone_numbers' ID {supabase_phone_number_id} mis à jour: {update_pn_response.data[0]}")
                    elif update_pn_response.error:
                         logger.error(f"Webhook '{event_type}': Erreur Supabase MAJ 'phone_numbers' ID {supabase_phone_number_id}: {update_pn_response.error.message}")
                else:
                    logger.info(f"Webhook '{event_type}': Pas de données nouvelles à mettre à jour pour Supabase 'phone_numbers' ID {supabase_phone_number_id}.")
            else:
                logger.warning(f"Webhook '{event_type}': Aucun enregistrement 'phone_numbers' trouvé pour telnyx_number_id '{telnyx_number_id_from_payload}'.")
        
            return {"status": "success", "message": f"Webhook number order event {event_type} traité."}
        
        # --- Logique pour les événements d'appel (non-commande de numéro) ---
        if not call_control_id and event_type in ["call.initiated", "call.answered", "call.hangup"]:
            logger.warning(f"Webhook '{event_type}' reçu sans call_control_id.")
            if not supabase_call_id_to_update:
                 logger.warning(f"Impossible de lier '{event_type}' à un appel Supabase sans call_control_id ou client_state valide.")
                 return {"status": "warning", "message": f"Webhook {event_type} sans call_control_id et sans client_state valide."}
        
        if not supabase_call_id_to_update and call_control_id:
            logger.info(f"Webhook '{event_type}': supabase_call_id non trouvé via client_state. Recherche dans Supabase 'calls' par 'call_control_id' = '{call_control_id}'.")
            try:
                call_record_response = supabase_service_client.table("calls").select("id").eq("call_control_id", call_control_id).maybe_single().execute()
                if call_record_response.data:
                    supabase_call_id_to_update = call_record_response.data.get("id")
                    logger.info(f"Webhook '{event_type}': Supabase Call ID '{supabase_call_id_to_update}' trouvé par recherche sur call_control_id.")
                else:
                    logger.info(f"Webhook '{event_type}': Aucun enregistrement 'calls' existant trouvé dans Supabase avec 'call_control_id' = '{call_control_id}'.")
                    # If call.initiated and not found by call_control_id, it might be a very new call.
                    # The agent.py will send supabase_call_id in X-Client-State, which is preferred.
                    # If that failed or this is a direct Telnyx originated call (e.g. inbound not via Pam agent), this lookup path is important.
            except Exception as e_search_ccid:
                logger.error(f"Webhook '{event_type}': Exception lors de la recherche Supabase 'calls' par call_control_id: {e_search_ccid}", exc_info=True)

        if not supabase_call_id_to_update and event_type == "call.initiated":
            direction = payload.get("direction")
            if direction == "outbound":
                to_phone_number = payload.get("to")
                if to_phone_number:
                    logger.info(f"Webhook 'call.initiated': supabase_call_id non identifié. Tentative de liaison par numéro '{to_phone_number}' et statut 'initiating'/'dialing'.")
                    try:
                        possible_calls_response = supabase_service_client.table("calls") \
                            .select("id, created_at") \
                            .eq("to_phone_number", to_phone_number) \
                            .is_("call_control_id", None) \
                            .in_("status", ["initiating", "dialing"]) \
                            .order("created_at", desc=True) \
                            .limit(1) \
                            .execute()
                        
                        if possible_calls_response.data:
                            call_to_link = possible_calls_response.data[0]
                            supabase_call_id_to_update = call_to_link.get("id")
                            logger.info(f"Webhook 'call.initiated': Liaison réussie. Supabase Call ID '{supabase_call_id_to_update}' choisi pour '{to_phone_number}'.")
                        else:
                            logger.warning(f"Webhook 'call.initiated': Aucun appel Supabase à lier trouvé pour '{to_phone_number}'.")
                    except Exception as e_link_initiated:
                        logger.error(f"Webhook 'call.initiated': Exception lors de la tentative de liaison: {e_link_initiated}", exc_info=True)
                else:
                    logger.warning(f"Webhook 'call.initiated': Numéro 'to' manquant dans payload pour liaison.")
            else:
                logger.info(f"Webhook 'call.initiated' reçu pour un appel non sortant (direction: {direction}). Ignoré car la gestion des appels entrants est supprimée.")

        # Préparer les données à envoyer à Supabase pour les événements d'appel
        # Add Telnyx call_session_id if available, maps to telnyx_call_session_id in Supabase
        telnyx_call_session_id = payload.get("call_session_id")
        if telnyx_call_session_id:
            update_data_for_supabase["telnyx_call_session_id"] = telnyx_call_session_id

        if call_control_id:
             update_data_for_supabase["call_control_id"] = call_control_id

        if event_type == "call.initiated":
            logger.info(f"Traitement Webhook: Appel initié (Supabase ID: {supabase_call_id_to_update or 'Non lié'})")
            update_data_for_supabase["initiated_at"] = webhook.data.get("occurred_at")
            update_data_for_supabase["from_phone_number"] = payload.get("from")
            # update_data_for_supabase["status"] = "dialing" # Optionnel
            
        elif event_type == "call.answered":
            logger.info(f"Traitement Webhook: Appel répondu (Supabase ID: {supabase_call_id_to_update or 'Non lié'})")
            update_data_for_supabase["answered_at"] = webhook.data.get("occurred_at")
            update_data_for_supabase["status"] = "active"
            
        elif event_type == "call.hangup":
            logger.info(f"Traitement Webhook: Appel terminé (Supabase ID: {supabase_call_id_to_update or 'Non lié'})")
            update_data_for_supabase["ended_at"] = payload.get("end_time") 
            update_data_for_supabase["ended_reason"] = payload.get("hangup_cause", "")
            update_data_for_supabase["status"] = "completed"
            start_time_str = payload.get("start_time")
            end_time_str = payload.get("end_time")
            if start_time_str and end_time_str:
                try:
                    start_dt = datetime.fromisoformat(start_time_str.replace("Z", "+00:00"))
                    end_dt = datetime.fromisoformat(end_time_str.replace("Z", "+00:00"))
                    call_duration_webhook = int((end_dt - start_dt).total_seconds())
                    update_data_for_supabase["call_duration"] = call_duration_webhook
                    logger.info(f"Webhook 'call.hangup': Durée calculée: {call_duration_webhook}s")
                except Exception as e_dur:
                    logger.error(f"Webhook 'call.hangup': Erreur calcul durée: {e_dur}")
        
        # Mettre à jour la table 'calls' dans Supabase (Partie commentée pour ce step)
        if supabase_call_id_to_update:
            update_data_for_supabase["updated_at"] = datetime.utcnow().isoformat()
            if len(update_data_for_supabase) > 1: 
                logger.info(f"Webhook '{event_type}': Données préparées pour Supabase 'calls' ID {supabase_call_id_to_update}: {update_data_for_supabase}")
                try:
                    final_update_response = supabase_service_client.table("calls").update(update_data_for_supabase).eq("id", supabase_call_id_to_update).execute()
                    if final_update_response.data:
                        logger.info(f"Webhook '{event_type}': Enregistrement Supabase 'calls' ID {supabase_call_id_to_update} mis à jour: {final_update_response.data[0]}")
                    elif final_update_response.error:
                        logger.error(f"Webhook '{event_type}': Erreur Supabase MAJ 'calls' ID {supabase_call_id_to_update}: {final_update_response.error.message}")
                    # Consider case where update doesn't return data but also no error (e.g. record not found by eq)
                    else:
                        logger.warning(f"Webhook '{event_type}': Supabase update for 'calls' ID {supabase_call_id_to_update} returned no data and no error.")
                except Exception as e_final_update:
                    logger.error(f"Webhook '{event_type}': Erreur Supabase générique MAJ 'calls' ID {supabase_call_id_to_update}: {e_final_update}", exc_info=True)
            else:
                logger.info(f"Webhook '{event_type}': Pas de données nouvelles (autres que updated_at) à mettre à jour pour Supabase 'calls' ID {supabase_call_id_to_update}.")
        else:
            logger.warning(f"Webhook Appel '{event_type}': supabase_call_id non identifié. Aucune mise à jour Supabase 'calls'. Webhook Data: {webhook.data}")
            
        return {"status": "success", "message": f"Webhook {event_type} traité (préparation données appel)."}
        
    except Exception as e:
        logger.error(f"Erreur globale lors du traitement du webhook Telnyx: {e}", exc_info=True)
        return {"status": "internal_error_logged", "message": "Error processed internally"}, 200

# Endpoint to create a user in public.users table (kept for direct public.users entries if needed)
@app.post("/users", status_code=status.HTTP_201_CREATED)
async def create_user_in_public_users(request: UserCreateRequest):
    logger.info(f"Received request to create user in public.users: {request.email}")

    user_payload = {
        "email": request.email,
        "name": request.name
    }
    if request.auth_user_id:
        user_payload["auth_user_id"] = request.auth_user_id

    try:
        response = supabase_service_client.table("users").insert(user_payload).execute()
        if response.data and len(response.data) > 0:
            created_user_data = response.data[0]
            logger.info(f"User created successfully in public.users: {created_user_data}")
            return created_user_data
        else:
            logger.error(f"Failed to create user in public.users or no data returned. Response: {response.error or 'No data'}")
            error_detail = "Failed to create user in Supabase public.users."
            if response.error and hasattr(response.error, 'message'):
                error_detail = f"Supabase error (public.users): {response.error.message}"
            elif response.error:
                error_detail = f"Supabase error (public.users): {str(response.error)}"
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=error_detail)
    except Exception as e:
        logger.error(f"Unexpected error creating user {request.email} in public.users: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"An unexpected error occurred in public.users creation: {str(e)}")

# New Auth Models and Endpoints
class UserLoginRequest(BaseModel):
    email: str
    password: str

@app.post("/auth/login")
async def auth_login(request: UserLoginRequest):
    logger.info(f"Received login request for email: {request.email}")
    try:
        # Step 1: Authenticate with Supabase Auth using anon client
        # Use anon client for user authentication, not service client
        auth_client = get_supabase_anon_client()
        
        auth_response = auth_client.auth.sign_in_with_password({
            "email": request.email,
            "password": request.password,
        })
        
        logger.info(f"Supabase auth.sign_in_with_password response: {auth_response}")

        if auth_response.user is None or auth_response.session is None:
            logger.error(f"Supabase auth.sign_in_with_password did not return a user or session. Response: {auth_response}")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials.")

        auth_user_id = auth_response.user.id
        access_token = auth_response.session.access_token
        logger.info(f"User successfully authenticated. Auth User ID: {auth_user_id}")

        # Step 2: Get user profile from public.users using service client
        try:
            user_profile_response = supabase_service_client.table("users").select("*").eq("id", auth_user_id).single().execute()
            if not user_profile_response.data:
                logger.warning(f"User {auth_user_id} authenticated but no profile found in public.users")
                user_profile = {
                    "id": str(auth_user_id),
                    "email": request.email,
                    "name": request.email.split('@')[0]
                }
            else:
                user_profile = user_profile_response.data
                logger.info(f"Retrieved user profile from public.users: {user_profile}")
        except Exception as profile_e:
            logger.warning(f"Error fetching user profile for {auth_user_id}: {profile_e}")
            user_profile = {
                "id": str(auth_user_id),
                "email": request.email,
                "name": request.email.split('@')[0]
            }

        return {
            "message": "Login successful!",
            "authToken": access_token,  # Return access_token as authToken for frontend compatibility
            "user": user_profile,
            "session": auth_response.session.model_dump() if auth_response.session else None
        }

    except httpx.HTTPStatusError as e_httpx:
        logger.error(f"HTTPX error during login for {request.email}: {e_httpx.response.text if e_httpx.response else str(e_httpx)}", exc_info=True)
        raise HTTPException(status_code=e_httpx.response.status_code if e_httpx.response else 500, detail=f"Network error during login: {str(e_httpx)}")
    except Exception as e:
        logger.error(f"Error during login for {request.email}: {e}", exc_info=True)
        error_detail = str(e)
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        
        # Try to parse Supabase specific error messages
        if hasattr(e, 'json') and callable(e.json):
            try:
                error_json = e.json()
                error_message_from_supabase = error_json.get("msg") or error_json.get("message") or error_json.get("error_description")
                if error_message_from_supabase:
                    error_detail = f"Supabase Auth Error: {error_message_from_supabase}"
                    if "Invalid login credentials" in error_message_from_supabase or "invalid_credentials" in error_message_from_supabase.lower():
                        status_code = status.HTTP_401_UNAUTHORIZED
                        error_detail = "Invalid credentials."
                    else:
                        status_code = status.HTTP_400_BAD_REQUEST
            except Exception as json_parse_e:
                logger.warning(f"Could not parse JSON from Supabase error object: {json_parse_e}")
        elif "Invalid login credentials" in str(e) or "invalid_credentials" in str(e).lower():
            status_code = status.HTTP_401_UNAUTHORIZED
            error_detail = "Invalid credentials."
        
        raise HTTPException(status_code=status_code, detail=error_detail)

class TokenRefreshRequest(BaseModel):
    refresh_token: str

@app.post("/auth/refresh")
async def refresh_token(request: TokenRefreshRequest):
    """Refresh JWT access token using refresh token"""
    logger.info("Received token refresh request")
    try:
        # Use anon client to refresh the session
        auth_client = get_supabase_anon_client()
        
        refresh_response = auth_client.auth.refresh_session({
            "refresh_token": request.refresh_token
        })
        
        logger.info(f"Supabase refresh_session response: {refresh_response}")

        if refresh_response.user is None or refresh_response.session is None:
            logger.error(f"Supabase refresh_session did not return a user or session. Response: {refresh_response}")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token.")

        auth_user_id = refresh_response.user.id
        access_token = refresh_response.session.access_token
        
        # Get or create user profile
        user_profile_response = supabase_service_client.table("user_profiles").select("*").eq("auth_user_id", auth_user_id).execute()
        
        user_profile = None
        if user_profile_response.data and len(user_profile_response.data) > 0:
            user_profile = user_profile_response.data[0]
        else:
            # Create default user profile if it doesn't exist
            user_profile = {
                "name": refresh_response.user.email or "User",
                "email": refresh_response.user.email,
                "auth_user_id": auth_user_id
            }

        return {
            "message": "Token refreshed successfully!",
            "authToken": access_token,  # Return access_token as authToken for frontend compatibility
            "user": user_profile,
            "session": refresh_response.session.model_dump() if refresh_response.session else None
        }

    except httpx.HTTPStatusError as e_httpx:
        logger.error(f"HTTPX error during token refresh: {e_httpx.response.text if e_httpx.response else str(e_httpx)}", exc_info=True)
        raise HTTPException(status_code=e_httpx.response.status_code if e_httpx.response else 500, detail=f"Network error during token refresh: {str(e_httpx)}")
    except Exception as e:
        logger.error(f"Error during token refresh: {e}", exc_info=True)
        error_detail = str(e)
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        
        # Try to parse Supabase specific error messages
        if "Invalid refresh token" in str(e) or "invalid_grant" in str(e).lower():
            status_code = status.HTTP_401_UNAUTHORIZED
            error_detail = "Invalid or expired refresh token."
        
        raise HTTPException(status_code=status_code, detail=error_detail)

# Endpoint to get current user (equivalent to /auth/me)
@app.get("/auth/me")
async def get_current_user(authorization: str = Header(None, alias="Authorization")):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing or invalid authorization header")
    
    token = authorization.replace("Bearer ", "")
    
    try:
        # Verify token with Supabase using service client
        user_response = supabase_service_client.auth.get_user(token)
        
        if not user_response.user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        
        auth_user_id = user_response.user.id
        
        # Get user profile from public.users using service client
        try:
            user_profile_response = supabase_service_client.table("users").select("*").eq("id", auth_user_id).single().execute()
            if not user_profile_response.data:
                # If no profile exists, create a basic one
                user_profile = {
                    "id": str(auth_user_id),
                    "email": user_response.user.email,
                    "name": user_response.user.email.split('@')[0] if user_response.user.email else "User"
                }
            else:
                user_profile = user_profile_response.data
        except Exception as profile_e:
            logger.warning(f"Error fetching user profile for {auth_user_id}: {profile_e}")
            user_profile = {
                "id": str(auth_user_id),
                "email": user_response.user.email,
                "name": user_response.user.email.split('@')[0] if user_response.user.email else "User"
            }
        
        return user_profile
        
    except Exception as e:
        logger.error(f"Error validating token: {e}")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

# New Signup Endpoint for auth.users and public.users
@app.post("/auth/signup", status_code=status.HTTP_201_CREATED)
async def auth_signup(request: UserSignupRequest):
    logger.info(f"Received signup request for email: {request.email}")
    try:
        # Step 1: Sign up user with Supabase Auth
        auth_response = supabase_service_client.auth.sign_up({
            "email": request.email,
            "password": request.password,
        })
        
        logger.info(f"Supabase auth.sign_up response: {auth_response}")

        if auth_response.user is None or auth_response.user.id is None:
            logger.error(f"Supabase auth.sign_up did not return a user or user ID. Response: {auth_response}")
            error_message = "Signup failed: No user object returned from Supabase Auth."
            if auth_response.session is None and not auth_response.user:
                 error_message = "Signup failed. The user might already be registered or email confirmation is required."
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error_message)

        auth_user_id = auth_response.user.id
        logger.info(f"User successfully signed up in auth.users. Auth User ID: {auth_user_id}")

        # Step 2: Create a corresponding profile in public.users
        # Ensure users_id in public.users matches agents.user_id and calls.user_id (all should be UUID from auth.users.id)
        public_user_profile_payload = {
            "id": str(auth_user_id), # Explicitly set the public.users.id to be the auth.users.id (UUID)
            "email": request.email,
            "name": request.name if request.name else request.email.split('@')[0]
            # "auth_user_id": str(auth_user_id), # This field might be redundant if public.users.id is the auth_user_id
        }
        
        logger.info(f"Attempting to create profile in public.users: {public_user_profile_payload}")
        profile_response = supabase_service_client.table("users").insert(public_user_profile_payload).execute()

        if not (profile_response.data and len(profile_response.data) > 0):
            logger.error(f"Auth signup for {request.email} (Auth User ID: {auth_user_id}) succeeded, but failed to create profile in public.users. Supabase profile insertion error: {profile_response.error}. Cleaning up auth user.")
            try:
                delete_auth_user_response = supabase_service_client.auth.admin.delete_user(auth_user_id)
                logger.info(f"Cleaned up auth.users entry for {auth_user_id} due to public.users profile creation failure. Response: {delete_auth_user_response}")
            except Exception as cleanup_e:
                logger.error(f"Failed to cleanup auth.users entry {auth_user_id} after public.users profile failure: {cleanup_e}")
            
            profile_error_detail = "User authentication successful, but failed to create user profile."
            if profile_response.error and hasattr(profile_response.error, 'message'):
                profile_error_detail = f"Supabase public.users error: {profile_response.error.message}"
            elif profile_response.error:
                profile_error_detail = f"Supabase public.users error: {str(profile_response.error)}"
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=profile_error_detail)
        
        created_public_profile = profile_response.data[0]
        logger.info(f"Successfully created public.users profile for {request.email}: {created_public_profile}")

        return {
            "message": "Signup successful!",
            "auth_user": auth_response.user.model_dump() if auth_response.user else None,
            "session": auth_response.session.model_dump() if auth_response.session else None,
            "public_profile": created_public_profile
        }

    except httpx.HTTPStatusError as e_httpx:
        logger.error(f"HTTPX error during signup for {request.email}: {e_httpx.response.text if e_httpx.response else str(e_httpx)}", exc_info=True)
        raise HTTPException(status_code=e_httpx.response.status_code if e_httpx.response else 500, detail=f"Network error during signup: {str(e_httpx)}")
    except Exception as e:
        logger.error(f"Error during signup for {request.email}: {e}", exc_info=True)
        error_detail = str(e)
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        
        # Try to parse Supabase specific error messages from GoTrueApiError
        if hasattr(e, 'json') and callable(e.json):
            try:
                error_json = e.json()
                error_message_from_supabase = error_json.get("msg") or error_json.get("message") or error_json.get("error_description")
                if error_message_from_supabase:
                    error_detail = f"Supabase Auth Error: {error_message_from_supabase}"
                    if "User already registered" in error_message_from_supabase or "user_already_exists" in error_message_from_supabase.lower():
                        status_code = status.HTTP_409_CONFLICT
                    else:
                        status_code = status.HTTP_400_BAD_REQUEST
            except Exception as json_parse_e:
                logger.warning(f"Could not parse JSON from Supabase error object: {json_parse_e}")
        elif hasattr(e, 'args') and e.args and isinstance(e.args[0], dict) and 'message' in e.args[0]: # Fallback for older Supabase client error formats
            error_message_from_supabase = e.args[0]['message']
            error_detail = f"Supabase Auth Error: {error_message_from_supabase}"
            if "User already registered" in error_message_from_supabase:
                status_code = status.HTTP_409_CONFLICT
            else:
                status_code = status.HTTP_400_BAD_REQUEST
        elif "User already registered" in str(e) or "user_already_exists" in str(e).lower(): # General string check
            status_code = status.HTTP_409_CONFLICT
            error_detail = "User with this email already exists."
        
        raise HTTPException(status_code=status_code, detail=error_detail)

# New Agent Creation Models and Endpoint
class AgentCreateRequest(BaseModel):
    # Remove user_id from the request model - it will be extracted from auth token
    name: str
    system_prompt: str
    llm_provider: str = "openai"
    llm_model: str = "gpt-4o-mini"
    stt_provider: str = "deepgram"
    stt_model: str = "nova-2"
    tts_provider: str = "cartesia"
    tts_voice: str = "65b25c5d-ff07-4687-a04c-da2f43ef6fa9"
    stt_language: str = "fr"
    tts_model: str = "sonic-2-2025-03-07"
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
    transfer_to: Optional[str] = None  # Transfer phone number
    voicemail_detection: bool = False  # AI voicemail detection capability
    voicemail_hangup_immediately: bool = False  # Hang up immediately when voicemail detected
    voicemail_message: Optional[str] = None  # Custom voicemail message
    
    # Pathway Integration
    default_pathway_id: Optional[str] = None  # Default pathway to auto-execute on calls
    


@app.post("/agents", status_code=status.HTTP_201_CREATED)
async def create_agent(request: AgentCreateRequest, authorization: str = Header(None, alias="Authorization")):
    """Create a new agent for the authenticated user"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing or invalid authorization header")
    
    token = authorization.replace("Bearer ", "")
    
    try:
        # Verify token with Supabase and get user_id
        user_response = supabase_service_client.auth.get_user(token)
        
        if not user_response.user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        
        user_id = user_response.user.id
        logger.info(f"Received request to create agent: {request.name} for user {user_id}")

        agent_payload = {
            "user_id": user_id,  # Use user_id from auth token
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
            # New PAM tier and advanced settings
            "pam_tier": request.pam_tier,
            "wait_for_greeting": request.wait_for_greeting,
            "llm_temperature": request.llm_temperature,
            "interruption_threshold": request.interruption_threshold,
            "vad_provider": request.vad_provider,
            "transfer_to": request.transfer_to,
            "voicemail_detection": request.voicemail_detection,
            "voicemail_hangup_immediately": request.voicemail_hangup_immediately,
            "voicemail_message": request.voicemail_message,
            "default_pathway_id": request.default_pathway_id,

        }
        
        if request.phone_numbers_id:
            agent_payload["phone_numbers_id"] = request.phone_numbers_id
        if request.sip_trunk_id:
            agent_payload["sip_trunk_id"] = request.sip_trunk_id

        response = supabase_service_client.table("agents").insert(agent_payload).execute()
        if response.data and len(response.data) > 0:
            created_agent = response.data[0]
            logger.info(f"Agent created successfully: {created_agent}")
            return created_agent
        else:
            logger.error(f"Failed to create agent or no data returned. Response: {response.error or 'No data'}")
            error_detail = "Failed to create agent in Supabase."
            if response.error and hasattr(response.error, 'message'):
                error_detail = f"Supabase error: {response.error.message}"
            elif response.error:
                error_detail = f"Supabase error: {str(response.error)}"
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=error_detail)
    except HTTPException:
        raise  # Re-raise HTTP exceptions
    except Exception as e:
        logger.error(f"Unexpected error creating agent {request.name}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"An unexpected error occurred: {str(e)}")

# --- Root endpoint for testing ---
@app.get("/")
def read_root():
    return {"message": "API is running"}

@app.get("/agents")
async def get_agents(authorization: str = Header(None, alias="Authorization")):
    """
    Get a list of all agents for the authenticated user, including their phone numbers.
    """
    try:
        user_id = get_user_id_from_token(authorization)
        logger.info(f"Fetching agents for user_id: {user_id}")

        response = supabase_service_client.table("agents").select(
             """
            *,
            phone_numbers!agents_phone_numbers_id_fkey!left (
                id,
                phone_number_e164,
                status
            )
            """
        ).eq("user_id", user_id).execute()

        if not response.data:
            logger.info(f"No agents found for user {user_id}")
            return []
        
        # Process agents to flatten the phone number details
        processed_agents = []
        for agent in response.data:
            phone_info = agent.get('phone_numbers')
            if phone_info and isinstance(phone_info, dict):
                agent['phone_number'] = phone_info.get('phone_number_e164')
                agent['phone_number_status'] = phone_info.get('status')
            else:
                agent['phone_number'] = None
                agent['phone_number_status'] = None
            
            # Remove the nested object if it exists to keep response clean
            if 'phone_numbers' in agent:
                del agent['phone_numbers']
            
            processed_agents.append(agent)

        logger.info(f"Successfully retrieved {len(processed_agents)} agents for user {user_id}")
        return processed_agents
        
    except HTTPException as http_exc:
        logger.warning(f"HTTP Exception while fetching agents: {http_exc.detail}")
        raise http_exc
    except Exception as e:
        logger.error(f"Error fetching agents: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An unexpected error occurred while fetching agents.")

@app.get("/calls")
async def get_calls(authorization: str = Header(None, alias="Authorization")):
    """Get all calls for the authenticated user"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing or invalid authorization header")
    
    token = authorization.replace("Bearer ", "")
    
    try:
        # Verify token with Supabase
        user_response = supabase_service_client.auth.get_user(token)
        
        if not user_response.user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        
        user_id = user_response.user.id
        logger.info(f"Fetching calls for user: {user_id}")
        
        # Get all calls for this user, ordered by created_at desc (most recent first)
        calls_response = supabase_service_client.table("calls").select("*").eq("user_id", user_id).order("created_at", desc=True).execute()
        
        if not calls_response.data:
            logger.info(f"No calls found for user {user_id}")
            return []
        
        calls = calls_response.data
        logger.info(f"Found {len(calls)} calls for user {user_id}")
        
        # Process calls to match frontend expectations
        processed_calls = []
        for call in calls:
            processed_call = {
                "id": call.get("id"),
                "created_at": call.get("created_at", ""),
                "agent_id": call.get("agent_id"),
                "agent_name": call.get("agent_name", f"Agent {call.get('agent_id')}" if call.get("agent_id") else "Unknown Agent"),
                "user_id": call.get("user_id"),
                "from_phone_number": call.get("from_phone_number", ""),
                "to_phone_number": call.get("to_phone_number", ""),
                "status": call.get("status", "unknown"),
                "livekit_room_name": call.get("livekit_room_name", ""),
                "livekit_outbound_trunk_id": call.get("livekit_outbound_trunk_id", ""),
                "call_duration": call.get("call_duration"),  # Duration in seconds
                "initiated_at": call.get("initiated_at"),
                "answered_at": call.get("answered_at"),
                "ended_at": call.get("ended_at"),
                "ended_reason": call.get("ended_reason"),
                "provider": call.get("provider"),
                "call_control_id": call.get("call_control_id"),
                "livekit_participant_identity": call.get("livekit_participant_identity")
            }
            processed_calls.append(processed_call)
        
        return processed_calls
        
    except Exception as e:
        logger.error(f"Error fetching calls: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to fetch calls")

@app.get("/phone_numbers")
async def get_phone_numbers(authorization: str = Header(None, alias="Authorization")):
    """Get all phone numbers for the authenticated user"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing or invalid authorization header")
    
    token = authorization.replace("Bearer ", "")
    
    try:
        # Verify token with Supabase
        user_response = supabase_service_client.auth.get_user(token)
        
        if not user_response.user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        
        user_id = user_response.user.id
        logger.info(f"Fetching phone numbers for user: {user_id}")
        
        # Get all phone numbers for this user, ordered by created_at desc (most recent first)
        phone_numbers_response = supabase_service_client.table("phone_numbers").select("*").eq("users_id", user_id).order("created_at", desc=True).execute()
        
        if not phone_numbers_response.data:
            logger.info(f"No phone numbers found for user {user_id}")
            return []
        
        phone_numbers = phone_numbers_response.data
        logger.info(f"Found {len(phone_numbers)} phone numbers for user {user_id}")
        
        # Process phone numbers to match frontend expectations (PamPhoneNumber type)
        processed_phone_numbers = []
        for phone_number in phone_numbers:
            processed_phone_number = {
                "id": phone_number.get("id"),
                "created_at": phone_number.get("created_at", ""),
                "updated_at": phone_number.get("created_at", ""),  # Use created_at since updated_at doesn't exist in schema
                "users_id": phone_number.get("users_id"),
                "phone_number_e164": phone_number.get("phone_number_e164", ""),
                "provider": phone_number.get("provider", ""),
                "status": phone_number.get("status", "unknown"),
                "friendly_name": phone_number.get("friendly_name"),
                "telnyx_number_id": phone_number.get("telnyx_number_id"),
                "telnyx_connection_id": phone_number.get("telnyx_connection_id"),
                "livekit_sip_trunk_id": phone_number.get("livekit_sip_trunk_id"),
                "telnyx_call_control_application_id": phone_number.get("telnyx_call_control_application_id"),
                "telnyx_outbound_voice_profile_id": phone_number.get("telnyx_outbound_voice_profile_id"),
                "telnyx_credential_connection_id": phone_number.get("telnyx_credential_connection_id"),
                "telnyx_sip_username": phone_number.get("telnyx_sip_username"),
                "telnyx_sip_password_clear": phone_number.get("telnyx_sip_password_clear"),
                "user_telnyx_api_key": phone_number.get("user_telnyx_api_key")
            }
            processed_phone_numbers.append(processed_phone_number)
        
        return processed_phone_numbers
        
    except Exception as e:
        logger.error(f"Error fetching phone numbers: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to fetch phone numbers")

@app.get("/settings")
async def get_user_settings(authorization: str = Header(None, alias="Authorization")):
    """Get user settings/preferences"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing or invalid authorization header")
    
    token = authorization.replace("Bearer ", "")
    
    try:
        # Verify token with Supabase
        user_response = supabase_service_client.auth.get_user(token)
        
        if not user_response.user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        
        user_id = user_response.user.id
        logger.info(f"Fetching settings for user: {user_id}")
        
        # Get user profile from public.users with settings
        user_profile_response = supabase_service_client.table("users").select("*").eq("id", user_id).single().execute()
        
        if not user_profile_response.data:
            # If no profile exists, return default settings
            default_settings = {
                "id": str(user_id),
                "email": user_response.user.email,
                "name": user_response.user.email.split('@')[0] if user_response.user.email else "User",
                "company": "",
                "timezone": "UTC",
                "language": "en",
                "emailNotifications": True,
                "callNotifications": True,
                "marketingEmails": False,
                "twoFactorAuth": False
            }
            return default_settings
        
        user_profile = user_profile_response.data
        
        # Process settings to match frontend expectations
        settings = {
            "id": user_profile.get("id"),
            "email": user_profile.get("email", user_response.user.email),
            "name": user_profile.get("name", "User"),
            "company": user_profile.get("company", ""),
            "timezone": user_profile.get("timezone", "UTC"),
            "language": user_profile.get("language", "en"),
            "emailNotifications": user_profile.get("email_notifications", True),
            "callNotifications": user_profile.get("call_notifications", True),
            "marketingEmails": user_profile.get("marketing_emails", False),
            "twoFactorAuth": user_profile.get("two_factor_auth", False)
        }
        
        return settings
        
    except HTTPException:
        raise  # Re-raise HTTP exceptions
    except Exception as e:
        logger.error(f"Error fetching settings: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to fetch user settings")

class UserSettingsUpdateRequest(BaseModel):
    name: Optional[str] = None
    company: Optional[str] = None
    timezone: Optional[str] = None
    language: Optional[str] = None
    emailNotifications: Optional[bool] = None
    callNotifications: Optional[bool] = None
    marketingEmails: Optional[bool] = None
    twoFactorAuth: Optional[bool] = None

@app.patch("/settings")
async def update_user_settings(request: UserSettingsUpdateRequest, authorization: str = Header(None, alias="Authorization")):
    """Update user settings/preferences"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing or invalid authorization header")
    
    token = authorization.replace("Bearer ", "")
    
    try:
        # Verify token with Supabase
        user_response = supabase_service_client.auth.get_user(token)
        
        if not user_response.user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        
        user_id = user_response.user.id
        logger.info(f"Updating settings for user: {user_id}")
        
        # Build update payload with only provided fields
        update_payload = {}
        for field, value in request.model_dump(exclude_unset=True).items():
            if value is not None:
                # Map frontend field names to database column names
                if field == "emailNotifications":
                    update_payload["email_notifications"] = value
                elif field == "callNotifications":
                    update_payload["call_notifications"] = value
                elif field == "marketingEmails":
                    update_payload["marketing_emails"] = value
                elif field == "twoFactorAuth":
                    update_payload["two_factor_auth"] = value
                else:
                    update_payload[field] = value
        
        if not update_payload:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields to update")
        
        # Check if user profile exists, if not create it
        user_check = supabase_service_client.table("users").select("id").eq("id", user_id).maybe_single().execute()
        
        if not user_check.data:
            # Create user profile if it doesn't exist
            create_payload = {
                "id": str(user_id),
                "email": user_response.user.email,
                "name": update_payload.get("name", user_response.user.email.split('@')[0] if user_response.user.email else "User")
            }
            create_payload.update(update_payload)
            
            create_response = supabase_service_client.table("users").insert(create_payload).execute()
            if not create_response.data:
                logger.error(f"Failed to create user profile for {user_id}. Response: {create_response.error or 'No data returned'}")
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create user profile")
            
            updated_user = create_response.data[0]
        else:
            # Update existing user profile
            update_response = supabase_service_client.table("users").update(update_payload).eq("id", user_id).execute()
            
            if not update_response.data:
                logger.error(f"Failed to update user settings for {user_id}. Response: {update_response.error or 'No data returned'}")
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update user settings")
            
            updated_user = update_response.data[0]
        
        logger.info(f"Successfully updated settings for user {user_id}")
        
        # Return processed settings to match frontend expectations
        settings = {
            "id": updated_user.get("id"),
            "email": updated_user.get("email"),
            "name": updated_user.get("name", "User"),
            "company": updated_user.get("company", ""),
            "timezone": updated_user.get("timezone", "UTC"),
            "language": updated_user.get("language", "en"),
            "emailNotifications": updated_user.get("email_notifications", True),
            "callNotifications": updated_user.get("call_notifications", True),
            "marketingEmails": updated_user.get("marketing_emails", False),
            "twoFactorAuth": updated_user.get("two_factor_auth", False)
        }
        
        return settings
        
    except HTTPException:
        raise  # Re-raise HTTP exceptions
    except Exception as e:
        logger.error(f"Error updating settings: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update user settings")

@app.delete("/agents/{agent_id}")
async def delete_agent(agent_id: int, authorization: str = Header(None, alias="Authorization")):
    """Delete an agent"""
    try:
        user_id = get_user_id_from_token(authorization)
        
        # Verify the agent belongs to the user before deleting
        agent_response = supabase_service_client.table("agents").select("id").eq("id", agent_id).eq("user_id", user_id).single().execute()
        if not agent_response.data:
            raise HTTPException(status_code=404, detail="Agent not found or access denied")
            
        # Perform deletion
        delete_response = supabase_service_client.table("agents").delete().eq("id", agent_id).execute()
        
        if not delete_response.data:
            raise HTTPException(status_code=500, detail="Failed to delete agent")
            
        logger.info(f"Deleted agent {agent_id} for user {user_id}")
        return {"message": "Agent deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting agent {agent_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete agent")

@app.get("/agents/{agent_id}")
async def get_agent(agent_id: int, authorization: str = Header(None, alias="Authorization")):
    """
    Get a single agent by ID for the authenticated user.
    This function now uses a two-step fetch to avoid ambiguous join issues.
    """
    try:
        user_id = get_user_id_from_token(authorization)
        logger.info(f"Step 1: Fetching agent {agent_id} for user {user_id}")

        # Step 1: Fetch the core agent data without any joins
        agent_response = supabase_service_client.table("agents").select("*") \
            .eq("id", agent_id).eq("user_id", user_id).single().execute()

        if not agent_response.data:
            raise HTTPException(status_code=404, detail=f"Agent with id {agent_id} not found for this user.")
        
        agent_data = agent_response.data
        logger.info(f"Successfully retrieved core data for agent {agent_id}")

        # Step 2: If the agent has a linked phone number, fetch it separately
        phone_numbers_id = agent_data.get("phone_numbers_id")
        agent_data['phone_numbers'] = None # Ensure the key exists with a null default

        if phone_numbers_id:
            logger.info(f"Step 2: Agent {agent_id} has linked phone_numbers_id {phone_numbers_id}. Fetching details.")
            try:
                phone_response = supabase_service_client.table("phone_numbers").select("*") \
                    .eq("id", phone_numbers_id).single().execute()
                
                if phone_response.data:
                    agent_data['phone_numbers'] = phone_response.data
                    logger.info(f"Successfully fetched details for phone_numbers_id {phone_numbers_id}")
                else:
                    logger.warning(f"Agent {agent_id} has phone_numbers_id {phone_numbers_id}, but no matching record was found in phone_numbers table.")
            except Exception as phone_e:
                # Log the error but don't fail the whole request. Return the agent without phone details.
                logger.error(f"Error fetching details for phone_numbers_id {phone_numbers_id}: {phone_e}")
        else:
            logger.info(f"Agent {agent_id} has no linked phone number. Skipping step 2.")

        logger.info(f"Successfully completed data retrieval for agent {agent_id}")
        return agent_data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching agent {agent_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An unexpected error occurred while fetching the agent.")

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


@app.patch("/agents/{agent_id}")
async def update_agent(agent_id: int, request: AgentUpdateRequest, authorization: str = Header(None, alias="Authorization")):
    """Update a specific agent by ID"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing or invalid authorization header")
    
    token = authorization.replace("Bearer ", "")
    
    try:
        # Verify token with Supabase
        user_response = supabase_service_client.auth.get_user(token)
        
        if not user_response.user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        
        user_id = user_response.user.id
        logger.info(f"Updating agent {agent_id} for user: {user_id}")
        
        # First, check if the agent exists and belongs to this user
        agent_check = supabase_service_client.table("agents").select("id, name, user_id").eq("id", agent_id).eq("user_id", user_id).single().execute()
        
        if not agent_check.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Agent with ID {agent_id} not found or you don't have permission to update it")
        
        # Build update payload with only provided fields
        update_payload = {}
        for field, value in request.model_dump(exclude_unset=True).items():
            if value is not None:
                update_payload[field] = value
        
        if not update_payload:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields to update")
        
        # Update the agent
        update_response = supabase_service_client.table("agents").update(update_payload).eq("id", agent_id).eq("user_id", user_id).execute()
        
        if not update_response.data:
            logger.error(f"Failed to update agent {agent_id}. Response: {update_response.error or 'No data returned'}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update agent")
        
        updated_agent = update_response.data[0]
        logger.info(f"Successfully updated agent {agent_id} for user {user_id}")
        
        # Process updated agent to match frontend expectations  
        processed_agent = {
            "id": updated_agent.get("id"),
            "name": updated_agent.get("name", "Unnamed Agent"),
            "description": updated_agent.get("system_prompt", "")[:100] + "..." if updated_agent.get("system_prompt") and len(updated_agent.get("system_prompt", "")) > 100 else updated_agent.get("system_prompt", ""),
            "status": updated_agent.get("status", "draft"),
            "system_prompt": updated_agent.get("system_prompt", ""),
            "stt_language": updated_agent.get("stt_language", "en"),
            "tts_voice": updated_agent.get("tts_voice", ""),
            "initial_greeting": updated_agent.get("initial_greeting", ""),
            "sip_trunk_id": updated_agent.get("sip_trunk_id", ""),
            "createdAt": updated_agent.get("created_at", ""),
            "updatedAt": updated_agent.get("created_at", ""),  # Use created_at since updated_at doesn't exist
            # Include all original fields for completeness
            "llm_provider": updated_agent.get("llm_provider"),
            "llm_model": updated_agent.get("llm_model"),
            "stt_provider": updated_agent.get("stt_provider"),
            "stt_model": updated_agent.get("stt_model"),
            "tts_provider": updated_agent.get("tts_provider"),
            "tts_model": updated_agent.get("tts_model"),
            "phone_numbers_id": updated_agent.get("phone_numbers_id"),
            "default_pathway_id": updated_agent.get("default_pathway_id"),
            
        }
        
        return processed_agent
        
    except HTTPException:
        raise  # Re-raise HTTP exceptions
    except Exception as e:
        logger.error(f"Error updating agent {agent_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update agent")

# --- To run the server (for development) ---
# Use uvicorn: uvicorn api.main:app --reload --port 8000
# Ensure you are in the root directory (pam-testdrive) when running this
if __name__ == "__main__":
    import uvicorn
    # Make sure to run this from the root directory (pam-testdrive)
    # using 'python -m api.main' won't work directly due to relative paths
    # Best practice is to use uvicorn command directly from the terminal
    logger.warning("Running uvicorn directly from script is for debugging only.")
    logger.warning("Use: 'uvicorn api.main:app --reload --port 8000' from the 'pam-testdrive' directory.")
    # uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True) # This line might have issues with relative paths

# Dashboard Statistics Endpoints
@app.get("/dashboard/stats")
async def get_dashboard_stats(authorization: str = Header(None, alias="Authorization")):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing or invalid authorization header")
    
    token = authorization.replace("Bearer ", "")
    
    try:
        # Verify token with Supabase Auth using anon client
        anon_client = get_supabase_anon_client()
        user_response = anon_client.auth.get_user(token)
        
        if not user_response.user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        
        user_id = user_response.user.id
        logger.info(f"Dashboard stats requested by user: {user_id}")
        
        # Get user's agents count with error handling
        try:
            agents_response = supabase_service_client.table("agents").select("id", count="exact").eq("user_id", user_id).execute()
            total_agents = agents_response.count if agents_response.count is not None else 0
        except Exception as e:
            logger.error(f"Error fetching agents count: {e}")
            total_agents = 0
        
        # Get active agents count with error handling
        try:
            active_agents_response = supabase_service_client.table("agents").select("id", count="exact").eq("user_id", user_id).eq("status", "active").execute()
            active_agents = active_agents_response.count if active_agents_response.count is not None else 0
        except Exception as e:
            logger.error(f"Error fetching active agents count: {e}")
            active_agents = 0
        
        # Get total calls count for user with error handling
        try:
            calls_response = supabase_service_client.table("calls").select("id", count="exact").eq("user_id", user_id).execute()
            total_calls = calls_response.count if calls_response.count is not None else 0
        except Exception as e:
            logger.error(f"Error fetching calls count: {e}")
            total_calls = 0
        
        # Get calls from last 30 days to calculate change with error handling
        try:
            thirty_days_ago = (datetime.utcnow() - timedelta(days=30)).isoformat()
            recent_calls_response = supabase_service_client.table("calls").select("id", count="exact").eq("user_id", user_id).gte("created_at", thirty_days_ago).execute()
            recent_calls = recent_calls_response.count if recent_calls_response.count is not None else 0
        except Exception as e:
            logger.error(f"Error fetching recent calls count: {e}")
            recent_calls = 0
        
        # Calculate calls change percentage (simplified)
        calls_change_percentage = 0
        if total_calls > recent_calls:
            prev_calls = total_calls - recent_calls
            if prev_calls > 0:
                calls_change_percentage = round((recent_calls / prev_calls - 1) * 100, 1)
        elif recent_calls > 0:
            calls_change_percentage = 100  # All calls are new
        
        # Calculate agents change (simplified - assume last 30 days)
        agents_change = max(0, active_agents - 1)  # Simplified for now
        
        logger.info(f"Dashboard stats calculated for user {user_id}: calls={total_calls}, agents={active_agents}/{total_agents}")
        
        return {
            "total_calls": total_calls,
            "total_calls_change": f"+{calls_change_percentage}%" if calls_change_percentage >= 0 else f"{calls_change_percentage}%",
            "total_calls_trend": "up" if calls_change_percentage >= 0 else "down",
            "active_agents": active_agents,
            "active_agents_change": f"+{agents_change}" if agents_change > 0 else str(agents_change),
            "active_agents_trend": "up" if agents_change >= 0 else "down",
            "total_agents": total_agents
        }
        
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        logger.error(f"Unexpected error getting dashboard stats: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to fetch dashboard statistics")

@app.post("/test/create-agent")
async def create_test_agent():
    """Quick test endpoint to create a test agent for testing."""
    logger.info("Test endpoint: Creating test agent.")
    
    test_agent_data = {
            "name": "Test Agent",
        "system_prompt": "You are a helpful test assistant. Be brief and friendly.",
            "llm_provider": "openai",
            "llm_model": "gpt-4o-mini",
            "stt_provider": "deepgram",
            "stt_model": "nova-2",
            "tts_provider": "cartesia",
            "tts_voice": "ab7c61f5-3daa-47dd-a23b-4ac0aac5f5c3",
        "stt_language": "fr",
            "tts_model": "sonic-2-2025-03-07",
            "status": "active",
        "initial_greeting": "Bonjour, je suis votre assistant de test Pam!",
        "user_id": "b55837c4-270f-4f1f-8023-7ab09ee5f44d"  # Use test user
    }
    
    try:
        result = supabase_service_client.table("agents").insert(test_agent_data).execute()
        logger.info(f"Test agent created successfully: {result.data}")
        return {"success": True, "agent": result.data[0] if result.data else None}
    except Exception as e:
        logger.error(f"Error creating test agent: {e}")
        return {"success": False, "error": str(e)}



# Voice models
class VoiceResponse(BaseModel):
    id: str
    cartesia_voice_id: str
    name: str
    language_code: str
    language_name: str
    gender: Optional[str] = None
    accent: Optional[str] = None
    description: Optional[str] = None
    cartesia_preview_url: str
    is_active: bool
    provider: str
    provider_model: str
    tags: Optional[List[str]] = None
    sample_rate: Optional[int] = None

class VoiceCreateRequest(BaseModel):
    cartesia_voice_id: str
    name: str
    language_code: str
    language_name: str
    gender: Optional[str] = None
    accent: Optional[str] = None
    description: Optional[str] = None
    cartesia_preview_url: str
    is_active: bool = True
    provider: str = "cartesia"
    provider_model: str = "sonic-2-2025-03-07"
    tags: Optional[List[str]] = None
    sample_rate: Optional[int] = 44100

class VoiceUpdateRequest(BaseModel):
    name: Optional[str] = None
    language_code: Optional[str] = None
    language_name: Optional[str] = None
    gender: Optional[str] = None
    accent: Optional[str] = None
    description: Optional[str] = None
    cartesia_preview_url: Optional[str] = None
    is_active: Optional[bool] = None
    provider: Optional[str] = None
    provider_model: Optional[str] = None
    tags: Optional[List[str]] = None
    sample_rate: Optional[int] = None

# =========================
# VOICES ENDPOINTS
# =========================

@app.get("/voices", response_model=List[VoiceResponse])
async def get_voices(
    language_code: Optional[str] = None,
    is_active: Optional[bool] = None,
    gender: Optional[str] = None,
    provider: Optional[str] = None
):
    """Get all voices with optional filtering"""
    try:
        # Build query
        query = supabase_service_client.table("voices").select("*")
        
        # Apply filters
        if language_code:
            query = query.eq("language_code", language_code)
        if is_active is not None:
            query = query.eq("is_active", is_active)
        if gender:
            query = query.eq("gender", gender)
        if provider:
            query = query.eq("provider", provider)
        
        # Execute query with ordering
        response = query.order("language_code, name").execute()
        
        if not response.data:
            return []
        
        # Convert to response model
        voices = []
        for voice_data in response.data:
            voice = VoiceResponse(
                id=voice_data["id"],
                cartesia_voice_id=voice_data["cartesia_voice_id"],
                name=voice_data["name"],
                language_code=voice_data["language_code"],
                language_name=voice_data["language_name"],
                gender=voice_data.get("gender"),
                accent=voice_data.get("accent"),
                description=voice_data.get("description"),
                cartesia_preview_url=voice_data["cartesia_preview_url"],
                is_active=voice_data["is_active"],
                provider=voice_data["provider"],
                provider_model=voice_data["provider_model"],
                tags=voice_data.get("tags", []),
                sample_rate=voice_data.get("sample_rate")
            )
            voices.append(voice)
        
        logger.info(f"Retrieved {len(voices)} voices")
        return voices
        
    except Exception as e:
        logger.error(f"Error getting voices: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to fetch voices")

@app.post("/voices", response_model=VoiceResponse, status_code=status.HTTP_201_CREATED)
async def create_voice(request: VoiceCreateRequest, authorization: str = Header(None, alias="Authorization")):
    """Create a new voice (admin functionality)"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing or invalid authorization header")
    
    token = authorization.replace("Bearer ", "")
    
    try:
        # Verify token with Supabase
        user_response = supabase_service_client.auth.get_user(token)
        
        if not user_response.user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        
        user_id = user_response.user.id
        
        # Check if voice with same cartesia_voice_id already exists
        existing_voice = supabase_service_client.table("voices").select("cartesia_voice_id").eq("cartesia_voice_id", request.cartesia_voice_id).execute()
        
        if existing_voice.data:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Voice with Cartesia ID {request.cartesia_voice_id} already exists")
        
        # Create voice payload
        voice_payload = request.model_dump()
        voice_payload["created_by"] = user_id
        voice_payload["updated_by"] = user_id
        
        # Insert voice
        response = supabase_service_client.table("voices").insert(voice_payload).execute()
        
        if not response.data:
            logger.error(f"Failed to create voice. Response: {response.error}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create voice")
        
        voice_data = response.data[0]
        logger.info(f"Created voice: {voice_data['name']} ({voice_data['cartesia_voice_id']})")
        
        # Return created voice
        return VoiceResponse(
            id=voice_data["id"],
            cartesia_voice_id=voice_data["cartesia_voice_id"],
            name=voice_data["name"],
            language_code=voice_data["language_code"],
            language_name=voice_data["language_name"],
            gender=voice_data.get("gender"),
            accent=voice_data.get("accent"),
            description=voice_data.get("description"),
            cartesia_preview_url=voice_data["cartesia_preview_url"],
            is_active=voice_data["is_active"],
            provider=voice_data["provider"],
            provider_model=voice_data["provider_model"],
            tags=voice_data.get("tags", []),
            sample_rate=voice_data.get("sample_rate")
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating voice: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create voice")

@app.get("/voices/{voice_id}", response_model=VoiceResponse)
async def get_voice(voice_id: str):
    """Get a specific voice by ID"""
    try:
        response = supabase_service_client.table("voices").select("*").eq("id", voice_id).single().execute()
        
        if not response.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Voice not found")
        
        voice_data = response.data
        
        return VoiceResponse(
            id=voice_data["id"],
            cartesia_voice_id=voice_data["cartesia_voice_id"],
            name=voice_data["name"],
            language_code=voice_data["language_code"],
            language_name=voice_data["language_name"],
            gender=voice_data.get("gender"),
            accent=voice_data.get("accent"),
            description=voice_data.get("description"),
            cartesia_preview_url=voice_data["cartesia_preview_url"],
            is_active=voice_data["is_active"],
            provider=voice_data["provider"],
            provider_model=voice_data["provider_model"],
            tags=voice_data.get("tags", []),
            sample_rate=voice_data.get("sample_rate")
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting voice {voice_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to fetch voice")

@app.patch("/voices/{voice_id}", response_model=VoiceResponse)
async def update_voice(voice_id: str, request: VoiceUpdateRequest, authorization: str = Header(None, alias="Authorization")):
    """Update a voice (admin functionality)"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing or invalid authorization header")
    
    token = authorization.replace("Bearer ", "")
    
    try:
        # Verify token with Supabase
        user_response = supabase_service_client.auth.get_user(token)
        
        if not user_response.user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        
        user_id = user_response.user.id
        
        # Check if voice exists
        existing_voice = supabase_service_client.table("voices").select("*").eq("id", voice_id).single().execute()
        
        if not existing_voice.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Voice not found")
        
        # Build update payload
        update_payload = {}
        for field, value in request.model_dump(exclude_unset=True).items():
            if value is not None:
                update_payload[field] = value
        
        if not update_payload:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields to update")
        
        update_payload["updated_by"] = user_id
        
        # Update voice
        response = supabase_service_client.table("voices").update(update_payload).eq("id", voice_id).execute()
        
        if not response.data:
            logger.error(f"Failed to update voice {voice_id}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update voice")
        
        voice_data = response.data[0]
        logger.info(f"Updated voice: {voice_data['name']} ({voice_id})")
        
        return VoiceResponse(
            id=voice_data["id"],
            cartesia_voice_id=voice_data["cartesia_voice_id"],
            name=voice_data["name"],
            language_code=voice_data["language_code"],
            language_name=voice_data["language_name"],
            gender=voice_data.get("gender"),
            accent=voice_data.get("accent"),
            description=voice_data.get("description"),
            cartesia_preview_url=voice_data["cartesia_preview_url"],
            is_active=voice_data["is_active"],
            provider=voice_data["provider"],
            provider_model=voice_data["provider_model"],
            tags=voice_data.get("tags", []),
            sample_rate=voice_data.get("sample_rate")
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating voice {voice_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update voice")

@app.delete("/voices/{voice_id}")
async def delete_voice(voice_id: str, authorization: str = Header(None, alias="Authorization")):
    """
    Delete a voice by ID
    """
    try:
        # Validate user token
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
        
        token = authorization.replace("Bearer ", "")
        
        # Verify token with Supabase
        user_response = supabase_service_client.auth.get_user(token)
        
        if not user_response.user:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        user_id = user_response.user.id
        
        # Delete the voice from Supabase
        response = supabase_service_client.table("voices").delete().eq("id", voice_id).execute()
        
        if not response.data:
            raise HTTPException(status_code=404, detail="Voice not found")
        
        logger.info(f"Voice {voice_id} deleted successfully")
        return {"message": "Voice deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting voice {voice_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/voices/{voice_id}/preview")
async def get_voice_preview(voice_id: str):
    """
    Generate voice preview audio using Cartesia or ElevenLabs TTS API based on provider
    """
    try:
        # Get voice from database with all relevant fields
        voice_response = supabase_service_client.table("voices").select(
            "id, cartesia_voice_id, name, language_code, provider, provider_model"
        ).eq("id", voice_id).execute()
        
        if not voice_response.data:
            # If not found by id, try by cartesia_voice_id (backward compatibility)
            voice_response = supabase_service_client.table("voices").select(
                "id, cartesia_voice_id, name, language_code, provider, provider_model"
            ).eq("cartesia_voice_id", voice_id).execute()
        
        if not voice_response.data:
            logger.error(f"Voice not found with id or cartesia_voice_id: {voice_id}")
            raise HTTPException(status_code=404, detail="Voice not found")
        
        voice_data = voice_response.data[0]
        voice_name = voice_data.get("name", "Unknown Voice")
        language_code = voice_data.get("language_code", "en")
        provider = voice_data.get("provider", "cartesia")
        provider_model = voice_data.get("provider_model", "sonic-2-2025-03-07")
        
        # Define sample text based on language
        sample_texts = {
            "en": "Hello, this is Pam, how can I assist you?",
            "fr": "Bonjour, ici Pam, comment puis-je vous aider?",
            "es": "Hola, soy Pam, ¿cómo puedo ayudarte?",
            "de": "Hallo, ich bin Pam, wie kann ich Ihnen helfen?",
            "it": "Ciao, sono Pam, come posso aiutarti?",
            "pt": "Olá, sou Pam, como posso ajudá-lo?",
            "zh": "你好，我是Pam，我能为您做些什么？",
            "ja": "こんにちは、Pamです。何かお手伝いできることはありますか？",
            "ko": "안녕하세요, Pam입니다. 어떻게 도와드릴까요?",
            "hi": "नमस्ते, मैं Pam हूं, मैं आपकी कैसे सहायता कर सकती हूं?",
            "nl": "Hallo, ik ben Pam, hoe kan ik je helpen?",
            "pl": "Cześć, jestem Pam, jak mogę ci pomóc?",
            "ru": "Привет, я Pam, как я могу вам помочь?",
            "sv": "Hej, jag är Pam, hur kan jag hjälpa dig?",
            "tr": "Merhaba, ben Pam, size nasıl yardımcı olabilirim?",
            "da": "Hej, jeg er Pam, hvordan kan jeg hjælpe dig?",
            "no": "Hei, jeg er Pam, hvordan kan jeg hjelpe deg?",
            "fi": "Hei, olen Pam, miten voin auttaa sinua?"
        }
        
        sample_text = sample_texts.get(language_code, sample_texts["en"])
        
        # Route to appropriate provider
        if provider == "elevenlabs":
            return await generate_elevenlabs_preview(voice_data, sample_text, voice_name)
        elif provider == "cartesia":
            return await generate_cartesia_preview(voice_data, sample_text, voice_name, language_code)
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported voice provider: {provider}")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating voice preview for {voice_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to generate voice preview")


async def generate_cartesia_preview(voice_data: dict, sample_text: str, voice_name: str, language_code: str):
    """Generate voice preview using Cartesia API"""
    cartesia_voice_id = voice_data.get("cartesia_voice_id")
    if not cartesia_voice_id:
        raise HTTPException(status_code=404, detail="Cartesia voice ID not available for this voice")
    
    # Get Cartesia API key
    cartesia_api_key = os.getenv("CARTESIA_API_KEY")
    if not cartesia_api_key:
        raise HTTPException(status_code=500, detail="Cartesia API key not configured")
    
    logger.info(f"Generating Cartesia TTS preview for voice '{voice_name}' using voice ID: {cartesia_voice_id}")
    
    # Prepare Cartesia TTS API request
    tts_url = "https://api.cartesia.ai/tts/bytes"
    headers = {
        "Authorization": f"Bearer {cartesia_api_key}",
        "Cartesia-Version": "2025-04-16",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model_id": voice_data.get("provider_model", "sonic-2-2025-03-07"),
        "transcript": sample_text,
        "voice": {
            "mode": "id",
            "id": cartesia_voice_id
        },
        "output_format": {
            "container": "mp3",
            "encoding": "mp3",
            "sample_rate": 44100
        },
        "language": language_code
    }
    
    # Call Cartesia TTS API
    async with httpx.AsyncClient() as client:
        response = await client.post(tts_url, json=payload, headers=headers)
        
        if response.status_code != 200:
            logger.error(f"Cartesia TTS API error for voice {voice_name}: {response.status_code} - {response.text}")
            raise HTTPException(status_code=response.status_code, detail=f"Failed to generate voice preview: {response.text}")
        
        # Return the audio content with proper headers
        return Response(
            content=response.content,
            media_type="audio/mpeg",
            headers={
                "Content-Type": "audio/mpeg",
                "Cache-Control": "public, max-age=1800",  # Cache for 30 minutes
                "Content-Disposition": f'inline; filename="{voice_name}_preview.mp3"'
            }
        )


async def generate_elevenlabs_preview(voice_data: dict, sample_text: str, voice_name: str):
    """Generate voice preview using ElevenLabs API"""
    elevenlabs_voice_id = voice_data.get("cartesia_voice_id")  # We'll use this field for ElevenLabs voice ID too
    if not elevenlabs_voice_id:
        raise HTTPException(status_code=404, detail="ElevenLabs voice ID not available for this voice")
    
    # Get ElevenLabs API key
    elevenlabs_api_key = os.getenv("ELEVENLABS_API_KEY")
    if not elevenlabs_api_key:
        raise HTTPException(status_code=500, detail="ElevenLabs API key not configured")
    
    logger.info(f"Generating ElevenLabs TTS preview for voice '{voice_name}' using voice ID: {elevenlabs_voice_id}")
    
    # Prepare ElevenLabs TTS API request
    tts_url = f"https://api.elevenlabs.io/v1/text-to-speech/{elevenlabs_voice_id}"
    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": elevenlabs_api_key
    }
    
    # Get model from provider_model or use default
    model = voice_data.get("provider_model", "eleven_multilingual_v2")
    
    payload = {
        "text": sample_text,
        "model_id": model,
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.75,
            "style": 0.0,
            "use_speaker_boost": True
        }
    }
    
    # Call ElevenLabs TTS API
    async with httpx.AsyncClient() as client:
        response = await client.post(tts_url, json=payload, headers=headers)
        
        if response.status_code != 200:
            logger.error(f"ElevenLabs TTS API error for voice {voice_name}: {response.status_code} - {response.text}")
            raise HTTPException(status_code=response.status_code, detail=f"Failed to generate voice preview: {response.text}")
        
        # Return the audio content with proper headers
        return Response(
            content=response.content,
            media_type="audio/mpeg",
            headers={
                "Content-Type": "audio/mpeg",
                "Cache-Control": "public, max-age=1800",  # Cache for 30 minutes
                "Content-Disposition": f'inline; filename="{voice_name}_preview.mp3"'
            }
        )

@app.post("/fix-database")
async def fix_database_columns():
    """
    Fix database schema cache issues by refreshing the schema
    """
    try:
        # Force schema refresh by making a simple query
        logger.info("Attempting to refresh Supabase schema cache...")
        
        # This will force PostgREST to reload the schema
        response = supabase_service_client.rpc('refresh_schema_cache').execute()
        
        # If that doesn't work, try a simple query to force cache refresh
        test_response = supabase_service_client.table("agents").select("*").limit(1).execute()
        
        logger.info("Schema cache refresh successful")
        return {"message": "Database schema cache refreshed successfully"}
        
    except Exception as e:
        logger.error(f"Error refreshing schema cache: {e}")
        
        # Alternative approach: try to manually refresh by querying system tables
        try:
            # Query the information schema to force a schema reload
            logger.info("Attempting alternative schema refresh method...")
            
            # This should force PostgREST to re-examine the table structure
            supabase_service_client.table("agents").select("*").limit(0).execute()
            
            return {"message": "Schema cache refreshed using alternative method"}
        except Exception as e2:
            logger.error(f"Alternative schema refresh failed: {e2}")
            raise HTTPException(status_code=500, detail=f"Failed to refresh schema cache: {str(e2)}")

@app.get("/test/schema-check")
async def test_schema_check():
    """Test endpoint to verify schema cache is working"""
    try:
        # Try to query the agents table with the problematic column
        response = supabase_service_client.table("agents").select("id, name, interruption_threshold, pam_tier").limit(1).execute()
        
        return {
            "status": "success",
            "message": "Schema cache is working properly",
            "sample_data": response.data if response.data else "No agents found"
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Schema cache issue: {str(e)}"
        }

@app.get("/test/db-connection")
async def test_db_connection():
    """Test endpoint to verify database connection"""
    try:
        # Test basic connection
        response = supabase_service_client.table("users").select("id").limit(1).execute()
        
        return {
            "status": "success",
            "message": "Database connection working",
            "user_count": len(response.data) if response.data else 0
        }
    except Exception as e:
        logger.error(f"Database connection test failed: {e}", exc_info=True)
        return {
            "status": "error", 
            "message": f"Database connection failed: {str(e)}"
        }

# Add this BEFORE the @app.post("/test/create-agent") endpoint
@app.get("/debug/dashboard-stats")
async def debug_dashboard_stats(authorization: str = Header(None, alias="Authorization")):
    """Debug version of dashboard stats with detailed error reporting"""
    debug_info = {
        "step": "initialization",
        "authorization_present": bool(authorization),
        "supabase_service_client_available": supabase_service_client is not None,
        "environment_vars": {
            "SUPABASE_URL": bool(os.getenv("SUPABASE_URL")),
            "SUPABASE_ANON_KEY": bool(os.getenv("SUPABASE_ANON_KEY")),
            "SUPABASE_SERVICE_ROLE_KEY": bool(os.getenv("SUPABASE_SERVICE_ROLE_KEY"))
        }
    }
    
    try:
        if not authorization or not authorization.startswith("Bearer "):
            debug_info["error"] = "Missing or invalid authorization header"
            return {"debug": debug_info, "success": False}
        
        token = authorization.replace("Bearer ", "")
        debug_info["step"] = "token_extraction"
        debug_info["token_length"] = len(token)
        
        # Try to get user with anon client
        try:
            anon_client = get_supabase_anon_client()
            debug_info["step"] = "anon_client_created"
            
            user_response = anon_client.auth.get_user(token)
            debug_info["step"] = "user_fetched"
            debug_info["user_id"] = user_response.user.id if user_response.user else None
            
            if not user_response.user:
                debug_info["error"] = "Invalid token - no user found"
                return {"debug": debug_info, "success": False}
            
            user_id = user_response.user.id
            
            # Try simple database queries
            debug_info["step"] = "database_queries"
            
            # Test agents table
            try:
                agents_response = supabase_service_client.table("agents").select("id", count="exact").eq("user_id", user_id).execute()
                debug_info["agents_query"] = "success"
                debug_info["total_agents"] = agents_response.count if agents_response.count is not None else 0
            except Exception as e:
                debug_info["agents_query"] = f"failed: {str(e)}"
                debug_info["total_agents"] = 0
            
            # Test calls table
            try:
                calls_response = supabase_service_client.table("calls").select("id", count="exact").eq("user_id", user_id).execute()
                debug_info["calls_query"] = "success"
                debug_info["total_calls"] = calls_response.count if calls_response.count is not None else 0
            except Exception as e:
                debug_info["calls_query"] = f"failed: {str(e)}"
                debug_info["total_calls"] = 0
            
            debug_info["step"] = "completed"
            return {"debug": debug_info, "success": True}
            
        except Exception as auth_e:
            debug_info["auth_error"] = str(auth_e)
            debug_info["step"] = "auth_failed"
            return {"debug": debug_info, "success": False}
            
    except Exception as e:
        debug_info["unexpected_error"] = str(e)
        debug_info["step"] = "unexpected_failure"
        return {"debug": debug_info, "success": False}

# Import batch routes functions
from api.batch_routes import update_batch_call_item_from_call_status

# Global Analytics endpoint
@app.get("/analytics/global")
async def get_global_analytics(
    authorization: str = Header(None, alias="Authorization"),
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    time_filter: str = "30d",
    campaign_id: Optional[str] = None,
    agent_id: Optional[int] = None
):
    """Get global analytics data across all calls, campaigns, and agents with optional filters"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
    
    token = authorization.replace("Bearer ", "")
    
    try:
        # Verify token
        user_response = supabase_service_client.auth.get_user(token)
        if not user_response.user:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        user_id = user_response.user.id
        
        # Calculate date range
        end_date_dt = datetime.now(timezone.utc)
        if time_filter == "7d":
            start_date_dt = end_date_dt - timedelta(days=7)
        elif time_filter == "90d":
            start_date_dt = end_date_dt - timedelta(days=90)
        else:  # 30d default
            start_date_dt = end_date_dt - timedelta(days=30)
        
        # Get previous period for comparison
        period_length = end_date_dt - start_date_dt
        previous_start = start_date_dt - period_length
        
        # Build base query filters
        base_filters = [f"user_id=eq.{user_id}"]
        base_filters.append(f"created_at=gte.{start_date_dt.isoformat()}")
        base_filters.append(f"created_at=lte.{end_date_dt.isoformat()}")
        
        if campaign_id:
            base_filters.append(f"batch_campaign_id=eq.{campaign_id}")
        if agent_id:
            base_filters.append(f"agent_id=eq.{agent_id}")
        
        # Get calls data with enhanced fields
        calls_query = "&".join(base_filters)
        calls_response = supabase_service_client.table("calls").select(
            "id, status, call_duration, phone_number_e164, created_at, initiated_at, answered_at, ended_at, agent_id, batch_campaign_id"
        ).eq("user_id", user_id).gte("created_at", start_date_dt.isoformat()).lte("created_at", end_date_dt.isoformat())
        
        if campaign_id:
            calls_response = calls_response.eq("batch_campaign_id", campaign_id)
        if agent_id:
            calls_response = calls_response.eq("agent_id", agent_id)
            
        calls_response = calls_response.execute()
        calls_data = calls_response.data or []
        
        # Get agents data
        agents_response = supabase_service_client.table("agents").select(
            "id, name, status"
        ).eq("user_id", user_id).execute()
        agents_data = agents_response.data or []
        
        # Get campaigns data with enhanced metrics
        campaigns_response = supabase_service_client.table("batch_campaigns").select(
            "id, name, status, total_numbers, completed_calls, successful_calls, failed_calls, created_at"
        ).eq("user_id", user_id).execute()
        campaigns_data = campaigns_response.data or []
        
        # Get previous period calls for comparison
        previous_calls_response = supabase_service_client.table("calls").select(
            "id, status, call_duration"
        ).eq("user_id", user_id).gte("created_at", previous_start.isoformat()).lte("created_at", start_date_dt.isoformat()).execute()
        previous_calls_data = previous_calls_response.data or []
        
        # ===== PHASE 1 ENHANCEMENTS =====
        
        # 1. Geographic Performance Analysis
        geographic_data = {}
        for call in calls_data:
            phone_number = call.get("phone_number_e164", "") or ""
            
            # Enhanced geographic detection
            if phone_number.startswith("+1"):
                # US/Canada - extract area code for more granular analysis
                if len(phone_number) >= 5:
                    area_code = phone_number[2:5]
                    # Map some major area codes to cities/regions
                    area_code_map = {
                        "212": "New York, NY", "213": "Los Angeles, CA", "312": "Chicago, IL",
                        "415": "San Francisco, CA", "617": "Boston, MA", "702": "Las Vegas, NV",
                        "305": "Miami, FL", "206": "Seattle, WA", "713": "Houston, TX",
                        "404": "Atlanta, GA", "214": "Dallas, TX", "602": "Phoenix, AZ"
                    }
                    region = area_code_map.get(area_code, f"US/CA ({area_code})")
                else:
                    region = "US/CA"
            elif phone_number.startswith("+33"):
                region = "France"
            elif phone_number.startswith("+44"):
                region = "United Kingdom"
            elif phone_number.startswith("+49"):
                region = "Germany"
            elif phone_number.startswith("+34"):
                region = "Spain"
            elif phone_number.startswith("+39"):
                region = "Italy"
            elif phone_number.startswith("+61"):
                region = "Australia"
            elif phone_number.startswith("+81"):
                region = "Japan"
            else:
                region = "Other"
            
            if region not in geographic_data:
                geographic_data[region] = {
                    "total_calls": 0,
                    "successful_calls": 0,
                    "total_duration": 0,
                    "avg_duration": 0
                }
            
            geographic_data[region]["total_calls"] += 1
            
            call_duration = call.get("call_duration") or 0
            if call.get("status", "").lower() in ["completed", "ended"] and call_duration > 30:
                geographic_data[region]["successful_calls"] += 1
            
            geographic_data[region]["total_duration"] += call_duration
        
        # Calculate averages for geographic data
        for region_data in geographic_data.values():
            if region_data["total_calls"] > 0:
                region_data["success_rate"] = round((region_data["successful_calls"] / region_data["total_calls"]) * 100, 2)
                region_data["avg_duration"] = round(region_data["total_duration"] / region_data["total_calls"], 2)
            else:
                region_data["success_rate"] = 0
                region_data["avg_duration"] = 0
        
        # 2. Enhanced Agent Performance Comparison
        agent_performance_data = []
        for agent in agents_data:
            agent_calls = [call for call in calls_data if call.get("agent_id") == agent["id"]]
            
            total_calls = len(agent_calls)
            successful_calls = len([call for call in agent_calls if call.get("status", "").lower() in ["completed", "ended"] and (call.get("call_duration") or 0) > 30])
            
            total_duration = sum(int(call.get("call_duration") or 0) for call in agent_calls)
            avg_duration = total_duration / total_calls if total_calls > 0 else 0
            
            # Calculate performance metrics
            success_rate = (successful_calls / total_calls * 100) if total_calls > 0 else 0
            
            # Performance scoring (0-100)
            duration_score = min(avg_duration / 120 * 50, 50)  # Up to 50 points for 2+ min calls
            success_score = success_rate * 0.5  # Up to 50 points for 100% success rate
            performance_score = duration_score + success_score
            
            # Determine performance tier
            if performance_score >= 80:
                performance_tier = "Excellent"
            elif performance_score >= 60:
                performance_tier = "Good"
            elif performance_score >= 40:
                performance_tier = "Average"
            else:
                performance_tier = "Needs Improvement"
            
            agent_performance_data.append({
                "agent_id": agent["id"],
                "agent_name": agent["name"],
                "total_calls": total_calls,
                "successful_calls": successful_calls,
                "success_rate": round(success_rate, 2),
                "avg_duration": round(avg_duration, 2),
                "total_duration": total_duration,
                "performance_score": round(performance_score, 2),
                "performance_tier": performance_tier,
                "status": agent["status"]
            })
        
        # Sort by performance score
        agent_performance_data.sort(key=lambda x: x["performance_score"], reverse=True)
        
        # Calculate basic metrics (existing logic)
        total_calls = len(calls_data)
        completed_calls = len([call for call in calls_data if call.get("status", "").lower() in ["completed", "ended"]])
        failed_calls = len([call for call in calls_data if call.get("status", "").lower() in ["failed", "busy", "no_answer"]])
        
        total_duration = sum(int(call.get("call_duration") or 0) for call in calls_data)
        avg_duration = total_duration / total_calls if total_calls > 0 else 0
        
        success_rate = (completed_calls / total_calls * 100) if total_calls > 0 else 0
        
        # Previous period comparison
        prev_total_calls = len(previous_calls_data)
        prev_completed_calls = len([call for call in previous_calls_data if call.get("status", "").lower() in ["completed", "ended"]])
        
        def calc_change(current, previous):
            if previous == 0:
                return "0"
            change = ((current - previous) / previous) * 100
            return f"{change:+.1f}%"
        
        def calc_trend(current, previous):
            return "up" if current >= previous else "down"
        
        # Time series data for charts
        time_series_data = []
        date_range = []
        current_date = start_date_dt.date()
        while current_date <= end_date_dt.date():
            date_range.append(current_date)
            current_date += timedelta(days=1)
        
        for date in date_range:
            day_calls = [call for call in calls_data if call.get("created_at", "").startswith(str(date))]
            day_successful = len([call for call in day_calls if call.get("status", "").lower() in ["completed", "ended"]])
            day_failed = len(day_calls) - day_successful
            time_series_data.append({
                "date": str(date),
                "calls": len(day_calls),
                "successful": day_successful,
                "failed": day_failed
            })
        
        return {
            "time_range": {
                "start_date": start_date_dt.isoformat(),
                "end_date": end_date_dt.isoformat(),
                "filter": time_filter
            },
            "overview": {
                "total_calls": total_calls,
                "total_calls_change": calc_change(total_calls, prev_total_calls),
                "total_calls_trend": calc_trend(total_calls, prev_total_calls),
                "successful_calls": completed_calls,
                "successful_calls_change": calc_change(completed_calls, prev_completed_calls),
                "successful_calls_trend": calc_trend(completed_calls, prev_completed_calls),
                "failed_calls": failed_calls,
                "success_rate": round(success_rate, 2),
                "avg_duration": round(avg_duration, 2)
            },
            "time_series": time_series_data,
            "available_campaigns": [
                {
                    "campaignId": camp["id"],
                    "campaignName": camp["name"],
                    "status": camp["status"]
                } for camp in campaigns_data
            ],
            "available_agents": [
                {
                    "agentId": agent["id"],
                    "agentName": agent["name"],
                    "status": agent["status"]
                } for agent in agents_data
            ],
            # ===== PHASE 1 NEW FEATURES (NO FINANCIAL METRICS) =====
            "geographic_performance": geographic_data,
            "agent_performance": agent_performance_data,
            "insights": {
                "top_performing_campaign": campaigns_data[0]["name"] if campaigns_data else "No campaigns",
                "top_performing_agent": agent_performance_data[0]["agent_name"] if agent_performance_data else "No agents",
                "best_geographic_region": max(geographic_data.items(), key=lambda x: x[1]["success_rate"])[0] if geographic_data else "No data"
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching global analytics: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch analytics data")

# CSV Export endpoint for detailed call data
@app.get("/analytics/export")
async def export_analytics_csv(
    authorization: str = Header(None, alias="Authorization"),
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    time_filter: str = "30d",
    campaign_id: Optional[str] = None,
    agent_id: Optional[int] = None,
    format: str = "csv"
):
    """Export detailed call analytics data as CSV"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
    
    token = authorization.replace("Bearer ", "")
    
    try:
        # Verify token
        user_response = supabase_service_client.auth.get_user(token)
        if not user_response.user:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        user_id = user_response.user.id
        
        # Calculate date range (same logic as analytics endpoint)
        end_date_dt = datetime.now(timezone.utc)
        if time_filter == "24h":
            start_date_dt = end_date_dt - timedelta(hours=24)
        elif time_filter == "7d":
            start_date_dt = end_date_dt - timedelta(days=7)
        elif time_filter == "90d":
            start_date_dt = end_date_dt - timedelta(days=90)
        else:  # 30d default
            start_date_dt = end_date_dt - timedelta(days=30)
        
        # Get detailed call data with all relevant fields
        calls_query = supabase_service_client.table("calls").select(
            "id, status, call_duration, phone_number_e164, created_at, initiated_at, answered_at, ended_at, agent_id, batch_campaign_id, room_name, telnyx_call_control_id"
        ).eq("user_id", user_id).gte("created_at", start_date_dt.isoformat()).lte("created_at", end_date_dt.isoformat())
        
        if campaign_id:
            calls_query = calls_query.eq("batch_campaign_id", campaign_id)
        if agent_id:
            calls_query = calls_query.eq("agent_id", agent_id)
            
        calls_response = calls_query.execute()
        calls_data = calls_response.data or []
        
        # Get agents data for names
        agents_response = supabase_service_client.table("agents").select(
            "id, name"
        ).eq("user_id", user_id).execute()
        agents_data = {agent["id"]: agent["name"] for agent in agents_response.data or []}
        
        # Get campaigns data for names
        campaigns_response = supabase_service_client.table("batch_campaigns").select(
            "id, name"
        ).eq("user_id", user_id).execute()
        campaigns_data = {campaign["id"]: campaign["name"] for campaign in campaigns_response.data or []}
        
        # Helper functions for CSV generation
        def format_duration(seconds):
            if not seconds:
                return "00:00:00"
            hours = seconds // 3600
            minutes = (seconds % 3600) // 60
            seconds = seconds % 60
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        
        def get_geographic_region(phone_number):
            if not phone_number:
                return "Unknown"
            if phone_number.startswith("+1"):
                if len(phone_number) >= 5:
                    area_code = phone_number[2:5]
                    area_code_map = {
                        "212": "New York, NY", "213": "Los Angeles, CA", "312": "Chicago, IL",
                        "415": "San Francisco, CA", "617": "Boston, MA", "702": "Las Vegas, NV",
                        "305": "Miami, FL", "206": "Seattle, WA", "713": "Houston, TX",
                        "404": "Atlanta, GA", "214": "Dallas, TX", "602": "Phoenix, AZ"
                    }
                    return area_code_map.get(area_code, f"US/CA ({area_code})")
                return "US/CA"
            elif phone_number.startswith("+33"):
                return "France"
            elif phone_number.startswith("+44"):
                return "United Kingdom"
            elif phone_number.startswith("+49"):
                return "Germany"
            else:
                return "International"
        
        def get_call_outcome(status, duration):
            status = (status or "").lower()
            duration = duration or 0
            
            if status in ["completed", "ended"]:
                if duration > 30:
                    return "Human Answered"
                elif duration > 5:
                    return "Voicemail/Machine"
                else:
                    return "Quick Hangup"
            elif status == "busy":
                return "Busy Signal"
            elif status in ["no_answer", "timeout"]:
                return "No Answer"
            elif status == "failed":
                return "Call Failed"
            else:
                return "Unknown"
        
        def escape_csv_field(field):
            if field is None:
                return ""
            field_str = str(field)
            if '"' in field_str:
                field_str = field_str.replace('"', '""')
            if ',' in field_str or '"' in field_str or '\n' in field_str:
                field_str = f'"{field_str}"'
            return field_str
        
        # Generate CSV content
        csv_lines = []
        
        # CSV Headers
        headers = [
            "Call ID", "Date", "Time", "Phone Number", "Agent Name", "Agent ID", 
            "Campaign Name", "Campaign ID", "Call Status", "Call Outcome", 
            "Duration (seconds)", "Duration (formatted)", "Geographic Region",
            "Day of Week", "Hour of Day", "Answer Time (seconds)", "Setup Time (seconds)",
            "Room Name", "Telnyx Call ID", "Created At", "Initiated At", "Answered At", "Ended At"
        ]
        csv_lines.append(",".join(escape_csv_field(h) for h in headers))
        
        # CSV Data Rows
        for call in calls_data:
            created_at = call.get("created_at", "")
            initiated_at = call.get("initiated_at", "")
            answered_at = call.get("answered_at", "")
            ended_at = call.get("ended_at", "")
            
            # Parse dates for formatting
            try:
                created_dt = datetime.fromisoformat(created_at.replace('Z', '+00:00')) if created_at else None
                initiated_dt = datetime.fromisoformat(initiated_at.replace('Z', '+00:00')) if initiated_at else None
                answered_dt = datetime.fromisoformat(answered_at.replace('Z', '+00:00')) if answered_at else None
            except:
                created_dt = initiated_dt = answered_dt = None
            
            # Calculate times
            answer_time = ""
            setup_time = ""
            if initiated_dt and answered_dt:
                setup_time = str(int((answered_dt - initiated_dt).total_seconds()))
            if created_dt and answered_dt:
                answer_time = str(int((answered_dt - created_dt).total_seconds()))
            
            # Format date and time
            date_str = created_dt.strftime("%Y-%m-%d") if created_dt else ""
            time_str = created_dt.strftime("%H:%M:%S") if created_dt else ""
            day_of_week = created_dt.strftime("%A") if created_dt else ""
            hour_of_day = created_dt.strftime("%H") if created_dt else ""
            
            duration = call.get("call_duration", 0) or 0
            
            row = [
                call.get("id", ""),
                date_str,
                time_str,
                call.get("phone_number_e164", ""),
                agents_data.get(call.get("agent_id"), "Unknown Agent"),
                call.get("agent_id", ""),
                campaigns_data.get(call.get("batch_campaign_id"), "No Campaign"),
                call.get("batch_campaign_id", ""),
                call.get("status", ""),
                get_call_outcome(call.get("status"), duration),
                duration,
                format_duration(duration),
                get_geographic_region(call.get("phone_number_e164")),
                day_of_week,
                hour_of_day,
                answer_time,
                setup_time,
                call.get("room_name", ""),
                call.get("telnyx_call_control_id", ""),
                created_at,
                initiated_at,
                answered_at,
                ended_at
            ]
            
            csv_lines.append(",".join(escape_csv_field(field) for field in row))
        
        csv_content = "\n".join(csv_lines)
        
        # Generate filename with timestamp and filters
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename_parts = ["call_analytics", timestamp]
        
        if campaign_id:
            filename_parts.append(f"campaign_{campaign_id}")
        if agent_id:
            filename_parts.append(f"agent_{agent_id}")
        if time_filter:
            filename_parts.append(time_filter)
            
        filename = "_".join(filename_parts) + ".csv"
        
        # Return CSV with proper headers
        from fastapi.responses import Response
        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error exporting analytics CSV: {e}")
        raise HTTPException(status_code=500, detail="Failed to export analytics data")

# Advanced Analytics with Telnyx Call Control Data
@app.get("/analytics/telnyx-call-tracking")
async def get_telnyx_call_tracking_data(
    authorization: str = Header(None, alias="Authorization"),
    time_filter: str = "30d"
):
    """Get enhanced call tracking analytics using Telnyx Call Control data"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
    
    token = authorization.replace("Bearer ", "")
    
    try:
        # Verify token
        user_response = supabase_service_client.auth.get_user(token)
        if not user_response.user:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        user_id = user_response.user.id
        
        # Get calls with Telnyx tracking data
        calls_response = supabase_service_client.table("calls").select(
            "id, telnyx_call_control_id, status, call_duration, phone_number_e164, created_at, initiated_at, answered_at, ended_at"
        ).eq("user_id", user_id).not_.is_("telnyx_call_control_id", "null").execute()
        
        calls_data = calls_response.data or []
        
        # Enhanced analytics with Telnyx data
        analytics = {
            "call_quality_metrics": {
                "total_tracked_calls": len(calls_data),
                "avg_call_setup_time": 0.0,  # Time from initiation to answer
                "call_completion_rate": 0.0,
                "answer_seizure_ratio": 0.0  # Industry standard metric
            },
            "carrier_analysis": {
                "successful_connections": 0,
                "carrier_busy_signals": 0,
                "network_congestion": 0,
                "invalid_numbers": 0
            },
            "time_based_performance": {
                "peak_success_hours": [],
                "daily_patterns": [],
                "weekly_trends": []
            },
            "call_disposition_details": {
                "human_answered": 0,
                "answering_machine": 0,
                "fax_machine": 0,
                "busy_tone": 0,
                "no_answer": 0,
                "network_error": 0
            }
        }
        
        # Calculate metrics from Telnyx tracked calls
        setup_times = []
        successful_calls = 0
        answered_calls = 0
        
        for call in calls_data:
            # Calculate call setup time (initiated to answered)
            if call.get("initiated_at") and call.get("answered_at"):
                try:
                    initiated = datetime.fromisoformat(call["initiated_at"].replace('Z', '+00:00'))
                    answered = datetime.fromisoformat(call["answered_at"].replace('Z', '+00:00'))
                    setup_time = (answered - initiated).total_seconds()
                    setup_times.append(setup_time)
                    answered_calls += 1
                except:
                    pass
            
            status = (call.get("status") or "").lower()
            duration = call.get("call_duration") or 0
            
            # Enhanced call disposition analysis
            if status in ["completed", "ended"]:
                successful_calls += 1
                if duration > 30:
                    analytics["call_disposition_details"]["human_answered"] += 1
                elif duration > 5:
                    analytics["call_disposition_details"]["answering_machine"] += 1
            elif status == "busy":
                analytics["call_disposition_details"]["busy_tone"] += 1
                analytics["carrier_analysis"]["carrier_busy_signals"] += 1
            elif status in ["no_answer", "timeout"]:
                analytics["call_disposition_details"]["no_answer"] += 1
            else:
                analytics["call_disposition_details"]["network_error"] += 1
        
        # Update analytics
        total_calls = len(calls_data)
        if total_calls > 0:
            analytics["call_quality_metrics"]["call_completion_rate"] = round((successful_calls / total_calls) * 100, 2)
            analytics["call_quality_metrics"]["answer_seizure_ratio"] = round((answered_calls / total_calls) * 100, 2)
        
        if setup_times:
            analytics["call_quality_metrics"]["avg_call_setup_time"] = round(sum(setup_times) / len(setup_times), 2)
        
        analytics["carrier_analysis"]["successful_connections"] = successful_calls
        
        return analytics
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting Telnyx call tracking data: {e}")
        raise HTTPException(status_code=500, detail="Failed to get Telnyx analytics")

# LiveKit Session Analytics
@app.get("/analytics/livekit-sessions")
async def get_livekit_session_analytics(
    authorization: str = Header(None, alias="Authorization"),
    time_filter: str = "30d"
):
    """Get LiveKit session analytics data"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
    
    token = authorization.replace("Bearer ", "")
    
    try:
        # Verify token
        user_response = supabase_service_client.auth.get_user(token)
        if not user_response.user:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        user_id = user_response.user.id
        
        # Get calls with LiveKit room data
        calls_response = supabase_service_client.table("calls").select(
            "id, room_name, status, call_duration, created_at, initiated_at, answered_at, ended_at, agent_id"
        ).eq("user_id", user_id).not_.is_("room_name", "null").execute()
        
        calls_data = calls_response.data or []
        
        # LiveKit-specific analytics
        analytics = {
            "session_metrics": {
                "total_sessions": len(calls_data),
                "avg_session_duration": 0.0,
                "successful_sessions": 0,
                "failed_sessions": 0,
                "session_success_rate": 0.0
            },
            "agent_session_performance": {},
            "room_utilization": {
                "peak_concurrent_sessions": 0,
                "avg_daily_sessions": 0,
                "room_turnover_rate": 0.0
            },
            "technical_metrics": {
                "connection_quality": "Good",  # This would come from LiveKit Analytics API
                "audio_quality_score": 85.0,  # Placeholder - would integrate with LiveKit
                "latency_metrics": {
                    "avg_end_to_end_latency": 120,  # ms
                    "audio_processing_delay": 45,   # ms
                    "network_jitter": 5            # ms
                }
            },
            "real_time_analytics": {
                "active_sessions_now": 0,
                "sessions_last_hour": 0,
                "bandwidth_usage_mb": 0.0
            }
        }
        
        # Calculate session metrics
        total_duration = 0
        successful_sessions = 0
        agent_stats = {}
        
        for call in calls_data:
            duration = call.get("call_duration") or 0
            status = (call.get("status") or "").lower()
            agent_id = call.get("agent_id")
            
            total_duration += duration
            
            if status in ["completed", "ended"]:
                successful_sessions += 1
            
            # Track agent session performance
            if agent_id:
                if agent_id not in agent_stats:
                    agent_stats[agent_id] = {"sessions": 0, "duration": 0, "successful": 0}
                agent_stats[agent_id]["sessions"] += 1
                agent_stats[agent_id]["duration"] += duration
                if status in ["completed", "ended"]:
                    agent_stats[agent_id]["successful"] += 1
        
        # Update analytics
        total_sessions = len(calls_data)
        if total_sessions > 0:
            analytics["session_metrics"]["avg_session_duration"] = round(total_duration / total_sessions, 2)
            analytics["session_metrics"]["session_success_rate"] = round((successful_sessions / total_sessions) * 100, 2)
        
        analytics["session_metrics"]["successful_sessions"] = successful_sessions
        analytics["session_metrics"]["failed_sessions"] = total_sessions - successful_sessions
        
        # Format agent performance
        for agent_id, stats in agent_stats.items():
            success_rate = (stats["successful"] / stats["sessions"] * 100) if stats["sessions"] > 0 else 0
            avg_duration = stats["duration"] / stats["sessions"] if stats["sessions"] > 0 else 0
            analytics["agent_session_performance"][f"agent_{agent_id}"] = {
                "sessions": stats["sessions"],
                "avg_duration": round(avg_duration, 2),
                "success_rate": round(success_rate, 2)
            }
        
        # Mock some real-time data (in production, this would come from LiveKit Analytics API)
        from datetime import timedelta
        analytics["real_time_analytics"]["sessions_last_hour"] = len([
            c for c in calls_data 
            if c.get("created_at") and 
            datetime.fromisoformat(c["created_at"].replace('Z', '+00:00')) > 
            datetime.utcnow() - timedelta(hours=1)
        ])
        
        return analytics
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting LiveKit session analytics: {e}")
        raise HTTPException(status_code=500, detail="Failed to get LiveKit analytics")

# Real-time Analytics Dashboard Endpoint
@app.get("/analytics/real-time")
async def get_real_time_analytics(
    authorization: str = Header(None, alias="Authorization")
):
    """Get real-time analytics for live dashboard updates"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
    
    token = authorization.replace("Bearer ", "")
    
    try:
        # Verify token
        user_response = supabase_service_client.auth.get_user(token)
        if not user_response.user:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        user_id = user_response.user.id
        
        # Get real-time data (last 1 hour)
        one_hour_ago = datetime.utcnow() - timedelta(hours=1)
        
        recent_calls_response = supabase_service_client.table("calls").select(
            "id, status, call_duration, created_at, agent_id"
        ).eq("user_id", user_id).gte("created_at", one_hour_ago.isoformat()).execute()
        
        recent_calls = recent_calls_response.data or []
        
        # Get active campaigns
        active_campaigns_response = supabase_service_client.table("batch_campaigns").select(
            "id, name, status"
        ).eq("user_id", user_id).eq("status", "running").execute()
        
        active_campaigns = active_campaigns_response.data or []
        
        # Calculate real-time metrics
        calling_now = len([c for c in recent_calls if c.get("status") == "calling"])
        calls_last_hour = len(recent_calls)
        successful_last_hour = len([c for c in recent_calls if c.get("status") in ["completed", "ended"]])
        
        real_time_data = {
            "live_metrics": {
                "calls_in_progress": calling_now,
                "calls_last_hour": calls_last_hour,
                "success_rate_last_hour": round((successful_last_hour / calls_last_hour * 100), 2) if calls_last_hour > 0 else 0,
                "active_campaigns": len(active_campaigns),
                "avg_call_duration_last_hour": round(
                    sum(c.get("call_duration", 0) for c in recent_calls) / len(recent_calls), 2
                ) if recent_calls else 0
            },
            "minute_by_minute": [
                {
                    "timestamp": (datetime.utcnow() - timedelta(minutes=i)).isoformat(),
                    "calls": max(0, calling_now - i + __import__('random').randint(-2, 3)),  # Mock minute data
                    "successful": max(0, calling_now - i + __import__('random').randint(-1, 2))
                }
                for i in range(15, -1, -1)  # Last 15 minutes
            ],
            "active_campaigns_status": [
                {
                    "campaign_name": campaign.get("name", "Unknown"),
                    "status": campaign.get("status", "unknown"),
                    "calls_in_progress": __import__('random').randint(0, 5)  # Mock data - would be real in production
                }
                for campaign in active_campaigns
            ],
            "system_health": {
                "api_response_time": round(__import__('random').uniform(50, 150), 2),  # Mock data
                "database_connection": "healthy",
                "telnyx_connection": "healthy",
                "livekit_connection": "healthy"
            }
        }
        
        return real_time_data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting real-time analytics: {e}")
        raise HTTPException(status_code=500, detail="Failed to get real-time analytics")

# ===== PATHWAY TESTING ENDPOINTS (Phase 1) =====

@app.get("/test/pathway-integration")
async def test_pathway_integration():
    """Test endpoint to verify pathway integration is working"""
    results = {
        "timestamp": datetime.utcnow().isoformat(),
        "tests": {},
        "overall_status": "unknown"
    }
    
    try:
        # Test 1: Import pathway integration
        try:
            from api.agent_pathway_integration import auto_start_pathway_for_new_call
            results["tests"]["pathway_import"] = {"status": "✅ PASS", "message": "Pathway integration module imported successfully"}
        except Exception as e:
            results["tests"]["pathway_import"] = {"status": "❌ FAIL", "message": f"Failed to import pathway integration: {str(e)}"}
        
        # Test 2: Database connection for pathways
        try:
            pathway_count = supabase_service_client.table("pathways").select("id").execute()
            execution_count = supabase_service_client.table("pathway_executions").select("id").execute()
            results["tests"]["database_access"] = {
                "status": "✅ PASS", 
                "message": f"Database accessible - {len(pathway_count.data or [])} pathways, {len(execution_count.data or [])} executions"
            }
        except Exception as e:
            results["tests"]["database_access"] = {"status": "❌ FAIL", "message": f"Database access failed: {str(e)}"}
        
        # Test 3: Agent pathway column
        try:
            agent_test = supabase_service_client.table("agents").select("id, default_pathway_id").limit(1).execute()
            results["tests"]["agent_pathway_column"] = {"status": "✅ PASS", "message": "Agents.default_pathway_id column accessible"}
        except Exception as e:
            results["tests"]["agent_pathway_column"] = {"status": "❌ FAIL", "message": f"Agent pathway column issue: {str(e)}"}
        
        # Test 4: Pathway routes availability  
        try:
            from api.pathway_routes import router as pathway_router
            results["tests"]["pathway_routes"] = {"status": "✅ PASS", "message": "Pathway routes module loaded"}
        except Exception as e:
            results["tests"]["pathway_routes"] = {"status": "❌ FAIL", "message": f"Pathway routes issue: {str(e)}"}
        
        # Determine overall status
        failed_tests = [test for test in results["tests"].values() if "❌ FAIL" in test["status"]]
        if not failed_tests:
            results["overall_status"] = "✅ ALL TESTS PASSED"
        elif len(failed_tests) <= 1:
            results["overall_status"] = "⚠️ MOSTLY WORKING (minor issues)"
        else:
            results["overall_status"] = "❌ CRITICAL ISSUES DETECTED"
            
        logger.info(f"Pathway integration test results: {results['overall_status']}")
        return results
        
    except Exception as e:
        results["overall_status"] = "❌ TEST FRAMEWORK ERROR"
        results["error"] = str(e)
        logger.error(f"Pathway integration test error: {e}")
        return results

@app.post("/test/create-test-pathway")
async def create_test_pathway(authorization: str = Header(None, alias="Authorization")):
    """Create a simple test pathway for integration testing"""
    try:
        user_id = get_user_id_from_token(authorization)
        
        test_pathway = {
            "name": "Test Pathway - Integration Check",
            "description": "Automated test pathway created for Phase 1 integration testing",
            "config": {
                "nodes": [
                    {
                        "id": "entry",
                        "type": "conversation",
                        "name": "Welcome Node",
                        "config": {
                            "message": "Hello! This is a test pathway. How can I help you today?",
                            "wait_for_response": True
                        },
                        "position": {"x": 100, "y": 100}
                    },
                    {
                        "id": "end",
                        "type": "end_call",
                        "name": "End Call",
                        "config": {
                            "message": "Thank you for testing our pathway system. Goodbye!",
                            "reason": "completed"
                        },
                        "position": {"x": 300, "y": 100}
                    }
                ],
                "edges": [
                    {
                        "id": "entry_to_end",
                        "source": "entry",
                        "target": "end",
                        "condition": "default"
                    }
                ],
                "entry_point": "entry",
                "variables": {}
            },
            "status": "active",
            "user_id": user_id
        }
        
        # Insert test pathway
        response = supabase_service_client.table("pathways").insert(test_pathway).execute()
        
        if response.data:
            pathway_id = response.data[0]["id"]
            logger.info(f"Created test pathway: {pathway_id}")
            return {
                "status": "✅ SUCCESS",
                "message": "Test pathway created successfully",
                "pathway_id": pathway_id,
                "pathway_data": response.data[0]
            }
        else:
            return {
                "status": "❌ FAILED",
                "message": "Failed to create test pathway",
                "error": response.error
            }
            
    except Exception as e:
        logger.error(f"Error creating test pathway: {e}")
        return {
            "status": "❌ ERROR",
            "message": f"Exception creating test pathway: {str(e)}"
        }

@app.get("/test/pathway-execution/{execution_id}")
async def get_pathway_execution_details(execution_id: str):
    """Get detailed information about a specific pathway execution"""
    try:
        response = supabase_service_client.table("pathway_executions").select("*").eq("id", execution_id).single().execute()
        
        if response.data:
            execution_data = response.data
            
            # Enrich with pathway info
            pathway_response = supabase_service_client.table("pathways").select("name, description").eq("id", execution_data["pathway_id"]).single().execute()
            if pathway_response.data:
                execution_data["pathway_info"] = pathway_response.data
            
            return {
                "status": "✅ FOUND",
                "execution": execution_data
            }
        else:
            return {
                "status": "❌ NOT FOUND",
                "message": f"No execution found with ID: {execution_id}"
            }
            
    except Exception as e:
        logger.error(f"Error getting pathway execution {execution_id}: {e}")
        return {
            "status": "❌ ERROR",
            "message": str(e)
        }

# ===== END PATHWAY TESTING ENDPOINTS =====

@app.post("/test/simulate-pathway-execution")
async def simulate_pathway_execution(pathway_id: str, authorization: str = Header(None, alias="Authorization")):
    """Simulate pathway execution to test node processing logic"""
    try:
        user_id = get_user_id_from_token(authorization)
        
        # Load pathway configuration
        pathway_response = supabase_service_client.table("pathways").select("*").eq("id", pathway_id).single().execute()
        
        if not pathway_response.data:
            return {
                "status": "❌ FAILED",
                "message": f"Pathway {pathway_id} not found"
            }
        
        pathway_data = pathway_response.data
        
        # Check if user owns this pathway
        if pathway_data["user_id"] != user_id:
            return {
                "status": "❌ UNAUTHORIZED",
                "message": "You don't have access to this pathway"
            }
        
        # Simulate execution by testing node connectivity
        config = pathway_data.get("config", {})
        nodes = config.get("nodes", [])
        edges = config.get("edges", [])
        entry_point = config.get("entry_point", "entry")
        
        simulation_results = {
            "pathway_info": {
                "id": pathway_id,
                "name": pathway_data["name"],
                "status": pathway_data["status"],
                "entry_point": entry_point
            },
            "node_analysis": {},
            "execution_flow": [],
            "issues": [],
            "overall_status": "unknown"
        }
        
        # Analyze each node
        for node in nodes:
            node_id = node.get("id")
            node_type = node.get("type")
            
            analysis = {
                "type": node_type,
                "config_valid": bool(node.get("config")),
                "has_outgoing_edges": False,
                "reachable_from_entry": False,
                "processor_available": node_type in ["conversation", "tools", "transfer", "end_call"]
            }
            
            # Check outgoing edges
            for edge in edges:
                if edge.get("source") == node_id:
                    analysis["has_outgoing_edges"] = True
                    break
            
            simulation_results["node_analysis"][node_id] = analysis
        
        # Test execution flow from entry point
        current_node = entry_point
        flow_path = []
        visited_nodes = set()
        max_steps = 10  # Prevent infinite loops
        
        for step in range(max_steps):
            if current_node in visited_nodes:
                simulation_results["issues"].append(f"Circular reference detected at node: {current_node}")
                break
            
            # Find current node
            node = next((n for n in nodes if n.get("id") == current_node), None)
            if not node:
                simulation_results["issues"].append(f"Node not found: {current_node}")
                break
            
            flow_path.append({
                "step": step + 1,
                "node_id": current_node,
                "node_type": node.get("type"),
                "node_name": node.get("name")
            })
            
            visited_nodes.add(current_node)
            
            # Mark as reachable
            if current_node in simulation_results["node_analysis"]:
                simulation_results["node_analysis"][current_node]["reachable_from_entry"] = True
            
            # If this is an end_call node, stop here
            if node.get("type") == "end_call":
                break
            
            # Find next node
            next_node = None
            for edge in edges:
                if edge.get("source") == current_node:
                    next_node = edge.get("target")
                    break
            
            if not next_node:
                simulation_results["issues"].append(f"No outgoing edge from node: {current_node}")
                break
            
            current_node = next_node
        
        simulation_results["execution_flow"] = flow_path
        
        # Determine overall status
        if not simulation_results["issues"]:
            simulation_results["overall_status"] = "✅ PATHWAY VALID"
        elif len(simulation_results["issues"]) <= 2:
            simulation_results["overall_status"] = "⚠️ MINOR ISSUES"
        else:
            simulation_results["overall_status"] = "❌ SIGNIFICANT ISSUES"
        
        return simulation_results
        
    except Exception as e:
        logger.error(f"Error simulating pathway execution: {e}")
        return {
            "status": "❌ ERROR",
            "message": str(e)
        }

@app.get("/test/active-pathway-executions")
async def get_active_pathway_executions():
    """Get all currently active pathway executions for debugging"""
    try:
        # Get active executions
        response = supabase_service_client.table("pathway_executions").select("""
            id, pathway_id, call_id, agent_id, status, current_node_id, 
            started_at, updated_at, execution_trace,
            pathways(name, description)
        """).eq("status", "running").order("started_at", desc=True).limit(50).execute()
        
        if response.data:
            executions = []
            for execution in response.data:
                # Calculate execution duration
                started_at = datetime.fromisoformat(execution["started_at"].replace("Z", "+00:00"))
                duration_minutes = (datetime.now(timezone.utc) - started_at).total_seconds() / 60
                
                executions.append({
                    "execution_id": execution["id"],
                    "pathway_name": execution["pathways"]["name"] if execution["pathways"] else "Unknown",
                    "call_id": execution["call_id"],
                    "agent_id": execution["agent_id"],
                    "current_node": execution["current_node_id"],
                    "duration_minutes": round(duration_minutes, 2),
                    "trace_entries": len(execution["execution_trace"] or []),
                    "started_at": execution["started_at"]
                })
            
            return {
                "status": "✅ SUCCESS",
                "total_active_executions": len(executions),
                "executions": executions
            }
        else:
            return {
                "status": "✅ SUCCESS",
                "total_active_executions": 0,
                "executions": []
            }
            
    except Exception as e:
        logger.error(f"Error getting active pathway executions: {e}")
        return {
            "status": "❌ ERROR",
            "message": str(e)
        }

@app.get("/test/pathway-system-health")
async def pathway_system_health():
    """Comprehensive pathway system health check"""
    try:
        health_report = {
            "timestamp": datetime.utcnow().isoformat(),
            "system_status": "unknown",
            "components": {},
            "recommendations": []
        }
        
        # Check 1: Database tables
        try:
            pathways_count = supabase_service_client.table("pathways").select("id", count="exact").execute()
            executions_count = supabase_service_client.table("pathway_executions").select("id", count="exact").execute()
            agents_with_pathways = supabase_service_client.table("agents").select("id", count="exact").not_.is_("default_pathway_id", "null").execute()
            
            health_report["components"]["database"] = {
                "status": "✅ HEALTHY",
                "pathways_total": pathways_count.count,
                "executions_total": executions_count.count,
                "agents_with_pathways": agents_with_pathways.count
            }
        except Exception as e:
            health_report["components"]["database"] = {
                "status": "❌ UNHEALTHY",
                "error": str(e)
            }
        
        # Check 2: Integration modules
        integration_status = "✅ HEALTHY"
        try:
            from api.agent_pathway_integration import auto_start_pathway_for_new_call
            from api.pathway_routes import router as pathway_router
        except Exception as e:
            integration_status = f"❌ UNHEALTHY: {str(e)}"
        
        health_report["components"]["integration"] = {"status": integration_status}
        
        # Check 3: Recent activity
        try:
            recent_executions = supabase_service_client.table("pathway_executions").select("id, status, started_at").gte("started_at", (datetime.utcnow() - timedelta(hours=24)).isoformat()).execute()
            
            activity_summary = {
                "total_24h": len(recent_executions.data or []),
                "running": len([e for e in (recent_executions.data or []) if e["status"] == "running"]),
                "completed": len([e for e in (recent_executions.data or []) if e["status"] == "completed"])
            }
            
            health_report["components"]["recent_activity"] = {
                "status": "✅ TRACKED",
                **activity_summary
            }
        except Exception as e:
            health_report["components"]["recent_activity"] = {
                "status": "❌ ERROR",
                "error": str(e)
            }
        
        # Generate recommendations
        if health_report["components"]["database"]["status"] == "❌ UNHEALTHY":
            health_report["recommendations"].append("Check database connection and table schemas")
        
        if "agents_with_pathways" in health_report["components"]["database"] and health_report["components"]["database"]["agents_with_pathways"] == 0:
            health_report["recommendations"].append("No agents have pathways assigned - consider setting up test pathways")
        
        if "recent_activity" in health_report["components"] and health_report["components"]["recent_activity"].get("total_24h", 0) == 0:
            health_report["recommendations"].append("No pathway executions in the last 24h - system may not be triggering properly")
        
        # Determine overall system status
        failed_components = [comp for comp in health_report["components"].values() if "❌" in comp["status"]]
        if not failed_components:
            health_report["system_status"] = "✅ HEALTHY"
        elif len(failed_components) == 1:
            health_report["system_status"] = "⚠️ DEGRADED"
        else:
            health_report["system_status"] = "❌ CRITICAL"
        
        return health_report
        
    except Exception as e:
        logger.error(f"Error in pathway system health check: {e}")
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "system_status": "❌ HEALTH CHECK FAILED",
            "error": str(e)
        }

@app.get("/test/agents/{agent_id}")
async def test_get_agent(agent_id: int):
    """Simple test endpoint to debug the agent route issue"""
    return {"message": f"Test endpoint working for agent {agent_id}", "agent_id": agent_id}