"""
PAM Outbound Agent - Handles Outbound Calls

This agent handles outbound calls using the LiveKit Agents framework.
It connects to the LiveKit cloud service and initiates SIP calls to specified phone numbers.

The agent is configured as an "outbound-caller" worker and runs on port 8081.
"""

from __future__ import annotations

import os
import asyncio
import logging
from dotenv import load_dotenv, find_dotenv
import json
import sys
import locale
from typing import Any, Optional
import uuid
from dataclasses import dataclass
import random
import httpx
import time
import base64
from datetime import datetime

# Forcer l'encodage UTF-8 pour Windows
if sys.platform == 'win32':
    # Tentative de définir le locale en français UTF-8
    try:
        locale.setlocale(locale.LC_ALL, 'fr_FR.UTF-8')
    except locale.Error:
        try:
            locale.setlocale(locale.LC_ALL, 'French_France.1252')
        except locale.Error:
            pass

# Configuration du logger pour gérer les accents  
# Configure root logger to catch ALL logs from any module
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)

# Remove any existing handlers to avoid duplicates
for handler in root_logger.handlers[:]:
    root_logger.removeHandler(handler)

# ✅ ADD FILE LOGGING CONFIGURATION
# Check if we have log file paths from the launcher
agent_log_file = os.getenv("AGENT_LOG_FILE")
agent_err_file = os.getenv("AGENT_ERR_FILE")

if agent_log_file and agent_err_file:
    # Create file handlers with UTF-8 encoding
    file_handler = logging.FileHandler(agent_log_file, mode='a', encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    
    error_handler = logging.FileHandler(agent_err_file, mode='a', encoding='utf-8')
    error_handler.setLevel(logging.WARNING)
    
    # Create formatter without emojis to avoid encoding issues
    file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(file_formatter)
    error_handler.setFormatter(file_formatter)
    
    # Add file handlers to root logger
    root_logger.addHandler(file_handler)
    root_logger.addHandler(error_handler)
    
    print(f"[AGENT] File logging enabled: {agent_log_file}")

# Créer un gestionnaire de flux qui gère l'encodage UTF-8 sans utiliser buffer
handler = logging.StreamHandler(sys.stderr)
handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
root_logger.addHandler(handler)

# Get the specific logger for this module
logger = logging.getLogger("outbound-caller")

# Logs au démarrage du script pour débogage
logger.info(f"Outbound Agent script démarre, args: {sys.argv}")
logger.info(f"Python version: {sys.version}")
logger.info(f"Répertoire courant: {os.getcwd()}")
logger.info(f"Encodage par défaut: {sys.getdefaultencoding()}")
logger.info(f"Locale système: {locale.getlocale()}")

# Load environment variables from .env files
load_dotenv(find_dotenv('.env.local'), override=True)
load_dotenv(find_dotenv('.env'), override=True)

# Remove these lines that load from environment
# outbound_trunk_id = os.getenv("SIP_OUTBOUND_TRUNK_ID")
patient_name = os.getenv("PATIENT_NAME", "Jayden")
appointment_time = os.getenv("APPOINTMENT_TIME", "next Tuesday at 3pm")
room_name = os.getenv("LK_ROOM_NAME", "")
job_metadata = os.getenv("LK_JOB_METADATA", "{}")

# Ajout de logs pour débugger
# logger.info(f"SIP_OUTBOUND_TRUNK_ID: {outbound_trunk_id}")
logger.info(f"PATIENT_NAME: {patient_name}")
logger.info(f"APPOINTMENT_TIME: {appointment_time}")
logger.info(f"LK_ROOM_NAME: {room_name}")
logger.info(f"LK_JOB_METADATA: {job_metadata}")
logger.info(f"LIVEKIT_URL: {os.getenv('LIVEKIT_URL', 'non défini')}")
logger.info(f"LIVEKIT_API_KEY présent: {'Oui' if os.getenv('LIVEKIT_API_KEY') else 'Non'}")

# Importer les modules après la configuration du logger
from livekit import rtc, api
from livekit.agents import (
    AgentSession,
    Agent,
    JobContext,
    function_tool,
    RunContext,
    get_job_context,
    cli,
    RoomInputOptions,
    WorkerOptions,
)
from livekit.plugins import (
    deepgram,
    openai,
    cartesia,
    silero,
)
from livekit.agents.llm import ChatMessage
from pydantic import BaseModel, Field
from typing import AsyncIterable

# --- Répliquer les modèles Pydantic (ou importer d'un fichier commun) ---
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
    vad: VADConfig = Field(default_factory=VADConfig)
    stt: STTConfig = Field(default_factory=STTConfig)
    tts: TTSConfig = Field(default_factory=TTSConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)

# --- Définition des constantes pour l'appel au backend ---
BACKEND_API_URL = os.getenv("BACKEND_API_URL", "http://localhost:8000") # URL de votre API FastAPI
AGENT_INTERNAL_TOKEN = os.getenv("AGENT_INTERNAL_TOKEN") # Token secret partagé avec le backend

# TELNYX_API_KEY = os.getenv("TELNYX_API_KEY") # Supprimé car create_telnyx_call est supprimée

# --- Pathway Integration ---
try:
    # Add API directory to path for pathway integration
    import sys
    import os
    api_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'api')
    if api_path not in sys.path:
        sys.path.insert(0, api_path)
    
    # Use absolute imports to avoid relative import issues
    import agent_pathway_integration
    from agent_pathway_integration import (
        auto_start_pathway_for_new_call,
        handle_call_event,
        get_agent_pathway_manager
    )
    
    # Import WorkflowAgent for advanced pathway execution
    # First try from agents directory for WorkflowAgent
    agents_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'agents')
    if agents_dir not in sys.path:
        sys.path.insert(0, agents_dir)
    
    import workflow_agent
    from workflow_agent import WorkflowAgent, load_pathway_config
    
    PATHWAY_INTEGRATION_AVAILABLE = True
    logger.info("Pathway integration loaded successfully")
except ImportError as e:
    logger.warning(f"Pathway integration not available: {e}")
    PATHWAY_INTEGRATION_AVAILABLE = False
    
    # Create mock functions to avoid AttributeError
    async def auto_start_pathway_for_new_call(*args, **kwargs):
        return None
    
    async def handle_call_event(*args, **kwargs):
        pass
    
    def create_pathway_agent(*args, **kwargs):
        return None

# --- Multi-Agent Pathway Factory Integration ---
try:
    from pathway_agent_factory import create_pathway_agent as factory_create_pathway_agent, create_legacy_pathway_agent
    MULTI_AGENT_FACTORY_AVAILABLE = True
    logger.info("✅ Multi-agent pathway factory imported successfully")
except ImportError as e:
    MULTI_AGENT_FACTORY_AVAILABLE = False
    logger.warning(f"Multi-agent factory not available: {e}")
    # Fallback functions
    async def factory_create_pathway_agent(*args, **kwargs):
        return None, None
    def create_legacy_pathway_agent(*args, **kwargs):
        return None, None

