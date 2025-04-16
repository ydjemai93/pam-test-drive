from __future__ import annotations

import asyncio
import logging
from dotenv import load_dotenv
import json
import os
import sys
import locale
from typing import Any
import uuid
from dataclasses import dataclass
import random

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
logger = logging.getLogger("outbound-caller")
logger.setLevel(logging.INFO)

# Créer un gestionnaire de flux qui gère l'encodage UTF-8 sans utiliser buffer
handler = logging.StreamHandler(sys.stderr)
handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

# Logs au démarrage du script pour débogage
logger.info(f"Agent script démarre, args: {sys.argv}")
logger.info(f"Python version: {sys.version}")
logger.info(f"Répertoire courant: {os.getcwd()}")
logger.info(f"Encodage par défaut: {sys.getdefaultencoding()}")
logger.info(f"Locale système: {locale.getlocale()}")

# Charger le fichier .env spécifié par la variable d'environnement ou .env.local par défaut
dotenv_file = os.getenv("DOTENV_FILE", ".env.local")
logger.info(f"Chargement du fichier .env: {dotenv_file}")
load_dotenv(dotenv_path=dotenv_file, encoding='utf-8')

outbound_trunk_id = os.getenv("SIP_OUTBOUND_TRUNK_ID")
patient_name = os.getenv("PATIENT_NAME", "Jayden")
appointment_time = os.getenv("APPOINTMENT_TIME", "next Tuesday at 3pm")
room_name = os.getenv("LK_ROOM_NAME", "")
job_metadata = os.getenv("LK_JOB_METADATA", "{}")

# Ajout de logs pour débugger
logger.info(f"SIP_OUTBOUND_TRUNK_ID: {outbound_trunk_id}")
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

