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

# ===== ULTIMATE POWERSHELL LOGGING FIX =====
# This must be applied BEFORE any other imports or logging setup
import threading
from typing import TextIO


def setup_ultimate_powershell_logging():
    """Apply comprehensive fixes for PowerShell logging issues"""
    print("[LOGGING] Applying ultimate PowerShell logging fixes...")

    # 1. FORCE UNBUFFERED OUTPUT AT OS LEVEL
    if sys.platform == 'win32':
        os.environ['PYTHONUNBUFFERED'] = '1'
        os.environ['PYTHONIOENCODING'] = 'utf-8'
        os.environ['PYTHONDONTWRITEBYTECODE'] = '1'

        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(
    encoding='utf-8',
    errors='replace',
     line_buffering=True)
            sys.stderr.reconfigure(
    encoding='utf-8',
    errors='replace',
     line_buffering=True)

        sys.stdout = ForceFlushingTextIO(sys.stdout)
        sys.stderr = ForceFlushingTextIO(sys.stderr)

    # 2. CLEAR ALL EXISTING HANDLERS
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    for name in logging.Logger.manager.loggerDict:
        logger = logging.getLogger(name)
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)

    # 3. CREATE POWERSHELL-OPTIMIZED HANDLER
    handler = PowerShellCompatibleHandler()
    handler.setLevel(logging.INFO)

    formatter = logging.Formatter(
        fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    handler.setFormatter(formatter)

    # 4. APPLY TO ROOT LOGGER
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(handler)

    # 5. START PERSISTENT LOGGING MONITOR
    start_logging_monitor()

    print("[LOGGING] Ultimate PowerShell logging fix completed!")


def start_logging_monitor():
    """Start a background thread that continuously enforces logging configuration"""
    global _logging_monitor_active
    _logging_monitor_active = True

    def monitor_logging():
        """Background thread that enforces logging configuration every 2 seconds"""
        while _logging_monitor_active:
            try:
                # Check if our handler is still present
                root_logger = logging.getLogger()
                has_powershell_handler = any(
    isinstance(
        h, PowerShellCompatibleHandler) for h in root_logger.handlers)

                if not has_powershell_handler:
                    print("[LOGGING MONITOR] Reapplying logging fix...")
                    reapply_logging_fix()

                # Also ensure key loggers have our handler
                for logger_name in [
    'livekit.agents',
    'outbound-caller',
     'pathway_global_context']:
                    logger_obj = logging.getLogger(logger_name)
                    has_handler = any(
    isinstance(
        h, PowerShellCompatibleHandler) for h in logger_obj.handlers)
                    if not has_handler:
                        handler = PowerShellCompatibleHandler()
                        handler.setLevel(logging.INFO)
                        formatter = logging.Formatter(
                            fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                            datefmt='%Y-%m-%d %H:%M:%S'
                        )
                        handler.setFormatter(formatter)
                        logger_obj.addHandler(handler)
                        logger_obj.setLevel(logging.INFO)

            except Exception as e:
                print(f"[LOGGING MONITOR ERROR] {e}")

            time.sleep(2)  # Check every 2 seconds

    monitor_thread = threading.Thread(target=monitor_logging, daemon=True)
    monitor_thread.start()
    print("[LOGGING] Started persistent logging monitor")


def stop_logging_monitor():
    """Stop the logging monitor"""
    global _logging_monitor_active
    _logging_monitor_active = False


# Global flag for logging monitor
_logging_monitor_active = False


def reapply_logging_fix():
    """Re-apply logging fix - call this after LiveKit initialization"""
    print("[LOGGING] Re-applying PowerShell logging fix after LiveKit...")

    # Clear any handlers LiveKit may have added
    root_logger = logging.getLogger()
    livekit_handlers = []
    for handler in root_logger.handlers[:]:
        if not isinstance(handler, PowerShellCompatibleHandler):
            livekit_handlers.append(handler)
            root_logger.removeHandler(handler)

    # Ensure our PowerShell handler is present
    has_powershell_handler = any(isinstance(
        h, PowerShellCompatibleHandler) for h in root_logger.handlers)
    if not has_powershell_handler:
        handler = PowerShellCompatibleHandler()
        handler.setLevel(logging.INFO)
        formatter = logging.Formatter(
            fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        handler.setFormatter(formatter)
        root_logger.addHandler(handler)

    # Also apply to LiveKit loggers specifically
    for logger_name in [
    'livekit.agents',
    'livekit.rtc',
    'outbound-caller',
     'workflow-agent']:
        logger = logging.getLogger(logger_name)
        logger.handlers.clear()
        handler = PowerShellCompatibleHandler()
        handler.setLevel(logging.INFO)
        formatter = logging.Formatter(
            fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

    print("[LOGGING] PowerShell logging fix re-applied!")

class ForceFlushingTextIO:
    """Wrapper that forces immediate flushing for PowerShell compatibility"""
    
    def __init__(self, wrapped_stream: TextIO):
        self._wrapped = wrapped_stream
        
    def write(self, text):
        try:
            result = self._wrapped.write(text)
            self._wrapped.flush()
            return result
        except Exception:
            return self._wrapped.write(text)
    
    def flush(self):
        try:
            self._wrapped.flush()
        except Exception:
            pass
    
    def __getattr__(self, name):
        return getattr(self._wrapped, name)

class PowerShellCompatibleHandler(logging.StreamHandler):
    """Logging handler optimized for PowerShell compatibility"""
    
    def __init__(self):
        super().__init__(sys.stderr)
        self._lock = threading.Lock()
    
    def emit(self, record):
        """Emit a record with PowerShell-specific optimizations"""
        with self._lock:
            try:
                msg = self.format(record)
                stream = self.stream
                stream.write(msg + '\n')
                stream.flush()
                
                if sys.platform == 'win32' and hasattr(stream, 'fileno'):
                    try:
                        os.fsync(stream.fileno())
                    except (OSError, AttributeError):
                        pass
                        
            except Exception as e:
                try:
                    print(f"LOGGING ERROR: {e}")
                    print(f"ORIGINAL MESSAGE: {record.getMessage()}")
                except:
                    pass

# APPLY THE FIX IMMEDIATELY
setup_ultimate_powershell_logging()

# Forcer l'encodage UTF-8 pour Windows (legacy support)
if sys.platform == 'win32':
    try:
        locale.setlocale(locale.LC_ALL, 'fr_FR.UTF-8')
    except locale.Error:
        try:
            locale.setlocale(locale.LC_ALL, 'French_France.1252')
        except locale.Error:
            pass

# ===== END LOGGING FIX =====

# Configuration du logger principal
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
# Load API environment for OAuth encryption key (must match backend)
load_dotenv(find_dotenv('../api/.env'), override=True)

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

# ✅ Import database client BEFORE other imports
try:
    # Import the supabase client - using relative import since we're in agents/ folder
    import sys
    sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'api'))
    from db_client import supabase_service_client
    logger.info("✅ Supabase client imported successfully")
except Exception as e:
    logger.error(f"❌ Failed to import supabase client: {e}")
    supabase_service_client = None

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
    metrics,
    MetricsCollectedEvent,
)
from livekit.plugins import (
    openai,
    cartesia,
    elevenlabs,
    silero,
    deepgram,
)
from livekit.agents.llm import ChatMessage
from pydantic import BaseModel, Field
from typing import AsyncIterable
from voice_adaptation_manager import VoiceAdaptationManager


class MetricsAggregator:
    """Aggregates metrics by speech_id to build complete turn metrics"""
    
    def __init__(self):
        self.metrics_by_speech_id = {}
        
    def add_metric(self, metric):
        """Add a metric to the aggregator"""
        speech_id = getattr(metric, 'speech_id', None)
        if not speech_id:
            return
            
        if speech_id not in self.metrics_by_speech_id:
            self.metrics_by_speech_id[speech_id] = {}
            
        metrics_dict = self.metrics_by_speech_id[speech_id]
        
        if isinstance(metric, metrics.STTMetrics):
            metrics_dict['stt'] = {
                'audio_duration': metric.audio_duration,
                'duration': metric.duration,
                'streamed': metric.streamed
            }
        elif isinstance(metric, metrics.EOUMetrics):
            metrics_dict['eou'] = {
                'transcription_delay': metric.transcription_delay,
                'end_of_utterance_delay': metric.end_of_utterance_delay,
                'on_user_turn_completed_delay': getattr(metric, 'on_user_turn_completed_delay', 0)
            }
        elif isinstance(metric, metrics.LLMMetrics):
            metrics_dict['llm'] = {
                'ttft': metric.ttft,
                'duration': metric.duration,
                'tokens_per_second': getattr(metric, 'tokens_per_second', 0),
                'completion_tokens': getattr(metric, 'completion_tokens', 0),
                'prompt_tokens': getattr(metric, 'prompt_tokens', 0),
                'prompt_cached_tokens': getattr(metric, 'prompt_cached_tokens', 0),
                'total_tokens': getattr(metric, 'total_tokens', 0)
            }
        elif isinstance(metric, metrics.TTSMetrics):
            metrics_dict['tts'] = {
                'ttfb': metric.ttfb,
                'duration': metric.duration,
                'audio_duration': metric.audio_duration,
                'streamed': getattr(metric, 'streamed', False),
                'characters_count': getattr(metric, 'characters_count', 0)
            }
    
    def get_turn_summary(self, speech_id: str) -> dict:
        """Get a complete turn summary for a speech_id"""
        if speech_id not in self.metrics_by_speech_id:
            return {}
            
        turn_data = self.metrics_by_speech_id[speech_id]
        
        # Calculate total conversation latency
        total_latency = 0
        if 'eou' in turn_data and 'llm' in turn_data and 'tts' in turn_data:
            total_latency = (
                turn_data['eou']['end_of_utterance_delay'] +
                turn_data['llm']['ttft'] +
                turn_data['tts']['ttfb']
            )
        
        return {
            'speech_id': speech_id,
            'stt_final_latency': turn_data.get('eou', {}).get('transcription_delay', 0),
            'stt_audio_duration': turn_data.get('stt', {}).get('audio_duration', 0),
            'stt_streamed': turn_data.get('stt', {}).get('streamed', False),
            'llm_ttft': turn_data.get('llm', {}).get('ttft', 0),
            'llm_total': turn_data.get('llm', {}).get('duration', 0),
            'llm_tokens_per_sec': turn_data.get('llm', {}).get('tokens_per_second', 0),
            'llm_data': turn_data.get('llm', {}),  # Include full LLM data for detailed analysis
            'tts_ttfb': turn_data.get('tts', {}).get('ttfb', 0),
            'tts_total': turn_data.get('tts', {}).get('duration', 0),
            'tts_audio_duration': turn_data.get('tts', {}).get('audio_duration', 0),
            'tts_data': turn_data.get('tts', {}),  # Include full TTS data for detailed analysis
            'total_conversation_latency': total_latency,
            'complete': len(turn_data) >= 3  # STT+LLM+TTS or EOU+LLM+TTS
        }

