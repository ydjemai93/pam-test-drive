"""
Agent Type Definitions for Multi-Agent Pathway System
This file contains the core data structures for mapping pathway nodes to agent classes.
"""

from dataclasses import dataclass

@dataclass
class AgentTypeMapping:
    """Configuration for mapping pathway node types to agent classes"""
    node_type: str
    module_name: str
    class_name: str
    description: str
    supports_conditions: bool = True
    supports_handoffs: bool = True

# Default agent type mappings for different pathway node types
DEFAULT_AGENT_MAPPINGS = [
    AgentTypeMapping(
        node_type="conversation",
        module_name="specialized_pathway_agents",
        class_name="ConversationAgent",
        description="Handles general conversation and dialogue",
    ),
    AgentTypeMapping(
        node_type="greeting",
        module_name="specialized_pathway_agents",
        class_name="GreetingAgent",
        description="Specialized for initial greetings",
    ),
    AgentTypeMapping(
        node_type="qualification",
        module_name="specialized_pathway_agents",
        class_name="QualificationAgent",
        description="Specialized for lead qualification",
    ),
    AgentTypeMapping(
        node_type="booking",
        module_name="specialized_pathway_agents",
        class_name="BookingAgent",
        description="Specialized for appointment scheduling",
    ),
    AgentTypeMapping(
        node_type="transfer",
        module_name="specialized_pathway_agents",
        class_name="TransferAgent",
        description="Handles call transfers to human agents",
        supports_conditions=False,
        supports_handoffs=False,
    ),
    AgentTypeMapping(
        node_type="end_call",
        module_name="specialized_pathway_agents",
        class_name="EndCallAgent",
        description="Handles conversation conclusion",
        supports_conditions=False,
        supports_handoffs=False,
    ),
] 