# === UNIFIED AGENT CLASSES ===
# OutboundCaller handles outbound calls.
class OutboundCaller(Agent):
    def __init__(
        self,
        *,
        name: str,
        dial_info: dict[str, Any],
        instructions: str,
        initial_greeting: str,
        wait_for_greeting: bool = False,
        interruption_threshold: int = 100,
    ):
        # Log the final prompt being sent to the agent for debugging
        logger.info("--- Agent System Prompt ---")
        logger.info(instructions)
        logger.info("--- End Agent System Prompt ---")

        # Passer le prompt reçu au constructeur parent
        super().__init__(instructions=instructions)
        
        # Store participant reference for transfers etc.
        self.participant: rtc.RemoteParticipant | None = None
        self.dial_info = dial_info
        self.initial_greeting = initial_greeting
        self.wait_for_greeting = wait_for_greeting
        self.interruption_threshold = interruption_threshold

        # Extract phone number for outbound calls
        self.phone_number = dial_info.get("phone_number")
        
        # Log call context
        logger.info(f"Agent initialized for OUTBOUND call to {self.phone_number}")

        # Log still uses name correctly
        logger.info(f"OutboundCaller (Pam Assistant) initialized for {name}")
        logger.info(f"dial_info provided: {dial_info}")
        logger.info(f"Initial greeting set to: {self.initial_greeting}")
        logger.info(f"Wait for greeting: {self.wait_for_greeting}")
        logger.info(f"Interruption threshold: {self.interruption_threshold}ms")

    async def ainit(self, sess: AgentSession):
        """Called by AgentSession when the session starts."""
        logger.info("ENTERING OutboundCaller.ainit - TOP OF METHOD")
        await super().ainit(sess)
        # La logique du message d'accueil est déplacée vers la méthode run
        logger.info(f"Agent '{self.name}' ainit completed.")

    def set_participant(self, participant: rtc.RemoteParticipant):
        self.participant = participant

    async def hangup(self):
        """Helper function to hang up the call by deleting the room"""

        job_ctx = get_job_context()
        await job_ctx.api.room.delete_room(
            api.DeleteRoomRequest(
                room=job_ctx.room.name
            )
        )
        logger.info("Room deleted to hang up the call.")

    # === FUNCTION TOOLS ===
    @function_tool()
    async def get_call_info(self, ctx: RunContext):
        """Get information about the current call"""
        return f"This is an outbound call to {self.phone_number}. We initiated this call."

    @function_tool()
    async def transfer_call(self, ctx: RunContext):
        """Transfer the call to a human operator or another number"""
        transfer_number = self.dial_info.get("transfer_to")
        if transfer_number:
            logger.info(f"Call transfer requested to {transfer_number}")
            # TODO: Implement actual call transfer logic
            return f"I'm transferring you to {transfer_number}. Please hold on."
        else:
            logger.warning("Transfer requested but no transfer number configured")
            return "I apologize, but I don't have a transfer number configured. Let me see how else I can help you."

    @function_tool()
    async def end_call(self, ctx: RunContext):
        """End the call gracefully"""
        logger.info("Call termination requested by agent")
        goodbye_message = "Thank you for your time. Have a great day! Goodbye."
        
        await self.hangup()
        return goodbye_message

    @function_tool()
    async def look_up_availability(
        self,
        ctx: RunContext,
        date: str,
    ):
        """Look up available appointments for the given date"""
        # TODO: Implement actual availability checking logic here
        logger.info(f"Availability lookup requested for {date}")
        return f"I found several available slots on {date}: 9:00 AM, 2:00 PM, and 4:30 PM"

    @function_tool()
    async def confirm_appointment(
        self,
        ctx: RunContext,
        date: str,
        time: str,
    ):
        """Confirm an appointment for the given date and time"""
        # TODO: Implement actual appointment confirmation logic here
        logger.info(f"Appointment confirmation requested for {date} at {time}")
        return f"Perfect! I've confirmed your appointment for {date} at {time}. You should receive a confirmation email shortly."

    @function_tool()
    async def detected_answering_machine(self, ctx: RunContext):
        """Handle answering machine detection for outbound calls"""
        logger.info("Answering machine detected")
        
        # Check voicemail settings from dial_info
        voicemail_detection = self.dial_info.get("voicemail_detection", False)
        voicemail_hangup_immediately = self.dial_info.get("voicemail_hangup_immediately", False)
        voicemail_message = self.dial_info.get("voicemail_message")
        
        if voicemail_hangup_immediately:
            logger.info("Hanging up immediately due to voicemail_hangup_immediately setting")
            await self.hangup()
            return "Answering machine detected, hanging up as configured."
        
        if voicemail_message:
            logger.info(f"Leaving custom voicemail message: {voicemail_message}")
            return voicemail_message
        else:
            default_message = f"Hello, this is a call from Pam. I was trying to reach you. Please call us back when you get a chance. Thank you."
            logger.info(f"Leaving default voicemail message")
            return default_message

    async def run(self, room: rtc.Room) -> None:
        """Main run loop for the agent's conversational logic."""
        logger.info("ENTERING OutboundCaller.run - TOP OF METHOD")
        sess = self._session
        if not sess:
            logger.error("Agent session not found in agent.run(), cannot proceed.")
            return

        # Initialize pathway integration if available
        pathway_execution_id = None
        if PATHWAY_INTEGRATION_AVAILABLE:
            try:
                # Extract pathway information from metadata
                job_ctx = get_job_context()
                raw_metadata = job_ctx.job.metadata
                metadata = json.loads(raw_metadata) if raw_metadata else {}
                
                call_id = metadata.get("supabase_call_id")
                agent_id = metadata.get("agent_id")
                
                if call_id and agent_id:
                    # Auto-start pathway for this call
                    pathway_execution_id = await auto_start_pathway_for_new_call(
                        call_id=str(call_id),
                        agent_id=int(agent_id),
                        room_name=room.name
                    )
                    if pathway_execution_id:
                        logger.info(f"Pathway execution started: {pathway_execution_id}")
                        
                        # Send call answered event
                        await handle_call_event(str(call_id), "call_answered", {
                            "room_name": room.name,
                            "agent_id": agent_id,
                            "timestamp": time.time()
                        })
                    else:
                        logger.info("No default pathway found for this agent")
                else:
                    logger.warning("Missing call_id or agent_id in metadata - pathway integration disabled")
            except Exception as e:
                logger.error(f"Error initializing pathway integration: {e}")
                pathway_execution_id = None

        # Handle initial greeting based on wait_for_greeting setting
        if self.wait_for_greeting:
            logger.info(f"Agent '{self.name}' configured to wait for user greeting first")
            # Wait for user input first, then deliver greeting
            try:
                logger.info("Waiting for user to speak first...")
                async for user_input in sess.user_input():
                    if not user_input.is_final:
                        continue
                    
                    logger.info(f"User spoke first: '{user_input.text}'. Now delivering initial greeting.")
                    
                    # Deliver initial greeting as response to user's first input
                    if self.initial_greeting:
                        await sess.say(self.initial_greeting, allow_interruptions=True)
                        logger.info("Initial greeting delivered after user spoke.")
                    
                    # Continue with normal conversation flow
                    break
                    
            except Exception as e:
                logger.error(f"Error while waiting for user greeting: {e}")
                # Fallback: deliver greeting anyway
                if self.initial_greeting:
                    await sess.say(self.initial_greeting, allow_interruptions=True)
        else:
            # Standard behavior: deliver greeting immediately
            if self.initial_greeting:
                logger.info(f"Agent '{self.name}' delivering immediate greeting: '{self.initial_greeting}'")
                try:
                    await sess.say(self.initial_greeting, allow_interruptions=True)
                    logger.info("Initial greeting delivered immediately.")
                except Exception as e:
                    logger.error(f"Error delivering initial greeting: {e}")
            else:
                logger.info("No initial greeting to deliver.")

        # Main conversation loop
        logger.info(f"Agent '{self.name}' entering main conversation loop.")
        try:
            async for user_input in sess.user_input():
                if not user_input.is_final:
                    continue # Attendre la transcription finale

                logger.info(f"User said: '{user_input.text}'")
                
                # Send speech detection event to pathway
                if PATHWAY_INTEGRATION_AVAILABLE and pathway_execution_id:
                    try:
                        job_ctx = get_job_context()
                        metadata = json.loads(job_ctx.job.metadata) if job_ctx.job.metadata else {}
                        call_id = metadata.get("supabase_call_id")
                        
                        if call_id:
                            await handle_call_event(str(call_id), "speech_detected", {
                                "text": user_input.text,
                                "confidence": getattr(user_input, 'confidence', 1.0),
                                "timestamp": time.time()
                            })
                    except Exception as e:
                        logger.error(f"Error sending speech event to pathway: {e}")
                
                # Pour une conversation simple, l'historique peut juste être le dernier message utilisateur.
                # Pour des conversations plus complexes, vous géreriez un historique plus long.
                history = [ChatMessage(role="user", content=user_input.text)]
                
                logger.info(f"Sending to LLM with history: {history}")
                # Le system_prompt est déjà défini au niveau de l'Agent (super().__init__(instructions=...))
                # et devrait être utilisé par le plugin LLM.
                llm_stream = await sess.llm.chat(history=history) 
                
                logger.info("Streaming LLM response to TTS.")
                # Use interruption threshold setting
                allow_interruptions = True if self.interruption_threshold > 0 else False
                await sess.say(llm_stream, allow_interruptions=allow_interruptions)
                logger.info("Agent finished responding to user input.")
        except asyncio.CancelledError:
            logger.info(f"Agent run loop for '{self.name}' cancelled.")
        except Exception as e:
            logger.error(f"Error in agent run loop for '{self.name}': {e}", exc_info=True)
        finally:
            logger.info(f"Agent run loop for '{self.name}' finished.")
        
        logger.info("Exiting OutboundCaller.run after conversation loop.")