# RE-APPLY LOGGING FIX AFTER LIVEKIT IMPORTS
reapply_logging_fix()

# Add the missing import for PathwaySessionData and PathwayNodeAgent
from pathway_global_context import PathwaySessionData, PathwayNodeAgent

# At the top of the file, add WorkflowAgent import
from workflow_agent import WorkflowAgent, load_pathway_config

# --- Voice Adaptation Helper ---
async def say_with_voice_adaptation(
    sess: AgentSession,
    manager: VoiceAdaptationManager,
    text_or_stream: Any,
    *,
    stage: str | None = None,
    analysis_text: str | None = None,
    allow_interruptions_default: bool = True,
) -> None:
    try:
        base_text = analysis_text if analysis_text is not None else (text_or_stream if isinstance(text_or_stream, str) else "")
        decision = manager.decide(base_text, stage=stage or "conversation")
        delay = decision.timing.pre_speech_delay_sec
        if delay > 0:
            await asyncio.sleep(delay)
        allow_interruptions = decision.voice_settings.allow_interruptions
        logger.info(
            f"VoiceAdapt decision: stage={stage} speed={decision.voice_settings.speed} "
            f"delay={delay}s interruptions={allow_interruptions} emotions={decision.voice_settings.emotions}"
        )
    except Exception:
        allow_interruptions = allow_interruptions_default
    await sess.say(text_or_stream, allow_interruptions=allow_interruptions)

# Import multi-agent pathway factory for enhanced agent creation
# try:
#     logger.info("Attempting to import multi-agent pathway factory...")
#     from pathway_agent_factory import create_pathway_agent, create_legacy_pathway_agent
#     MULTI_AGENT_FACTORY_AVAILABLE = True
#     logger.info("✅ Multi-agent pathway factory imported successfully in outbound_agent")
# except ImportError as e:
#     MULTI_AGENT_FACTORY_AVAILABLE = False
#     logger.error(f"Failed to import multi-agent factory in outbound_agent: {e}", exc_info=True)
#     # Fallback functions
#     async def create_pathway_agent(*args, **kwargs):
#         return None, None
    
#     async def create_legacy_pathway_agent(*args, **kwargs):
#         return None

# --- Répliquer les modèles Pydantic (ou importer d'un fichier commun) ---
class VADConfig(BaseModel):
    provider: str = "silero"

class STTConfig(BaseModel):
    provider: str = "deepgram"  # Default to Deepgram
    language: str = "fr"        # Default to French
    model: str = "nova-3"       # Deepgram's fastest and most accurate model

class TTSConfig(BaseModel):
    provider: str = "cartesia"
    model: str = "sonic-turbo-2025-03-07"  # Default to sonic-turbo for speed
    voice_id: str = "65b25c5d-ff07-4687-a04c-da2f43ef6fa9"

