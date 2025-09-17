"""
Dynamic App Action Tools for WorkflowAgent

Implements LiveKit temporal tools pattern for context-aware app actions.
No variable mapping needed - tools extract directly from conversation context.
"""

import logging
import json
from typing import Dict, Any, List, Optional
from datetime import datetime

from livekit.agents import function_tool, RunContext
from livekit.agents.llm import ChatContext
import httpx

logger = logging.getLogger("dynamic-app-tools")

class DynamicAppToolFactory:
    """
    Creates context-aware app action tools using LiveKit temporal tools pattern.
    
    Based on LiveKit Option 3: Add temporal tools only for specific LLM calls.
    Tools extract variables directly from conversation context.
    """
    
    def __init__(self, user_id: str, backend_api_url: str = None):
        self.user_id = user_id
        self.backend_api_url = backend_api_url or "http://localhost:8000"
        self.app_schemas = {}
        
    async def initialize_app_schemas(self):
        """Load app schemas from backend via n8n integration"""
        try:
            # Get user's connected apps via n8n integration
            response = await httpx.AsyncClient().get(
                f"{self.backend_api_url}/integrations/n8n/user-apps",
                headers={"Authorization": f"Bearer {self.user_id}"}
            )
            
            if response.status_code == 200:
                apps_data = response.json()
                for app in apps_data:
                    self.app_schemas[app["app_name"]] = app["supported_actions"]
                logger.info(f"Loaded schemas for {len(self.app_schemas)} connected apps via n8n")
            else:
                logger.warning(f"Failed to load app schemas: {response.status_code}")
                
        except Exception as e:
            logger.error(f"Error loading app schemas: {e}")
    
    def create_app_action_tool(self, app_name: str, action_name: str, node_id: str):
        """
        Create a context-aware app action tool for specific app/action.
        
        Uses LiveKit temporal tools pattern - tool extracts what it needs from context.
        """
        
        # Get app schema to know what fields are expected
        app_schema = self.app_schemas.get(app_name, {})
        action_schema = app_schema.get(action_name, {})
        required_fields = action_schema.get("required_fields", [])
        
        # Create dynamic app action function with proper LiveKit integration
        async def dynamic_app_action(context: RunContext) -> str:
            """
            Execute app action using conversation context and workflow state.
            This is a dynamically generated tool for workflow-driven app integrations.
            """
            try:
                logger.info(f"Executing {app_name} {action_name} via dynamic tool for node {node_id}")
                
                # Check workflow state - only execute if at correct step
                workflow_state = context.session.userdata.get('workflow_state')
                if workflow_state and hasattr(workflow_state, 'current_step'):
                    if workflow_state.current_step != node_id:
                        return f"⏭️ Skipping {app_name} action - not at correct workflow step"
                
                # Get conversation context
                chat_context = context.chat_ctx
                conversation_text = ""
                if chat_context and chat_context.messages:
                    # Extract recent conversation for context
                    recent_messages = chat_context.messages[-10:]  # Last 10 messages
                    conversation_text = "\n".join([
                        f"{msg.role}: {msg.content}" for msg in recent_messages
                    ])
                
                # AI-powered extraction using LLM
                extracted_data = await self._extract_app_fields(
                    conversation_text=conversation_text,
                    app_name=app_name,
                    action_name=action_name,
                    required_fields=required_fields,
                    context=context
                )
                
                if not extracted_data:
                    return f"❌ Could not extract required information for {app_name} {action_name}"
                
                # Execute the app action via backend API
                result = await self._execute_app_action(
                    app_name=app_name,
                    action_name=action_name,
                    data=extracted_data
                )
                
                # Store action result in workflow state
                if workflow_state:
                    if not hasattr(workflow_state, 'collected_data'):
                        workflow_state.collected_data = {}
                    workflow_state.collected_data[f"{app_name}_action_result"] = {
                        'action': action_name,
                        'data': extracted_data,
                        'result': result,
                        'executed_at': datetime.now().isoformat()
                    }
                
                return f"✅ Successfully executed {app_name} {action_name}: {result}"
                
            except Exception as e:
                logger.error(f"Error in {app_name} {action_name} tool: {e}")
                return f"❌ Failed to execute {app_name} action: {str(e)}"
        
        # Set dynamic function name and description with LLM-friendly naming
        function_name = self._generate_llm_friendly_name(app_name, action_name)
        dynamic_app_action.__name__ = function_name
        dynamic_app_action.__doc__ = f"Execute {app_name} {action_name} action using conversation context"
        
        # ✅ CRITICAL: Apply @function_tool decorator AFTER setting name and docs
        decorated_function = function_tool(dynamic_app_action)
        
        return decorated_function
    
    def _generate_llm_friendly_name(self, app_name: str, action_name: str) -> str:
        """
        Generate LLM-friendly function names that match what AI models expect.
        This maps generic app_name + action_name to intuitive function names.
        """
        
        # Google Calendar mappings
        if app_name == "google_calendar":
            if action_name in ["create_event", "schedule_event"]:
                return "schedule_google_calendar_appointment"
            elif action_name in ["list_events", "get_events"]:
                return "list_google_calendar_events"
            elif action_name in ["update_event", "modify_event"]:
                return "update_google_calendar_event"
            elif action_name in ["delete_event", "cancel_event"]:
                return "cancel_google_calendar_event"
        
        # HubSpot CRM mappings
        elif app_name == "hubspot":
            if action_name in ["create_contact", "add_contact"]:
                return "create_hubspot_contact"
            elif action_name in ["create_deal", "add_deal"]:
                return "create_hubspot_deal"
            elif action_name in ["get_contact", "find_contact"]:
                return "find_hubspot_contact"
        
        # Gmail mappings  
        elif app_name == "gmail":
            if action_name in ["send_email", "send"]:
                return "send_gmail_email"
            elif action_name in ["reply_email", "reply"]:
                return "reply_gmail_email"
        
        # Fallback to original naming if no mapping exists
        return f"{app_name}_{action_name}"
    
    async def _extract_app_fields(
        self, 
        conversation_text: str, 
        app_name: str, 
        action_name: str,
        required_fields: List[str],
        context: RunContext
    ) -> Optional[Dict[str, Any]]:
        """
        Use LLM to extract required fields from conversation context.
        
        This is the core dynamic extraction logic.
        """
        
        # Create extraction prompt
        extraction_prompt = f"""
        Extract the following information from the conversation for {app_name} {action_name}:
        
        Required fields: {required_fields}
        
        Conversation:
        {conversation_text}
        
        Instructions:
        - Extract only the information that is clearly mentioned in the conversation
        - If a field is not mentioned, omit it from the response
        - For names, split full names into first_name and last_name if needed
        - For dates/times, use ISO format when possible
        - Return valid JSON only
        
        Example output:
        {{
            "first_name": "John",
            "last_name": "Smith", 
            "email": "john@example.com",
            "company": "Acme Corp"
        }}
        
        JSON output:
        """
        
        try:
            # Use the LLM from the current context to extract fields
            llm = context.session.llm
            if llm:
                # Create a simple chat message for extraction
                from livekit.agents.llm import ChatMessage
                messages = [ChatMessage(role="user", content=extraction_prompt)]
                
                # Get LLM response
                response = await llm.achat(messages)
                
                # Parse JSON response
                extracted_json = json.loads(response.content.strip())
                
                # Validate that we have some required fields
                if any(field in extracted_json for field in required_fields):
                    logger.info(f"Extracted {len(extracted_json)} fields for {app_name} {action_name}")
                    return extracted_json
                else:
                    logger.warning(f"No required fields found in extraction for {app_name} {action_name}")
                    return None
                    
            else:
                logger.error("No LLM available for field extraction")
                return None
                
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse extraction JSON: {e}")
            return None
        except Exception as e:
            logger.error(f"Error in field extraction: {e}")
            return None
    
    async def _execute_app_action(
        self, 
        app_name: str, 
        action_name: str, 
        data: Dict[str, Any]
    ) -> str:
        """
        Execute the actual app action via n8n backend API.
        """
        
        try:
            # Call n8n backend API to execute app action
            response = await httpx.AsyncClient().post(
                f"{self.backend_api_url}/integrations/n8n/execute-action",
                json={
                    "user_id": self.user_id,
                    "app_name": app_name,
                    "action_name": action_name,
                    "action_data": data,
                    "workflow_context": {
                        "source": "livekit_agent",
                        "timestamp": datetime.now().isoformat()
                    }
                },
                headers={"Authorization": f"Bearer {self.user_id}"}
            )
            
            if response.status_code == 200:
                result = response.json()
                return result.get("message", "Action completed successfully via n8n")
            else:
                error_msg = f"N8N API error {response.status_code}"
                try:
                    error_data = response.json()
                    error_msg = error_data.get("detail", error_msg)
                except:
                    pass
                return f"Failed: {error_msg}"
                
        except Exception as e:
            logger.error(f"Error executing {app_name} action via n8n: {e}")
            return f"Execution failed: {str(e)}"