class OutboundCaller(Agent):
    def __init__(
        self,
        *,
        name: str,
        dial_info: dict[str, Any],
    ):
        # Define a list of possible greetings (professional, neutral role)
        greetings = [
            f"Bonjour {name}. Ici Pam.",
            f"Bonjour {name}, c'est Pam à l'appareil.",
            f"Ici Pam. Bonjour {name}.",
            f"{name}, bonjour. C'est Pam.",
        ]
        # Randomly select one greeting
        selected_greeting = random.choice(greetings)

        # Construct the final instructions string
        # The initial greeting is now part of the LLM's first mandated response.
        instructions_string = f"""### INSTRUCTIONS TRÈS IMPORTANTES POUR VOTRE PREMIÈRE INTERVENTION ###
        VOUS ÊTES L'AGENT QUI APPELLE "Pam". Votre TOUTE PREMIÈRE réponse générée lorsque l'utilisateur décroche (par exemple en disant "Allo?") DOIT COMMENCER EXACTEMENT PAR une phrase très proche de :
        "{selected_greeting} Je fais suite à votre demande d'information via notre tout nouveau site web - nous sommes ravis que vous l'ayez découvert juste avant son lancement officiel ! Comment puis-je vous renseigner aujourd'hui ?"

        Utilisez la salutation choisie ({selected_greeting}) au début de cette phrase.
        ***NE DITES RIEN DE PLUS DANS CETTE PREMIÈRE INTERVENTION.*** Attendez la réponse de l'utilisateur.
        NE DEMANDEZ PAS "Comment puis-je vous aider ?" de manière générale au début. Votre première phrase doit directement donner le contexte de l'appel et inviter une question spécifique de l'utilisateur.
        ### FIN DES INSTRUCTIONS IMPORTANTES ###

        --- Informations générales sur votre rôle (à utiliser PLUS TARD dans la conversation, SI NÉCESSAIRE) ---
        Mon rôle général est d'assister les utilisateurs suite à leur intérêt manifesté sur notre site. Je peux répondre aux questions fréquentes sur nos offres et services.
        Je suis également capable d'effectuer des tâches spécifiques comme :
        *   La prospection commerciale : Intégrée à une équipe de vente, je peux initier des contacts et qualifier des prospects.
        *   Le support administratif/secrétariat : Je peux gérer des agendas, planifier des rendez-vous (fictifs pour cette démo), ou fournir des informations standards, par exemple dans un contexte de secrétariat médical ou administratif.
        *   Des tâches de support client de base : Comme vérifier une information simple (ex: statut d'une facture fictive) ou mettre à jour des coordonnées.
        
        IMPORTANT : Ne jamais utiliser de formatage markdown (pas d'astérisques, tirets, etc.). Parlez naturellement en texte brut.
        Si l'utilisateur ne sait pas quoi demander après votre première intervention, ALORS vous pouvez suggérer des options basées sur ces capacités, par exemple : "Je peux répondre à vos questions sur nos services, planifier un rendez-vous ou vérifier une information. Qu'aimeriez-vous faire ?"
        
        ### Règles et Limitations Strictes pour la Démo ###
        1.  **Sujet Principal :** Votre rôle est de répondre aux questions liées à la demande d'information initiale sur le site web et aux services présentés. Vous POUVEZ et DEVEZ également expliquer vos propres capacités (prospection, support administratif/secrétariat, support client de base) et comment elles peuvent être utilisées dans un contexte professionnel si l'utilisateur pose la question. Restez concentrée sur ces domaines. Refusez poliment les discussions sur des sujets sans aucun rapport (politique, opinions personnelles, météo, etc.). Exemple de refus pour sujets hors cadre : "Je suis là pour discuter de la manière dont je peux assister dans un cadre professionnel, par exemple pour la prospection ou le support. Pourriez-vous me poser une question sur ces aspects ?" 
        2.  **Pas d'Improvisation :** Ne proposez JAMAIS d'actions ou d'informations non listées explicitement. Ne promettez rien qui sorte de ce cadre.
        3.  **Persona "Pam" :** Vous êtes 'Pam', une assistante. Ne révélez JAMAIS que vous êtes une IA ou un programme. Restez dans ce rôle.
        4.  **Incompréhension :** Si vous ne comprenez pas, dites-le simplement. Exemple : "Je ne suis pas certaine de comprendre. Pourriez-vous reformuler s'il vous plaît ?" ou "Excusez-moi, je n'ai pas bien saisi votre demande."
        5.  **Demandes Inappropriées :** Refusez poliment mais fermement toute demande illégale, dangereuse, discriminatoire ou manifestement hors sujet. Exemple de refus subtil : "Je ne suis pas en mesure de vous aider avec ce type de demande." ou "Cela sort du cadre de ce que je peux faire pour vous aujourd'hui."
        6.  **Concision :** Soyez aussi directe et concise que possible, tout en restant naturelle.

        --- Autres instructions ---
        Si vous préférez parler directement à un collègue humain, dites-le moi et j'organiserai le transfert. Indiquez-moi également si vous souhaitez terminer notre conversation.
        Je communique uniquement en français.
        """
        
        # Log the final prompt being sent to the agent for debugging
        logger.info("--- Agent System Prompt ---")
        logger.info(instructions_string)
        logger.info("--- End Agent System Prompt ---")

        # System Prompt for "Pam", acting as an assistant without revealing AI nature
        super().__init__(instructions=instructions_string)
        
        # Store participant reference for transfers etc.
        self.participant: rtc.RemoteParticipant | None = None
        self.dial_info = dial_info

        # Log still uses name correctly
        logger.info(f"OutboundCaller (Pam Assistant) initialized for {name}")
        logger.info(f"dial_info provided: {dial_info}")

    def set_participant(self, participant: rtc.RemoteParticipant):
        self.participant = participant

    async def hangup(self):
        """Helper function to hang up the call by deleting the room"""

        job_ctx = get_job_context()
        await job_ctx.api.room.delete_room(
            api.DeleteRoomRequest(
                room=job_ctx.room.name,
            )
        )

    @function_tool()
    async def transfer_call(self, ctx: RunContext):
        """Transfer the call to a human agent, called after confirming with the user"""

        transfer_to = self.dial_info["transfer_to"]
        if not transfer_to:
            return "cannot transfer call"

        logger.info(f"transferring call to {transfer_to}")

        # let the message play fully before transferring
        await ctx.session.generate_reply(
            instructions="let the user know you'll be transferring them"
        )

        job_ctx = get_job_context()
        try:
            await job_ctx.api.sip.transfer_sip_participant(
                api.TransferSIPParticipantRequest(
                    room_name=job_ctx.room.name,
                    participant_identity=self.participant.identity,
                    transfer_to=f"tel:{transfer_to}",
                )
            )

            logger.info(f"transferred call to {transfer_to}")
        except Exception as e:
            logger.error(f"error transferring call: {e}")
            await ctx.session.generate_reply(
                instructions="there was an error transferring the call."
            )
            await self.hangup()

    @function_tool()
    async def end_call(self, ctx: RunContext):
        """Called when the user wants to end the call"""
        logger.info(f"ending the call for {self.participant.identity}")

        # let the agent finish speaking
        current_speech = ctx.session.current_speech
        if current_speech:
            # current_speech.done() likely returns a boolean, not awaitable
            # Simply check its status or allow the hangup to proceed
            # No await needed here based on the TypeError
            pass # Or potentially log current_speech.done() if needed

        await self.hangup()

    @function_tool()
    async def look_up_availability(
        self,
        ctx: RunContext,
        date: str,
    ):
        """Called when the user asks about alternative appointment availability

        Args:
            date: The date of the appointment to check availability for
        """
        logger.info(
            f"looking up availability for {self.participant.identity} on {date}"
        )
        await asyncio.sleep(3)
        return {
            "available_times": ["1pm", "2pm", "3pm"],
        }

    @function_tool()
    async def confirm_appointment(
        self,
        ctx: RunContext,
        date: str,
        time: str,
    ):
        """Called when the user confirms their appointment on a specific date.
        Use this tool only when they are certain about the date and time.

        Args:
            date: The date of the appointment
            time: The time of the appointment
        """
        logger.info(
            f"confirming appointment for {self.participant.identity} on {date} at {time}"
        )
        return "reservation confirmed"

    @function_tool()
    async def detected_answering_machine(self, ctx: RunContext):
        """Called when the call reaches voicemail. Use this tool AFTER you hear the voicemail greeting"""
        logger.info(f"detected answering machine for {self.participant.identity}")
        await self.hangup()