class LLMConfig(BaseModel):
    provider: str = "openai"
    model: str = "gpt-4o-mini"  # GPT-4o-mini for better performance

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
    # First try from current directory
    current_dir = os.path.dirname(__file__)
    if current_dir not in sys.path:
        sys.path.insert(0, current_dir)
    
    import workflow_agent
    from workflow_agent import WorkflowAgent
    
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
        
        # Store the name for use in methods
        self.name = name
        
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
        
        # RE-APPLY LOGGING FIX FOR CALL EXECUTION
        reapply_logging_fix()
        logger.info("LOGGING FIX RE-APPLIED FOR CALL EXECUTION")
        
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
        
        # ✅ CRITICAL: FORCE LOGGING FIX AT CALL START
        print("[CALL] ENFORCING LOGGING FIX AT CALL START")
        reapply_logging_fix()
        logger.info("✅ LOGGING FIX ENFORCED AT CALL START")
        
        # ✅ DIRECT CONSOLE OUTPUT - BYPASSES ALL LOGGING SYSTEMS
        print("=" * 60)
        print("🎯 AGENT RUN METHOD STARTED - CALL EXECUTION BEGINNING", flush=True)
        print("=" * 60)
        
        logger.info("ENTERING OutboundCaller.run - TOP OF METHOD")
        sess = self._session
        if not sess:
            print("❌ ERROR: Agent session not found in agent.run(), cannot proceed.")
            logger.error("Agent session not found in agent.run(), cannot proceed.")
            return

        print(f"✅ Agent session found: {type(sess)}", flush=True)

        # Initialize pathway integration if available
        pathway_execution_id = None
        if PATHWAY_INTEGRATION_AVAILABLE:
            print("🔄 Initializing pathway integration...", flush=True)
            try:
                # Extract pathway information from metadata
                job_ctx = get_job_context()
                raw_metadata = job_ctx.job.metadata
                metadata = json.loads(raw_metadata) if raw_metadata else {}
                
                call_id = metadata.get("supabase_call_id")
                agent_id = metadata.get("agent_id")
                
                print(f"📋 Call metadata: call_id={call_id}, agent_id={agent_id}", flush=True)
                
                if call_id and agent_id:
                    # Auto-start pathway for this call
                    pathway_execution_id = await auto_start_pathway_for_new_call(
                        call_id=str(call_id),
                        agent_id=int(agent_id),
                        session_metadata={"room_name": room.name}
                    )
                    if pathway_execution_id:
                        print(f"✅ Pathway execution started: {pathway_execution_id}", flush=True)
                        logger.info(f"Pathway execution started: {pathway_execution_id}")
                        
                        # Send call answered event
                        await handle_call_event("call_answered", str(call_id), {
                            "room_name": room.name,
                            "agent_id": agent_id,
                            "timestamp": time.time()
                        })
                        print(f"📞 Call answered event sent", flush=True)
                    else:
                        print("ℹ️ No default pathway found for this agent", flush=True)
                        logger.info("No default pathway found for this agent")
                else:
                    print("⚠️ Missing call_id or agent_id in metadata - pathway integration disabled", flush=True)
                    logger.warning("Missing call_id or agent_id in metadata - pathway integration disabled")
            except Exception as e:
                print(f"❌ Error initializing pathway integration: {e}", flush=True)
                logger.error(f"Error initializing pathway integration: {e}")
                pathway_execution_id = None
        else:
            print("⚠️ Pathway integration not available", flush=True)

        print("🎙️ Handling initial greeting...", flush=True)

        # === PHASE 5: BIDIRECTIONAL GREETING LOGIC ===
        # Check if this is an inbound call
        job_ctx = get_job_context()
        metadata = json.loads(job_ctx.job.metadata) if job_ctx.job.metadata else {}
        is_inbound = metadata.get("is_inbound_call", False)

        if is_inbound:
            # === INBOUND CALL GREETING ===
            print(f"📞 INBOUND call detected - fetching greeting from pathway/database")
            logger.info(f"INBOUND call detected - fetching greeting from pathway/database")
            
            # Get pathway session data (already loaded in entrypoint)
            session_data = sess.userdata if hasattr(sess, 'userdata') else None
            
            if session_data and hasattr(session_data, 'pathway_config'):
                # Try to get greeting from current pathway node
                current_node_id = session_data.current_node_id
                pathway_config = session_data.pathway_config
                
                greeting_text = None
                
                # Look for greeting in current node or find greeting/conversation node
                if current_node_id and pathway_config:
                    current_node = next((node for node in pathway_config.get('nodes', []) if node.get('id') == current_node_id), None)
                    if current_node:
                        # Try to get greeting from node's agent instructions or specific greeting field
                        node_data = current_node.get('data', {})
                        greeting_text = node_data.get('greeting') or node_data.get('initialMessage')
                        
                # Fallback: look for any greeting/conversation node
                if not greeting_text and pathway_config:
                    for node in pathway_config.get('nodes', []):
                        if node.get('type') in ['conversation', 'greeting']:
                            node_data = node.get('data', {})
                            greeting_text = node_data.get('greeting') or node_data.get('initialMessage')
                            if greeting_text:
                                break
                
                if greeting_text:
                    try:
                        await sess.say(greeting_text, allow_interruptions=True)
                        print("✅ Pathway greeting delivered for inbound call.", flush=True)
                        logger.info("Pathway greeting delivered for inbound call.")
                    except Exception as e:
                        print(f"❌ Error delivering pathway greeting: {e}", flush=True)
                        logger.error(f"Error delivering pathway greeting: {e}")
                else:
                    print("⚠️ No greeting found in pathway - using agent default instructions", flush=True)
                    logger.warning("No greeting found in pathway - using agent default instructions")
            else:
                print("⚠️ No pathway data available for inbound greeting - using agent instructions", flush=True)
                logger.warning("No pathway data available for inbound greeting")

        else:
            # === OUTBOUND CALL GREETING (EXISTING LOGIC UNCHANGED) ===
            print(f"📞 OUTBOUND call detected - using existing greeting logic")
            logger.info(f"OUTBOUND call detected - using existing greeting logic")

        # Handle initial greeting based on wait_for_greeting setting
        if self.wait_for_greeting:
            print(f"⏳ Agent '{self.name}' configured to wait for user greeting first")
            logger.info(f"Agent '{self.name}' configured to wait for user greeting first")
            # Wait for user input first, then deliver greeting
            try:
                print("👂 Waiting for user to speak first...")
                logger.info("Waiting for user to speak first...")
                async for user_input in sess.user_input():
                    if not user_input.is_final:
                        continue
                    
                    print(f"👤 User spoke first: '{user_input.text}'. Now delivering initial greeting.")
                    logger.info(f"User spoke first: '{user_input.text}'. Now delivering initial greeting.")
                    
                    # Deliver initial greeting as response to user's first input
                    if self.initial_greeting:
                        await sess.say(self.initial_greeting, allow_interruptions=True)
                        print("✅ Initial greeting delivered after user spoke.", flush=True)
                        logger.info("Initial greeting delivered after user spoke.")
                    
                    # Continue with normal conversation flow
                    break
                    
            except Exception as e:
                print(f"❌ Error while waiting for user greeting: {e}", flush=True)
                logger.error(f"Error while waiting for user greeting: {e}")
                # Fallback: deliver greeting anyway
                if self.initial_greeting:
                    await sess.say(self.initial_greeting, allow_interruptions=True)
        else:
            # Standard behavior: deliver greeting immediately
            if self.initial_greeting:
                print(f"🎙️ Agent '{self.name}' delivering immediate greeting: '{self.initial_greeting}'")
                logger.info(f"Agent '{self.name}' delivering immediate greeting: '{self.initial_greeting}'")
                try:
                    await say_with_voice_adaptation(sess, voice_adapt, self.initial_greeting, stage="greeting", analysis_text=self.initial_greeting, allow_interruptions_default=True)
                    print("✅ Initial greeting delivered immediately.", flush=True)
                    logger.info("Initial greeting delivered immediately.")
                except Exception as e:
                    print(f"❌ Error delivering initial greeting: {e}", flush=True)
                    logger.error(f"Error delivering initial greeting: {e}")
            else:
                print("ℹ️ No initial greeting to deliver.", flush=True)
                logger.info("No initial greeting to deliver.")

        # Main conversation loop
        logger.info(f"Agent '{self.name}' entering main conversation loop.")
        
        # ✅ FINAL LOGGING ENFORCEMENT BEFORE CONVERSATION LOOP
        reapply_logging_fix()
        logger.info("✅ FINAL LOGGING FIX ENFORCED BEFORE CONVERSATION")
        
        print("🔄 ENTERING MAIN CONVERSATION LOOP", flush=True)
        print("👂 Listening for user input...", flush=True)
        
        try:
            async for user_input in sess.user_input():
                if not user_input.is_final:
                    continue # Attendre la transcription finale

                print(f"👤 USER SAID: '{user_input.text}'", flush=True)
                logger.info(f"User said: '{user_input.text}'")
                
                # Send speech detection event to pathway
                if PATHWAY_INTEGRATION_AVAILABLE and pathway_execution_id:
                    print("📡 Sending speech event to pathway...", flush=True)
                    try:
                        job_ctx = get_job_context()
                        metadata = json.loads(job_ctx.job.metadata) if job_ctx.job.metadata else {}
                        call_id = metadata.get("supabase_call_id")
                        
                        if call_id:
                            await handle_call_event("speech_detected", str(call_id), {
                                "text": user_input.text,
                                "confidence": getattr(user_input, 'confidence', 1.0),
                                "timestamp": time.time()
                            })
                            print("✅ Speech event sent to pathway", flush=True)
                    except Exception as e:
                        print(f"❌ Error sending speech event to pathway: {e}", flush=True)
                        logger.error(f"Error sending speech event to pathway: {e}")
                
                # Pour une conversation simple, l'historique peut juste être le dernier message utilisateur.
                # Pour des conversations plus complexes, vous géreriez un historique plus long.
                history = [ChatMessage(role="user", content=user_input.text)]
                
                print(f"🤖 Sending to LLM with history: {[msg.content for msg in history]}", flush=True)
                logger.info(f"Sending to LLM with history: {history}")
                # Le system_prompt est déjà défini au niveau de l'Agent (super().__init__(instructions=...))
                # et devrait être utilisé par le plugin LLM.
                llm_stream = await sess.llm.chat(history=history) 
                
                print("🎙️ Streaming LLM response to TTS...", flush=True)
                logger.info("Streaming LLM response to TTS.")
                # Use interruption threshold setting with voice adaptation
                allow_interruptions = True if self.interruption_threshold > 0 else False
                await say_with_voice_adaptation(sess, voice_adapt, llm_stream, stage="conversation", analysis_text=user_input.text, allow_interruptions_default=allow_interruptions)
                print("✅ Agent finished responding to user input.", flush=True)
                logger.info("Agent finished responding to user input.")
        except asyncio.CancelledError:
            print(f"⚠️ Agent run loop for '{self.name}' cancelled.", flush=True)
            logger.info(f"Agent run loop for '{self.name}' cancelled.")
        except Exception as e:
            print(f"❌ Error in agent run loop for '{self.name}': {e}", flush=True)
            logger.error(f"Error in agent run loop for '{self.name}': {e}", exc_info=True)
        finally:
            print(f"🏁 Agent run loop for '{self.name}' finished.", flush=True)
            logger.info(f"Agent run loop for '{self.name}' finished.")
        
        print("🚪 Exiting OutboundCaller.run after conversation loop.", flush=True)
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
    """
    Entry point for the outbound calling agent
    """
    print("🚀 ENTRYPOINT CALLED - OUTBOUND AGENT STARTING", flush=True)
    
    # ✅ INITIALIZE session_start_agent early to avoid UnboundLocalError
    session_start_agent = None
    session = None
    
    logger.info(f"📞 Outbound Agent entrypoint called")
    
    # ✅ EXTRACT CALL_ID FROM ROOM NAME (for outbound calls)
    call_id = None
    try:
        # Try to extract call_id from room name like "agent-call-123"
        if ctx.room.name.startswith("agent-call-"):
            call_id = int(ctx.room.name.split('-')[-1])
            print(f"📋 Starting entrypoint for supabase_call_id: {call_id}", flush=True)
            logger.info(f"Starting entrypoint for supabase_call_id: {call_id}")
        else:
            # This is an inbound call with room name like "call_+33661329235_fqCVoDYpu8b9"
            print(f"📞 Inbound call detected with room name: {ctx.room.name}", flush=True)
            logger.info(f"Inbound call detected with room name: {ctx.room.name}")
            call_id = None  # No supabase call_id for inbound calls
    except (ValueError, IndexError) as e:
        print(f"⚠️ Could not extract supabase_call_id from room name '{ctx.room.name}': {e}", flush=True)
        logger.warning(f"Could not extract supabase_call_id from room name '{ctx.room.name}': {e}")
        # Continue anyway - this might be an inbound call
        call_id = None
        
    # ✅ EXTRACT METADATA AND DIAL_INFO
    dial_info = {}
    if not ctx.job.metadata:
        # For inbound calls, no metadata is expected
        if call_id is None:
            print("📞 Inbound call: No metadata expected, proceeding...", flush=True)
            logger.info("Inbound call: No metadata expected, proceeding...")
        else:
            logger.error("No job metadata provided. Cannot proceed with outbound call.")
            return

    # Extract call details from job metadata
    metadata = {}
    if ctx.job.metadata:
        import json
        try:
            metadata = json.loads(ctx.job.metadata)
            dial_info = metadata.get("dial_info", {})
            logger.info(f"📋 Extracted dial_info: {dial_info}")
        except (json.JSONDecodeError, ValueError) as e:
            print(f"⚠️ Invalid JSON in metadata: {e}, using empty metadata", flush=True)
            logger.warning(f"Invalid JSON in metadata: {e}, using empty metadata")
            metadata = {}
            dial_info = {}
    else:
        dial_info = {}
        
    # === PHASE 5: CALL DIRECTION DETECTION ===
    # Check for phone number in dial_info (outbound) or top-level metadata (inbound)
    outbound_phone = dial_info.get("phone_number")
    inbound_phone = metadata.get("phone_number")
    
    if outbound_phone:
        # OUTBOUND CALL: Has target phone number in dial_info
        is_inbound_call = False
        logger.info(f"🔄 OUTBOUND call detected - dialing {outbound_phone}")
    elif inbound_phone:
        # INBOUND CALL: Has phone number in top-level metadata (bidirectional agent style)
        is_inbound_call = False
        logger.info(f"🔄 OUTBOUND call detected - dialing {inbound_phone} (bidirectional style)")
    else:
        # INBOUND CALL: No target phone number anywhere
        is_inbound_call = True
        logger.info("📞 INBOUND call detected - customer already connected")

    # Store direction in metadata for agent access
    metadata["is_inbound_call"] = is_inbound_call
    if ctx.job.metadata:
        ctx.job.metadata = json.dumps(metadata)
    
    # ✅ FIRST: Connect to the room
    await ctx.connect()
    logger.info("✅ Connected to LiveKit room")
    
    # RE-APPLY LOGGING FIX AFTER LIVEKIT CONNECTION
    reapply_logging_fix()
    logger.info("✅ Logging fix re-applied after LiveKit connection")
    
    # ✅ INBOUND CALL SETUP - MUST RUN BEFORE AI MODEL CONFIGURATION
    if is_inbound_call:
        print("🔍 UNIVERSAL AGENT: Waiting for SIP participant to extract receiving phone number...", flush=True)
        logger.info("UNIVERSAL AGENT: Waiting for SIP participant to extract receiving phone number...")
        
        # Wait for SIP participant to connect and extract receiving phone number
        receiving_phone_number = None
        
        # Wait for participant connection to get SIP details
        print("👂 Waiting for SIP participant to connect...", flush=True)
        participant = await ctx.wait_for_participant()
        
        if participant.kind == rtc.ParticipantKind.PARTICIPANT_KIND_SIP:
            print(f"🔍 SIP participant detected - extracting receiving number...", flush=True)
            logger.info(f"SIP participant attributes: {participant.attributes}")
            
            # Extract receiving phone number (DNIS) from SIP participant attributes
            for attr_key in ["sip.trunkPhoneNumber", "sip_call_to", "call_to", "dnis", "to", "called_number"]:
                if attr_key in participant.attributes:
                    receiving_phone_number = participant.attributes[attr_key]
                    print(f"📱 Found receiving phone number: {receiving_phone_number} (from {attr_key})", flush=True)
                    logger.info(f"Found receiving phone number: {receiving_phone_number} (from {attr_key})")
                    break
            
            if receiving_phone_number:
                # Get inbound agent ID from phone number
                inbound_agent_id = await get_inbound_agent_id_for_phone_number(receiving_phone_number)
                
                if inbound_agent_id:
                    print(f"✅ Found inbound agent ID: {inbound_agent_id} for {receiving_phone_number}", flush=True)
                    logger.info(f"Found inbound agent ID: {inbound_agent_id} for {receiving_phone_number}")
                    
                    # Create call record in database for this inbound call
                    inbound_call_id = await create_inbound_call_record(
                        receiving_phone_number=receiving_phone_number,
                        caller_phone_number=participant.attributes.get("sip.phoneNumber"),
                        agent_id=inbound_agent_id,
                        room_name=ctx.room.name
                    )
                    
                    if inbound_call_id:
                        print(f"📞 Created inbound call record: {inbound_call_id}", flush=True)
                        logger.info(f"Created inbound call record: {inbound_call_id}")
                        
                        # Load agent's AI model configuration from database
                        agent_ai_config = await load_agent_ai_models(inbound_agent_id)
                        
                        # Update metadata to include call info for pathway system
                        metadata.update({
                            "supabase_call_id": inbound_call_id,
                            "agent_id": inbound_agent_id,
                            "ai_models": agent_ai_config,  # ✅ ADD AGENT'S AI CONFIG
                            "dial_info": {
                                "agent_id": inbound_agent_id,
                                "phone_number": receiving_phone_number  # For compatibility
                            }
                        })
                        
                        # Set call_id so pathway system kicks in
                        call_id = inbound_call_id
                        print(f"🔄 Inbound call will use pathway system with call_id: {call_id}", flush=True)
                        logger.info(f"Inbound call will use pathway system with call_id: {call_id}")
                    else:
                        print(f"❌ Failed to create call record for {receiving_phone_number}", flush=True)
                        logger.error(f"Failed to create call record for {receiving_phone_number}")
                else:
                    print(f"❌ No agent configuration found for {receiving_phone_number} - using fallback", flush=True)
                    logger.warning(f"No agent configuration found for {receiving_phone_number} - using fallback")
            else:
                print("⚠️ Could not extract receiving phone number from SIP participant attributes", flush=True)
                logger.warning("Could not extract receiving phone number from SIP participant attributes")
                print(f"Available attributes: {list(participant.attributes.keys())}", flush=True)

    # ✅ CONFIGURE AI MODELS FROM JOB METADATA (AFTER INBOUND CALL SETUP)
    logger.info("Configuring AI models from job metadata...")
    
    ai_models = metadata.get("ai_models", {})
    
    # Configure VAD (Voice Activity Detection)
    vad = silero.VAD.load()
    
    # Configure STT (Speech-to-Text) - will be updated after voice config
    stt_config = ai_models.get("stt", {})
    
    # Configure TTS (Text-to-Speech) with dynamic provider support
    tts_config = ai_models.get("tts", {})
    voice_id = tts_config.get("voice_id", "65b25c5d-ff07-4687-a04c-da2f43ef6fa9")
    
    # Get complete voice configuration (provider, language, model)
    voice_config = await get_voice_configuration(voice_id)
    tts_provider = voice_config["provider"]
    voice_language = voice_config["language"]
    voice_model = voice_config["model"]
    voice_name = voice_config["voice_name"]
    
    if tts_provider == "elevenlabs":
        print(f"🎙️ Using ElevenLabs TTS with voice: {voice_name} ({voice_id}) - {voice_language}", flush=True)
        
        # Configure ElevenLabs voice settings - Optimized for natural human-like speech
        voice_settings = elevenlabs.VoiceSettings(
            stability=0.35,         # 35% stability (more natural variation, less robotic)
            similarity_boost=0.55,  # 55% similarity (less rigid matching)
            style=0.6,              # 60% style (more expressive, human-like)
            use_speaker_boost=True, # Enhanced clarity
            speed=1.05              # 105% speed (slightly faster, conversational)
        )
        
        tts = elevenlabs.TTS(
            voice_id=voice_id,
            model=voice_model,  # Use dynamic model from voice config
            voice_settings=voice_settings
        )
    else:
        # Use Cartesia with sonic-turbo for French language
        print(f"🎙️ Using Cartesia TTS with voice: {voice_name} ({voice_id}) - {voice_language}", flush=True)
        # Use sonic-turbo for French language, upgrade other models if needed
        if voice_language == "fr":
            final_cartesia_model = "sonic-turbo-2025-03-07"  # Turbo model for French
            print(f"🚀 Using Cartesia Sonic Turbo for French: {final_cartesia_model}", flush=True)
        else:
            final_cartesia_model = voice_model
            if final_cartesia_model == "sonic-2":
                final_cartesia_model = "sonic-2-2025-03-07"
        
        tts = cartesia.TTS(
            model=final_cartesia_model,
            voice=voice_id,
            language=voice_language
        )
    
    # Configure STT with Deepgram Nova-3 - OPTIMIZED FOR SPEED & FRENCH  
    stt = deepgram.STT(
        model="nova-3",  # Deepgram's fastest and most accurate model (54% better than nova-2)
        language="fr",   # French language
        endpointing_ms=50,   # ULTRA-aggressive endpointing for speed (reduced from 100ms)
    )
    
    # Configure LLM (Large Language Model) - USING GPT-4O-MINI
    llm_config = ai_models.get("llm", {})
    llm = openai.LLM(
        model=llm_config.get("model", "gpt-4o-mini"),  # GPT-4o-mini for better performance
        parallel_tool_calls=False,  # ✅ CRITICAL: Required for workflow agents with function tools
        temperature=llm_config.get("temperature", 0.1),  # ULTRA-LOW temp for speed (reduced from 0.3)
        # Note: LiveKit OpenAI LLM automatically handles streaming and token limits
    )
    
    logger.info("✅ AI Models configured successfully")
    # Initialize voice adaptation manager (feature-flaggable + per-agent overrides)
    voice_adapt_enabled = os.getenv('VOICE_ADAPTATION_ENABLED', 'true').lower() in ('1','true','yes','on')
    try:
        voice_adapt_rate_limit = float(os.getenv('VOICE_ADAPTATION_RATE_LIMIT_S', '2.0'))
    except Exception:
        voice_adapt_rate_limit = 2.0
    try:
        voice_adapt_memory = int(os.getenv('VOICE_ADAPTATION_MEMORY_LIMIT', '20'))
    except Exception:
        voice_adapt_memory = 20
    # Per-agent overrides from metadata
    voice_adapt_cfg = ai_models.get("voice_adaptation", {}) if isinstance(ai_models, dict) else {}
    if isinstance(voice_adapt_cfg, dict):
        voice_adapt_enabled = bool(voice_adapt_cfg.get("enabled", voice_adapt_enabled))
        try:
            voice_adapt_rate_limit = float(voice_adapt_cfg.get("rate_limit_seconds", voice_adapt_rate_limit))
        except Exception:
            pass
        try:
            voice_adapt_memory = int(voice_adapt_cfg.get("memory_limit", voice_adapt_memory))
        except Exception:
            pass
    voice_adapt = VoiceAdaptationManager(
        enable_adaptation=voice_adapt_enabled,
        rate_limit_seconds=voice_adapt_rate_limit,
        memory_limit=voice_adapt_memory
    )
    print(f"🎙️ TTS configured: {tts_provider} provider with voice {voice_id}", flush=True)
    
    # ✅ AUTO-START PATHWAY EXECUTION IF NEEDED
    try:
        # Import the auto-start function
        import sys
        sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'api'))
        from agent_pathway_integration import auto_start_pathway_for_new_call
        
        agent_id = metadata.get('dial_info', {}).get('agent_id')
        if agent_id and call_id is not None:
            # Check if pathway execution already exists, if not create it
            execution_id = await auto_start_pathway_for_new_call(
                call_id=str(call_id), 
                agent_id=agent_id,
                session_metadata={"room_name": ctx.room.name}
            )
            logger.info(f"✅ Auto-started pathway execution: {execution_id}")
        elif call_id is None:
            logger.info("Inbound call: Skipping pathway auto-start (no call_id)")
        
    except Exception as e:
        logger.error(f"Error in auto-start pathway: {e}")
    
    # ✅ FETCH PATHWAY CONFIG AND CREATE SESSION WITH CORRECT AGENT
    try:
        # Fetch pathway config (only for calls with call_id)
        pathway_config = None
        execution_id = None
        
        if call_id is not None:
            pathway_config, execution_id = await get_pathway_for_call(call_id)
            
        if not pathway_config:
            if call_id is not None:
                logger.error(f"No pathway configuration found for call_id {call_id}. Using agent fallback.")
            else:
                logger.info("Inbound call: No pathway configuration needed. Using agent fallback.")
            
            # 🔍 TRY TO GET AGENT CONFIGURATION FROM DATABASE (for inbound calls)
            agent_instructions = "I am Pam from TechSolutions Pro. How can I help you today?"  # Default fallback
            agent_greeting = None
            
            # For inbound calls (with or without call_id), try to get agent config
            # STRATEGY 1: If we have call_id, get agent_id from call record
            if call_id is not None:
                try:
                    logger.info(f"🔍 Looking up agent configuration via call_id: {call_id}")
                    call_details = await get_call_details_from_supabase(supabase_service_client, call_id)
                    if call_details and call_details.get("agent_id"):
                        agent_id = call_details.get("agent_id")
                        logger.info(f"🔍 Found agent_id {agent_id} from call record")
                        
                        # Get agent configuration directly by ID
                        agent_response = supabase_service_client.table("agents").select(
                            "id, name, system_prompt, initial_greeting"
                        ).eq("id", agent_id).maybe_single().execute()
                        
                        if agent_response.data:
                            agent_data = agent_response.data
                            agent_instructions = agent_data.get("system_prompt", agent_instructions)
                            agent_greeting = agent_data.get("initial_greeting")
                            logger.info(f"✅ Using agent instructions from database for {agent_data.get('name')}: {agent_instructions[:50]}...")
                            logger.info(f"✅ Using agent greeting from database: {agent_greeting}")
                        else:
                            logger.warning(f"❌ Agent {agent_id} not found in database")
                except Exception as e:
                    logger.error(f"❌ Error fetching agent config via call_id {call_id}: {e}")
            
            # STRATEGY 2: Try to get the receiving phone number from metadata sources
            else:
                logger.info(f"🔍 DEBUG: inbound_phone={inbound_phone}, metadata keys={list(metadata.keys())}")
                logger.info(f"🔍 DEBUG: dial_info in metadata={metadata.get('dial_info')}")
                receiving_number = inbound_phone or metadata.get("dial_info", {}).get("phone_number")
                
                if receiving_number:
                    try:
                        logger.info(f"🔍 Looking up agent configuration for inbound number: {receiving_number}")
                        agent_config = await get_agent_config_by_phone_number(receiving_number)
                        if agent_config:
                            agent_instructions = agent_config.get("instructions", agent_instructions)
                            agent_greeting = agent_config.get("initial_greeting")
                            logger.info(f"✅ Using agent instructions from database for {agent_config.get('agent_name')}: {agent_instructions[:50]}...")
                            logger.info(f"✅ Using agent greeting from database: {agent_greeting}")
                        else:
                            logger.warning(f"❌ No agent configuration found for {receiving_number}, using default")
                    except Exception as e:
                        logger.error(f"❌ Error fetching agent config for {receiving_number}: {e}")
                else:
                    logger.warning("❌ No receiving phone number available for agent lookup")
            
            # Create basic session as fallback with empty PathwaySessionData
            fallback_session_data = PathwaySessionData(
                pathway_config={},
                agent_instances={},
                current_node_id=None,
                collected_data={}
            )
            # Pass per-agent voice adaptation config into session data for pathway agents
            try:
                if isinstance(voice_adapt_cfg, dict):
                    fallback_session_data.collected_data["voice_adaptation"] = voice_adapt_cfg
            except Exception:
                pass
            session = AgentSession(
                vad=vad,
                stt=stt, 
                tts=tts,
                llm=llm,
                userdata=fallback_session_data
            )
            # ✅ ENSURE session_start_agent is assigned with proper agent instructions
            # Create a custom agent that can deliver greetings for fallback scenarios
            if agent_greeting:
                class FallbackAgentWithGreeting(Agent):
                    def __init__(self, instructions, greeting):
                        super().__init__(instructions=instructions)
                        self.greeting = greeting
                    
                    async def on_enter(self):
                        # Deliver the greeting when the agent starts
                        if hasattr(self, 'session') and self.session:
                            await self.session.say(self.greeting, allow_interruptions=True)
                        else:
                            # Fallback if session not available yet
                            pass
                        
                session_start_agent = FallbackAgentWithGreeting(agent_instructions, agent_greeting)
                logger.info(f"✅ Created fallback agent with greeting: {agent_greeting}")
            else:
                session_start_agent = Agent(instructions=agent_instructions)
                logger.info(f"✅ Created fallback agent without greeting")
        else:
            logger.info(f"✅ Fetched pathway config for call_id {call_id}")
            
            # Create session data and initialize pathway agents
            session_data = PathwaySessionData(
                pathway_config=pathway_config,
                agent_instances={},
                current_node_id=None,
                collected_data={}
            )
            # Pass per-agent voice adaptation config into session data
            try:
                if isinstance(voice_adapt_cfg, dict):
                    session_data.collected_data["voice_adaptation"] = voice_adapt_cfg
            except Exception:
                pass
            
            # Pre-initialize conversation nodes
            conversation_nodes = [node for node in pathway_config.get('nodes', []) if node.get('type') == 'conversation']
            for node_config in conversation_nodes:
                node_id = node_config.get('id')
                if node_id:
                    agent_instance = PathwayNodeAgent(node_config=node_config, session_data=session_data)
                    session_data.agent_instances[node_id] = agent_instance
                    logger.info(f"Pre-initialized PathwayNodeAgent for node: {node_id}")

            # ✅ FIND STARTING AGENT AND CREATE SESSION
            start_node_id = find_start_node_id(pathway_config)
            if start_node_id and start_node_id in session_data.agent_instances:
                # ✅ GET INITIAL PATHWAY AGENT
                initial_agent = session_data.agent_instances[start_node_id]
                session_data.current_node_id = start_node_id

                logger.info(f"✅ Creating session with PathwayNodeAgent for node: {start_node_id}")
                # ✅ CORRECT LIVEKIT PATTERN: Create session without agent
                session = AgentSession(
                    vad=vad,
                    stt=stt, 
                    tts=tts,
                    llm=llm,
                    userdata=session_data
                )
                # ✅ CORRECT LIVEKIT PATTERN: Start session with agent
                session_start_agent = initial_agent
            else:
                logger.error(f"Start node '{start_node_id}' not found. Using basic session.")
                # Fallback to basic session if pathway fails
                session = AgentSession(
                    vad=vad,
                    stt=stt, 
                    tts=tts,
                    llm=llm,
                    userdata=session_data
                )
                # ✅ ENSURE session_start_agent is assigned
                # Use same agent instructions from fallback logic above
                session_start_agent = Agent(instructions=agent_instructions)
            
    except Exception as e:
        logger.error(f"Error during pathway initialization: {e}")
        # Create basic session as fallback with empty PathwaySessionData
        fallback_session_data = PathwaySessionData(
            pathway_config={},
            agent_instances={},
            current_node_id=None,
            collected_data={}
        )
        try:
            if isinstance(voice_adapt_cfg, dict):
                fallback_session_data.collected_data["voice_adaptation"] = voice_adapt_cfg
        except Exception:
            pass
        session = AgentSession(
            vad=vad,
            stt=stt, 
            tts=tts,
            llm=llm,
            userdata=fallback_session_data
        )
        # ✅ ENSURE session_start_agent is assigned
        # Use default fallback instructions
        session_start_agent = Agent(instructions="I am Pam from TechSolutions Pro. How can I help you today?")
    
    # ✅ Add metrics collection for STT and other components
    metrics_aggregator = MetricsAggregator()
    usage_collector = metrics.UsageCollector()  # For cost estimation per LiveKit docs
    
    @session.on("metrics_collected")
    def _on_metrics_collected(ev: MetricsCollectedEvent):
        """Handle metrics collected from the session"""
        metric = ev.metrics
        
        # Log all metrics for debugging
        metrics.log_metrics(metric)
        
        # Add to aggregators
        metrics_aggregator.add_metric(metric)
        usage_collector.collect(metric)  # Collect for cost estimation
        speech_id = getattr(metric, 'speech_id', None)
        
        # Handle specific metric types
        if isinstance(metric, metrics.STTMetrics):
            logger.info(f"📊 STT Metrics - speech_id: {speech_id}, "
                       f"audio_duration: {metric.audio_duration:.3f}s, "
                       f"duration: {metric.duration:.3f}s, streamed: {metric.streamed}")
        
        elif isinstance(metric, metrics.EOUMetrics):
            logger.info(f"📊 EOU Metrics - speech_id: {speech_id}, "
                       f"transcription_delay: {metric.transcription_delay:.3f}s, "
                       f"end_of_utterance_delay: {metric.end_of_utterance_delay:.3f}s")
        
        elif isinstance(metric, metrics.LLMMetrics):
            # Enhanced LLM metrics logging per LiveKit docs
            completion_tokens = getattr(metric, 'completion_tokens', 0)
            prompt_tokens = getattr(metric, 'prompt_tokens', 0)
            prompt_cached_tokens = getattr(metric, 'prompt_cached_tokens', 0)
            total_tokens = getattr(metric, 'total_tokens', 0)
            tokens_per_second = getattr(metric, 'tokens_per_second', 0)
            
            logger.info(f"📊 LLM Metrics - speech_id: {speech_id}, "
                       f"ttft: {metric.ttft:.3f}s, duration: {metric.duration:.3f}s, "
                       f"tokens/sec: {tokens_per_second:.1f}, "
                       f"completion_tokens: {completion_tokens}, prompt_tokens: {prompt_tokens}, "
                       f"cached_tokens: {prompt_cached_tokens}, total_tokens: {total_tokens}")
        
        elif isinstance(metric, metrics.TTSMetrics):
            # Enhanced TTS metrics logging per LiveKit docs
            characters_count = getattr(metric, 'characters_count', 0)
            streamed = getattr(metric, 'streamed', False)
            
            # Calculate TTS efficiency metrics
            chars_per_sec = characters_count / metric.duration if metric.duration > 0 else 0
            real_time_factor = metric.audio_duration / metric.duration if metric.duration > 0 else 0
            
            logger.info(f"📊 TTS Metrics - speech_id: {speech_id}, "
                       f"ttfb: {metric.ttfb:.3f}s, duration: {metric.duration:.3f}s, "
                       f"audio_duration: {metric.audio_duration:.3f}s, "
                       f"characters: {characters_count}, streamed: {streamed}, "
                       f"efficiency: {chars_per_sec:.1f}chars/s, RT_factor: {real_time_factor:.2f}x")
        
        # Check if we have a complete turn and emit structured metrics
        if speech_id:
            turn_summary = metrics_aggregator.get_turn_summary(speech_id)
            if turn_summary.get('complete'):
                # Enhanced turn complete logging with token and TTS metrics
                llm_data = turn_summary.get('llm_data', {})
                tts_data = turn_summary.get('tts_data', {})
                
                completion_tokens = llm_data.get('completion_tokens', 0)
                prompt_tokens = llm_data.get('prompt_tokens', 0)
                total_tokens = llm_data.get('total_tokens', 0)
                tokens_per_sec = llm_data.get('tokens_per_second', 0)
                
                tts_characters = tts_data.get('characters_count', 0)
                tts_streamed = tts_data.get('streamed', False)
                tts_audio_duration = tts_data.get('audio_duration', 0)
                
                # Calculate TTS efficiency (characters per second)
                tts_char_per_sec = tts_characters / turn_summary['tts_total'] if turn_summary['tts_total'] > 0 else 0
                
                logger.info(f"🎯 TURN COMPLETE - {speech_id}: "
                           f"STT={turn_summary['stt_final_latency']:.3f}s, "
                           f"LLM_TTFT={turn_summary['llm_ttft']:.3f}s, "
                           f"LLM_Total={turn_summary['llm_total']:.3f}s, "
                           f"TTS_TTFB={turn_summary['tts_ttfb']:.3f}s, "
                           f"TTS_Total={turn_summary['tts_total']:.3f}s, "
                           f"Total_Latency={turn_summary['total_conversation_latency']:.3f}s, "
                           f"Tokens={completion_tokens}/{total_tokens} @{tokens_per_sec:.1f}tok/s, "
                           f"TTS={tts_characters}chars @{tts_char_per_sec:.1f}c/s, streamed={tts_streamed}")
                
                # Emit structured event for external tracking (async via task)
                async def emit_turn_metrics():
                    try:
                        from agent_pathway_integration import handle_call_event
                        job_ctx = get_job_context()
                        metadata = {}
                        if job_ctx and job_ctx.job and job_ctx.job.metadata:
                            try:
                                metadata = json.loads(job_ctx.job.metadata)
                            except Exception:
                                metadata = {}
                        call_id = metadata.get('supabase_call_id') or metadata.get('call_id')
                        if call_id:
                            await handle_call_event("turn_metrics_complete", str(call_id), turn_summary)
                    except Exception as e:
                        logger.debug(f"Failed to emit turn metrics: {e}")
                
                # Use asyncio.create_task for async operation in sync callback
                import asyncio
                try:
                    asyncio.create_task(emit_turn_metrics())
                except Exception as e:
                    logger.debug(f"Failed to create turn metrics task: {e}")

    # Add session end callback for usage summary
    async def log_usage_summary():
        try:
            summary = usage_collector.get_summary()
            logger.info(f"💰 Session Usage Summary: {summary}")
        except Exception as e:
            logger.debug(f"Failed to log usage summary: {e}")
    
    ctx.add_shutdown_callback(log_usage_summary)

    # ✅ SAFETY CHECK: Ensure both session and session_start_agent are defined
    if session is None:
        logger.error("Session was not created. Creating fallback session.")
        fallback_session_data = PathwaySessionData(
            pathway_config={},
            agent_instances={},
            current_node_id=None,
            collected_data={}
        )
        try:
            if isinstance(voice_adapt_cfg, dict):
                fallback_session_data.collected_data["voice_adaptation"] = voice_adapt_cfg
        except Exception:
            pass
        session = AgentSession(
            vad=vad,
            stt=stt, 
            tts=tts,
            llm=llm,
            userdata=fallback_session_data
        )
    
    if session_start_agent is None:
        logger.error("session_start_agent was not assigned. Creating fallback agent.")
        # Use default fallback instructions
        session_start_agent = Agent(instructions="I am Pam from TechSolutions Pro. How can I help you today?")
    
    # Note: Dynamic agent configuration removed - inbound calls now use pathway system
    
    # ✅ SIP CALL INITIATION (conditional based on call direction)
    if not is_inbound_call:
        # OUTBOUND: Create SIP participant to initiate call
        print("📞 Creating SIP participant to initiate outbound call...", flush=True)
        logger.info("Creating SIP participant to initiate outbound call...")
        
        phone_number = metadata.get("dial_info", {}).get("phone_number")
        sip_trunk_id = metadata.get("dial_info", {}).get("sip_trunk_id")
            
        print(f"📱 Phone: {phone_number}, Trunk: {sip_trunk_id}", flush=True)
        
        if phone_number and sip_trunk_id:
            print(f"☎️ Dialing {phone_number} using SIP trunk {sip_trunk_id}", flush=True)
            logger.info(f"Dialing {phone_number} using SIP trunk {sip_trunk_id}")
            
            await ctx.api.sip.create_sip_participant(
                api.CreateSIPParticipantRequest(
                    room_name=ctx.room.name,
                    sip_trunk_id=sip_trunk_id,
                    sip_call_to=phone_number,
                    participant_identity="phone_user",
                    wait_until_answered=True,
                )
            )
            print(f"📞 SIP call initiated to {phone_number}. Waiting for participant to join...", flush=True)
            logger.info(f"SIP call initiated to {phone_number}. Waiting for participant to join...")
        else:
            print("⚠️ Missing phone_number or sip_trunk_id - cannot initiate SIP call", flush=True)
    else:
        # INBOUND: Customer already connected via SIP trunk/dispatch rule
        print("📞 INBOUND call - customer already connected, waiting for participant...", flush=True)
        logger.info("INBOUND call - customer already connected, waiting for participant...")
    
    # Note: Inbound call setup moved earlier to run before pathway logic
    
    # ✅ START SESSION WITH CORRECT LIVEKIT PATTERN
    # FINAL LOGGING FIX BEFORE SESSION START
    reapply_logging_fix()
    logger.info("✅ Final logging fix applied before session start")
    
    print("🎬 STARTING LIVEKIT SESSION", flush=True)
    print(f"   Agent: {type(session_start_agent)}", flush=True)
    print(f"   Room: {ctx.room.name}", flush=True)
    
    await session.start(agent=session_start_agent, room=ctx.room)

    print("🏁 SESSION COMPLETED", flush=True)