# Factory function for WorkflowAgent integration
async def create_dynamic_app_tools(
    user_id: str, 
    workflow_config: Dict[str, Any],
    backend_api_url: str = None
) -> List:
    """
    Create dynamic app action tools based on workflow configuration.
    
    This is called from WorkflowAgent._inject_workflow_tools() using LiveKit
    temporal tools pattern.
    """
    
    factory = DynamicAppToolFactory(user_id, backend_api_url)
    await factory.initialize_app_schemas()
    
    tools = []
    
    # Scan workflow for app_action nodes
    config = workflow_config.get('config', {})
    nodes = config.get('nodes', [])
    
    logger.info(f"Scanning {len(nodes)} nodes for app_action types")
    
    for node in nodes:
        if node.get('type') == 'app_action':
            node_id = node.get('id')
            node_config = node.get('config', {})
            
            # FIXED: Extract app_name and action_type from the correct location
            # Based on actual pathway structure: config.data.app_name and config.data.action_type
            action_data = node_config.get('data', {})
            app_name = action_data.get('app_name')
            action_type = action_data.get('action_type')  # Note: action_type, not action_name
            
            logger.info(f"Found app_action node: {node_id}, app_name: {app_name}, action_type: {action_type}")
            
            if app_name and action_type and node_id:
                # Create context-aware tool for this specific app action
                tool = factory.create_app_action_tool(app_name, action_type, node_id)
                tools.append(tool)
                
                # Show the actual function name that was created (not the generic format)
                actual_function_name = tool.__name__ if hasattr(tool, '__name__') else f"{app_name}_{action_type}"
                logger.info(f"✅ Created dynamic tool: {actual_function_name} for node {node_id}")
            else:
                logger.warning(f"❌ Skipping incomplete app_action node {node_id}: app_name={app_name}, action_type={action_type}")
    
    logger.info(f"Created {len(tools)} dynamic app action tools")
    return tools 