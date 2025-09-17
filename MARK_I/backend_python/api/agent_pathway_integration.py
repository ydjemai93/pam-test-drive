# Agent Pathway Integration Module
# Bridges WorkflowAgent with existing OutboundCaller system

import logging
import json
from typing import Dict, Any, Optional
from datetime import datetime, timezone

# Import database client
from db_client import supabase_service_client

logger = logging.getLogger(__name__)

async def auto_start_pathway_for_new_call(call_id: str, agent_id: int, session_metadata: Dict[str, Any] = None) -> Optional[str]:
    """
    Auto-start pathway execution for a new call if the agent has a default pathway assigned.
    
    Args:
        call_id: The Supabase call ID
        agent_id: The agent ID
        session_metadata: Additional session metadata
    
    Returns:
        execution_id if pathway was started, None otherwise
    """
    try:
        logger.info(f"Checking for default pathway for agent {agent_id} and call {call_id}")
        
        # Get agent details to check for default pathway
        agent_response = supabase_service_client.table("agents").select(
            "id, name, default_pathway_id"
        ).eq("id", agent_id).single().execute()
        
        if not agent_response.data:
            logger.warning(f"Agent {agent_id} not found")
            return None
        
        agent_data = agent_response.data
        default_pathway_id = agent_data.get("default_pathway_id")
        
        if not default_pathway_id:
            logger.info(f"Agent {agent_id} has no default pathway assigned")
            return None
        
        # Load pathway configuration
        pathway_response = supabase_service_client.table("pathways").select("*").eq("id", default_pathway_id).single().execute()
        
        if not pathway_response.data:
            logger.warning(f"Default pathway {default_pathway_id} not found for agent {agent_id}")
            return None
        
        pathway_data = pathway_response.data
        
        # Check if pathway is active
        if pathway_data.get("status") != "active":
            logger.info(f"Pathway {default_pathway_id} is not active (status: {pathway_data.get('status')})")
            return None
        
        # Create pathway execution record
        execution_id = await create_pathway_execution(
            pathway_id=default_pathway_id,
            call_id=call_id,
            agent_id=agent_id,
            pathway_data=pathway_data,
            session_metadata=session_metadata
        )
        
        if execution_id:
            logger.info(f"✅ Started pathway execution {execution_id} for call {call_id}")
            return execution_id
        else:
            logger.error(f"Failed to create pathway execution for call {call_id}")
            return None
            
    except Exception as e:
        logger.error(f"Error auto-starting pathway for call {call_id}: {e}")
        return None

async def create_pathway_execution(
    pathway_id: str, 
    call_id: str, 
    agent_id: int, 
    pathway_data: Dict[str, Any],
    session_metadata: Dict[str, Any] = None
) -> Optional[str]:
    """
    Create a pathway execution record in the database
    
    Returns:
        execution_id if successful, None otherwise
    """
    try:
        import uuid
        
        execution_id = str(uuid.uuid4())
        
        # Get entry point from pathway config
        entry_point = pathway_data.get("config", {}).get("entry_point", "entry")
        
        execution_data = {
            "id": execution_id,
            "pathway_id": pathway_id,
            "call_id": call_id,
            "agent_id": agent_id,
            "status": "running",
            "current_node_id": entry_point,
            "variables": session_metadata or {},
            "execution_trace": [{
                "node": entry_point,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "action": "pathway_started"
            }],
            "started_at": datetime.now(timezone.utc).isoformat()
        }
        
        # Insert into pathway_executions table
        response = supabase_service_client.table("pathway_executions").insert(execution_data).execute()
        
        if response.data:
            logger.info(f"Created pathway execution record: {execution_id}")
            
            # Update call record with pathway execution info
            await link_call_to_pathway_execution(call_id, execution_id, entry_point)
            
            return execution_id
        else:
            logger.error(f"Failed to insert pathway execution record")
            return None
            
    except Exception as e:
        logger.error(f"Error creating pathway execution: {e}")
        return None

async def link_call_to_pathway_execution(call_id: str, execution_id: str, current_node: str):
    """Link a call record to its pathway execution"""
    try:
        update_data = {
            "pathway_execution_id": execution_id,
            "current_pathway_node_id": current_node
        }
        
        response = supabase_service_client.table("calls").update(update_data).eq("id", call_id).execute()
        
        if response.data:
            logger.info(f"Linked call {call_id} to pathway execution {execution_id}")
        else:
            logger.warning(f"Failed to link call {call_id} to pathway execution")
            
    except Exception as e:
        logger.error(f"Error linking call to pathway execution: {e}")