def find_start_node_id(pathway_config: dict) -> str | None:
    """Find the starting node_id from the pathway configuration."""
    # ✅ FIRST: Check for explicit entry_point in pathway config
    entry_point = pathway_config.get('entry_point')
    if entry_point:
        logger.info(f"🎯 Using entry_point from pathway config: {entry_point}")
        return entry_point
    
    # FALLBACK 1: Look for a node with isStart flag
    nodes = pathway_config.get('nodes', [])
    for node in nodes:
        if node.get('data', {}).get('isStart'):
            logger.info(f"🎯 Using isStart node: {node.get('id')}")
            return node.get('id')
    
    # FALLBACK 2: Use the first conversation node if no explicit start node is set
    for node in nodes:
        if node.get('type') == 'conversation':
            logger.info(f"🎯 Using first conversation node as fallback: {node.get('id')}")
            return node.get('id')
            
    logger.warning("❌ No valid start node found in pathway config")
    return None


async def get_pathway_for_call(call_id: int) -> tuple[dict | None, str | None]:
    """Fetch the pathway configuration associated with a call."""
    # This function needs to be implemented to fetch the pathway config from your backend
    # based on the call_id. For now, it's a placeholder.
    # In a real scenario, you'd call an API endpoint like:
    # backend_url = os.getenv("BACKEND_API_URL", "http://localhost:8000")
    # response = await httpx.AsyncClient().get(f"{backend_url}/pathways/call/{call_id}")
    # if response.status_code == 200:
    #     return response.json(), response.json().get("pathway_execution_id")
    # else:
    #     logger.error(f"Failed to fetch pathway config for call_id {call_id}: {response.status_code} - {response.text}")
    #     return None, None

    # Placeholder for actual backend call
    logger.info(f"Placeholder: Fetching pathway config for call_id {call_id} from backend...")
    # In a real scenario, you would fetch the pathway config from your backend
    # For example, using Supabase:
    try:
        # Assuming you have a function to get call details from Supabase
        call_details = await get_call_details_from_supabase(supabase_service_client, call_id)
        if call_details and call_details.get("pathway_config"):
            pathway_config_json = json.loads(call_details["pathway_config"])
            entry_point = pathway_config_json.get("entry_point", "NOT_FOUND")
            logger.info(f"🔍 DEBUG: Fetched pathway config for call_id {call_id} with entry_point: {entry_point}")
            logger.info(f"Fetched pathway config for call_id {call_id}: {pathway_config_json}")
            return pathway_config_json, call_details.get("pathway_execution_id")
        else:
            logger.warning(f"No pathway config found for call_id {call_id} in Supabase.")
            return None, None
    except Exception as e:
        logger.error(f"Error fetching pathway config from Supabase for call_id {call_id}: {e}", exc_info=True)
        return None, None


