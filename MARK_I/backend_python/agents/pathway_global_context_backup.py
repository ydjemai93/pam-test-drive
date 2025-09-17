from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, Any, Optional
from livekit.agents import Agent, AgentSession, RunContext, function_tool

logger = logging.getLogger(__name__)

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
    """

    def __init__(self, node_config: Dict[str, Any], session_data: PathwaySessionData, chat_ctx=None):
        self.node_config = node_config
        self.session_data = session_data
        self.pathway_config = session_data.pathway_config  # Extract the actual config dict
        
        # Build instructions for this node
        instructions = self._build_instructions()
        
        # Initialize with chat context preservation (LiveKit pattern)
        super().__init__(instructions=instructions, chat_ctx=chat_ctx)

    def _build_instructions(self) -> str:
        """
        Build comprehensive instructions for this pathway node that guide the LLM
        on both the conversation content and when to transition to other nodes.
        """
        base_instructions = []
        
        # 1. Add node-specific prompt/instructions
        node_prompt = self.node_config.get('config', {}).get('prompt', '')
        if node_prompt:
            base_instructions.append(f"CONVERSATION ROLE: {node_prompt}")
        
        # 2. Add context about current pathway position
        node_name = self.node_config.get('name', 'Unknown Node')
        node_id = self.node_config.get('id', 'unknown')
        base_instructions.append(f"CURRENT NODE: You are currently in '{node_name}' (ID: {node_id})")
        
        # 3. ✅ ADD CRITICAL TOOL USAGE RULES
        base_instructions.extend([
            "",
            "🔥 CRITICAL TOOL USAGE RULES:",
            "- ONLY call ONE transition tool per conversation turn",
            "- NEVER call multiple transition tools simultaneously", 
            "- Complete your current task BEFORE moving to the next node",
            "- If scheduling appointments, ALWAYS complete the booking process first",
            ""
        ])
        
        # 4. Add transition guidance based on available tools
        available_transitions = []
        current_node_id = self.node_config.get('id')
        all_edges = self.pathway_config.get('edges', [])
        outgoing_edges = [edge for edge in all_edges if edge.get('source') == current_node_id]
        
        if outgoing_edges:
            base_instructions.append("AVAILABLE TRANSITIONS:")
            for edge in outgoing_edges:
                condition = edge.get('condition', 'default')
                target_id = edge.get('target')
                target_node = next((n for n in self.pathway_config.get('nodes', []) if n.get('id') == target_id), None)
                if target_node:
                    target_name = target_node.get('name', target_id)
                    
                    # ✅ PRIORITIZE CALENDAR BOOKING TOOLS
                    if 'calendar' in condition.lower() or 'appointment' in condition.lower() or 'schedule' in condition.lower():
                        base_instructions.append(f"  🅰️ PRIORITY: Call transition_to_{condition} when appointment details are confirmed")
                        available_transitions.append(f"transition_to_{condition}")
                    elif 'end' in condition.lower() or 'call' in target_name.lower():
                        base_instructions.append(f"  🅱️ SECONDARY: Call transition_to_{condition} only after all other tasks are complete")  
                        available_transitions.append(f"transition_to_{condition}")
                    else:
                        base_instructions.append(f"  - Call transition_to_{condition} when: {condition}")
                        available_transitions.append(f"transition_to_{condition}")
        
        # 5. Add tool execution priority
        if 'schedule' in node_name.lower() or 'appointment' in node_name.lower() or 'callback' in node_name.lower():
            base_instructions.extend([
                "",
                "📋 APPOINTMENT SCHEDULING PRIORITY:",
                "1. FIRST: Collect appointment details (date, time, duration, purpose)",
                "2. SECOND: Confirm details with user",  
                "3. THIRD: Call transition_to_create_calendar_event to book appointment",
                "4. LAST: Do NOT call any other transition tools until booking is complete",
                ""
            ])
        
        return "\n".join(base_instructions)
    
    # ✅ SIMPLE LIVEKIT PATTERN: Static function tools that check pathway dynamically
    @function_tool()
    async def transition_to_qualify_lead(self) -> Agent:
        """Transition when the person is available to talk and shows interest in our services."""
        return await self._handle_transition_to_target("conversation-1752585487904", "qualify_lead")
    
    @function_tool() 
    async def transition_to_schedule_callback(self) -> Agent:
        """Transition when the person is busy or wants to be called back later."""
        return await self._handle_transition_to_target("conversation-1752585570818", "schedule_callback")
    
    @function_tool()
    async def transition_to_end_call_greeting(self) -> Agent:
        """Transition when the person seems uninterested, hostile, or wants to end the call."""
        return await self._handle_transition_to_target("end_call", "end_call_greeting")
    
    @function_tool()
    async def transition_to_book_appointment(self) -> Agent:
        """Transition when the person is a qualified lead with genuine interest and budget."""
        return await self._handle_transition_to_target("conversation-1752585662522", "book_appointment")
    
    @function_tool()
    async def transition_to_send_information(self) -> Agent:
        """Transition when the person wants more information before scheduling."""
        return await self._handle_transition_to_target("conversation-1752585818106", "send_information")
    
    @function_tool()
    async def transition_to_polite_decline(self) -> Agent:
        """Transition when the person politely declines but might be interested later."""
        return await self._handle_transition_to_target("conversation-1752585761728", "polite_decline")
    
    @function_tool()
    async def transition_to_create_calendar_event(self) -> Agent:
        """IMMEDIATELY call this to schedule/book the appointment when user confirms time/date. This will create a calendar event for the appointment. Use this when: user provides availability, confirms a time, agrees to schedule, or says 'book it', 'schedule it', 'let's do it', etc."""
        return await self._handle_transition_to_target("app_action-1752586209057", "create_calendar_event")
    
    @function_tool()
    async def transition_to_end_callback(self) -> Agent:
        """End the call after successfully scheduling a callback."""
        return await self._handle_transition_to_target("end_call", "end_callback")
    
    @function_tool()
    async def transition_to_capture_email(self) -> Agent:
        """Capture the customer's email address for follow-up."""
        return await self._handle_transition_to_target("conversation-1752585818106", "capture_email")
    
    @function_tool()
    async def transition_to_end_success(self) -> Agent:
        """End the call successfully after completing the sales process."""
        return await self._handle_transition_to_target("end_call", "end_success")
    
    async def _handle_transition_to_target(self, target_node_partial_id: str, transition_type: str) -> Agent:
        """
        Handle transition to target node following LiveKit workflow pattern.
        This method finds the actual target node and creates/returns the appropriate agent.
        """
        logger.info(f"🎯 Attempting transition from {self.node_config.get('id')} to {target_node_partial_id} ({transition_type})")
        
        # Find the actual target node in the pathway
        all_nodes = self.pathway_config.get('nodes', [])
        target_node = None
        
        # For app_action and end_call nodes, find by partial ID match
        if target_node_partial_id.startswith('app_action') or target_node_partial_id.startswith('end_call'):
            target_node = next((n for n in all_nodes if target_node_partial_id in n.get('id', '')), None)
        else:
            # For conversation nodes, find by exact ID
            target_node = next((n for n in all_nodes if n.get('id') == target_node_partial_id), None)
            
            if not target_node:
                logger.warning(f"❌ Target node {target_node_partial_id} not found in pathway")
                # Return self to stay in current node
                return self
        
        target_node_id = target_node.get('id')
        logger.info(f"✅ Found target node: {target_node_id}")
        
        # Update session tracking
        self.session_data.current_node_id = target_node_id
                    
                    # Get or create the target agent
        if target_node_id in self.session_data.agent_instances:
            target_agent = self.session_data.agent_instances[target_node_id]
                        logger.info(f"✅ Using existing PathwayNodeAgent for: {target_node_id}")
                    else:
                        # Create new agent for this node
                        target_agent = PathwayNodeAgent(
                            node_config=target_node, 
                session_data=self.session_data,
                chat_ctx=None  # ✅ FIX: Use None instead of accessing session.chat_ctx
                        )
            self.session_data.agent_instances[target_node_id] = target_agent
                        logger.info(f"✅ Created new PathwayNodeAgent for: {target_node_id}")
                    
        
                    return target_agent

    async def on_enter(self):
        """
        Called when this agent becomes active.
        Delivers a greeting message if configured and preserves context.
        Following LiveKit workflow patterns.
        """
        logger.info(f"🎯 Entering pathway node: {self.node_config.get('id')}")
        
        # Update the current node tracking
        session_data: PathwaySessionData = self.session.userdata
        session_data.current_node_id = self.node_config.get('id')
        
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
                    await self.session.say(user_message, allow_interruptions=True)
                else:
                    error_message = result.get('error', f"Failed to complete {action_type}")
                    await self.session.say(f"I apologize, but I encountered an issue: {error_message}", allow_interruptions=True)
                    
                # Auto-transition to next node after app action
                logger.info(f"🎯 Auto-transitioning from app_action to next node")
                return await self._auto_transition_from_app_action()
                    
                except Exception as e:
                    logger.error(f"❌ App action failed: {e}")
                await self.session.say("I apologize, but I encountered a technical issue while processing your request.", allow_interruptions=True)
                # Continue to normal conversation if app action fails
                pass
            
            return  # Exit early for app_action nodes
        
        # ✅ HANDLE END_CALL NODES PROPERLY
        if self.node_config.get('type') == 'end_call':
            logger.info(f"📞 Processing end_call node: {self.node_config.get('id')}")
            
            # Get goodbye message from node config
            goodbye_message = self.node_config.get('config', {}).get('goodbye_message')
            if not goodbye_message:
                goodbye_message = "Thank you for your time. Have a great day!"
            
            logger.info(f"💬 Delivering goodbye message: '{goodbye_message}'")
            await self.session.say(goodbye_message, allow_interruptions=False)
            
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
        
        if greeting:
            logger.info(f"💬 Delivering greeting: '{greeting}'")
            # ✅ CRITICAL FIX: Add allow_interruptions=True to prevent TTS cutoff
            await self.session.say(greeting, allow_interruptions=True)
        
        # ✅ PROPER LIVEKIT PATTERN: Use generate_reply to start conversation
        logger.info(f"🤖 Starting conversation for node: {self.node_config.get('id')}")
        await self.session.generate_reply(
            instructions="Continue the conversation according to your role and instructions. Listen to the user's response and respond appropriately."
        )

    async def _execute_app_action(self, app_name: str, action_type: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute app action using real API integration with OAuth tokens
        """
        logger.info(f"🔧 Executing {app_name}.{action_type} with real API integration")
        
        try:
            # Import required modules for API calls
            import aiohttp
            import json
            from datetime import datetime, timedelta
            import base64
            import os
            
            # Check if cryptography is available
            try:
                from cryptography.fernet import Fernet
                cryptography_available = True
            except ImportError:
                logger.warning("⚠️ cryptography module not available, skipping Fernet decryption")
                cryptography_available = False
            
            # Import database client
            import sys
            sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
            from api.db_client import supabase_service_client
            
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
                
                # Try different decryption methods based on the credential format
                access_token = None
                
                # Method 1: Try base64 decoding (common format)
                try:
                    import base64
                    decoded_data = base64.b64decode(encrypted_credentials)
                    oauth_data = json.loads(decoded_data.decode())
                    access_token = oauth_data.get("access_token")
                    logger.info(f"✅ Successfully decoded credentials using base64")
                except:
                    pass
                
                # Method 2: Try Fernet decryption if base64 failed
                if not access_token and cryptography_available:
                    try:
                        # Get encryption key for decrypting OAuth tokens
                        encryption_key = os.getenv('INTEGRATION_ENCRYPTION_KEY', 'your-32-byte-base64-encoded-key==')
                        f = Fernet(encryption_key.encode())
                        decrypted_data = f.decrypt(encrypted_credentials.encode())
                        oauth_data = json.loads(decrypted_data.decode())
                        access_token = oauth_data.get("access_token")
                        logger.info(f"✅ Successfully decrypted credentials using Fernet")
                    except:
                        pass
                
                # Method 3: Try direct JSON parsing (if stored as plain JSON)
                if not access_token:
                    try:
                        oauth_data = json.loads(encrypted_credentials)
                        access_token = oauth_data.get("access_token")
                        logger.info(f"✅ Successfully parsed credentials as direct JSON")
                    except:
                        pass
                
                if not access_token:
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
                    "timeZone": "America/New_York"  # TODO: Make timezone configurable
                },
                "end": {
                    "dateTime": end_time.isoformat(),
                    "timeZone": "America/New_York"
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
            
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }
            
            async with aiohttp.ClientSession() as session:
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
        Automatically transition to the next node after completing an app action
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
                
                logger.info(f"🎯 Auto-transitioning to: {target_node_id}")
                
                # Find target node
                all_nodes = self.pathway_config.get('nodes', [])
                target_node = next((node for node in all_nodes if node.get('id') == target_node_id), None)
                
                if target_node:
                    # Create and return the target agent
                    target_agent = PathwayNodeAgent(
                        node_config=target_node, 
                        session_data=self.session_data,
                        chat_ctx=None
                    )
                    
                    # Update current node tracking
                    self.session_data.current_node_id = target_node_id
                    self.session_data.agent_instances[target_node_id] = target_agent
                    
                    logger.info(f"✅ Auto-transition completed to: {target_node_id}")
                    return target_agent
                else:
                    logger.error(f"❌ Target node not found: {target_node_id}")
            else:
                logger.warning(f"⚠️ No outgoing edges found from app_action node: {current_node_id}")
                
        except Exception as e:
            logger.error(f"❌ Auto-transition failed: {e}")
        
        # If auto-transition fails, return self to continue current conversation
        return self

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