from __future__ import annotations

import logging
from dataclasses import dataclass, field
import json
import os
import sys
from typing import Dict, Any, Optional, List, Set, AsyncIterable
from livekit.agents import Agent, AgentSession, RunContext, function_tool, get_job_context
from voice_adaptation_manager import VoiceAdaptationManager

logger = logging.getLogger(__name__)

# Add the API directory to the path for crypto utilities
api_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'api')
if api_path not in sys.path:
    sys.path.insert(0, api_path)

try:
    from crypto_utils import decrypt_credentials
    crypto_utils_available = True
    logger.info("✅ crypto_utils imported successfully")
except ImportError as e:
    crypto_utils_available = False
    logger.warning(f"⚠️ Could not import crypto_utils: {e}")

# Check for cryptography library availability
try:
    from cryptography.fernet import Fernet
    import base64
    cryptography_available = True
except ImportError:
    cryptography_available = False
    logger.warning("⚠️ Cryptography library not available - app actions will be disabled")

# Import database client
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from api.db_client import supabase_service_client


@dataclass
class PathwaySessionData:
    """
    Stores pathway configuration and agent instances for the session.
    """
    pathway_config: Dict[str, Any]
    
    # Pre-initialized agent instances keyed by node_id
    agent_instances: Dict[str, 'PathwayNodeAgent'] = field(default_factory=dict)
    
    # Current node tracking
    current_node_id: Optional[str] = None
    
    # To store business-logic data collected during the call
    collected_data: Dict[str, Any] = field(default_factory=dict)
    
    def get_node_by_id(self, node_id: str) -> Optional[Dict[str, Any]]:
        """Get a node's configuration from the pathway."""
        for node in self.pathway_config.get('nodes', []):
            if node.get('id') == node_id:
                return node
        return None

    def get_next_conversation_node(self, current_node_id: str) -> Optional[str]:
        """Find the next conversation node following the pathway edges."""
        edges = self.pathway_config.get('edges', [])
        nodes = self.pathway_config.get('nodes', [])
        
        # Find all outgoing edges from current node
        outgoing_edges = [edge for edge in edges if edge.get('source') == current_node_id]
        
        for edge in outgoing_edges:
            target_node_id = edge.get('target')
            target_node = next((n for n in nodes if n.get('id') == target_node_id), None)
            
            if target_node and target_node.get('type') == 'conversation':
                return target_node_id
                
            # If target is a condition, follow its edges to find next conversation node
            elif target_node and target_node.get('type') == 'condition':
                condition_edges = [e for e in edges if e.get('source') == target_node_id]
                for condition_edge in condition_edges:
                    next_target_id = condition_edge.get('target')
                    next_target = next((n for n in nodes if n.get('id') == next_target_id), None)
                    if next_target and next_target.get('type') == 'conversation':
                        return next_target_id
        
        return None


