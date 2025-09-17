
import logging
from typing import Any, Dict, Optional, Tuple

from specialized_pathway_agents import (
    GreetingAndConditionAgent,
    GoodbyeAgent,

)
# Make sure to import the base agent class if it's defined elsewhere
# from .base_agent import PathwayAgent

logger = logging.getLogger(__name__)

def create_pathway_agent(
    node_config: Dict[str, Any],
    pathway_config: Dict[str, Any],
    global_context: Optional[Dict[str, Any]] = None
) -> Tuple[Optional[Any], Optional[str]]:
    """
    Factory function to create a pathway agent based on the node type.
    """
    node_type = node_config.get("type")
    node_id = node_config.get("id")
    logger.info(f"Creating agent for node_id: {node_id}, type: {node_type}")

    agent_class_map = {
        "greeting_and_condition": GreetingAndConditionAgent,
        "goodbye": GoodbyeAgent,
    }

    agent_class = agent_class_map.get(node_type)
        
        if agent_class:
        try:
            # Pass both node and pathway configs to the agent constructor
            agent = agent_class(
                node_config=node_config,
                pathway_config=pathway_config,
                global_context=global_context
            )
            logger.info(f"Successfully created {agent.__class__.__name__} for node {node_id}")
            return agent, None
    except Exception as e:
            error_message = f"Error creating agent for node {node_id}: {e}"
            logger.error(error_message, exc_info=True)
            return None, error_message
    else:
        error_message = f"Unsupported node type: {node_type}"
        logger.warning(error_message)
        return None, error_message 