async def entrypoint(ctx: JobContext):
    # Reference global variables if they are genuinely needed globally or managed outside
    # Prefer passing necessary configs explicitly if possible
    global outbound_trunk_id # appointment_time is no longer directly needed by the agent prompt

    logger.info(f"Entrée dans la fonction entrypoint pour le job {ctx.job.id}")
    
    # Connect to the room first
    try:
        await ctx.connect()
        logger.info(f"Connexion établie à la room {ctx.room.name}")
    except Exception as e:
        logger.error(f"Erreur de connexion à la room {ctx.room.name}: {e}")
        return # Cannot proceed without connection

    # -- Start Metadata Extraction --
    logger.info(f"Métadonnées du job: {ctx.job.metadata}")

    first_name = "Valued Customer" # Default value
    last_name = ""
    phone_number = None
    dial_info = {} # Initialize dial_info

    try:
        # Use job metadata first, fallback to env var LK_JOB_METADATA
        metadata_str = ctx.job.metadata or os.getenv("LK_JOB_METADATA", "{}")
        if metadata_str and metadata_str != "{}":
            dial_info = json.loads(metadata_str)
            logger.info(f"dial_info parsed from metadata: {dial_info}")
            first_name = dial_info.get("firstName", first_name)
            last_name = dial_info.get("lastName", last_name)
            phone_number = dial_info.get("phoneNumber")
            # Keep transfer_to if present, ensure it's in dial_info for the agent
            if "transfer_to" in dial_info:
                 logger.info(f"Transfer number found in metadata: {dial_info['transfer_to']}")
            else:
                 # If not in metadata, maybe check environment? Or leave it empty.
                 # dial_info["transfer_to"] = os.getenv("DEFAULT_TRANSFER_NUMBER") 
                 pass # Assuming transfer_to is optional unless specified
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
            await ctx.disconnect() # Disconnect before returning
            return # Stop processing if no number

    # Update dial_info with the final phone number and names for the agent
    dial_info["phone_number"] = phone_number
    dial_info["firstName"] = first_name
    dial_info["lastName"] = last_name
    # -- End Metadata Extraction --

    logger.info(f"Final dial info for agent: {dial_info}")
    logger.info(f"Agent will use name: {first_name}")
    logger.info(f"Dialing number: {phone_number}")

    # -- Agent and Session Setup --
    # Create the agent instance *inside* entrypoint using extracted data
    # appointment_time is removed from agent creation as it's not in the new prompt
    agent = OutboundCaller(
        name=first_name, 
        dial_info=dial_info, 
    )

    # Setup plugins and session (Restored Logic)
    logger.info(f"Création de l'AgentSession avec les plugins")
    session = AgentSession(
        vad=silero.VAD.load(),
        stt=deepgram.STT(language="fr", model="nova-2"),
        # Ensure Cartesia model and voice ID are correct
        tts=cartesia.TTS(model="sonic-2", # Reverted to sonic-2 based on original script
             voice="65b25c5d-ff07-4687-a04c-da2f43ef6fa9"), 
        llm=openai.LLM(model="gpt-4o-mini"),
    )

    # Start the session task to handle interactions
    logger.info(f"Démarrage de la session agent en arrière-plan")
    session_task = asyncio.create_task(
        session.start(
            agent=agent,
            room=ctx.room,
            # No specific participant needed here, agent will interact with joined participants
            # room_input_options=RoomInputOptions(), # Use default options
        )
    )
    # -- End Agent and Session Setup --

    # -- Start Outbound SIP Call --
    current_outbound_trunk_id = os.getenv("SIP_OUTBOUND_TRUNK_ID") # Get current value
    logger.info(f"Attempting SIP dial: {phone_number} via trunk {current_outbound_trunk_id}")

    if not current_outbound_trunk_id:
        logger.error("SIP_OUTBOUND_TRUNK_ID n'est pas défini dans l'environnement.")
        await ctx.disconnect()
        session_task.cancel() 
        return

    try:
        logger.info(f"Executing create_sip_participant for {phone_number}")
        await ctx.api.sip.create_sip_participant(
            api.CreateSIPParticipantRequest(
                room_name=ctx.room.name,
                sip_trunk_id=current_outbound_trunk_id,
                sip_call_to=phone_number, 
                participant_identity="phone_user",
                wait_until_answered=True, 
                # caller_id=os.getenv("SIP_CALLER_ID", ""), # Removed unsupported parameter
            )
        )
        logger.info(f"SIP call answered for {phone_number}. Waiting for participant 'phone_user' to join.")

        # Wait for the participant corresponding to the SIP call to join the room
        participant = await ctx.wait_for_participant(identity="phone_user")
        logger.info(f"Participant 'phone_user' ({participant.sid}) connected to room {ctx.room.name}.")
        agent.set_participant(participant) # Link participant to agent for context (e.g., transfer)

    except api.TwirpError as e:
        logger.error(
            f"Erreur Twirp during SIP call: {e.code} {e.message}, "
            f"SIP Status: {e.metadata.get('sip_status_code')} {e.metadata.get('sip_status')}"
        )
        ctx.shutdown()
        session_task.cancel()
    except asyncio.TimeoutError:
        logger.error("Timeout waiting for participant 'phone_user' to join after SIP call answered.")
        ctx.shutdown()
        session_task.cancel()
    except Exception as e:
        logger.error(f"Unexpected error during SIP call or participant wait: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        ctx.shutdown()
        session_task.cancel()
        return # Exit on critical error
    # -- End Outbound SIP Call --

    # If SIP call successful and participant joined, let the agent session run
    logger.info("SIP call connected, participant joined. Agent session is active.")
    
    # The entrypoint completes here, the background session_task handles the interaction.


if __name__ == "__main__":
    # Basic logging config for the worker process
    logging.basicConfig(level=logging.INFO)
    
    logger.info("Configuring and starting LiveKit Agent worker (outbound-caller)")

    # Define the worker options, primarily setting the entrypoint function
    # The agent name allows LiveKit Server to dispatch jobs to this worker type
    worker_options = WorkerOptions(
        entrypoint_fnc=entrypoint,
        agent_name="outbound-caller",
        # Optional: Define resource limits, health checks, etc.
    )

    # Use the standard LiveKit agent CLI runner
    # run_app handles worker registration with LiveKit Server and job processing loop
    try:
        cli.run_app(worker_options)
    except Exception as e:
        logger.critical(f"Failed to run the agent worker: {str(e)}")
        import traceback
        logger.critical(traceback.format_exc())
        sys.exit(1) # Exit with error code if runner fails critically