# === END OF OUTBOUND CALLER CLASS ===


async def get_telnyx_call_duration(call_control_id: str | None) -> int | None: # call_control_id est maintenant optionnel
    # MODIFIÉ: Obtenir TELNYX_API_KEY ici car il n'est plus global au même endroit
    telnyx_api_key_local = os.getenv("TELNYX_API_KEY")
    if not telnyx_api_key_local or not call_control_id:
        logger.warning("TELNYX_API_KEY ou call_control_id manquant pour récupérer la durée réelle d'appel.")
        return None
    
    url = f"https://api.telnyx.com/v2/calls/{call_control_id}"
    headers = {
        "Authorization": f"Bearer {telnyx_api_key_local}", # Utiliser la variable locale
        "Accept": "application/json"
    }
    
    try:
        async with httpx.AsyncClient() as client:
            logger.info(f"Tentative de récupération de la durée via Telnyx pour call_control_id: {call_control_id}")
            response = await client.get(url, headers=headers)
            
            if response.status_code == 404:
                logger.warning(f"Call not found in Telnyx for call_control_id: {call_control_id}")
                return None
            elif response.status_code == 422:
                logger.warning(f"Invalid call_control_id format for Telnyx: {call_control_id}")
                return None
            
            response.raise_for_status()
            data = response.json()
            
            if not data.get("data"):
                logger.warning(f"No data field in Telnyx response for call_control_id: {call_control_id}")
                return None
                
            duration = data["data"].get("call_duration_secs")
            if duration is None:
                logger.warning(f"No call_duration_secs in Telnyx response for call_control_id: {call_control_id}")
                return None
                
            logger.info(f"Durée réelle récupérée via Telnyx pour call_control_id {call_control_id}: {duration}s")
            return duration
            
    except httpx.HTTPStatusError as e:
        logger.error(f"Erreur HTTP lors de la récupération de la durée via Telnyx: {e.response.status_code} - {e.response.text}")
        return None
    except Exception as e:
        logger.error(f"Erreur lors de la récupération de la durée via Telnyx: {e}")
        return None

async def update_call_status_in_backend(room_name: str, new_status: str, supabase_call_id: str | None = None, call_duration_seconds: int | None = None, telnyx_id: str | None = None) -> None:
    """Met à jour le statut et potentiellement d'autres infos de l'appel dans le backend."""
    if not supabase_call_id:
        logger.error(f"supabase_call_id manquant pour la mise à jour du statut de la room {room_name}")
        return

    backend_url = os.getenv("BACKEND_API_URL", "http://localhost:8000")
    update_url = f"{backend_url}/calls/room/{room_name}/status"
    
    agent_token = os.getenv("AGENT_INTERNAL_TOKEN")
    if not agent_token:
        logger.error("AGENT_INTERNAL_TOKEN non configuré. Impossible de mettre à jour le statut de l'appel.")
        return

    headers = {
        "Content-Type": "application/json",
        "X-Agent-Token": agent_token
    }

    payload = {
        "new_status": new_status,
        "supabase_call_id": supabase_call_id
    }
    if call_duration_seconds is not None:
        payload["call_duration_seconds"] = call_duration_seconds
    if telnyx_id is not None:
        payload["telnyx_call_control_id"] = telnyx_id

    logger.info(f"Tentative de mise à jour des infos pour room {room_name} (Supabase ID: {supabase_call_id}) avec payload: {payload} via backend: {update_url}")
    try:
        async with httpx.AsyncClient() as client:
            response = await client.patch(update_url, json=payload, headers=headers)
            response.raise_for_status()
            logger.info(f"Infos mises à jour avec succès pour room {room_name} (Supabase ID: {supabase_call_id}): {response.json()}")
    except httpx.HTTPStatusError as e:
        logger.error(f"Erreur HTTP lors de la mise à jour des infos pour {room_name} (Supabase ID: {supabase_call_id}): {e.response.status_code} - {e.response.text}")
    except Exception as e:
        logger.error(f"Erreur lors de la mise à jour des infos pour {room_name} (Supabase ID: {supabase_call_id}): {e}")

