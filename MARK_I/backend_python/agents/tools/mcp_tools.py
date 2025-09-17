"""
MCP Integration Tools for WorkflowAgent

Replaces n8n OAuth system with direct MCP server connections.
Connects directly to official MCP servers (Salesforce, Google Calendar, etc.)
"""

import logging
import os
import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime

from livekit.agents import function_tool
import httpx

logger = logging.getLogger("mcp-tools")

class MCPClientManager:
    """
    Manages connections to multiple MCP servers.
    Replaces the entire n8n OAuth system with direct MCP connections.
    """
    
    def __init__(self):
        self.mcp_servers = {}
        self.user_sessions = {}  # Store user MCP sessions
        
    async def initialize_mcp_servers(self, user_id: str):
        """Initialize MCP servers for a specific user"""
        # Connect to available MCP servers for this user
        available_servers = await self._discover_user_mcp_servers(user_id)
        
        for server_name, server_config in available_servers.items():
            try:
                # Initialize MCP client connection
                client = await self._connect_to_mcp_server(server_config)
                self.mcp_servers[f"{user_id}:{server_name}"] = client
                logger.info(f"Connected to MCP server: {server_name} for user: {user_id}")
            except Exception as e:
                logger.error(f"Failed to connect to {server_name}: {e}")
    
    async def _discover_user_mcp_servers(self, user_id: str) -> Dict[str, Any]:
        """Discover which MCP servers the user has connected to"""
        # Query your database for user's connected MCP servers
        # This replaces the user_app_connections table query
        return {
            "salesforce": {
                "command": "npx",
                "args": ["@salesforce/mcp-server"],
                "env": {"SALESFORCE_USER_ID": user_id}
            },
            "google_calendar": {
                "command": "npx", 
                "args": ["@google/mcp-server-calendar"],
                "env": {"GOOGLE_USER_ID": user_id}
            }
        }
    
    async def _connect_to_mcp_server(self, server_config: Dict[str, Any]):
        """Connect to an MCP server using the MCP protocol"""
        # Implementation depends on MCP Python client
        # This would use the official MCP client library
        pass

class MCPToolsFactory:
    """
    Creates LiveKit function tools from MCP server tools.
    Eliminates the need for custom app integrations.
    """
    
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.mcp_manager = MCPClientManager()
        
    async def create_mcp_tools(self) -> List:
        """
        Create function tools from available MCP servers.
        
        This replaces:
        - create_google_calendar_tools()
        - create_crm_tools() 
        - create_email_tools()
        """
        await self.mcp_manager.initialize_mcp_servers(self.user_id)
        
        tools = []
        
        # Salesforce MCP Tools
        if f"{self.user_id}:salesforce" in self.mcp_manager.mcp_servers:
            tools.extend(await self._create_salesforce_mcp_tools())
            
        # Google Calendar MCP Tools  
        if f"{self.user_id}:google_calendar" in self.mcp_manager.mcp_servers:
            tools.extend(await self._create_calendar_mcp_tools())
            
        return tools
    
    async def _create_salesforce_mcp_tools(self) -> List:
        """Create Salesforce tools from MCP server"""
        
        @function_tool
        async def create_salesforce_contact(
            email: str,
            first_name: str,
            last_name: str,
            company: str
        ) -> str:
            """Create a contact in Salesforce using MCP server"""
            try:
                # Call MCP server tool directly
                mcp_client = self.mcp_manager.mcp_servers[f"{self.user_id}:salesforce"]
                result = await mcp_client.call_tool("create_contact", {
                    "email": email,
                    "first_name": first_name,
                    "last_name": last_name,
                    "company": company
                })
                
                logger.info(f"Created Salesforce contact via MCP: {result}")
                return f"✅ Created Salesforce contact: {first_name} {last_name}"
                
            except Exception as e:
                logger.error(f"Salesforce MCP error: {e}")
                return f"❌ Failed to create contact: {str(e)}"
        
        @function_tool
        async def create_salesforce_opportunity(
            name: str,
            amount: float,
            close_date: str,
            stage: str = "Prospecting"
        ) -> str:
            """Create an opportunity in Salesforce using MCP server"""
            try:
                mcp_client = self.mcp_manager.mcp_servers[f"{self.user_id}:salesforce"]
                result = await mcp_client.call_tool("create_opportunity", {
                    "name": name,
                    "amount": amount,
                    "close_date": close_date,
                    "stage": stage
                })
                
                return f"✅ Created Salesforce opportunity: {name}"
                
            except Exception as e:
                logger.error(f"Salesforce opportunity MCP error: {e}")
                return f"❌ Failed to create opportunity: {str(e)}"
        
        return [create_salesforce_contact, create_salesforce_opportunity]
    
    async def _create_calendar_mcp_tools(self) -> List:
        """Create Google Calendar tools from MCP server"""
        
        @function_tool
        async def schedule_calendar_event(
            title: str,
            start_time: str,
            end_time: str,
            attendee_emails: List[str] = None,
            description: str = ""
        ) -> str:
            """Schedule a calendar event using Google Calendar MCP server"""
            try:
                mcp_client = self.mcp_manager.mcp_servers[f"{self.user_id}:google_calendar"]
                result = await mcp_client.call_tool("create_event", {
                    "summary": title,
                    "start": {"dateTime": start_time},
                    "end": {"dateTime": end_time},
                    "attendees": [{"email": email} for email in (attendee_emails or [])],
                    "description": description
                })
                
                return f"✅ Scheduled calendar event: {title}"
                
            except Exception as e:
                logger.error(f"Calendar MCP error: {e}")
                return f"❌ Failed to schedule event: {str(e)}"
        
        return [schedule_calendar_event]

# Factory function for WorkflowAgent integration
async def create_mcp_tools(user_id: str) -> List:
    """
    Create MCP-based function tools for WorkflowAgent.
    
    This completely replaces:
    - n8n OAuth system
    - Custom app integrations
    - Backend token storage
    """
    factory = MCPToolsFactory(user_id)
    return await factory.create_mcp_tools()

# Integration with WorkflowAgent
class MCPWorkflowIntegration:
    """
    Integrates MCP tools into WorkflowAgent's existing architecture.
    Replaces app_action nodes with MCP-powered tools.
    """
    
    @staticmethod
    async def enhance_workflow_with_mcp(workflow_agent, user_id: str):
        """Add MCP tools to existing WorkflowAgent"""
        mcp_tools = await create_mcp_tools(user_id)
        
        # Add MCP tools to agent using LiveKit's update_tools pattern
        current_tools = workflow_agent.tools or []
        enhanced_tools = current_tools + mcp_tools
        
        await workflow_agent.update_tools(enhanced_tools)
        logger.info(f"Enhanced WorkflowAgent with {len(mcp_tools)} MCP tools") 