async def get_inbound_agent_id_for_phone_number(receiving_phone_number: str) -> int | None:
    """
    Get the inbound agent ID for a receiving phone number.
    
    Args:
        receiving_phone_number: The phone number that received the inbound call (E.164 format)
    
    Returns:
        Agent ID or None if not found
    """
    try:
        logger.info(f"🔍 Looking up inbound agent for receiving number: {receiving_phone_number}")
        
        if not supabase_service_client:
            logger.error("❌ Supabase client not available for agent lookup")
            return None
        
        # Get inbound_agent_id from phone_numbers table
        phone_response = supabase_service_client.table("phone_numbers").select(
            "inbound_agent_id"
        ).eq("phone_number_e164", receiving_phone_number).maybe_single().execute()
        
        if not phone_response.data:
            logger.warning(f"❌ Phone number {receiving_phone_number} not found in database")
            return None
        
        inbound_agent_id = phone_response.data.get("inbound_agent_id")
        
        if not inbound_agent_id:
            logger.warning(f"❌ No inbound_agent_id configured for phone number {receiving_phone_number}")
            return None
        
        logger.info(f"📞 Found inbound_agent_id: {inbound_agent_id} for number {receiving_phone_number}")
        return inbound_agent_id
        
    except Exception as e:
        logger.error(f"❌ Error looking up inbound agent for {receiving_phone_number}: {e}", exc_info=True)
        return None


