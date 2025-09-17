"""
WorkflowAgent - A LiveKit agent that implements workflow-driven conversations
using proper LLM orchestration with function tools instead of manual node processing.

REFACTORED VERSION: Implements proper LiveKit patterns:
- @function_tool for conditions and agent handoffs
- Proper lifecycle hooks (on_enter, on_exit, on_user_turn_completed)
- Context preservation with chat_ctx and userdata
- LLM-driven workflow orchestration
"""

import logging
import uuid
import json
import os
from typing import Dict, Any, Optional, List, Callable, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timezone

from livekit.agents import (
    Agent, 
    AgentSession, 
    JobContext,
    function_tool,
    llm,
    RunContext
)
from livekit.agents.llm import ChatMessage, ChatContext, FunctionCall
import livekit.rtc as rtc
from tools.calendar_tools import create_google_calendar_tools
from tools.email_tools import create_email_tools
from tools.crm_tools import create_crm_tools
from tools.mcp_tools import create_mcp_tools, MCPWorkflowIntegration
from tools.dynamic_app_tools import create_dynamic_app_tools

# Import app action execution if available
try:
    import sys
    import os
    # Add the parent directory (backend_python) to sys.path so we can import api modules
    backend_path = os.path.dirname(os.path.dirname(__file__))
    if backend_path not in sys.path:
        sys.path.insert(0, backend_path)
    from api.app_actions import execute_pathway_app_action
    from api.app_actions import AppActionError
    APP_ACTIONS_AVAILABLE = True
    logger = logging.getLogger("workflow-agent")
    logger.info("[SUCCESS] App actions module imported successfully")
except ImportError as e:
    logger = logging.getLogger("workflow-agent")
    logger.warning(f"App actions not available: {e}")
    APP_ACTIONS_AVAILABLE = False
    
    # Create mock function
    async def execute_pathway_app_action(*args, **kwargs):
        return {"status": "error", "error": "App actions not available"}
    
    class AppActionError(Exception):
        pass

logger = logging.getLogger("workflow-agent")

@dataclass
class WorkflowState:
    """Clean workflow state management using LiveKit patterns"""
    workflow_id: str
    current_step: str = "entry"
    step_history: List[str] = field(default_factory=list)
    collected_data: Dict[str, Any] = field(default_factory=dict)
    execution_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    workflow_config: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

# ===== SPECIALIZED AGENT CLASSES FOR HANDOFFS =====

class BillingSpecialistAgent(Agent):
    """Specialized agent for billing and payment issues"""
    
    def __init__(self, chat_ctx=None, customer_info=None, **kwargs):
        super().__init__(
            instructions="""You are a billing specialist. You have access to billing records and can resolve 
            payment issues, process refunds, and handle subscription changes. Be professional and empathetic 
            when dealing with billing concerns.""",
            chat_ctx=chat_ctx,  # Preserve conversation history
            **kwargs
        )
        self.customer_info = customer_info or {}
    
    async def on_enter(self):
        """Called when this agent becomes active"""
        issue_context = ""
        if self.customer_info:
            issue_context = f" I can see from our conversation that you have concerns about {self.customer_info.get('issue_summary', 'billing')}."
        
        await self.session.say(f"I'm a billing specialist and I'm here to help resolve your billing issue.{issue_context} Let me look into this for you.")

class TechnicalSupportAgent(Agent):
    """Specialized agent for technical support issues"""
    
    def __init__(self, chat_ctx=None, customer_info=None, **kwargs):
        super().__init__(
            instructions="""You are a technical support specialist. You can troubleshoot technical issues, 
            help with account access problems, and guide users through technical procedures. Be patient 
            and provide step-by-step guidance.""",
            chat_ctx=chat_ctx,
            **kwargs
        )
        self.customer_info = customer_info or {}
    
    async def on_enter(self):
        """Called when this agent becomes active"""
        await self.session.say("I'm a technical support specialist. I'll help you resolve your technical issue step by step.")