async def handle_call_event(event_type: str, call_id: str, event_data: Dict[str, Any] = None):
    """
    Handle call events that might affect pathway execution
    
    Args:
        event_type: Type of event (started, ended, user_input, etc.)
        call_id: The call ID
        event_data: Additional event data
    """
    try:
        logger.debug(f"Handling call event: {event_type} for call {call_id}")
        
        # Get pathway execution for this call
        execution_response = supabase_service_client.table("pathway_executions").select("*").eq("call_id", call_id).eq("status", "running").execute()
        
        if not execution_response.data:
            logger.debug(f"No active pathway execution found for call {call_id}")
            return
        
        execution_data = execution_response.data[0]
        execution_id = execution_data["id"]
        
        # Handle different event types
        if event_type == "call_ended":
            await complete_pathway_execution(execution_id, "call_ended")
        elif event_type == "user_input":
            await update_pathway_variables(execution_id, {"last_user_input": event_data.get("input", "")})
        elif event_type == "node_transition":
            await log_node_transition(execution_id, event_data)
        
        logger.debug(f"Processed call event: {event_type} for execution {execution_id}")
        
    except Exception as e:
        logger.error(f"Error handling call event {event_type} for call {call_id}: {e}")

async def complete_pathway_execution(execution_id: str, completion_reason: str = "completed"):
    """Mark a pathway execution as completed"""
    try:
        update_data = {
            "status": "completed",
            "completed_at": datetime.now(timezone.utc).isoformat()
        }
        
        response = supabase_service_client.table("pathway_executions").update(update_data).eq("id", execution_id).execute()
        
        if response.data:
            logger.info(f"Completed pathway execution {execution_id} (reason: {completion_reason})")
        
    except Exception as e:
        logger.error(f"Error completing pathway execution {execution_id}: {e}")

async def update_pathway_variables(execution_id: str, new_variables: Dict[str, Any]):
    """Update pathway variables for an execution"""
    try:
        # Get current variables
        execution_response = supabase_service_client.table("pathway_executions").select("variables").eq("id", execution_id).single().execute()
        
        if execution_response.data:
            current_variables = execution_response.data.get("variables", {})
            current_variables.update(new_variables)
            
            # Update in database
            response = supabase_service_client.table("pathway_executions").update({
                "variables": current_variables,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }).eq("id", execution_id).execute()
            
            if response.data:
                logger.debug(f"Updated pathway variables for execution {execution_id}")
        
    except Exception as e:
        logger.error(f"Error updating pathway variables for execution {execution_id}: {e}")

async def log_node_transition(execution_id: str, transition_data: Dict[str, Any]):
    """Log a node transition in the pathway execution"""
    try:
        # Get current execution trace
        execution_response = supabase_service_client.table("pathway_executions").select("execution_trace, current_node_id").eq("id", execution_id).single().execute()
        
        if execution_response.data:
            current_trace = execution_response.data.get("execution_trace", [])
            
            # Add new transition to trace
            transition_entry = {
                "from_node": execution_response.data.get("current_node_id"),
                "to_node": transition_data.get("to_node"),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "result": transition_data.get("result", {}),
                "action": "node_transition"
            }
            
            current_trace.append(transition_entry)
            
            # Update in database
            update_data = {
                "execution_trace": current_trace,
                "current_node_id": transition_data.get("to_node"),
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
            
            response = supabase_service_client.table("pathway_executions").update(update_data).eq("id", execution_id).execute()
            
            if response.data:
                logger.debug(f"Logged node transition for execution {execution_id}")
        
    except Exception as e:
        logger.error(f"Error logging node transition for execution {execution_id}: {e}")

def get_agent_pathway_manager():
    """
    Get the pathway manager instance for agent integration
    This is a placeholder for future advanced pathway management
    """
    return {
        "auto_start_pathway": auto_start_pathway_for_new_call,
        "handle_event": handle_call_event,
        "complete_execution": complete_pathway_execution
    }

logger.info("Agent Pathway Integration module loaded successfully")