async def load_agent_ai_models(agent_id: int) -> dict:
    """
    Load agent's AI model configuration from database.
    
    Args:
        agent_id: The agent ID to load configuration for
    
    Returns:
        Dict containing AI model configuration in the format expected by the agent
    """
    try:
        logger.info(f"🔍 Loading AI models configuration for agent {agent_id}")
        
        if not supabase_service_client:
            logger.error("❌ Supabase client not available for AI models lookup")
            return {}
        
        # Get agent's AI model configuration
        agent_response = supabase_service_client.table("agents").select(
            "tts_provider, tts_model, tts_voice, llm_provider, llm_model, llm_temperature, stt_provider, stt_model, stt_language, vad_provider"
        ).eq("id", agent_id).maybe_single().execute()
        
        if not agent_response.data:
            logger.warning(f"❌ Agent {agent_id} not found in database for AI models")
            return {}
        
        agent_data = agent_response.data
        
        # Build AI models configuration in expected format
        ai_models = {}
        
        # TTS Configuration
        if agent_data.get("tts_provider"):
            voice_id = agent_data.get("tts_voice", "f9836c6e-a0bd-460e-9d3c-f7299fa60f94")
            print(f"🎙️ Loading TTS voice for agent {agent_id}: {voice_id}", flush=True)
            logger.info(f"Loading TTS voice for agent {agent_id}: {voice_id}")
            
            ai_models["tts"] = {
                "provider": agent_data.get("tts_provider", "cartesia"),
                "model": agent_data.get("tts_model", "sonic-2-2025-03-07"),
                "voice_id": voice_id
            }
        
        # LLM Configuration  
        if agent_data.get("llm_provider"):
            ai_models["llm"] = {
                "provider": agent_data.get("llm_provider", "openai"),
                "model": agent_data.get("llm_model", "gpt-5-mini"),
                "temperature": agent_data.get("llm_temperature", 0.45)
            }
        
        # STT Configuration
        if agent_data.get("stt_provider"):
            ai_models["stt"] = {
                "provider": agent_data.get("stt_provider", "openai"),
                "model": agent_data.get("stt_model", "gpt-5-transcribe"),
                "language": agent_data.get("stt_language", "en")
            }
        
        # VAD Configuration
        if agent_data.get("vad_provider"):
            ai_models["vad"] = {
                "provider": agent_data.get("vad_provider", "silero")
            }
        
        loaded_voice = ai_models.get('tts', {}).get('voice_id', 'default')
        print(f"✅ Agent {agent_id} AI models loaded - Voice: {loaded_voice}", flush=True)
        logger.info(f"✅ Loaded AI models for agent {agent_id}: TTS={loaded_voice}")
        return ai_models
        
    except Exception as e:
        logger.error(f"❌ Error loading AI models for agent {agent_id}: {e}", exc_info=True)
        return {}