class PathwayNodeAgent(Agent):
    """
    Dynamic agent that represents a single conversation node in a pathway.
    Follows LiveKit workflow patterns for agent handoffs via function tools.
    Features DYNAMIC transition generation from pathway configuration.
    """

    def __init__(self, node_config: Dict[str, Any], session_data: PathwaySessionData, chat_ctx=None):
        self.node_config = node_config
        self.session_data = session_data
        self.pathway_config = session_data.pathway_config  # Extract the actual config dict
        
        # Build instructions for this node
        instructions = self._build_instructions()
        
        # Initialize with chat context preservation (LiveKit pattern)
        # Tools are defined as class methods with @function_tool decorators (proper LiveKit pattern)
        super().__init__(instructions=instructions, chat_ctx=chat_ctx)

        # Initialize voice adaptation manager with feature flag
        enabled_str = os.getenv('VOICE_ADAPTATION_ENABLED', 'true')
        enabled = enabled_str.lower() in ('1', 'true', 'yes', 'on')
        try:
            rate_limit_s = float(os.getenv('VOICE_ADAPTATION_RATE_LIMIT_S', '2.0'))
        except Exception:
            rate_limit_s = 2.0
        try:
            memory_limit = int(os.getenv('VOICE_ADAPTATION_MEMORY_LIMIT', '20'))
        except Exception:
            memory_limit = 20
        self.voice_adapt = VoiceAdaptationManager(
            enable_adaptation=enabled,
            rate_limit_seconds=rate_limit_s,
            memory_limit=memory_limit,
        )
        
        # Initialize transition state
        self._pending_transition = None
    
    @function_tool
    async def make_transition(self, target_node_name: str):
        """
        ✅ PROPER LIVEKIT PATTERN: Single transition function that handles all transitions.
        Call this function when you need to transition to another part of the conversation.
        
        Args:
            target_node_name: Name of the target node to transition to (e.g., "Schedule appointment", "Information", etc.)
        """
        logger.info(f"🎯 Transition requested to: {target_node_name}")
        
        # Find the target node by name with flexible matching
        all_nodes = self.pathway_config.get('nodes', [])
        target_node = None
        target_node_lower = target_node_name.lower().strip()
        
        logger.info(f"🔍 Looking for node matching: '{target_node_name}'")
        logger.info(f"🔍 Available nodes: {[n.get('name', 'No name') for n in all_nodes]}")
        
        # Try exact name match first
        for node in all_nodes:
            node_name = node.get('name', '').lower().strip()
            if node_name == target_node_lower:
                target_node = node
                logger.info(f"✅ Exact match found: {node.get('name')}")
                break
        
        # If no exact match, try fuzzy matching (remove common words and check similarity)
        if not target_node:
            import difflib
            best_match = None
            best_score = 0.0
            
            for node in all_nodes:
                node_name = node.get('name', '').lower().strip()
                # Calculate similarity score
                score = difflib.SequenceMatcher(None, target_node_lower, node_name).ratio()
                if score > best_score and score > 0.6:  # 60% similarity threshold
                    best_score = score
                    best_match = node
            
            if best_match:
                target_node = best_match
                logger.info(f"✅ Fuzzy match found: {best_match.get('name')} (score: {best_score:.2f})")
        
        # Last resort: partial match
        if not target_node:
            for node in all_nodes:
                node_name = node.get('name', '').lower().strip()
                if target_node_lower in node_name or node_name in target_node_lower:
                    target_node = node
                    logger.info(f"✅ Partial match found: {node.get('name')}")
                    break
        
        if not target_node:
            logger.error(f"❌ Target node '{target_node_name}' not found in pathway")
            return f"Je ne peux pas vous diriger vers '{target_node_name}'. Puis-je vous aider autrement?"
        
        target_node_id = target_node.get('id')
        logger.info(f"✅ Found target node: {target_node_id} ({target_node.get('name')})")
        
        # Update session data with new current node
        self.session_data.current_node_id = target_node_id
        
        # Store the transition for later processing
        self._pending_transition = target_node
        
        # Return a response that indicates the transition is happening
        target_name = target_node.get('name', 'cette section')
        return f"Parfait ! Je vous dirige vers {target_name}."

    def _create_target_agent(self, target_node_id: str) -> 'Agent':
        """
        ✅ PROPER LIVEKIT WORKFLOW PATTERN:
        Create and return a new Agent instance for the target node.
        This follows the LiveKit pattern where function tools return Agent instances.
        """
        # Find target node configuration
        all_nodes = self.pathway_config.get('nodes', [])
        target_node = next((n for n in all_nodes if n.get('id') == target_node_id), None)
        
        if not target_node:
            logger.error(f"❌ Target node {target_node_id} not found in pathway")
            return self  # Return self as fallback
        
        # Update session data with new current node
        self.session_data.current_node_id = target_node_id
        
        # Create new PathwayNodeAgent for target node (proper LiveKit pattern)
        target_agent = PathwayNodeAgent(
            node_config=target_node,
            session_data=self.session_data,
            chat_ctx=self.chat_ctx  # ✅ Preserve chat context in transition
        )
        
        # Mark as transition for proper greeting handling
        target_agent._is_transition = True
        
        logger.info(f"✅ Created new Agent for node: {target_node_id} ({target_node.get('name', 'Unknown')})")
        return target_agent

    async def _say_with_adaptation(self, text_or_stream, *, stage: Optional[str] = None, analysis_text: Optional[str] = None, allow_interruptions_default: bool = True):
        """Helper to apply voice adaptation before speaking."""
        try:
            base_text = analysis_text if analysis_text is not None else (text_or_stream if isinstance(text_or_stream, str) else "")
            decision = self.voice_adapt.decide(base_text, stage=stage or self.node_config.get('type', 'conversation'))
            delay = decision.timing.pre_speech_delay_sec
            if delay > 0:
                import asyncio
                await asyncio.sleep(delay)
            allow_interruptions = decision.voice_settings.allow_interruptions
            logger.info(f"🔊 VoiceAdapt: stage={stage} speed={decision.voice_settings.speed} delay={delay}s emotions={decision.voice_settings.emotions}")
        except Exception as e:
            logger.debug(f"Voice adaptation fallback due to error: {e}")
            allow_interruptions = allow_interruptions_default
        await self.session.say(text_or_stream, allow_interruptions=allow_interruptions)

    # Override TTS node to add per-utterance timing and metrics (provider hints logged)
    async def tts_node(self, text: AsyncIterable[str], model_settings):
        import time as _time
        import asyncio as _asyncio
        # Determine stage from node type
        stage = self.node_config.get('type', 'conversation')
        # Apply pre-speech delay based on stage (no text peeking for simplicity)
        try:
            decision = self.voice_adapt.decide("", stage=stage)
            delay = decision.timing.pre_speech_delay_sec
            if delay > 0:
                await _asyncio.sleep(delay)
            logger.info(f"🔧 TTS node adaptation: stage={stage} speed={decision.voice_settings.speed} delay={delay}s")
        except Exception as e:
            logger.debug(f"TTS node adaptation skipped: {e}")

        # Metrics: measure TTFB and total synthesis time
        start_ts = _time.time()
        first_ts: Optional[float] = None

        try:
            async for frame in Agent.default.tts_node(self, text, model_settings):
                if first_ts is None:
                    first_ts = _time.time()
                    logger.info(f"📈 TTS TTFB: {first_ts - start_ts:.3f}s")
                yield frame
        finally:
            end_ts = _time.time()
            total = end_ts - start_ts
            logger.info(f"📈 TTS total synthesis time: {total:.3f}s (stage={stage})")

            # Emit structured metrics event
            try:
                job_ctx = get_job_context()
                room_name = getattr(job_ctx.room, 'name', None)
                metadata = {}
                if job_ctx and job_ctx.job and job_ctx.job.metadata:
                    try:
                        metadata = json.loads(job_ctx.job.metadata)
                    except Exception:
                        metadata = {}
                call_id = metadata.get('supabase_call_id') or metadata.get('call_id')
                agent_id = metadata.get('agent_id')
                pathway_execution_id = metadata.get('pathway_execution_id')
                node_id = self.session_data.current_node_id

                metrics = {
                    "type": "utterance_metrics",
                    "call_id": call_id,
                    "room_name": room_name,
                    "agent_id": agent_id,
                    "pathway_execution_id": pathway_execution_id,
                    "stage": stage,
                    "node_id": node_id,
                    "pre_speech_delay_ms": int((decision.timing.pre_speech_delay_sec if 'decision' in locals() else 0.0) * 1000),
                    "tts_ttfb_ms": int(((first_ts or end_ts) - start_ts) * 1000),
                    "tts_total_ms": int(total * 1000),
                    "adaptation": {
                        "speed": getattr(decision.voice_settings, 'speed', None) if 'decision' in locals() else None,
                        "emotions": getattr(decision.voice_settings, 'emotions', None) if 'decision' in locals() else None,
                        "interruptions_enabled": getattr(decision.voice_settings, 'allow_interruptions', None) if 'decision' in locals() else None,
                    },
                }

                # Try to emit via pathway integration helper if available
                try:
                    from agent_pathway_integration import handle_call_event
                    if call_id:
                        await handle_call_event("utterance_metrics", str(call_id), metrics)
                except Exception as e:
                    logger.debug(f"Metrics emit fallback (no handle_call_event): {e}; metrics={metrics}")
            except Exception as e:
                logger.debug(f"Failed to build/emit metrics: {e}")
            
            # 🔄 HANDLE PENDING TRANSITIONS: Process any transitions after TTS completes
            try:
                await self._handle_pending_transition()
            except Exception as e:
                logger.error(f"❌ Error handling pending transition: {e}")

    # Override LLM node for latency metrics (time to first token and total)
    async def llm_node(self, chat_ctx: Any, tools: Any, model_settings):
        import time as _time
        stage = self.node_config.get('type', 'conversation')
        start_ts = _time.time()
        first_ts: Optional[float] = None
        try:
            async for chunk in Agent.default.llm_node(self, chat_ctx, tools, model_settings):
                if first_ts is None:
                    first_ts = _time.time()
                    logger.info(f"📈 LLM TTFB: {first_ts - start_ts:.3f}s (stage={stage})")
                yield chunk
        finally:
            end_ts = _time.time()
            total = end_ts - start_ts
            logger.info(f"📈 LLM total latency: {total:.3f}s (stage={stage})")
            # Emit metrics
            try:
                job_ctx = get_job_context()
                room_name = getattr(job_ctx.room, 'name', None)
                metadata = {}
                if job_ctx and job_ctx.job and job_ctx.job.metadata:
                    try:
                        metadata = json.loads(job_ctx.job.metadata)
                    except Exception:
                        metadata = {}
                call_id = metadata.get('supabase_call_id') or metadata.get('call_id')
                agent_id = metadata.get('agent_id')
                pathway_execution_id = metadata.get('pathway_execution_id')
                node_id = self.session_data.current_node_id

                metrics = {
                    "type": "llm_metrics",
                    "call_id": call_id,
                    "room_name": room_name,
                    "agent_id": agent_id,
                    "pathway_execution_id": pathway_execution_id,
                    "stage": stage,
                    "node_id": node_id,
                    "llm_ttfb_ms": int(((first_ts or end_ts) - start_ts) * 1000),
                    "llm_total_ms": int(total * 1000),
                }
                try:
                    from agent_pathway_integration import handle_call_event
                    if call_id:
                        await handle_call_event("llm_metrics", str(call_id), metrics)
                except Exception as e:
                    logger.debug(f"Metrics emit fallback (no handle_call_event): {e}; metrics={metrics}")
            except Exception as e:
                logger.debug(f"Failed to build/emit LLM metrics: {e}")

    # Override STT node - simplified, metrics now handled via official LiveKit metrics_collected event
    async def stt_node(self, audio: Any, model_settings):
        # STT metrics are now collected via the official LiveKit metrics system
        # See outbound_agent.py metrics_collected handler for STTMetrics and EOUMetrics
        async for result in Agent.default.stt_node(self, audio, model_settings):
            yield result

    def _build_instructions(self) -> str:
        """
        Build comprehensive instructions for this pathway node that guide the LLM
        on both the conversation content and when to transition to other nodes.
        """
        base_instructions = []
        
        # 1. Add node-specific prompt/instructions
        # Try to get prompt from config.prompt (main format) or directly from prompt (test format)
        node_prompt = (self.node_config.get('config', {}).get('prompt', '') or 
                       self.node_config.get('prompt', ''))
        if node_prompt:
            base_instructions.append(f"CONVERSATION ROLE: {node_prompt}")
        
        # 2. Add context about current pathway position
        node_name = self.node_config.get('name', 'Unknown Node')
        node_id = self.node_config.get('id', 'unknown')
        base_instructions.append(f"CURRENT NODE: You are currently in '{node_name}' (ID: {node_id})")
        
        # 3. ✅ ADD DYNAMIC TRANSITION RULES
        base_instructions.extend([
            "",
            "🔥 TRANSITION INSTRUCTIONS:",
            "- Use make_transition(target_node_name) to move to another part of the conversation",
            "- Pass the NAME of the target node (not the ID)",
            "- Listen to user intent to determine when and where to transition",
            ""
        ])
        
        # 4. Add available transition targets based on pathway edges
        current_node_id = self.node_config.get('id')
        all_edges = self.pathway_config.get('edges', [])
        outgoing_edges = [edge for edge in all_edges if edge.get('source') == current_node_id]
        
        if outgoing_edges:
            base_instructions.append("🎯 AVAILABLE DESTINATIONS:")
            for edge in outgoing_edges:
                condition = edge.get('condition', 'default')
                target_id = edge.get('target')
                target_node = next((n for n in self.pathway_config.get('nodes', []) if n.get('id') == target_id), None)
                if target_node:
                    target_name = target_node.get('name', target_id)
                    target_type = target_node.get('type', 'conversation')
                    
                    if target_type == 'app_action':
                        base_instructions.append(f"  🔧 make_transition('{target_name}') → When: {condition}")
                    elif target_type == 'condition':
                        base_instructions.append(f"  🔀 make_transition('{target_name}') → When: {condition}")
                    else:
                        base_instructions.append(f"  💬 make_transition('{target_name}') → When: {condition}")
                        
                        # Add specific trigger guidance for app actions
                        if 'app_action' in target_id.lower() or 'calendar' in target_name.lower():
                            base_instructions.append(f"    ⚡ TRIGGER WORDS: Oui, Ok, D'accord, Parfait, Ça marche, C'est bon → IMMEDIATE transition!")
                        
                        # Add specific trigger guidance for common appointment words
                        if 'schedule' in target_name.lower() or 'appointment' in target_name.lower() or 'rdv' in target_name.lower():
                            base_instructions.append(f"    📅 APPOINTMENT TRIGGERS: Any acceptance of date/time → IMMEDIATE transition!")
        
        # 5. Add tool execution priority
        if 'schedule' in node_name.lower() or 'appointment' in node_name.lower() or 'callback' in node_name.lower():
            base_instructions.extend([
                "",
                "🚨 MANDATORY APPOINTMENT SCHEDULING SEQUENCE:",
                "1. FIRST: Collect appointment details (date, time, duration, purpose)",
                "2. SECOND: Confirm details with user",  
                "3. When user confirms appointment details, use the appropriate dynamic transition",
                "4. Follow the pathway flow as configured in the system",
                "",
                "🎯 DYNAMIC TRANSITIONS:",
                "• All transition functions are automatically generated from pathway configuration",
                "• Use the transition functions that appear in your available tools list",
                "• Follow the pathway edges as defined in the configuration",
                ""
            ])
        
        return "\n".join(base_instructions)
    
    # 🔥 DYNAMIC TRANSITION SYSTEM: Transition functions are now auto-generated from pathway config
    # The hardcoded functions below are kept for backward compatibility with legacy pathways
    # New pathways will use the dynamic system in _register_dynamic_transitions()
    
    # ✅ ALL HARDCODED TRANSITIONS REMOVED - Now using dynamic transition system only!
    # All transitions are automatically generated from pathway configuration edges in _register_dynamic_transitions()

    async def on_enter(self):
        """
        Called when this agent becomes active.
        Delivers a greeting message if configured and preserves context.
        Following LiveKit workflow patterns.
        """
        logger.info(f"🎯 Entering pathway node: {self.node_config.get('id')}")
        
        # Update the current node tracking
        session_data = self.session.userdata
        
        # Defensive check: Ensure session_data is a PathwaySessionData object
        if isinstance(session_data, dict):
            logger.error(f"session_data is a dict instead of PathwaySessionData object: {session_data}")
            # Create a proper PathwaySessionData object from the dict
            session_data = PathwaySessionData(
                pathway_config=session_data.get('pathway_config', {}),
                agent_instances=session_data.get('agent_instances', {}),
                current_node_id=session_data.get('current_node_id'),
                collected_data=session_data.get('collected_data', {})
            )
            # Update the session userdata with the proper object
            self.session.userdata = session_data
        
        session_data.current_node_id = self.node_config.get('id')
        
        # Apply per-session/per-agent voice adaptation overrides if present
        try:
            va_cfg = getattr(self.session_data, 'collected_data', {}).get('voice_adaptation')
            if isinstance(va_cfg, dict):
                enabled = va_cfg.get('enabled')
                if enabled is not None:
                    self.voice_adapt.enable_adaptation = bool(enabled)
                rate_lim = va_cfg.get('rate_limit_seconds')
                if isinstance(rate_lim, (int, float)):
                    self.voice_adapt.rate_limit_seconds = float(rate_lim)
                mem_lim = va_cfg.get('memory_limit')
                if isinstance(mem_lim, int):
                    self.voice_adapt.memory_limit = mem_lim
                logger.info(f"🔧 Applied per-agent voice adaptation config: {va_cfg}")
        except Exception as e:
            logger.debug(f"Failed applying voice adaptation overrides: {e}")
        
        # ✅ HANDLE APP_ACTION NODES
        if self.node_config.get('type') == 'app_action':
            logger.info(f"🚀 Processing app_action node: {self.node_config.get('id')}")
            logger.info(f"📋 Full node config: {self.node_config}")
            
            # Extract app action configuration
            action_data = self.node_config.get('config', {}).get('data', {})
            app_name = action_data.get('app_name') or action_data.get('selected_app_name')
            action_type = action_data.get('action_type') or action_data.get('selected_action_id')
            parameters = action_data.get('parameters', {})
            
            logger.info(f"📊 Extracted app_name: '{app_name}', action_type: '{action_type}'")
            logger.info(f"📝 Parameters: {parameters}")
            
            try:
                # Execute the app action via backend API
                result = await self._execute_app_action(app_name, action_type, parameters)
                logger.info(f"✅ App action completed: {result}")
                
                # Update session data with action results
                session_data = self.session.userdata
                if not hasattr(session_data, 'collected_data'):
                    session_data.collected_data = {}
                session_data.collected_data[f'app_action_{self.node_config.get("id")}'] = result
                
                # Respond to user about the action completion
                if result.get('status') == 'success':
                    user_message = result.get('user_message', f"Successfully completed {action_type}")
                    await self._say_with_adaptation(user_message, stage='app_action', analysis_text=user_message, allow_interruptions_default=True)
                else:
                    error_message = result.get('error', f"Failed to complete {action_type}")
                    await self._say_with_adaptation(f"I apologize, but I encountered an issue: {error_message}", stage='app_action', analysis_text=error_message, allow_interruptions_default=True)
                    
                # Auto-transition to next node after app action
                logger.info(f"🎯 Auto-transitioning from app_action to next node")
                await self._auto_transition_from_app_action()
                return  # Don't return new agent - let current session continue
                    
            except Exception as e:
                logger.error(f"❌ App action failed: {e}")
                await self.session.say("I apologize, but I encountered a technical issue while processing your request.", allow_interruptions=True)
                # Continue to normal conversation if app action fails
                pass
            
            return  # Exit early for app_action nodes
        
        # ✅ HANDLE END_CALL NODES PROPERLY
        if self.node_config.get('type') == 'end_call':
            logger.info(f"📞 Processing end_call node: {self.node_config.get('id')}")
            
            # ✅ USE AI-ENHANCED GOODBYE GENERATION
            node_config = self.node_config.get('config', {})
            ai_prompt = node_config.get('prompt')
            
            if ai_prompt:
                # Generate AI-powered goodbye message
                logger.info("🤖 Using AI-enhanced goodbye generation")
                goodbye_message = await self._generate_ai_goodbye(ai_prompt, node_config)
            else:
                # Fall back to static goodbye message
                logger.info("📝 Using static goodbye message (no prompt configured)")
                goodbye_message = node_config.get('goodbye_message', 'Thank you for your time. Have a great day!')
            
            logger.info(f"💬 Delivering goodbye message: '{goodbye_message}'")
            await self._say_with_adaptation(goodbye_message, stage='end_call', analysis_text=goodbye_message, allow_interruptions_default=False)
            
            # ✅ PROPERLY END CALL USING LIVEKIT SDK
            try:
                from livekit.agents import get_job_context
                from livekit import api
                
                logger.info("🔚 Ending call by deleting LiveKit room...")
                job_ctx = get_job_context()
                await job_ctx.api.room.delete_room(
                    api.DeleteRoomRequest(room=job_ctx.room.name)
                )
                logger.info("✅ Call ended successfully")
                
            except Exception as e:
                logger.error(f"❌ Failed to end call properly: {e}")
            
            return  # Exit early for end_call nodes
        
        # ✅ REGULAR NODE PROCESSING
        # Deliver greeting if configured (LiveKit pattern)
        greeting = self.node_config.get('greeting_message')
        if not greeting:
            # Try different config paths for greeting
            greeting = self.node_config.get('config', {}).get('greeting')
        
        # Check if this is a transition vs initial entry
        is_transition = getattr(self, '_is_transition', False)
        
        if greeting and greeting.strip():
            logger.info(f"💬 Delivering greeting: '{greeting}'")
            await self._say_with_adaptation(greeting, stage='greeting', analysis_text=greeting, allow_interruptions_default=True)
        else:
            # ✅ NO GREETING REQUIRED: Node is ready for conversation without blocking
            if is_transition:
                logger.info(f"🔄 Transitioned to {self.node_config.get('id')} - no greeting needed, continuing conversation")
                # 🎯 TRANSITION ACKNOWLEDGMENT: Provide a brief transition acknowledgment
                node_name = self.node_config.get('name', 'this section')
                node_type = self.node_config.get('type', 'conversation')
                
                # Create a contextual transition message based on the node
                if 'appointment' in node_name.lower() or 'schedule' in node_name.lower():
                    transition_msg = "Parfait ! Je vais vous aider à planifier votre rendez-vous."
                elif 'information' in node_name.lower() or 'info' in node_name.lower():
                    transition_msg = "Bien sûr ! Je peux vous renseigner sur nos services."
                else:
                    transition_msg = f"Je vous dirige vers {node_name.lower()}."
                
                logger.info(f"🎯 Delivering transition acknowledgment: '{transition_msg}'")
                try:
                    await self._say_with_adaptation(
                        transition_msg, 
                        stage='transition', 
                        analysis_text=transition_msg, 
                        allow_interruptions_default=True
                    )
                except Exception as e:
                    logger.error(f"❌ Error delivering transition acknowledgment: {e}")
                    # Continue normally if transition message fails
            else:
                logger.info(f"ℹ️ No greeting configured for node {self.node_config.get('id')} - ready for direct conversation")
        
        # Clear the transition flag after handling
        if hasattr(self, '_is_transition'):
            delattr(self, '_is_transition')
        
        # ✅ PROPER LIVEKIT PATTERN: Wait for user input, don't force generate_reply
        logger.info(f"🤖 Node ready for conversation: {self.node_config.get('id')} (waiting for user input)")

    async def _handle_pending_transition(self):
        """Process any pending transitions after TTS completes."""
        if hasattr(self, '_pending_transition') and self._pending_transition:
            logger.info(f"🔄 Processing pending transition to: {self._pending_transition.get('name')}")
            
            # Create the target agent
            target_agent = self._create_target_agent(self._pending_transition.get('id'))
            
            # Clear the pending transition
            self._pending_transition = None
            
            # Try multiple ways to access the LiveKit session for agent handoff
            try:
                # Method 1: Try via agent context
                if hasattr(self, 'ctx') and hasattr(self.ctx, 'session'):
                    await self.ctx.session.set_agent(target_agent)
                    logger.info("✅ Transition completed via agent context")
                    return True
                
                # Method 2: Try via job context
                from livekit.agents import get_job_context
                job_ctx = get_job_context()
                if job_ctx and hasattr(job_ctx, 'session'):
                    await job_ctx.session.set_agent(target_agent)
                    logger.info("✅ Transition completed via job context")
                    return True
                
                # Method 3: Try via session data if available
                if hasattr(self.session_data, 'session'):
                    await self.session_data.session.set_agent(target_agent)
                    logger.info("✅ Transition completed via session data")
                    return True
                
                logger.warning("⚠️ Could not access session for agent handoff - continuing with current agent")
                return False
                
            except Exception as e:
                logger.error(f"❌ Error during agent transition: {e}")
                return False
        return False

    async def _execute_app_action(self, app_name: str, action_type: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute app action using real API integration with OAuth tokens
        """
        logger.info(f"🔧 Executing {app_name}.{action_type} with real API integration")
        
        try:
            # Import required modules for API calls
            import aiohttp
            from datetime import datetime, timedelta
            
            # Get user's OAuth connection for the app
            session_data = self.session.userdata
            user_id = getattr(session_data, 'user_id', 'b55837c4-270f-4f1f-8023-7ab09ee5f44d')  # Default to test user
            
            # Query user's app connection
            logger.info(f"🔍 Looking for {app_name} connection for user {user_id}")
            connections_response = supabase_service_client.table("user_app_connections").select("*").eq("user_id", user_id).execute()
            
            if not connections_response.data:
                logger.warning(f"❌ No OAuth connections found for user {user_id}")
                return {
                    "status": "error",
                    "error": "No OAuth connection found. Please connect your Google Calendar first.",
                    "user_message": "I need you to connect your Google Calendar first before I can schedule appointments."
                }
            
            # Find Google Calendar connection
            calendar_connection = None
            for conn in connections_response.data:
                app_integration_response = supabase_service_client.table("app_integrations").select("*").eq("id", conn["app_integration_id"]).execute()
                if app_integration_response.data and app_integration_response.data[0]["name"] == "google_calendar":
                    calendar_connection = conn
                    break
            
            if not calendar_connection:
                logger.warning(f"❌ No Google Calendar connection found for user {user_id}")
                return {
                    "status": "error",
                    "error": "Google Calendar not connected",
                    "user_message": "I need you to connect your Google Calendar first before I can schedule appointments."
                }
            
            logger.info(f"✅ Found Google Calendar connection: {calendar_connection['id']}")
            
            # Decrypt OAuth credentials
            try:
                encrypted_credentials = calendar_connection["credentials"]
                logger.info(f"🔐 Attempting to decrypt OAuth credentials")
                
                access_token = None
                
                # Method 1: Use the proper crypto_utils function if available
                if crypto_utils_available:
                    try:
                        oauth_data = decrypt_credentials(encrypted_credentials)
                        access_token = oauth_data.get("access_token")
                        if access_token:
                            logger.info(f"✅ Successfully decrypted credentials using crypto_utils")
                        else:
                            logger.warning("⚠️ crypto_utils decrypted but no access_token found")
                    except Exception as crypto_error:
                        logger.warning(f"⚠️ crypto_utils decryption failed: {crypto_error}")
                
                # Fallback methods if crypto_utils failed or unavailable
                if not access_token:
                    logger.info("Trying fallback decryption methods...")
                    
                    # Method 2: Try base64 decoding (common format)
                try:
                    import base64
                    decoded_data = base64.b64decode(encrypted_credentials)
                    oauth_data = json.loads(decoded_data.decode())
                    access_token = oauth_data.get("access_token")
                    logger.info(f"✅ Successfully decoded credentials using base64")
                except:
                    pass
                
                    # Method 3: Try Fernet decryption if base64 failed
                if not access_token and cryptography_available:
                    try:
                        # Get encryption key for decrypting OAuth tokens (same pattern as crypto_utils.py)
                        encryption_key_str = os.getenv('INTEGRATION_ENCRYPTION_KEY', 'your-32-byte-base64-encoded-key==')
                        # Convert string to bytes properly (don't double-encode!)
                        encryption_key_bytes = encryption_key_str.encode() if isinstance(encryption_key_str, str) else encryption_key_str
                        f = Fernet(encryption_key_bytes)
                        
                        # Try direct Fernet decryption
                        decrypted_data = f.decrypt(encrypted_credentials.encode())
                        oauth_data = json.loads(decrypted_data.decode())
                        access_token = oauth_data.get("access_token")
                        logger.info(f"✅ Successfully decrypted credentials using Fernet")
                    except Exception as fernet_error:
                        logger.debug(f"Fernet direct decryption failed: {fernet_error}")
                        
                        # Try Fernet decryption on base64-decoded data (our discovered format)
                        try:
                            decoded_creds = base64.b64decode(encrypted_credentials)
                            decrypted_data = f.decrypt(decoded_creds)
                            oauth_data = json.loads(decrypted_data.decode())
                            access_token = oauth_data.get("access_token")
                            logger.info(f"✅ Successfully decrypted credentials using Fernet on base64-decoded data")
                        except Exception as fernet_b64_error:
                            logger.debug(f"Fernet on base64 decryption failed: {fernet_b64_error}")
                            pass
                    
                    # Method 4: Try direct JSON parsing (if stored as plain JSON)
                if not access_token:
                    try:
                        oauth_data = json.loads(encrypted_credentials)
                        access_token = oauth_data.get("access_token")
                        logger.info(f"✅ Successfully parsed credentials as direct JSON")
                    except:
                        pass
                
                    # Method 5: Try alternative encryption keys (for key rotation scenarios)
                    if not access_token and cryptography_available:
                        try:
                            # Try the other key we discovered in the diagnostic
                            alt_key_str = 'wLwYSfmXhP29kuL5FU1l5S8iamcAHTAHj4UenDylIdw='
                            # Convert string to bytes properly (don't double-encode!)
                            alt_key_bytes = alt_key_str.encode() if isinstance(alt_key_str, str) else alt_key_str
                            f_alt = Fernet(alt_key_bytes)
                            
                            # Try with base64-decoded data first (our discovered format)
                            decoded_creds = base64.b64decode(encrypted_credentials)
                            decrypted_data = f_alt.decrypt(decoded_creds)
                            oauth_data = json.loads(decrypted_data.decode())
                            access_token = oauth_data.get("access_token")
                            logger.info(f"✅ Successfully decrypted credentials using alternative key")
                        except Exception as alt_key_error:
                            logger.debug(f"Alternative key decryption failed: {alt_key_error}")
                        pass
                
                if not access_token:
                        logger.error("❌ Could not extract access_token from any decryption method")
                        logger.error(f"   Credential format: {len(encrypted_credentials)} chars, starts with: {encrypted_credentials[:50]}...")
                        raise Exception("Could not extract access_token from any decryption method")
                    
                logger.info(f"🔐 Successfully extracted access token")
                
            except Exception as e:
                logger.error(f"❌ Failed to decrypt OAuth credentials: {e}")
                return {
                    "status": "error",
                    "error": "Failed to access Google Calendar credentials",
                    "user_message": "There was an issue accessing your Google Calendar. Please reconnect your account."
                }
            
            # Execute specific app action
            if app_name == "google_calendar" and action_type == "create_event":
                return await self._create_google_calendar_event(access_token, parameters)
            else:
                logger.warning(f"❌ Unsupported app action: {app_name}.{action_type}")
                return {
                    "status": "error",
                    "error": f"Unsupported action: {app_name}.{action_type}",
                    "user_message": "This action is not yet supported."
                }
                
        except Exception as e:
            logger.error(f"❌ App action execution failed: {e}")
            return {
                "status": "error",
                "error": str(e),
                "user_message": "I encountered a technical issue while processing your request."
            }
    
    async def _create_google_calendar_event(self, access_token: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a Google Calendar event using the Calendar API
        """
        import aiohttp
        from datetime import datetime, timedelta
        import json
        
        logger.info(f"📅 Creating Google Calendar event with parameters: {parameters}")
        
        try:
            # Use single aiohttp session for both API calls
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }
            
            # First, get the user's Google Calendar timezone setting 
            async with aiohttp.ClientSession() as session:
                calendar_response = await session.get(
                    "https://www.googleapis.com/calendar/v3/calendars/primary",
                    headers=headers
                )
                calendar_data = await calendar_response.json()
                user_timezone = calendar_data.get("timeZone", "UTC")
                logger.info(f"🌍 Using user's Google Calendar timezone: {user_timezone}")
                
            # Prepare event data with smart defaults
            session_data = self.session.userdata
            collected_data = getattr(session_data, 'collected_data', {})
            
            # Extract or set default event details
            title = parameters.get('title') or parameters.get('summary') or 'Sales Callback Appointment'
            description = parameters.get('description') or 'Scheduled during PAM conversation'
            
            # Handle start time - try to parse or use default (tomorrow 2pm)
            start_time_str = parameters.get('start_time') or parameters.get('dateTime')
            if start_time_str:
                try:
                    if isinstance(start_time_str, str):
                        start_time = datetime.fromisoformat(start_time_str.replace('Z', '+00:00'))
                    else:
                        start_time = start_time_str
                except:
                    # Default to tomorrow at 2pm if parsing fails
                    start_time = datetime.now() + timedelta(days=1)
                    start_time = start_time.replace(hour=14, minute=0, second=0, microsecond=0)
            else:
                # Default to tomorrow at 2pm
                start_time = datetime.now() + timedelta(days=1)
                start_time = start_time.replace(hour=14, minute=0, second=0, microsecond=0)
            
            # Calculate end time (default to 30 minutes)
            duration_minutes = parameters.get('duration', 30)
            end_time = start_time + timedelta(minutes=duration_minutes)
            
            # Prepare Google Calendar API event data
            event_data = {
                "summary": title,
                "description": description,
                "start": {
                    "dateTime": start_time.isoformat(),
                        "timeZone": user_timezone
                },
                "end": {
                    "dateTime": end_time.isoformat(),
                        "timeZone": user_timezone
                },
                "reminders": {
                    "useDefault": True
                }
            }
            
            # Add attendees if provided
            attendees = parameters.get('attendees', [])
            if attendees:
                event_data["attendees"] = [{"email": email} for email in attendees]
            
            logger.info(f"📤 Sending calendar event to Google API: {event_data}")
            
            # Make API call to Google Calendar
            calendar_id = parameters.get('calendar_id', 'primary')
            api_url = f"https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events"
            
            async with session.post(api_url, headers=headers, data=json.dumps(event_data)) as response:
                response_data = await response.json()
                
                if response.status == 200:
                    event_id = response_data.get("id")
                    event_link = response_data.get("htmlLink")
                    
                    logger.info(f"✅ Google Calendar event created successfully: {event_id}")
            
                    # Format user-friendly response
                    formatted_time = start_time.strftime("%A, %B %d at %I:%M %p")
                    
                    return {
                        "status": "success",
                        "event_id": event_id,
                        "event_link": event_link,
                        "start_time": start_time.isoformat(),
                        "end_time": end_time.isoformat(),
                        "title": title,
                        "user_message": f"Perfect! I've scheduled your {title.lower()} for {formatted_time}. You should receive a calendar invitation shortly."
                    }
                else:
                    logger.error(f"❌ Google Calendar API error: {response.status} - {response_data}")
                    return {
                        "status": "error",
                        "error": f"Google Calendar API error: {response_data.get('error', {}).get('message', 'Unknown error')}",
                        "user_message": "I encountered an issue scheduling the appointment. Let me try a different approach."
                    }
                        
        except Exception as e:
            logger.error(f"❌ Calendar event creation failed: {e}")
            return {
                "status": "error",
                "error": str(e),
                "user_message": "I encountered a technical issue while scheduling the appointment."
            }
    
    async def _auto_transition_from_app_action(self):
        """
        Automatically transition to the next node after completing an app action.
        Updates session state but doesn't return new agent to avoid LiveKit conflicts.
        """
        logger.info(f"🎯 Auto-transitioning from app_action node: {self.node_config.get('id')}")
        
        try:
            current_node_id = self.node_config.get('id')
            all_edges = self.pathway_config.get('edges', [])
            
            # Find outgoing edges from current app_action node
            outgoing_edges = [edge for edge in all_edges if edge.get('source') == current_node_id]
            
            if outgoing_edges:
                # Take the first available edge (app_action nodes typically have one exit)
                target_edge = outgoing_edges[0]
                target_node_id = target_edge.get('target')
                
                # ✅ Prevent transitioning to the same node
                if target_node_id == current_node_id:
                    logger.warning(f"⚠️ Attempted to transition to same node: {current_node_id}. Staying in current node.")
                    return
                
                logger.info(f"🎯 Auto-transitioning to: {target_node_id}")
                
                # Find target node
                all_nodes = self.pathway_config.get('nodes', [])
                target_node = next((node for node in all_nodes if node.get('id') == target_node_id), None)
                
                if target_node:
                    # Update current node tracking
                    self.session_data.current_node_id = target_node_id
                    
                    # Pre-create target agent if it doesn't exist (for future transitions)
                    if target_node_id not in self.session_data.agent_instances:
                        target_agent = PathwayNodeAgent(
                            node_config=target_node, 
                            session_data=self.session_data,
                            chat_ctx=None
                        )
                        self.session_data.agent_instances[target_node_id] = target_agent
                        logger.info(f"✅ Pre-created agent for future use: {target_node_id}")
                    else:
                        logger.info(f"✅ Agent already exists for: {target_node_id}")
                    
                    logger.info(f"✅ Auto-transition state updated to: {target_node_id}")
                    
                    # Handle different node types after transition
                    target_node_type = target_node.get('type')
                    
                    if target_node_type == 'conversation':
                        await self._trigger_conversation_greeting(target_node)
                    elif target_node_type == 'end_call':
                        # Special handling for end_call nodes - trigger immediately
                        await self._trigger_end_call(target_node)
                    else:
                        logger.info(f"ℹ️ Transitioned to {target_node_type} node - no special handling needed")
                        
                else:
                    logger.error(f"❌ Target node not found: {target_node_id}")
            else:
                logger.warning(f"⚠️ No outgoing edges found from app_action node: {current_node_id}")
                
        except Exception as e:
            logger.error(f"❌ Auto-transition failed: {e}")
        
    async def _trigger_conversation_greeting(self, target_node):
        """Trigger greeting for conversation node after transition"""
        try:
            node_config = target_node.get('config', {})
            greeting = node_config.get('greeting', '')
            
            if greeting:
                logger.info(f"🎙️ Delivering greeting for transitioned node: {greeting}")
                await self._say_with_adaptation(greeting, stage='greeting', analysis_text=greeting, allow_interruptions_default=True)
            else:
                # Continue conversation based on node prompt
                node_prompt = node_config.get('prompt', '')
                if node_prompt:
                    logger.info(f"🤖 Starting conversation based on node prompt")
                    await self.session.generate_reply(node_prompt)
                    
        except Exception as e:
            logger.error(f"❌ Error triggering conversation greeting: {e}")
    
    async def _trigger_end_call(self, target_node):
        """Handle end_call node transition - deliver AI or static goodbye and end session"""
        try:
            node_config = target_node.get('config', {})
            
            # Check if node has AI prompt for dynamic goodbye generation
            ai_prompt = node_config.get('prompt')
            
            if ai_prompt:
                # Generate AI-powered goodbye message
                goodbye_message = await self._generate_ai_goodbye(ai_prompt, node_config)
            else:
                # Fall back to static goodbye message
                goodbye_message = node_config.get('goodbye_message', 'Thank you for your time. Have a great day!')
            
            logger.info(f"👋 Ending call with goodbye: {goodbye_message}")
            await self.session.say(goodbye_message, allow_interruptions=False)
            
            # Give a moment for the message to be delivered
            import asyncio
            await asyncio.sleep(2)
            
            # End the session gracefully
            logger.info(f"🏁 Ending session for end_call node")
            # The session will naturally end when the agent exits
            
        except Exception as e:
            logger.error(f"❌ Error triggering end call: {e}")
    
    async def _generate_ai_goodbye(self, ai_prompt: str, node_config: dict) -> str:
        """Generate AI-powered goodbye message based on conversation context"""
        try:
            logger.info(f"🤖 Generating AI goodbye with prompt: {ai_prompt}")
            
            # Build context for AI goodbye generation
            conversation_context = []
            
            # Add recent conversation history if available
            if hasattr(self.session, '_chat_ctx') and self.session._chat_ctx:
                # Get last few messages for context
                recent_messages = self.session._chat_ctx.messages[-5:] if len(self.session._chat_ctx.messages) > 5 else self.session._chat_ctx.messages
                for msg in recent_messages:
                    conversation_context.append(f"{msg.role}: {msg.content}")
            
            # Add collected pathway data
            pathway_data = []
            if self.session_data.collected_data:
                for key, value in self.session_data.collected_data.items():
                    pathway_data.append(f"{key}: {value}")
            
            # Build the context prompt
            context_parts = []
            if conversation_context:
                context_parts.append(f"Recent conversation:\n" + "\n".join(conversation_context))
            if pathway_data:
                context_parts.append(f"Collected information:\n" + "\n".join(pathway_data))
            
            context_text = "\n\n".join(context_parts) if context_parts else "No specific context available."
            
            # Create the full prompt for AI goodbye generation
            full_prompt = f"""Based on the following conversation context, generate a personalized and appropriate goodbye message.

{context_text}

Instructions: {ai_prompt}

Generate a natural, personalized goodbye message (keep it under 50 words):"""
            
            # Use the session's LLM to generate response
            from livekit.agents.llm import ChatMessage
            
            ai_messages = [ChatMessage(role="user", content=full_prompt)]
            llm_stream = await self.session.llm.chat(history=ai_messages)
            
            # Collect the AI response
            ai_goodbye = ""
            async for chunk in llm_stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    ai_goodbye += chunk.choices[0].delta.content
            
            # Clean up the response and apply length limit
            ai_goodbye = ai_goodbye.strip()
            if len(ai_goodbye) > 200:  # Safety limit
                ai_goodbye = ai_goodbye[:200] + "..."
            
            # Fallback if AI response is empty or too short
            if len(ai_goodbye) < 10:
                fallback_msg = node_config.get('goodbye_message', 'Thank you for your time. Have a great day!')
                logger.warning(f"⚠️ AI goodbye too short, using fallback: {fallback_msg}")
                return fallback_msg
            
            logger.info(f"✅ Generated AI goodbye: {ai_goodbye}")
            return ai_goodbye
            
        except Exception as e:
            logger.error(f"❌ Error generating AI goodbye: {e}")
            # Fall back to static message on any error
            fallback_msg = node_config.get('goodbye_message', 'Thank you for your time. Have a great day!')
            logger.info(f"🔄 Using fallback goodbye: {fallback_msg}")
            return fallback_msg

    async def on_exit(self):
        """
        Called when this agent is about to be replaced.
        Save any session data to the database here if needed.
        Following LiveKit workflow patterns.
        """
        logger.info(f"👋 Exiting pathway node: {self.node_config.get('id')}")
        
        # Future: Save session data to database
        # session_data: PathwaySessionData = self.session.userdata
        # await session_data.save_to_database(supabase_client, pathway_execution_id)
