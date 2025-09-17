"""
Agent Launcher Module for PAM Outbound Calls

This module handles launching and managing agent processes for outbound calls.
It provides subprocess management, environment configuration, PID tracking,
and proper cleanup mechanisms.

Key Features:
- Launch agent subprocesses with proper configuration
- Environment variable setup for agents
- PID tracking for call records
- Process monitoring and cleanup
- Error handling and recovery
"""

import subprocess
import os
import logging
import asyncio
import psutil
import signal
import time
import json
import socket
from typing import Dict, Any, Optional, List
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime

from .db_client import supabase_service_client

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class AgentProcessConfig:
    """Configuration for an agent process"""
    agent_id: int
    call_id: str
    room_name: str
    call_direction: str
    caller_number: Optional[str] = None
    called_number: Optional[str] = None
    agent_config: Optional[Dict[str, Any]] = None
    supabase_call_id: Optional[str] = None
    telnyx_call_control_id: Optional[str] = None

@dataclass
class ProcessInfo:
    """Information about a running agent process"""
    pid: int
    call_id: str
    agent_id: int
    room_name: str
    started_at: datetime
    status: str
    process: Optional[subprocess.Popen] = None

class AgentLauncher:
    """Main agent launcher class"""
    
    def __init__(self):
        self.running_processes: Dict[str, ProcessInfo] = {}
        self.supabase_client = supabase_service_client
        
        # Get paths for agent
        self.project_root = Path(__file__).parent.parent
        self.agents_dir = self.project_root / "agents"
        
        # Agent script path (updated to new location)
        self.unified_agent_script = self.agents_dir / "outbound_agent.py"
        
        # Use agents .env file for calls
        self.unified_env_file = self.agents_dir / ".env"
        
        # Create a directory for agent logs if it doesn't exist
        self.logs_dir = self.agents_dir / "logs"
        self.logs_dir.mkdir(exist_ok=True)
        
        # Verify agent script exists
        if not self.unified_agent_script.exists():
            raise FileNotFoundError(f"Unified agent script not found at {self.unified_agent_script}")
        
        # Verify environment file exists
        if not self.unified_env_file.exists():
            raise FileNotFoundError(f"Unified environment file not found at {self.unified_env_file}")
            
        logger.info(f"AgentLauncher initialized. Using agent script: {self.unified_agent_script}")
        logger.info(f"Using environment file: {self.unified_env_file}")

    def _get_free_port(self) -> int:
        """Find and return an available TCP port."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('', 0))
            return s.getsockname()[1]

    def _get_agent_paths(self) -> tuple[Path, Path, Path]:
        """Get the paths for the agent script, env file, and working directory."""
        agent_script_path = self.agents_dir / "outbound_agent.py"
        env_file_path = self.unified_env_file
        working_dir = self.agents_dir
        return agent_script_path, env_file_path, working_dir

    async def launch_outbound_agent(self, call_record: Dict[str, Any], agent_id: int) -> bool:
        """
        Launch agent process for outbound call
        
        Args:
            call_record: Database call record
            agent_id: Agent to launch
            
        Returns:
            True if launched successfully
        """
        try:
            call_id = call_record.get("id")
            room_name = call_record.get("room_name")
            
            if not call_id or not room_name:
                logger.error(f"Missing call_id or room_name in call_record: {call_record}")
                return False
                
            logger.info(f"Launching agent for call {call_id}, agent {agent_id}")
            
            # Get agent configuration
            agent_config = await self._get_agent_config(agent_id)
            if not agent_config:
                logger.error(f"Failed to get agent config for agent {agent_id}")
                return False
            
            # Create agent process configuration
            process_config = AgentProcessConfig(
                agent_id=agent_id,
                call_id=call_id,
                room_name=room_name,
                call_direction="outbound",
                called_number=call_record.get("phone_number_e164"),
                agent_config=agent_config,
                supabase_call_id=call_id,
                telnyx_call_control_id=call_record.get("call_control_id")
            )
            
            # Launch the agent process
            process = await self._launch_agent_process(process_config)
            if not process:
                return False
                
            # Store process info
            process_info = ProcessInfo(
                pid=process.pid,
                call_id=call_id,
                agent_id=agent_id,
                room_name=room_name,
                started_at=datetime.now(),
                status="running",
                process=process
            )
            
            self.running_processes[call_id] = process_info
            
            # Update call record with PID
            await self._update_call_pid(call_id, process.pid)
            
            logger.info(f"Successfully launched agent process PID {process.pid} for call {call_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to launch outbound agent: {e}")
            return False

    async def terminate_agent_for_call(self, call_id: str) -> bool:
        """
        Terminate agent process for a call
        
        Args:
            call_id: Call ID to terminate agent for
            
        Returns:
            True if terminated successfully
        """
        try:
            if call_id not in self.running_processes:
                logger.warning(f"No running process found for call {call_id}")
                return True  # Consider it successful if already gone
                
            process_info = self.running_processes[call_id]
            logger.info(f"Terminating agent process PID {process_info.pid} for call {call_id}")
            
            # Try to terminate the process gracefully
            success = await self._terminate_process(process_info.process, process_info.pid)
            
            # Remove from tracking
            del self.running_processes[call_id]
            
            # Update call record to clear PID
            await self._update_call_pid(call_id, None)
            
            return success
            
        except Exception as e:
            logger.error(f"Failed to terminate agent for call {call_id}: {e}")
            return False

    async def get_agent_status(self, call_id: str) -> Optional[Dict[str, Any]]:
        """
        Get status of agent process for a call
        
        Args:
            call_id: Call ID to check
            
        Returns:
            Status information or None if not found
        """
        try:
            if call_id not in self.running_processes:
                return None
                
            process_info = self.running_processes[call_id]
            
            # Check if process is still running
            is_running = await self._is_process_running(process_info.pid)
            
            status = {
                "call_id": call_id,
                "agent_id": process_info.agent_id,
                "pid": process_info.pid,
                "room_name": process_info.room_name,
                "started_at": process_info.started_at.isoformat(),
                "status": "running" if is_running else "stopped",
                "uptime_seconds": (datetime.now() - process_info.started_at).total_seconds()
            }
            
            # If process stopped, clean up
            if not is_running:
                del self.running_processes[call_id]
                await self._update_call_pid(call_id, None)
                
            return status
            
        except Exception as e:
            logger.error(f"Failed to get agent status for call {call_id}: {e}")
            return None

    async def cleanup_orphaned_processes(self) -> int:
        """
        Clean up any orphaned agent processes
        
        Returns:
            Number of processes cleaned up
        """
        cleanup_count = 0
        
        try:
            # Get list of call IDs to check
            call_ids_to_check = list(self.running_processes.keys())
            
            for call_id in call_ids_to_check:
                process_info = self.running_processes[call_id]
                
                # Check if process is still running
                if not await self._is_process_running(process_info.pid):
                    logger.info(f"Cleaning up orphaned process for call {call_id}")
                    del self.running_processes[call_id]
                    await self._update_call_pid(call_id, None)
                    cleanup_count += 1
                    
            logger.info(f"Cleaned up {cleanup_count} orphaned processes")
            return cleanup_count
            
        except Exception as e:
            logger.error(f"Failed to cleanup orphaned processes: {e}")
            return cleanup_count

    async def get_all_agent_statuses(self) -> List[Dict[str, Any]]:
        """
        Get status of all running agent processes
        
        Returns:
            List of status information for all processes
        """
        statuses = []
        
        try:
            for call_id in list(self.running_processes.keys()):
                status = await self.get_agent_status(call_id)
                if status:
                    statuses.append(status)
                    
            return statuses
            
        except Exception as e:
            logger.error(f"Failed to get all agent statuses: {e}")
            return []

    async def _launch_agent_process(self, config: AgentProcessConfig) -> Optional[subprocess.Popen]:
        """Launch agent subprocess with proper configuration"""
        try:
            # Create environment for the subprocess
            env = await self._create_agent_environment(config)
            
            # Create metadata for the agent
            metadata = await self._create_agent_metadata(config)
            
            # Get the agent script path and working directory
            agent_script, env_file, working_dir = self._get_agent_paths()
            
            # Prepare the command
            python_path = self._get_python_executable()
            
            # For calls, use worker mode
            # The agent will be automatically dispatched by LiveKit when calls come in
            cmd = [
                python_path,
                str(agent_script),
                "start"  # Use worker mode for better SIP call handling
            ]
            
            # Pass all configuration via environment variables
            # The agent will read these when it gets dispatched to a room
            env.update({
                "LK_JOB_METADATA": json.dumps(metadata),
                "LK_ROOM_NAME": config.room_name,
                "AGENT_CALL_DIRECTION": config.call_direction,
                "EXPECTED_ROOM_NAME": config.room_name,  # Help agent identify the right room
            })
            
            logger.info(f"Launching agent process: {' '.join(cmd)}")
            
            # Create log files for stdout and stderr with proper buffering
            log_file_path = self.logs_dir / f"agent_{config.call_id}.log"
            err_file_path = self.logs_dir / f"agent_{config.call_id}.err"
            
            # Use unbuffered files and store handles for proper cleanup
            stdout_log = open(log_file_path, 'w', buffering=1)  # Line buffered
            stderr_log = open(err_file_path, 'w', buffering=1)  # Line buffered
            
            # Add logging configuration environment variables
            env.update({
                "AGENT_LOG_FILE": str(log_file_path),
                "AGENT_ERR_FILE": str(err_file_path),
                "AGENT_LOG_LEVEL": "INFO",
                "PYTHONUNBUFFERED": "1",  # Force unbuffered output
            })
            
            # Launch the process
            process = subprocess.Popen(
                cmd,
                env=env,
                cwd=str(working_dir),
                stdout=stdout_log,
                stderr=stderr_log,
                preexec_fn=os.setsid if os.name != 'nt' else None
            )
            
            # Store file handles for later cleanup
            process._log_files = (stdout_log, stderr_log)
            
            # Give the process a moment to start
            await asyncio.sleep(0.5)
            
            # Check if process started successfully
            if process.poll() is not None:
                # Flush and close log files if process failed to start
                stdout_log.flush()
                stderr_log.flush()
                stdout_log.close()
                stderr_log.close()
                
                # Read error output to understand why it failed
                try:
                    with open(err_file_path, 'r') as f:
                        error_output = f.read()
                    logger.error(f"Agent process failed to start: {error_output}")
                except Exception as e:
                    logger.error(f"Agent process failed to start and couldn't read error log: {e}")
                return None
                
            logger.info(f"Agent process started successfully with PID {process.pid}")
            return process
            
        except Exception as e:
            logger.error(f"Failed to launch agent process: {e}")
            return None

    async def _create_agent_environment(self, config: AgentProcessConfig) -> Dict[str, str]:
        """Create environment variables for agent subprocess"""
        # Start with current environment
        env = os.environ.copy()
        
        # Get the appropriate environment file
        _, env_file, _ = self._get_agent_paths()
        
        # Load environment from the .env file
        if env_file.exists():
            with open(env_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        env[key.strip()] = value.strip().strip('"')
        
        # Add specific configuration for this agent
        env.update({
            "AGENT_CALL_ID": str(config.call_id),
            "AGENT_ROOM_NAME": str(config.room_name) if config.room_name else "",
            "AGENT_ID": str(config.agent_id),
            # NEW: Assign a dynamic free port for each agent worker
            "LIVEKIT_AGENT_HTTP_PORT": str(self._get_free_port()),
        })
        
        if config.supabase_call_id:
            env["SUPABASE_CALL_ID"] = str(config.supabase_call_id)
            
        if config.telnyx_call_control_id:
            env["TELNYX_CALL_CONTROL_ID"] = str(config.telnyx_call_control_id)
            
        return env

    async def _create_agent_metadata(self, config: AgentProcessConfig) -> Dict[str, Any]:
        """Create metadata dictionary for agent"""
        agent_config = config.agent_config or {}
        
        # --- Get phone number details from the database ---
        phone_number_details = {}
        agent_caller_id_number = None  # Initialize here
        phone_numbers_id = agent_config.get("phone_numbers_id")
        if phone_numbers_id:
            try:
                # Fetch both the phone number and the SIP trunk ID
                pn_response = self.supabase_client.table("phone_numbers").select(
                    "phone_number_e164, livekit_sip_trunk_id"
                ).eq("id", phone_numbers_id).single().execute()
                
                if pn_response.data:
                    phone_number_details = pn_response.data
                    # Correctly get the phone number to use as caller ID
                    agent_caller_id_number = phone_number_details.get("phone_number_e164")
                    logger.info(f"Retrieved phone number details for agent {config.agent_id}: {phone_number_details}")
            except Exception as e:
                logger.error(f"Failed to retrieve phone number details for agent {config.agent_id}: {e}")
        
        # --- Determine the final SIP trunk ID ---
        final_sip_trunk_id = phone_number_details.get("livekit_sip_trunk_id") or agent_config.get("sip_trunk_id")
        
        if not final_sip_trunk_id:
            logger.warning(f"No SIP Trunk ID found for agent {config.agent_id} in agent config or assigned number. Call may fail.")

        # Base metadata
        metadata = {
            "firstName": "Valued Customer",  # Default
            "lastName": "",
            "dial_info": {
                "agent_id": config.agent_id,
                "call_direction": config.call_direction,
                "room_name": config.room_name,
                "supabase_call_id": config.supabase_call_id,
                "telnyx_call_control_id": config.telnyx_call_control_id,
                "default_pathway_id": agent_config.get("default_pathway_id"),
                "user_id": agent_config.get("user_id"), # Pass user_id for context
                "phone_number": config.called_number,
                "sip_trunk_id": final_sip_trunk_id, # Pass the dynamically determined SIP trunk ID
                "agent_caller_id_number": agent_caller_id_number # Pass the agent's own number
            }
        }
            
        # Add agent configuration
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
        
        metadata.update({
            "system_prompt": system_prompt,
            "initial_greeting": initial_greeting,
            "wait_for_greeting": agent_config.get("wait_for_greeting", False),
            "pam_tier": agent_config.get("pam_tier", "core"),
            "interruption_threshold": agent_config.get("interruption_threshold", 100),
            
            # AI Model Configuration
            "ai_models": {
                "vad": {"provider": "silero"},
                "stt": {
                    "provider": agent_config.get("stt_provider", "deepgram"),
                    "language": agent_config.get("stt_language", "fr"),
                    "model": agent_config.get("stt_model", "nova-2")
                },
                "tts": {
                    "provider": "dynamic",  # Will be determined by voice lookup
                    "model": agent_config.get("tts_model", "sonic-2-2025-03-07"),
                    "voice_id": agent_config.get("tts_voice", "65b25c5d-ff07-4687-a04c-da2f43ef6fa9")
                },
                "llm": {
                    "provider": agent_config.get("llm_provider", "openai"),
                    "model": agent_config.get("llm_model", "gpt-4o-mini")
                }
            }
        })
        
        return metadata

    async def _get_agent_config(self, agent_id: int) -> Optional[Dict[str, Any]]:
        """Get agent configuration from database"""
        try:
            response = self.supabase_client.table("agents").select("*").eq("id", agent_id).execute()
            
            if response.data:
                return response.data[0]
            else:
                logger.error(f"Agent {agent_id} not found in database")
                return None
                
        except Exception as e:
            logger.error(f"Failed to get agent config for agent {agent_id}: {e}")
            return None

    async def _update_call_pid(self, call_id: str, pid: Optional[int]):
        """Update call record with agent process PID"""
        try:
            update_data = {"agent_process_pid": pid}
            
            response = self.supabase_client.table("calls").update(update_data).eq("id", call_id).execute()
            
            if response.data:
                logger.info(f"Updated call {call_id} with PID {pid}")
            else:
                logger.warning(f"Failed to update call {call_id} with PID {pid}")
                
        except Exception as e:
            logger.error(f"Failed to update call PID: {e}")

    async def _terminate_process(self, process: subprocess.Popen, pid: int) -> bool:
        """Terminate a process gracefully"""
        try:
            if not await self._is_process_running(pid):
                # Process already terminated, clean up log files
                await self._cleanup_process_logs(process)
                return True
                
            # Try graceful termination first
            logger.info(f"Sending SIGTERM to process {pid}")
            if os.name == 'nt':  # Windows
                process.terminate()
            else:  # Unix/Linux
                os.killpg(os.getpgid(pid), signal.SIGTERM)
            
            # Wait a few seconds for graceful shutdown
            for _ in range(5):
                await asyncio.sleep(1)
                if not await self._is_process_running(pid):
                    logger.info(f"Process {pid} terminated gracefully")
                    await self._cleanup_process_logs(process)
                    return True
                    
            # Force kill if still running
            logger.warning(f"Force killing process {pid}")
            if os.name == 'nt':  # Windows
                process.kill()
            else:  # Unix/Linux
                os.killpg(os.getpgid(pid), signal.SIGKILL)
            
            # Final check
            await asyncio.sleep(1)
            if not await self._is_process_running(pid):
                logger.info(f"Process {pid} force killed")
                await self._cleanup_process_logs(process)
                return True
            else:
                logger.error(f"Failed to kill process {pid}")
                await self._cleanup_process_logs(process)
                return False
                
        except ProcessLookupError:
            # Process already dead
            await self._cleanup_process_logs(process)
            return True
        except Exception as e:
            logger.error(f"Failed to terminate process {pid}: {e}")
            await self._cleanup_process_logs(process)
            return False

    async def _cleanup_process_logs(self, process: subprocess.Popen):
        """Clean up log file handles for a process"""
        try:
            if hasattr(process, '_log_files'):
                stdout_log, stderr_log = process._log_files
                try:
                    stdout_log.flush()
                    stderr_log.flush()
                    stdout_log.close()
                    stderr_log.close()
                    logger.debug("Successfully closed process log files")
                except Exception as e:
                    logger.warning(f"Error closing log files: {e}")
        except Exception as e:
            logger.warning(f"Error during log cleanup: {e}")

    async def _is_process_running(self, pid: int) -> bool:
        """Check if a process is still running"""
        try:
            return psutil.pid_exists(pid)
        except Exception:
            return False

    def _get_python_executable(self) -> str:
        """Get the Python executable to use"""
        # Try to use the same Python executable that's running this script
        python_exe = os.sys.executable
        
        # If we're in a virtual environment, make sure we use that
        venv_dir = self.agents_dir / "venv"
        if venv_dir.exists():
            if os.name == 'nt':  # Windows
                venv_python = venv_dir / "Scripts" / "python.exe"
            else:  # Unix/Linux/macOS
                venv_python = venv_dir / "bin" / "python"
                
            if venv_python.exists():
                python_exe = str(venv_python)
                
        logger.info(f"Using Python executable: {python_exe}")
        return python_exe


# Global agent launcher instance
_agent_launcher = None

def get_agent_launcher() -> AgentLauncher:
    """Get the global agent launcher instance"""
    global _agent_launcher
    if _agent_launcher is None:
        _agent_launcher = AgentLauncher()
    return _agent_launcher


# Convenience functions for external use
async def launch_outbound_agent(call_record: Dict[str, Any], agent_id: int) -> bool:
    """Launch agent process for outbound call"""
    launcher = get_agent_launcher()
    return await launcher.launch_outbound_agent(call_record, agent_id)

async def terminate_agent_for_call(call_id: str) -> bool:
    """Terminate agent process for a call"""
    launcher = get_agent_launcher()
    return await launcher.terminate_agent_for_call(call_id)

async def get_agent_status(call_id: str) -> Optional[Dict[str, Any]]:
    """Get status of agent process for a call"""
    launcher = get_agent_launcher()
    return await launcher.get_agent_status(call_id)

async def cleanup_orphaned_processes() -> int:
    """Clean up any orphaned agent processes"""
    launcher = get_agent_launcher()
    return await launcher.cleanup_orphaned_processes()

async def get_all_agent_statuses() -> List[Dict[str, Any]]:
    """Get status of all running agent processes"""
    launcher = get_agent_launcher()
    return await launcher.get_all_agent_statuses() 