async def get_voice_provider(voice_id: str) -> str:
    """
    Look up the provider for a voice ID in the database.
    
    Args:
        voice_id: The voice ID to look up (could be Cartesia or ElevenLabs voice ID)
    
    Returns:
        Provider name: "cartesia", "elevenlabs", or "cartesia" (default)
    """
    try:
        if not supabase_service_client:
            logger.warning("⚠️ Supabase client not available for voice provider lookup")
            return "cartesia"  # Default fallback
        
        # Look up voice by voice ID (stored in cartesia_voice_id field for both providers)
        voice_response = supabase_service_client.table("voices").select(
            "provider, language_code, name"
        ).eq("cartesia_voice_id", voice_id).maybe_single().execute()
        
        if voice_response.data and voice_response.data.get("provider"):
            provider = voice_response.data["provider"]
            voice_name = voice_response.data.get("name", "Unknown")
            language = voice_response.data.get("language_code", "en")
            logger.info(f"🎙️ Voice '{voice_name}' ({voice_id}) uses provider: {provider} (language: {language})")
            return provider
        else:
            logger.info(f"🎙️ Voice {voice_id} not found in database, defaulting to Cartesia")
            return "cartesia"  # Default to Cartesia if not found
            
    except Exception as e:
        logger.error(f"❌ Error looking up voice provider for {voice_id}: {e}", exc_info=True)
        return "cartesia"  # Default fallback on error