async def entrypoint(ctx: JobContext):
    logger.info(f"Entrée dans la fonction entrypoint pour le job {ctx.job.id}")
    participant = None
    call_connected_time = None
    supabase_call_id = None

    try:
        await ctx.connect()
        logger.info(f"Connexion établie à la room {ctx.room.name}")
        raw_metadata = ctx.job.metadata
        logger.info(f"Métadonnées brutes du job: {raw_metadata}")
        try:
            metadata = json.loads(raw_metadata)
            logger.info(f"Métadonnées parsées: {metadata}")
            supabase_call_id = metadata.get("supabase_call_id")
            logger.info(f"supabase_call_id extrait des métadonnées: {supabase_call_id}")
        except json.JSONDecodeError as e:
            logger.error(f"Erreur de parsing des métadonnées JSON: {e}")
            logger.error(f"Métadonnées brutes qui ont causé l'erreur: {raw_metadata}")
            await ctx.room.disconnect()
            return
    except Exception as e:
        logger.error(f"Erreur de connexion à la room {ctx.room.name}: {e}")
        await ctx.room.disconnect()
        return
        
    # Ensure we have a supabase_call_id for outbound calls
    if not supabase_call_id:
        logger.error("supabase_call_id non trouvé dans les métadonnées du job. Impossible de continuer.")
        await ctx.room.disconnect()
        return

    # -- Start Metadata Extraction --
    logger.info(f"Métadonnées du job: {ctx.job.metadata}")

    first_name = "Valued Customer" # Default value
    last_name = ""
    phone_number = None
    dial_info = {} # Initialize dial_info
    system_prompt_from_metadata = "Default prompt if none provided." # Default prompt
    sip_trunk_id_from_metadata = None # Initialize
    agent_name_from_metadata = None # Initialize for agent name
    
    # PAM tier and advanced settings
    pam_tier_from_metadata = "core"  # Default value
    wait_for_greeting_from_metadata = False  # Default value
    interruption_threshold_from_metadata = 100  # Default value in ms

    try:
        # Use job metadata first, fallback to env var LK_JOB_METADATA
        metadata_str = ctx.job.metadata or os.getenv("LK_JOB_METADATA", "{}")
        if metadata_str and metadata_str != "{}":
            dial_info = json.loads(metadata_str)
            logger.info(f"dial_info parsed from metadata: {dial_info}")
            
            # Extract agent name - prefer 'agentName' from backend, fallback to 'firstName'
            agent_name_from_metadata = dial_info.get("agentName")
            if agent_name_from_metadata:
                logger.info(f"Agent name from metadata (agentName): {agent_name_from_metadata}")
                first_name = agent_name_from_metadata  # Use agent name as first_name for compatibility
            else:
                first_name = dial_info.get("firstName", first_name)
                logger.info(f"Using firstName from metadata or default: {first_name}")
            
            last_name = dial_info.get("lastName", last_name)
            phone_number = dial_info.get("phoneNumber")
            
            # Log outbound call info
            logger.info(f"OUTBOUND CALL: To {phone_number}")
            
            # Extract pathway information from the nested dial_info structure
            nested_dial_info = dial_info.get("dial_info", {})
            default_pathway_id = nested_dial_info.get("default_pathway_id")
            agent_id = nested_dial_info.get("agent_id")
            user_id = nested_dial_info.get("user_id")  # Extract user_id for RLS filtering
            
            if default_pathway_id:
                logger.info(f"Default pathway found for agent: {default_pathway_id}")
            else:
                logger.info("No default pathway found in metadata")
            
            if agent_id:
                logger.info(f"Agent ID from metadata: {agent_id}")
            else:
                logger.warning("No agent_id found in metadata")
            
            # Extraction du system_prompt obligatoire des métadonnées
            system_prompt_from_metadata_extracted = dial_info.get("system_prompt")
            if not system_prompt_from_metadata_extracted:
                 logger.error("ERREUR CRITIQUE : system_prompt manquant dans les métadonnées du job ! Utilisation d'un prompt par défaut.")
                 # system_prompt_from_metadata est déjà initialisé avec un défaut
            else:
                system_prompt_from_metadata = system_prompt_from_metadata_extracted
            
            sip_trunk_id_from_metadata = dial_info.get("sip_trunk_id") # Récupérer sip_trunk_id des métadonnées
            
            # Extract PAM tier and advanced settings
            pam_tier_from_metadata = dial_info.get("pam_tier", pam_tier_from_metadata)
            wait_for_greeting_from_metadata = dial_info.get("wait_for_greeting", wait_for_greeting_from_metadata)
            interruption_threshold_from_metadata = dial_info.get("interruption_threshold", interruption_threshold_from_metadata)
            
            logger.info(f"PAM Tier: {pam_tier_from_metadata}, Wait for Greeting: {wait_for_greeting_from_metadata}, Interruption Threshold: {interruption_threshold_from_metadata}ms")

            # Keep transfer_to if present, ensure it's in dial_info for the agent
            if "transfer_to" in dial_info:
                 logger.info(f"Transfer number found in metadata: {dial_info['transfer_to']}")
            else:
                 # If not in metadata, maybe check environment? Or leave it empty.
                 # dial_info["transfer_to"] = os.getenv("DEFAULT_TRANSFER_NUMBER") 
                 pass # Assuming transfer_to is optional unless specified
            
            # Log voicemail settings if present
            if "voicemail_detection" in dial_info:
                logger.info(f"Voicemail detection found in metadata: {dial_info['voicemail_detection']}")
            if "voicemail_hangup_immediately" in dial_info:
                logger.info(f"Voicemail hangup immediately found in metadata: {dial_info['voicemail_hangup_immediately']}")
            if "voicemail_message" in dial_info:
                logger.info(f"Custom voicemail message found in metadata: {'Set' if dial_info['voicemail_message'] else 'Empty'}")
        else:
             logger.warning("No metadata found in job context or environment variable LK_JOB_METADATA.")

    except json.JSONDecodeError as e:
        logger.error(f"Erreur lors du décodage des métadonnées JSON: {e}")
        # Utiliser une variable temporaire pour éviter l'erreur de syntaxe f-string
        raw_metadata_content = ctx.job.metadata or os.getenv("LK_JOB_METADATA", "{}")
        logger.error(f"Contenu brut des métadonnées: {raw_metadata_content}")
        # Keep dial_info as {}, defaults for names/phone will be used
        dial_info = {} # Assurer que dial_info est aussi initialisé ici en cas d'erreur

    # Determine phone number: Parsed Metadata > PHONE_NUMBER env var
    if not phone_number:
        phone_number_env = os.getenv("PHONE_NUMBER")
        if phone_number_env:
            logger.info(f"Phone number taken from PHONE_NUMBER env var: {phone_number_env}")
            phone_number = phone_number_env
        else:
            logger.error("Phone number is missing in metadata and PHONE_NUMBER env var. Cannot dial.")
            await ctx.room.disconnect() # Disconnect before returning
            return # Stop processing if no number

    # Update dial_info with the final phone number and names for the agent
    dial_info["phone_number"] = phone_number
    dial_info["firstName"] = first_name
    dial_info["lastName"] = last_name
    # -- End Metadata Extraction --

    # NOUVEAU: Récupérer le agent_caller_id_number des métadonnées (dial_info)
    agent_caller_id_number_from_metadata = dial_info.get("agent_caller_id_number")
    if agent_caller_id_number_from_metadata:
        logger.info(f"Agent Caller ID (agent_caller_id_number) found in job metadata: {agent_caller_id_number_from_metadata}")
    else:
        logger.warning("agent_caller_id_number NOT found in job metadata. Outbound call may fail if Caller ID is required by Telnyx.")

    # Récupérer le message d'accueil dynamique depuis les métadonnées
    initial_greeting = dial_info.get("initial_greeting", "Bonjour, ceci est un test de Pam.")

    # --- Récupération Trunk ID --- 
    # Only use metadata, no fallback to environment variable
    final_sip_trunk_id = sip_trunk_id_from_metadata

    if sip_trunk_id_from_metadata:
        logger.info(f"Utilisation du SIP Trunk ID des métadonnées: {final_sip_trunk_id}")
    else:
        logger.error("Aucun SIP Trunk ID fourni via métadonnées. Impossible de passer l'appel SIP.")
        await ctx.room.disconnect()
        return

    # Formater le prompt avec le prénom si possible
    try:
        final_system_prompt = system_prompt_from_metadata.format(first_name=first_name)
        logger.info("Utilisation du prompt système formaté depuis les métadonnées.")
    except KeyError:
        final_system_prompt = system_prompt_from_metadata
        logger.warning("Utilisation du prompt système non formaté depuis les métadonnées (placeholder {first_name} non trouvé ou erreur).")
    except Exception as e:
        logger.error(f"Erreur inattendue lors du formatage du prompt système : {e}")
        final_system_prompt = system_prompt_from_metadata # Fallback au prompt brut

    logger.info(f"Final dial info for agent: {dial_info}")
    logger.info(f"Agent will use name: {first_name}")
    logger.info(f"Dialing number: {phone_number}")

    # --- Configuration et Instanciation Plugins IA ---
    ai_models_config = AIModelConfig() # Start with defaults
    if "ai_models" in dial_info and isinstance(dial_info["ai_models"], dict):
        try:
            # Validate and potentially override defaults with metadata config
            ai_models_config = AIModelConfig(**dial_info["ai_models"])
            logger.info(f"Configuration IA chargée depuis les métadonnées: {ai_models_config.model_dump()}")
        except Exception as e: # More specific validation errors could be caught
            logger.warning(f"Erreur de validation de la configuration IA des métadonnées: {e}. Utilisation des défauts.")
    else:
        logger.warning("Configuration IA non trouvée ou invalide dans les métadonnées. Utilisation des défauts.")

    # Instantiate VAD plugin based on parsed config
    vad_plugin = None
    if ai_models_config.vad.provider == "silero":
        try:
            vad_plugin = silero.VAD.load()
            logger.info(f"Plugin VAD Silero chargé.")
        except Exception as e:
            logger.error(f"Erreur lors du chargement du plugin VAD Silero: {e}")
    else:
        logger.error(f"Fournisseur VAD non supporté: {ai_models_config.vad.provider}")
        # Handle error: maybe default to Silero or raise an error?

    # Instantiate STT plugin based on parsed config
    stt_plugin = None
    if ai_models_config.stt.provider == "deepgram":
        try:
            stt_plugin = deepgram.STT(language=ai_models_config.stt.language, model=ai_models_config.stt.model)
            logger.info(f"Plugin STT Deepgram chargé (lang: {ai_models_config.stt.language}, model: {ai_models_config.stt.model}).")
        except Exception as e:
             logger.error(f"Erreur lors du chargement du plugin STT Deepgram: {e}")
    else:
        logger.error(f"Fournisseur STT non supporté: {ai_models_config.stt.provider}")

    # Instantiate TTS plugin based on parsed config
    tts_plugin = None
    if ai_models_config.tts.provider == "cartesia":
        try:
            tts_plugin = cartesia.TTS(model=ai_models_config.tts.model, voice=ai_models_config.tts.voice_id)
            logger.info(f"Plugin TTS Cartesia chargé (model: {ai_models_config.tts.model}, voice: {ai_models_config.tts.voice_id}).")
        except Exception as e:
             logger.error(f"Erreur lors du chargement du plugin TTS Cartesia: {e}")
    else:
        logger.error(f"Fournisseur TTS non supporté: {ai_models_config.tts.provider}")

    # Instantiate LLM plugin based on parsed config
    llm_plugin = None
    if ai_models_config.llm.provider == "openai":
        try:
            llm_plugin = openai.LLM(model=ai_models_config.llm.model)
            logger.info(f"Plugin LLM OpenAI chargé (model: {ai_models_config.llm.model}).")
        except Exception as e:
             logger.error(f"Erreur lors du chargement du plugin LLM OpenAI: {e}")
    else:
        logger.error(f"Fournisseur LLM non supporté: {ai_models_config.llm.provider}")

    # Check if all necessary plugins were loaded successfully
    if not all([vad_plugin, stt_plugin, tts_plugin, llm_plugin]):
        logger.error("Échec du chargement d'un ou plusieurs plugins IA essentiels. Arrêt de la session.")
        await ctx.room.disconnect()
        return
    # --- Fin Configuration Plugins IA ---

    # -- Agent and Session Setup --

    # ==== DEBUT SUPPRESSION BLOC DE TEST MINIMAL AGENT ====
    # logger.info("Début du bloc de test avec MinimalTestAgent.")

    # class MinimalTestAgent(Agent):
    #     def __init__(self, instructions: str = ""):
    #         super().__init__(instructions=instructions)
    #         logger.info(f"MinimalTestAgent: __init__ appelé avec instructions: '{instructions}'")

    #     async def ainit(self, sess: AgentSession):
    #         logger.info("MinimalTestAgent: Entrée dans ainit()")
    #         await super().ainit(sess)
    #         logger.info("MinimalTestAgent: ainit() terminé.")

    #     async def run(self, room: rtc.Room) -> None:
    #         logger.info("MinimalTestAgent: Entrée dans run()")
    #         try:
    #             logger.info("MinimalTestAgent: Début de la pause de 15 secondes.")
    #             await asyncio.sleep(15) 
    #             logger.info("MinimalTestAgent: Pause de 15s terminée.")
    #         except asyncio.CancelledError:
    #             logger.info("MinimalTestAgent: run() a été annulé pendant la pause.")
    #             raise 
    #         except Exception as e:
    #             logger.error(f"MinimalTestAgent: Erreur dans run(): {e}", exc_info=True)
    #         finally:
    #             logger.info("MinimalTestAgent: run() terminé.")

    # minimal_agent_instance = MinimalTestAgent(instructions="Instructions de test minimales.")
    
    # minimal_session = None
    # try:
    #     if 'tts_plugin' in locals() and tts_plugin:
    #          minimal_session = AgentSession(tts=tts_plugin) 
    #          logger.info("MinimalTestAgent: AgentSession créée AVEC plugin TTS.")
    #     else:
    #          logger.error("MinimalTestAgent: tts_plugin non disponible pour AgentSession minimale. Création SANS plugins.")
    #          minimal_session = AgentSession() 
    # except Exception as e:
    #     logger.error(f"MinimalTestAgent: Erreur lors de la création de AgentSession: {e}", exc_info=True)
    #     await ctx.room.disconnect()
    #     if xano_call_id:
    #         await update_call_status_in_backend(ctx.room.name, "failed_minimal_session_creation", xano_call_id)
    #     return

    # if not minimal_session:
    #     logger.error("MinimalTestAgent: Échec de la création de minimal_session. Arrêt.")
    #     await ctx.room.disconnect()
    #     return
    # ==== FIN SUPPRESSION BLOC DE TEST MINIMAL AGENT ====

    # ++++ DEBUT CREATION AGENT AVEC SUPPORT PATHWAY ++++
    # Create the agent - use WorkflowAgent if pathway is configured, otherwise OutboundCaller
    if PATHWAY_INTEGRATION_AVAILABLE and default_pathway_id:
        logger.info(f"🎯 Creating WorkflowAgent with pathway: {default_pathway_id}")
        
        # Create pathway agent using enhanced multi-agent factory
        try:
            if MULTI_AGENT_FACTORY_AVAILABLE:
                logger.info(f"🎭 Creating multi-agent pathway session for: {default_pathway_id}")
                
                # Prepare customer data for pre-population
                customer_data = {
                    'name': first_name,
                    'phone': phone_number,
                    'call_context': 'outbound',
                    'agent_id': agent_id,
                    'supabase_call_id': supabase_call_id,
                    'dial_info': dial_info
                }
                
                # Create agent using multi-agent factory
                agent, global_context = await factory_create_pathway_agent(
                    pathway_id=default_pathway_id,
                    user_id=user_id,  # Pass user_id for RLS filtering
                    customer_data=customer_data,
                    force_multi_agent=False  # Respect pathway configuration
                )
                
                if agent and global_context:
                    logger.info(f"✅ Created {agent.__class__.__name__} for pathway: {global_context.pathway_name}")
                    logger.info(f"🎯 Multi-agent enabled: {global_context.multi_agent_enabled}")
                    
                    # Store additional metadata for outbound call context
                    if hasattr(agent, 'global_context'):
                        agent.global_context.collected_data.update({
                            'call_type': 'outbound',
                            'agent_config': {
                                'interruption_threshold': interruption_threshold_from_metadata,
                                'initial_greeting': initial_greeting,
                                'wait_for_greeting': wait_for_greeting_from_metadata
                            }
                        })
                else:
                    logger.warning("Multi-agent factory returned None, falling back to legacy method")
                    agent = None
            else:
                logger.info("Multi-agent factory not available, using legacy WorkflowAgent creation")
                agent = None
            
            # Fallback to legacy WorkflowAgent creation if multi-agent failed
            if not agent:
                logger.info(f"🤖 Creating legacy WorkflowAgent for pathway: {default_pathway_id}")
                pathway_config = await load_pathway_config(default_pathway_id)
                
                if pathway_config:
                    logger.info(f"Successfully loaded pathway config: {pathway_config.get('name', 'Unknown')}")
                    
                    # Create legacy WorkflowAgent
                    agent = WorkflowAgent(
                        workflow_config=pathway_config,
                        initial_instructions=final_system_prompt,
                        wait_for_greeting=wait_for_greeting_from_metadata,
                    )
                    
                    # Initialize workflow state with customer context
                    if hasattr(agent, '_workflow_state'):
                        agent._workflow_state.collected_data.update({
                            'customer_name': first_name,
                            'phone_number': phone_number,
                            'call_context': 'outbound',
                            'agent_id': agent_id,
                            'supabase_call_id': supabase_call_id
                        })
                    
                    logger.info(f"✅ Successfully created legacy WorkflowAgent for pathway: {default_pathway_id}")
                else:
                    logger.error(f"Failed to load pathway config for {default_pathway_id}")
                    agent = None
                    
        except Exception as e:
            logger.error(f"Error creating pathway agent: {e}", exc_info=True)
            agent = None
        
        # Fallback to OutboundCaller if pathway agent creation failed
        if not agent:
            logger.warning(f"Failed to create pathway agent, falling back to OutboundCaller")
            agent = OutboundCaller(
                name=first_name, 
                dial_info=dial_info, 
                instructions=final_system_prompt,
                initial_greeting=initial_greeting,
                wait_for_greeting=wait_for_greeting_from_metadata,
                interruption_threshold=interruption_threshold_from_metadata,
            )
        else:
            logger.info(f"✅ Successfully created WorkflowAgent for pathway: {default_pathway_id}")
    else:
        # Create standard OutboundCaller agent (no pathway configured)
        logger.info("Creating standard OutboundCaller (no pathway configured)")
        agent = OutboundCaller(
            name=first_name, 
            dial_info=dial_info, 
            instructions=final_system_prompt,
            initial_greeting=initial_greeting,
            wait_for_greeting=wait_for_greeting_from_metadata,
            interruption_threshold=interruption_threshold_from_metadata,
        )

    # Instantiate the session with dynamically loaded plugins
    logger.info("Instantiating AgentSession with dynamically loaded plugins.")
    try:
        session = AgentSession(
            vad=vad_plugin,
            stt=stt_plugin,
            tts=tts_plugin,
            llm=llm_plugin,
        )
        logger.info("AgentSession created successfully with dynamic plugins.")
    except Exception as e:
        logger.error(f"Failed to create AgentSession with dynamic plugins: {e}", exc_info=True)
        await ctx.room.disconnect()
        if supabase_call_id:
            await update_call_status_in_backend(ctx.room.name, "failed_session_creation", supabase_call_id)
        return
    # ++++ FIN RESTAURATION AGENT NORMAL ++++

    # -- Start Outbound SIP Call --
    logger.info(f"OUTBOUND CALL: Attempting SIP dial to {phone_number} via trunk {final_sip_trunk_id} pour Supabase ID: {supabase_call_id}")

    custom_sip_headers = {}
    if supabase_call_id:
        try:
            client_state_bytes = str(supabase_call_id).encode('utf-8')
            client_state_base64 = base64.b64encode(client_state_bytes).decode('utf-8')
            # Tenter de passer le supabase_call_id via un en-tête SIP que Telnyx pourrait interpréter pour remplir 'client_state' dans les webhooks
            custom_sip_headers["X-Client-State"] = client_state_base64 
            logger.info(f"Préparation de l'en-tête SIP X-Client-State avec valeur (encodée): {client_state_base64}")
        except Exception as e:
            logger.error(f"Erreur lors de l'encodage du supabase_call_id pour l'en-tête SIP: {e}")

        try:
            # Supprimer l'appel à create_telnyx_call
            # local_telnyx_call_control_id = await create_telnyx_call(phone_number, xano_call_id=xano_call_id)
            # if not local_telnyx_call_control_id:
            #     logger.error("Impossible de créer l'appel via Telnyx")
            #     await ctx.room.disconnect()
            #     if xano_call_id:
            #         await update_call_status_in_backend(ctx.room.name, "failed_telnyx_setup", xano_call_id)
            #     return
                
            # telnyx_call_control_id = local_telnyx_call_control_id
            # logger.info(f"Telnyx call_control_id assigné: {telnyx_call_control_id} pour Xano ID: {xano_call_id}")

            if supabase_call_id:
                await update_call_status_in_backend(
                    room_name=ctx.room.name,
                    new_status="dialing",
                    supabase_call_id=supabase_call_id,
                    telnyx_id=None # L'agent ne connaît plus cet ID à ce stade
                )
            
            # participant_metadata_for_sip = json.dumps({"telnyx_call_control_id": telnyx_call_control_id}) # On n'a plus telnyx_call_control_id ici
            participant_metadata_for_sip = json.dumps({"supabase_call_id": str(supabase_call_id)}) # Passer supabase_call_id

            logger.info(f"Appel à ctx.api.sip.create_sip_participant avec phoneNumber: {phone_number}, trunk: {final_sip_trunk_id}, metadata: {participant_metadata_for_sip}")
            
            create_sip_participant_args = {
                "room_name": ctx.room.name,
                "sip_trunk_id": final_sip_trunk_id,
                "sip_call_to": phone_number,
                "participant_identity": "phone_user", # Identité du participant SIP
                "participant_metadata": participant_metadata_for_sip, # Métadonnées pour LiveKit
                "wait_until_answered": True
                # sip_call_to_headers=custom_sip_headers if custom_sip_headers else None # SUPPRIMÉ car non supporté
            }

            # Utiliser agent_caller_id_number_from_metadata s'il est disponible
            # REMOVED: The logic for adding sip_call_from based on agent_caller_id_number_from_metadata
            # as the field is not supported according to documentation. Caller ID must be set at the trunk level.
            # if agent_caller_id_number_from_metadata:
            #     create_sip_participant_args["sip_call_from"] = agent_caller_id_number_from_metadata
            #     logger.info(f"Utilisation de sip_call_from from metadata: {agent_caller_id_number_from_metadata}")
            # else:
            #     logger.warning("sip_call_from will not be set as agent_caller_id_number was not found in metadata.")

            _ = await ctx.api.sip.create_sip_participant(
                api.CreateSIPParticipantRequest(**create_sip_participant_args)
            )
                
            logger.info(f"SIP call presumably answered for {phone_number} (wait_until_answered=True). Waiting for participant 'phone_user' to join.")
            participant = await ctx.wait_for_participant(identity="phone_user")
            logger.info(f"Participant 'phone_user' ({participant.sid}) connected to room {ctx.room.name}.")
            # agent.set_participant(participant) 
            call_connected_time = time.time() # Record connection time

            if supabase_call_id:
                await update_call_status_in_backend(ctx.room.name, "connected", supabase_call_id)

        except api.TwirpError as e:
            logger.error(
                f"Erreur Twirp during SIP call: {e.code} {e.message}, "
                f"SIP Status: {e.metadata.get('sip_status_code')} {e.metadata.get('sip_status')}"
            )
            if supabase_call_id:
                await update_call_status_in_backend(ctx.room.name, "failed_sip_twirp", supabase_call_id, telnyx_id=None)
            # ctx.shutdown() # shutdown might be too aggressive, let entrypoint end.
            await ctx.room.disconnect()
            return
        except asyncio.TimeoutError:
            logger.error("Timeout waiting for participant 'phone_user' to join after SIP call answered.")
            if supabase_call_id:
                await update_call_status_in_backend(ctx.room.name, "failed_sip_timeout", supabase_call_id, telnyx_id=None)
            # ctx.shutdown()
            await ctx.room.disconnect()
            return
        except Exception as e:
            logger.error(f"Unexpected error during SIP call or participant wait: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            if supabase_call_id:
                await update_call_status_in_backend(ctx.room.name, "failed_sip_unexpected", supabase_call_id, telnyx_id=None)
            # ctx.shutdown()
            await ctx.room.disconnect()
            return
    # -- End Outbound SIP Call --

    # SIP call successful and participant joined. Now start the agent session.
    logger.info(f"Call connected (OUTBOUND), participant joined. Starting agent session for supabase_call_id: {supabase_call_id}")

    async def run_session_safely(): 
        final_status = "unknown" # Default status
        try:
            # ++++ MODIFICATION POUR UTILISER AGENT NORMAL ++++
            agent_class_name = agent.__class__.__name__
            logger.info(f"run_session_safely: AVANT appel à session.start() pour supabase_call_id: {supabase_call_id} (UTILISATION DE {agent_class_name} - OUTBOUND CALL)")
            
            await session.start( # Utiliser la session et l'agent restaurés
                agent=agent, 
                room=ctx.room,
            )
            
            # **NEW: Auto-start pathway execution if configured**
            if default_pathway_id and agent_id and supabase_call_id:
                logger.info(f"Auto-starting pathway execution: pathway_id={default_pathway_id}, agent_id={agent_id}, call_id={supabase_call_id}")
                try:
                    pathway_execution_id = await auto_start_pathway_for_new_call(
                        call_id=supabase_call_id,
                        agent_id=agent_id,
                        room_name=ctx.room.name
                    )
                    
                    if pathway_execution_id:
                        logger.info(f"Pathway execution started successfully: {pathway_execution_id}")
                        
                        # Store pathway execution ID in room metadata for real-time tracking
                        await ctx.room.set_metadata(json.dumps({
                            "pathway_execution_id": pathway_execution_id,
                            "pathway_id": default_pathway_id,
                            "call_id": supabase_call_id,
                            "agent_id": agent_id,
                            "call_direction": "outbound"
                        }))
                        
                        # Initialize call event handling
                        event_data = {
                            "timestamp": time.time(),
                            "phone_number": phone_number,
                            "agent_name": first_name,
                            "call_direction": "outbound"
                        }
                        
                        await handle_call_event(supabase_call_id, "call_answered", event_data)
                    else:
                        logger.warning(f"Failed to start pathway execution for call {supabase_call_id}")
                except Exception as e:
                    logger.error(f"Error starting pathway execution: {e}")
            else:
                logger.info("No pathway configured for this agent or missing required IDs")
            
            # ++++ FIN MODIFICATION POUR UTILISER AGENT NORMAL ++++
            
            logger.info(f"run_session_safely: APRÈS appel à session.start() pour supabase_call_id: {supabase_call_id} (OUTBOUND CALL). La session devrait avoir démarré et exécuté la logique de l'agent.")
            logger.info(f"Agent session task finished normally for outbound call supabase_call_id: {supabase_call_id}.")
            final_status = "completed" # Statut pour l'agent normal
        except asyncio.CancelledError:
            logger.info(f"Agent session task cancelled for outbound call supabase_call_id: {supabase_call_id}.")
            final_status = "failed_cancelled_session" 
        except Exception as e:
            logger.critical(f"CRITICAL ERROR in agent session task for outbound call supabase_call_id: {supabase_call_id}: {e}", exc_info=True)
            final_status = "failed_session_exception" 
        finally:
            logger.info(f"Fin du job pour la room {ctx.room.name} (OUTBOUND call, Supabase ID: {supabase_call_id}). Statut final de session: {final_status}")
            
            current_call_duration = None
            # telnyx_call_control_id n'est plus disponible directement dans l'agent pour cette fonction
            # if telnyx_call_control_id: 
            #     current_call_duration = await get_telnyx_call_duration(telnyx_call_control_id)
            
            # On essaie de récupérer la durée via get_telnyx_call_duration SI on avait un ID Telnyx (peu probable maintenant)
            # Sinon, on utilise la durée basée sur call_connected_time
            # Le telnyx_call_control_id à passer ici sera None si l'agent ne l'a pas.
            local_telnyx_id_for_duration = None # L'agent ne gère plus cet ID directement.
            current_call_duration = await get_telnyx_call_duration(local_telnyx_id_for_duration)

            if current_call_duration is None and call_connected_time is not None: 
                current_call_duration = int(time.time() - call_connected_time)
            
            if supabase_call_id: 
                await update_call_status_in_backend(
                    ctx.room.name, 
                    final_status, 
                    supabase_call_id, 
                    current_call_duration,
                    local_telnyx_id_for_duration 
                )
            else:
                logger.error(f"supabase_call_id non disponible dans run_session_safely pour la mise à jour finale du statut.")

    session_task = asyncio.create_task(run_session_safely())
    
    # Wait for the session task to complete. This task now handles its own final status update.
    try:
        await session_task 
        logger.info(f"Session task awaited and completed for supabase_call_id {supabase_call_id}.")
    except Exception as e: # This catches issues with the task creation or if it's cancelled externally before even running
        logger.error(f"Error awaiting session_task for supabase_call_id {supabase_call_id}: {e}", exc_info=True)
        # Ensure a failed status is logged if the session task itself crashes unexpectedly or fails to run
        if supabase_call_id: # Check if supabase_call_id is defined
            # Determine appropriate duration
            current_call_duration = None
            # final_telnyx_id_for_failure = telnyx_call_control_id if 'telnyx_call_control_id' in locals() else None # telnyx_call_control_id n'est plus géré ici
            final_telnyx_id_for_failure = None
            final_call_connected_time = call_connected_time if 'call_connected_time' in locals() else None

            # current_call_duration = await get_telnyx_call_duration(final_telnyx_id_for_failure) # Passera None
            if final_telnyx_id_for_failure: # Ce bloc ne sera probablement pas atteint
                 current_call_duration = await get_telnyx_call_duration(final_telnyx_id_for_failure)
            elif final_call_connected_time: 
                current_call_duration = int(time.time() - final_call_connected_time)

            await update_call_status_in_backend(
                ctx.room.name, 
                "failed_session_task_await", # More specific error
                supabase_call_id,
                current_call_duration,
                final_telnyx_id_for_failure
            )

    # The participant disconnect logic (final check)
    if participant and ctx.room.isconnected(): # Check if room is still connected
        logger.info(f"Setting up to wait for participant '{participant.identity}' to disconnect as a final check...")
        disconnected_future = asyncio.Future()

        # Define the callback inside this scope to capture 'participant' and 'disconnected_future'
        def on_participant_disconnected_callback(p: rtc.RemoteParticipant, room: rtc.Room):
            logger.info(f"Participant {p.identity} disconnected from room {room.name} (Supabase ID: {supabase_call_id}). Reason: {p.disconnect_reason}")
            if p.identity == "phone_user": 
                logger.info(f"Callback: Participant '{p.identity}' disconnected event received.")
                if not disconnected_future.done():
                    disconnected_future.set_result(True)
        
        ctx.room.on("participant_disconnected", on_participant_disconnected_callback)
        
        try:
            logger.info(f"Now waiting for participant '{participant.identity}' to disconnect (final check)...")
            await asyncio.wait_for(disconnected_future, timeout=5.0) # Short timeout, session_task should have handled it
            logger.info(f"Participant '{participant.identity}' disconnected (final check awaited future).")
            
        except asyncio.TimeoutError:
            logger.warning(f"Timeout waiting for participant '{participant.identity}' to disconnect (final check). Session likely already handled by agent logic or session_task.")
        
        except Exception as e: 
            logger.error(f"Error while waiting for participant LiveKit disconnect event (final check): {e}", exc_info=True)
        finally:
            ctx.room.off("participant_disconnected", on_participant_disconnected_callback)
            if not disconnected_future.done(): 
                disconnected_future.cancel()
    else:
        logger.info("No participant was connected, participant object is None, or room already disconnected. Skipping final disconnect wait.")

    # Ensure the room is disconnected before the entrypoint finishes
    if not ctx.room.isconnected():
        logger.info(f"Ensuring room disconnect for supabase_call_id {supabase_call_id} at the end of entrypoint.")
        await ctx.room.disconnect()
    
    logger.info(f"Entrypoint for supabase_call_id {supabase_call_id} completed.")
    # Return is implicitly None


if __name__ == "__main__":
    # Basic logging config for the worker process
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # The launcher script (`agent_launcher.py`) is responsible for setting up the
    # environment, including loading .env files and assigning a dynamic port.
    # This agent script simply reads the final configuration from the environment.

    # Configure worker name for outbound calls
    worker_name = "outbound-caller"

    # Get the http port for the worker from the environment
    http_port = 0  # Worker will auto-select if not provided or invalid
    http_port_str = os.getenv("LIVEKIT_AGENT_HTTP_PORT")
    if http_port_str:
        try:
            http_port = int(http_port_str)
        except (ValueError, TypeError):
            logging.error(f"Invalid LIVEKIT_AGENT_HTTP_PORT: '{http_port_str}'. Worker will use default port.")

    logging.info(f"Starting LiveKit Worker '{worker_name}' on port {http_port or 'default'}")

    # Define the worker options
    opts = WorkerOptions(
        entrypoint_fnc=entrypoint,
        agent_name=worker_name,
        port=http_port,  # Pass the dynamically assigned port here
    )

    # Run the agent using the standard LiveKit CLI runner
    try:
        cli.run_app(opts)
    except Exception as e:
        logging.critical(f"Failed to run the agent worker: {e}", exc_info=True)
        sys.exit(1)