class HumanSupportAgent(Agent):
    """Agent that facilitates handoff to human support"""
    
    def __init__(self, chat_ctx=None, customer_info=None, escalation_reason=None, **kwargs):
        super().__init__(
            instructions="""You facilitate handoffs to human support. Collect any final information needed 
            and ensure the customer knows they will be connected to a human representative.""",
            chat_ctx=chat_ctx,
            **kwargs
        )
        self.customer_info = customer_info or {}
        self.escalation_reason = escalation_reason or "complex issue"
    
    async def on_enter(self):
        """Called when this agent becomes active"""
        await self.session.say(f"I understand this requires human assistance. Let me connect you with one of our support representatives who can help with {self.escalation_reason}. Please hold for just a moment.")

class WorkflowAgent(Agent):
    """
    LiveKit agent that implements workflow-driven conversations using proper LLM orchestration.
    
    REFACTORED IMPLEMENTATION:
    - Uses @function_tool pattern for ALL workflow actions
    - Implements proper LiveKit lifecycle hooks
    - Uses LLM intelligence for condition evaluation and agent handoffs
    - Preserves context across agent transitions
    """
    
    def __init__(
        self,
        *,
        workflow_config: Dict[str, Any],
        initial_instructions: str,
        initial_step: str = None,
        wait_for_greeting: bool = False,
        **kwargs
    ):
        """Initialize WorkflowAgent with workflow configuration"""
        
        # Auto-detect entry point if not provided
        if initial_step is None:
            initial_step = self._determine_entry_point(workflow_config)
        
        # Extract dynamic instructions and greeting from workflow configuration
        workflow_instructions = self._extract_workflow_instructions(workflow_config, initial_step, initial_instructions)
        greeting = self._extract_workflow_greeting(workflow_config, initial_step)
        
        # Initialize Agent with enhanced instructions
        super().__init__(
            instructions=workflow_instructions,
            **kwargs
        )
        
        # Store workflow configuration
        self.workflow_config = workflow_config
        self.initial_instructions = initial_instructions
        self.initial_step = initial_step
        self.wait_for_greeting = wait_for_greeting
        self.greeting = greeting
        
        # Initialize workflow state
        self._workflow_state = WorkflowState(
            workflow_id=workflow_config.get("id", "unknown"),
            current_step=initial_step,
            workflow_config=workflow_config,
            collected_data={}
        )
        
        # Session will be set when agent is started
        self._session = None
        
        logger.info(f"WorkflowAgent initialized - Entry: {initial_step}, Greeting: {bool(greeting)}")

    # ===== LIVEKIT LIFECYCLE HOOKS =====
    
    async def on_enter(self):
        """Called when this agent becomes active - implements proper LiveKit pattern"""
        logger.info(f"WorkflowAgent entering with step: {self._workflow_state.current_step}")
        
        # Store workflow state in session userdata for context preservation
        if self._session:
            self._session.userdata['workflow_state'] = self._workflow_state
            self._session.userdata['workflow_config'] = self.workflow_config
        
        # Provide initial greeting if configured
        if self.greeting and not self.wait_for_greeting:
            await self.session.say(self.greeting)
        elif not self.wait_for_greeting:
            # Fallback greeting based on workflow context
            workflow_name = self.workflow_config.get('name', 'assistant')
            await self.session.say(f"Hello! I'm your {workflow_name}. How can I help you today?")
    
    async def on_exit(self):
        """Called before handoff to another agent - preserves context"""
        logger.info(f"WorkflowAgent exiting from step: {self._workflow_state.current_step}")
        
        # Ensure workflow state is saved before handoff
        if self._session:
            self._session.userdata['workflow_state'] = self._workflow_state
            self._session.userdata['handoff_history'] = self._session.userdata.get('handoff_history', [])
            self._session.userdata['handoff_history'].append({
                'from_agent': 'WorkflowAgent',
                'step': self._workflow_state.current_step,
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'collected_data': dict(self._workflow_state.collected_data)
            })
    
    def _safely_store_workflow_state(self, context):
        """Helper method to safely store workflow state in session"""
        if context.session:
            try:
                context.session.userdata['workflow_state'] = self._workflow_state
            except (ValueError, AttributeError):
                # userdata not available, store in session instance instead
                setattr(context.session, '_workflow_state', self._workflow_state)

    async def on_user_turn_completed(self, turn_ctx, new_message):
        """Called after user speaks, before LLM generates reply - implements LiveKit pattern"""
        logger.info("User turn completed - analyzing conversation context")
        
        # Update workflow state based on conversation
        if self._session and self._session.chat_ctx:
            # Extract conversation insights and update collected data
            await self._analyze_conversation_context()
            
            # Check if we should auto-trigger any workflow actions
            await self._check_auto_triggers()

    # ===== FUNCTION TOOLS FOR CONDITIONS (REPLACING MANUAL EVALUATION) =====
    
    @function_tool
    async def check_user_interest_level(self, context: RunContext, topic: str = "general") -> str:
        """
        Analyze user's interest level in a topic and determine appropriate next step.
        Use this when you need to evaluate if the user is interested in something.
        
        Args:
            topic: The topic to evaluate interest in (e.g., "appointment", "product", "support")
        """
        logger.info(f"🧠 Evaluating user interest in: {topic}")
        
        # Get recent conversation context
        conversation_text = self._get_recent_conversation_text()
        
        # AI analysis of user interest
        interest_indicators = {
            'high': ['yes', 'interested', 'want', 'need', 'please', 'help me', 'i would like'],
            'medium': ['maybe', 'possibly', 'consider', 'thinking about', 'might'],
            'low': ['no', 'not interested', 'later', 'maybe later', 'not now'],
            'negative': ['definitely not', 'never', 'absolutely not', 'no way']
        }
        
        conversation_lower = conversation_text.lower()
        interest_level = "unknown"
        
        # Simple interest detection based on keywords
        for level, indicators in interest_indicators.items():
            if any(indicator in conversation_lower for indicator in indicators):
                interest_level = level
                break
        
        # Update workflow state
        self._workflow_state.collected_data[f'interest_{topic}'] = interest_level
        self._safely_store_workflow_state(context)
        
        logger.info(f"✅ Interest level determined: {interest_level} for {topic}")
        
        # Return routing decision for LLM to use
        if interest_level == 'high':
            return f"high_interest_{topic}"
        elif interest_level == 'medium':
            return f"medium_interest_{topic}"
        elif interest_level in ['low', 'negative']:
            return f"low_interest_{topic}"
        else:
            return f"unclear_interest_{topic}"
    
    @function_tool
    async def evaluate_user_sentiment(self, context: RunContext) -> str:
        """
        Analyze user's current emotional state and determine appropriate response approach.
        Use this when you need to understand how the user is feeling.
        """
        logger.info("🎭 Evaluating user sentiment")
        
        conversation_text = self._get_recent_conversation_text()
        
        # Simple sentiment analysis
        positive_words = ['happy', 'great', 'good', 'excellent', 'pleased', 'satisfied', 'thank you']
        negative_words = ['frustrated', 'angry', 'upset', 'annoyed', 'problem', 'issue', 'terrible', 'awful']
        urgent_words = ['urgent', 'emergency', 'asap', 'immediately', 'quickly', 'right now']
        
        conversation_lower = conversation_text.lower()
        
        sentiment = "neutral"
        if any(word in conversation_lower for word in urgent_words):
            sentiment = "urgent"
        elif any(word in conversation_lower for word in negative_words):
            sentiment = "frustrated"
        elif any(word in conversation_lower for word in positive_words):
            sentiment = "positive"
        
        # Store sentiment in workflow state
        self._workflow_state.collected_data['user_sentiment'] = sentiment
        self._safely_store_workflow_state(context)
        
        logger.info(f"✅ User sentiment: {sentiment}")
        
        return sentiment
    
    @function_tool
    async def check_information_completeness(self, context: RunContext, required_fields: List[str]) -> str:
        """
        Check if we have collected all required information from the user.
        
        Args:
            required_fields: List of field names that must be collected (e.g., ["name", "email", "phone"])
        """
        logger.info(f"📋 Checking completeness of required fields: {required_fields}")
        
        collected_data = self._workflow_state.collected_data
        missing_fields = []
        
        for field in required_fields:
            if field not in collected_data or not collected_data[field]:
                missing_fields.append(field)
        
        if not missing_fields:
            logger.info("✅ All required information collected")
            return "information_complete"
        else:
            logger.info(f"❌ Missing fields: {missing_fields}")
            # Store missing fields for LLM to use
            self._workflow_state.collected_data['missing_fields'] = missing_fields
            self._safely_store_workflow_state(context)
            return f"missing_information"

    # ===== FUNCTION TOOLS FOR AGENT HANDOFFS (REPLACING MANUAL TRANSITIONS) =====
    
    @function_tool
    async def transfer_to_billing_specialist(self, context: RunContext, reason: str = "billing issue") -> Tuple[Agent, str]:
        """
        Transfer user to a billing specialist for payment and subscription issues.
        
        Args:
            reason: Brief description of why the transfer is needed
        """
        logger.info(f"🔄 Transferring to billing specialist - Reason: {reason}")
        
        # Prepare customer information for handoff
        customer_info = {
            'issue_summary': reason,
            'collected_data': dict(self._workflow_state.collected_data),
            'conversation_context': self._get_recent_conversation_text(),
            'workflow_step': self._workflow_state.current_step
        }
        
        # Create billing specialist with preserved context
        billing_agent = BillingSpecialistAgent(
            chat_ctx=context.session.chat_ctx,  # Preserve conversation history
            customer_info=customer_info
        )
        
        return billing_agent, f"Let me transfer you to our billing specialist who can help with {reason}."
    
    @function_tool
    async def transfer_to_technical_support(self, context: RunContext, issue_type: str = "technical issue") -> Tuple[Agent, str]:
        """
        Transfer user to technical support for technical problems.
        
        Args:
            issue_type: Type of technical issue (e.g., "login problem", "system error", "feature question")
        """
        logger.info(f"🔧 Transferring to technical support - Issue: {issue_type}")
        
        customer_info = {
            'issue_type': issue_type,
            'collected_data': dict(self._workflow_state.collected_data),
            'conversation_context': self._get_recent_conversation_text(),
            'workflow_step': self._workflow_state.current_step
        }
        
        tech_agent = TechnicalSupportAgent(
            chat_ctx=context.session.chat_ctx,
            customer_info=customer_info
        )
        
        return tech_agent, f"Let me connect you with our technical support team to help with {issue_type}."
    
    @function_tool
    async def escalate_to_human_support(self, context: RunContext, escalation_reason: str = "complex issue") -> Tuple[Agent, str]:
        """
        Escalate to human support for issues that require human intervention.
        
        Args:
            escalation_reason: Why human support is needed
        """
        logger.info(f"👨‍💼 Escalating to human support - Reason: {escalation_reason}")
        
        customer_info = {
            'escalation_reason': escalation_reason,
            'collected_data': dict(self._workflow_state.collected_data),
            'conversation_context': self._get_recent_conversation_text(),
            'workflow_step': self._workflow_state.current_step,
            'agent_attempts': self._workflow_state.step_history
        }
        
        human_agent = HumanSupportAgent(
            chat_ctx=context.session.chat_ctx,
            customer_info=customer_info,
            escalation_reason=escalation_reason
        )
        
        return human_agent, f"I'll connect you with one of our human representatives to help with {escalation_reason}."

    # ===== FUNCTION TOOLS FOR DATA COLLECTION =====
    
    @function_tool
    async def collect_user_information(self, context: RunContext, field_name: str, field_value: str) -> str:
        """
        Store collected user information in the workflow state.
        
        Args:
            field_name: Name of the field being collected (e.g., "name", "email", "phone")
            field_value: The value provided by the user
        """
        logger.info(f"📝 Collecting user information - {field_name}: {field_value}")
        
        # Store in workflow state
        self._workflow_state.collected_data[field_name] = field_value
        
        # Update session userdata for persistence
        self._safely_store_workflow_state(context)
        
        return f"Thank you! I've recorded your {field_name}."
    
    @function_tool
    async def execute_app_action(self, context: RunContext, app_name: str, action_type: str, parameters: str = "{}") -> str:
        """
        Execute an application action (Google Calendar, CRM, etc.) with collected data.
        
        Args:
            app_name: Name of the app (e.g., "google_calendar", "salesforce")
            action_type: Type of action (e.g., "create_event", "update_contact")
            parameters: JSON string of additional parameters for the action
        """
        logger.info(f"🚀 Executing app action: {app_name}.{action_type}")
        
        try:
            # Parse parameters from JSON string
            import json
            try:
                kwargs = json.loads(parameters) if parameters else {}
            except json.JSONDecodeError:
                kwargs = {}
                logger.warning(f"Invalid JSON parameters: {parameters}")
            
            # Prepare action data
            action_data = {
                'app_name': app_name,
                'action_type': action_type,
                'parameters': kwargs,
                'collected_data': dict(self._workflow_state.collected_data)
            }
            
            # Execute the app action
            if APP_ACTIONS_AVAILABLE:
                call_context = {
                    "session_id": getattr(context.session, 'id', 'unknown'),
                    "workflow_execution_id": self._workflow_state.execution_id,
                    "workflow_step": self._workflow_state.current_step
                }
                
                result = await execute_pathway_app_action(
                    pathway_app_action=action_data,
                    call_context=call_context,
                    pathway_variables=self._workflow_state.collected_data
                )
                
                # Store result in workflow state
                self._workflow_state.collected_data[f'app_action_{action_type}_result'] = result
                self._safely_store_workflow_state(context)
                
                logger.info(f"✅ App action completed successfully: {result}")
                return f"Successfully executed {app_name} {action_type}. {result.get('message', '')}"
            else:
                logger.warning("App actions not available")
                return f"App action {app_name}.{action_type} is not available in this environment."
                
        except Exception as e:
            logger.error(f"❌ App action failed: {e}")
            return f"I encountered an issue executing {app_name} {action_type}. Please try again or contact support."

    # ===== HELPER METHODS =====
    
    def _determine_entry_point(self, workflow_config: Dict[str, Any]) -> str:
        """Auto-detect the entry point of the workflow"""
        try:
            # Check for explicit entry_point configuration
            config_section = workflow_config.get('config', {})
            entry_point = config_section.get('entry_point')
            if entry_point:
                logger.info(f"✅ Found explicit entry point: {entry_point}")
                return entry_point
            
            # Get nodes from both new and legacy formats
            nodes = config_section.get('nodes', [])
            if not nodes:
                nodes = workflow_config.get('nodes', [])
            
            if not nodes:
                logger.warning("No nodes found in pathway configuration")
                return 'entry'
            
            # Priority 1: Look for node with isStart: true
            for node in nodes:
                if node.get('isStart') == True:
                    entry_id = node.get('id') or node.get('name', 'entry')
                    logger.info(f"✅ Found start node: {entry_id}")
                    return entry_id
            
            # Priority 2: Look for node with type 'start' or 'entry'
            for node in nodes:
                if node.get('type') in ['start', 'entry']:
                    entry_id = node.get('id') or node.get('name', 'entry')
                    logger.info(f"✅ Found start/entry type node: {entry_id}")
                    return entry_id
            
            # Priority 3: Look for conversation node (common entry pattern)
            for node in nodes:
                if node.get('type') == 'conversation':
                    entry_id = node.get('id') or node.get('name', 'entry')
                    logger.info(f"✅ Found conversation node as entry: {entry_id}")
                    return entry_id
            
            # Final fallback: use first node
            first_node = nodes[0]
            entry_id = first_node.get('id') or first_node.get('name', 'entry')
            logger.info(f"✅ Using first node as entry: {entry_id}")
            return entry_id
                
        except Exception as e:
            logger.warning(f"Could not determine entry point: {e}")
            return 'entry'
    
    def _extract_workflow_instructions(self, workflow_config: Dict[str, Any], initial_step: str, base_instructions: str) -> str:
        """Extract and enhance instructions based on workflow configuration"""
        try:
            # Get workflow-level instructions
            workflow_instructions = workflow_config.get('instructions', '')
            workflow_name = workflow_config.get('name', 'workflow assistant')
            
            # Get step-specific instructions from both new and legacy formats
            step_instructions = ""
            config_section = workflow_config.get('config', {})
            nodes = config_section.get('nodes', [])
            
            # If no nodes in config, check direct nodes array (legacy format)
            if not nodes:
                nodes = workflow_config.get('nodes', [])
            
            # Find the entry node by ID or name
            entry_node = None
            for node in nodes:
                if (node.get('id') == initial_step or 
                    node.get('name') == initial_step or
                    node.get('isStart') == True):
                    entry_node = node
                    break
            
            if entry_node:
                # Priority 1: Check for conversation node prompt in config.prompt (standard format)
                node_config = entry_node.get('config', {})
                node_prompt = node_config.get('prompt', '')
                if node_prompt:
                    step_instructions = node_prompt
                    logger.info(f"✅ Found conversation node prompt in config: {node_prompt[:50]}...")
                else:
                    # Priority 2: Check for direct prompt field (legacy format)
                    direct_prompt = entry_node.get('prompt', '')
                    if direct_prompt:
                        step_instructions = direct_prompt
                        logger.info(f"✅ Found direct node prompt: {direct_prompt[:50]}...")
                    else:
                        # Priority 3: Check legacy config.instructions format
                        step_instructions = node_config.get('instructions', '')
                        if step_instructions:
                            logger.info(f"✅ Found legacy instructions: {step_instructions[:50]}...")
            
            # Combine instructions with workflow context
            enhanced_instructions = f"""You are {workflow_name}.

{base_instructions}

{workflow_instructions}

{step_instructions}

IMPORTANT WORKFLOW CAPABILITIES:
- Use check_user_interest_level() when you need to evaluate user interest
- Use evaluate_user_sentiment() to understand user emotions
- Use collect_user_information() to store important user data  
- Use check_information_completeness() to verify you have required information
- Use transfer_to_billing_specialist() for billing/payment issues
- Use transfer_to_technical_support() for technical problems
- Use escalate_to_human_support() when human intervention is needed
- Use execute_app_action() to integrate with external systems

Always use these tools when appropriate to provide the best user experience."""

            return enhanced_instructions.strip()
            
        except Exception as e:
            logger.warning(f"Could not extract workflow instructions: {e}")
            return base_instructions
    
    def _extract_workflow_greeting(self, workflow_config: Dict[str, Any], initial_step: str) -> Optional[str]:
        """Extract initial greeting from the workflow configuration"""
        try:
            # Check both new and legacy pathway formats
            config_section = workflow_config.get('config', {})
            nodes = config_section.get('nodes', [])
            
            # If no nodes in config, check direct nodes array (legacy format)
            if not nodes:
                nodes = workflow_config.get('nodes', [])
            
            # Find the entry node by ID or name
            entry_node = None
            for node in nodes:
                if (node.get('id') == initial_step or 
                    node.get('name') == initial_step or
                    node.get('isStart') == True):
                    entry_node = node
                    break
            
            if entry_node:
                # Priority 1: Check for config.greeting (standard PAM format)
                node_config = entry_node.get('config', {})
                config_greeting = node_config.get('greeting')
                if config_greeting:
                    logger.info(f"✅ Found config.greeting: {config_greeting[:50]}...")
                    return config_greeting
                
                # Priority 2: Check for conversation node greeting in messagePlan.firstMessage (alternate format)
                message_plan = entry_node.get('messagePlan', {})
                first_message = message_plan.get('firstMessage')
                if first_message:
                    logger.info(f"✅ Found messagePlan.firstMessage: {first_message[:50]}...")
                    return first_message
                
                # Priority 3: Check for config.message (legacy format)
                legacy_message = node_config.get('message')
                if legacy_message:
                    logger.info(f"✅ Found config.message: {legacy_message[:50]}...")
                    return legacy_message
                
                # For conversation nodes, use the prompt as fallback greeting if no explicit greeting
                if entry_node.get('type') == 'conversation':
                    prompt = entry_node.get('prompt', '')
                    if prompt and 'start with:' in prompt.lower():
                        # Extract greeting from prompt if it contains "Start with: '...'"
                        import re
                        greeting_match = re.search(r"start with:\s*['\"]([^'\"]+)['\"]", prompt, re.IGNORECASE)
                        if greeting_match:
                            extracted_greeting = greeting_match.group(1)
                            logger.info(f"✅ Extracted greeting from prompt: {extracted_greeting}")
                            return extracted_greeting
            
            logger.warning(f"No greeting found for entry step: {initial_step}")
            return None
        except Exception as e:
            logger.warning(f"Could not extract greeting: {e}")
            return None
    
    def _get_recent_conversation_text(self, max_turns: int = 10) -> str:
        """Get recent conversation text for analysis"""
        try:
            if not self._session or not self._session.chat_ctx:
                return "No conversation context available"
            
            messages = self._session.chat_ctx.messages[-max_turns:]
            conversation_parts = []
            
            for msg in messages:
                role = msg.role if hasattr(msg, 'role') else 'unknown'
                content = msg.content if hasattr(msg, 'content') else str(msg)
                conversation_parts.append(f"{role}: {content}")
            
            return "\n".join(conversation_parts)
        except Exception as e:
            logger.error(f"Error getting conversation context: {e}")
            return "Error retrieving conversation context"
    
    async def _analyze_conversation_context(self):
        """Analyze conversation and update workflow state"""
        try:
            conversation_text = self._get_recent_conversation_text()
            
            # Simple keyword-based analysis for now
            # In production, this could use more sophisticated NLP
            
            # Extract potential user information
            conversation_lower = conversation_text.lower()
            
            # Look for email patterns
            import re
            email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
            emails = re.findall(email_pattern, conversation_text)
            if emails and 'email' not in self._workflow_state.collected_data:
                self._workflow_state.collected_data['email'] = emails[0]
            
            # Look for phone patterns
            phone_pattern = r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b'
            phones = re.findall(phone_pattern, conversation_text)
            if phones and 'phone' not in self._workflow_state.collected_data:
                self._workflow_state.collected_data['phone'] = phones[0]
            
            # Update session userdata if available
            if self._session:
                try:
                    self._session.userdata['workflow_state'] = self._workflow_state
                except (ValueError, AttributeError):
                    # userdata not available, store in session instance instead
                    setattr(self._session, '_workflow_state', self._workflow_state)
                
        except Exception as e:
            logger.error(f"Error analyzing conversation context: {e}")
    
    async def _check_auto_triggers(self):
        """Check if any workflow actions should be automatically triggered"""
        try:
            # This could implement auto-triggers based on conversation patterns
            # For now, just log that we're checking
            logger.debug("Checking auto-triggers for workflow actions")
        except Exception as e:
            logger.error(f"Error checking auto-triggers: {e}")

    # ===== SESSION MANAGEMENT =====
    
    async def ainit(self, sess: AgentSession):
        """Initialize the agent session - proper LiveKit pattern"""
        await super().ainit(sess)
        self._session = sess
        
        # Initialize workflow state in session userdata
        sess.userdata['workflow_state'] = self._workflow_state
        sess.userdata['workflow_config'] = self.workflow_config
        
        logger.info(f"WorkflowAgent session initialized. Execution ID: {self._workflow_state.execution_id}")