async def get_voice_configuration(voice_id: str) -> dict:
    """
    Get complete voice configuration including provider, language, and model settings.
    
    Args:
        voice_id: The voice ID to look up
    
    Returns:
        Dictionary with voice configuration: provider, language, model, etc.
    """
    try:
        if not supabase_service_client:
            logger.warning("⚠️ Supabase client not available for voice configuration lookup")
            return {
                "provider": "cartesia",
                "language": "fr",
                "model": "sonic-2-2025-03-07",
                "voice_name": "Unknown"
            }
        
        # Look up complete voice information
        voice_response = supabase_service_client.table("voices").select(
            "provider, language_code, name, provider_model"
        ).eq("cartesia_voice_id", voice_id).maybe_single().execute()
        
        if voice_response.data:
            voice_data = voice_response.data
            provider = voice_data.get("provider", "cartesia")
            language = voice_data.get("language_code", "fr")
            voice_name = voice_data.get("name", "Unknown")
            provider_model = voice_data.get("provider_model", "sonic-2-2025-03-07")
            
            # Set appropriate model based on provider
            if provider == "elevenlabs":
                model = "eleven_multilingual_v3"
            else:  # cartesia
                model = provider_model or "sonic-2-2025-03-07"
            
            config = {
                "provider": provider,
                "language": language,
                "model": model,
                "voice_name": voice_name,
                "voice_id": voice_id
            }
            
            logger.info(f"🎙️ Voice Configuration: '{voice_name}' ({voice_id}) → {provider} ({language}) with model {model}")
            return config
        else:
            logger.info(f"🎙️ Voice {voice_id} not found, using Cartesia defaults")
            return {
                "provider": "cartesia",
                "language": "fr", 
                "model": "sonic-2-2025-03-07",
                "voice_name": "Unknown",
                "voice_id": voice_id
            }
            
    except Exception as e:
        logger.error(f"❌ Error getting voice configuration for {voice_id}: {e}", exc_info=True)
        return {
            "provider": "cartesia",
            "language": "fr",
            "model": "sonic-2-2025-03-07", 
            "voice_name": "Unknown",
            "voice_id": voice_id
        }


async def create_inbound_call_record(receiving_phone_number: str, caller_phone_number: str, agent_id: int, room_name: str) -> int | None:
    """
    Create a call record in the database for an inbound call.
    
    Args:
        receiving_phone_number: The phone number that received the call
        caller_phone_number: The phone number that made the call
        agent_id: The agent ID to handle this call
        room_name: The LiveKit room name
    
    Returns:
        Call ID or None if creation failed
    """
    try:
        logger.info(f"📞 Creating inbound call record: from {caller_phone_number} to {receiving_phone_number}")
        
        if not supabase_service_client:
            logger.error("❌ Supabase client not available for call creation")
            return None
        
        # Get user_id for the agent (needed for call record)
        agent_response = supabase_service_client.table("agents").select(
            "user_id, default_pathway_id"
        ).eq("id", agent_id).maybe_single().execute()
        
        if not agent_response.data:
            logger.error(f"❌ Agent {agent_id} not found in database")
            return None
        
        user_id = agent_response.data.get("user_id")
        default_pathway_id = agent_response.data.get("default_pathway_id")
        
        # Create call record
        call_data = {
            "user_id": user_id,
            "agent_id": agent_id,
            "from_phone_number": caller_phone_number,  # The caller's number
            "to_phone_number": receiving_phone_number,  # Our number that received the call
            "status": "in_progress",
            "call_direction": "inbound",
            "room_name": room_name,
            "initiated_at": "now()"
        }
        
        # Note: pathway_execution_id will be set later by auto_start_pathway_for_new_call
        logger.info(f"🛤️ Agent has default pathway: {default_pathway_id} (will be used for execution)")
        
        call_response = supabase_service_client.table("calls").insert(call_data).execute()
        
        if call_response.data:
            call_id = call_response.data[0]["id"]
            logger.info(f"✅ Created inbound call record with ID: {call_id}")
            return call_id
        else:
            logger.error("❌ Failed to create call record - no data returned")
            return None
        
    except Exception as e:
        logger.error(f"❌ Error creating inbound call record: {e}", exc_info=True)
        return None


async def get_agent_config_by_phone_number(receiving_phone_number: str) -> dict | None:
    """
    Query database to get agent configuration based on receiving phone number.
    
    Args:
        receiving_phone_number: The phone number that received the inbound call (E.164 format)
    
    Returns:
        Dict containing agent configuration, or None if not found
    """
    try:
        logger.info(f"🔍 Looking up agent configuration for receiving number: {receiving_phone_number}")
        
        if not supabase_service_client:
            logger.error("❌ Supabase client not available for agent lookup")
            return None
        
        # Step 1: Get inbound_agent_id from phone_numbers table
        phone_response = supabase_service_client.table("phone_numbers").select(
            "inbound_agent_id, phone_number_e164"
        ).eq("phone_number_e164", receiving_phone_number).maybe_single().execute()
        
        if not phone_response.data:
            logger.warning(f"❌ Phone number {receiving_phone_number} not found in database")
            return None
        
        phone_data = phone_response.data
        inbound_agent_id = phone_data.get("inbound_agent_id")
        
        if not inbound_agent_id:
            logger.warning(f"❌ No inbound_agent_id configured for phone number {receiving_phone_number}")
            return None
        
        logger.info(f"📞 Found inbound_agent_id: {inbound_agent_id} for number {receiving_phone_number}")
        
        # Step 2: Get agent configuration from agents table
        agent_response = supabase_service_client.table("agents").select(
            "id, name, system_prompt, initial_greeting, wait_for_greeting, interruption_threshold, supports_inbound"
        ).eq("id", inbound_agent_id).maybe_single().execute()
        
        if not agent_response.data:
            logger.warning(f"❌ Agent {inbound_agent_id} not found in agents table")
            return None
        
        agent_data = agent_response.data
        
        # Verify agent supports inbound calls
        if not agent_data.get("supports_inbound", False):
            logger.warning(f"❌ Agent {inbound_agent_id} ({agent_data.get('name')}) does not support inbound calls")
            return None
        
        logger.info(f"✅ Found agent configuration: {agent_data.get('name')} (ID: {inbound_agent_id})")
        
        return {
            "agent_id": inbound_agent_id,
            "agent_name": agent_data.get("name"),
            "instructions": agent_data.get("system_prompt"),
            "initial_greeting": agent_data.get("initial_greeting"),
            "wait_for_greeting": agent_data.get("wait_for_greeting", False),
            "interruption_threshold": agent_data.get("interruption_threshold", 100),
            "receiving_phone_number": receiving_phone_number
        }
        
    except Exception as e:
        logger.error(f"❌ Error looking up agent configuration for {receiving_phone_number}: {e}", exc_info=True)
        return None


async def get_call_details_from_supabase(supabase_client, call_id: int) -> dict | None:
    """
    Fetch call details and associated pathway configuration from Supabase.
    
    Args:
        supabase_client: The Supabase client instance
        call_id: The call ID to fetch details for
    
    Returns:
        Dict containing call details and pathway_config, or None if not found
    """
    try:
        logger.info(f"🔍 Fetching call details for call_id: {call_id}")
        
        # First, get the call details including pathway_execution_id
        call_response = supabase_client.table("calls").select(
            "id, pathway_execution_id, current_pathway_node_id, pathway_variables, agent_id, user_id, status"
        ).eq("id", call_id).maybe_single().execute()
        
        if not call_response.data:
            logger.warning(f"❌ Call {call_id} not found in database")
            return None
        
        call_data = call_response.data
        pathway_execution_id = call_data.get("pathway_execution_id")
        
        logger.info(f"📞 Call {call_id} found with pathway_execution_id: {pathway_execution_id}")
        
        # If there's no pathway execution, return call data without pathway config
        if not pathway_execution_id:
            logger.info(f"ℹ️ Call {call_id} has no pathway execution - returning basic call data")
            return call_data
        
        # Get pathway execution details
        execution_response = supabase_client.table("pathway_executions").select(
            "id, pathway_id, status, variables"
        ).eq("id", pathway_execution_id).maybe_single().execute()
        
        if not execution_response.data:
            logger.warning(f"❌ Pathway execution {pathway_execution_id} not found")
            return call_data
        
        execution_data = execution_response.data
        pathway_id = execution_data.get("pathway_id")
        
        logger.info(f"📋 Pathway execution found with pathway_id: {pathway_id}")
        
        # Get the actual pathway configuration
        pathway_response = supabase_client.table("pathways").select(
            "id, name, config, status"
        ).eq("id", pathway_id).maybe_single().execute()
        
        if not pathway_response.data:
            logger.warning(f"❌ Pathway {pathway_id} not found")
            return call_data
        
        pathway_data = pathway_response.data
        pathway_config = pathway_data.get("config", {})
        
        logger.info(f"✅ Found pathway '{pathway_data.get('name')}' with config")
        
        # Combine call data with pathway config
        result = {
            **call_data,
            "pathway_config": json.dumps(pathway_config) if pathway_config else None,
            "pathway_execution_id": pathway_execution_id,
            "pathway_name": pathway_data.get("name"),
            "pathway_status": pathway_data.get("status")
        }
        
        return result
        
    except Exception as e:
        logger.error(f"❌ Error fetching call details from Supabase for call_id {call_id}: {e}", exc_info=True)
        return None


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