# ===== PATHWAY CONFIGURATION UTILITIES =====

try:
    # Import Supabase client for pathway configuration loading
    import sys
    import os
    # Add API directory to path for database client access
    api_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'api')
    if api_path not in sys.path:
        sys.path.insert(0, api_path)
    
    from db_client import supabase_service_client
    SUPABASE_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Supabase client not available: {e}")
    supabase_service_client = None
    SUPABASE_AVAILABLE = False


async def load_pathway_config(pathway_id: str) -> Optional[Dict[str, Any]]:
    """
    Load pathway configuration from database
    
    Args:
        pathway_id: The pathway ID to load
        
    Returns:
        Pathway configuration dict or None if not found
    """
    if not SUPABASE_AVAILABLE or not supabase_service_client:
        logger.error("Database not available, cannot load pathway config")
        return None
        
    try:
        # Load pathway config from database
        response = supabase_service_client.table("pathways").select("*").eq("id", pathway_id).single().execute()
        
        if not response.data:
            logger.error(f"Failed to load pathway config: {pathway_id}")
            return None
        
        pathway_config = response.data
        
        # Validate pathway configuration
        if pathway_config.get("status") != "active":
            logger.warning(f"Pathway {pathway_id} is not active (status: {pathway_config.get('status')})")
            return None
        
        config = pathway_config.get("config", {})
        if not config.get("nodes"):
            logger.error(f"Pathway {pathway_id} has no nodes configured")
            return None
        
        logger.info(f"Successfully loaded pathway config: {pathway_config.get('name', 'Unknown')}")
        return pathway_config
        
    except Exception as e:
        logger.error(f"Error loading pathway config: {e}")
        return None