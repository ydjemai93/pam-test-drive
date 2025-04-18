from fastapi import APIRouter, Depends, HTTPException, status
from typing import List

from app.models.agent import AgentCreate, AgentRead, AgentUpdate
from app.services import xano_service
from app.api.v1.dependencies import get_current_user_id

router = APIRouter()

@router.post("/", response_model=AgentRead, status_code=status.HTTP_201_CREATED)
async def create_agent(
    *, 
    agent_in: AgentCreate, 
    current_user_id: int = Depends(get_current_user_id)
):
    """Create a new agent for the current user."""
    # The service function expects a dict, Pydantic v2 uses model_dump()
    agent_data = agent_in.model_dump()
    created_agent = await xano_service.create_agent_in_xano(
        agent_data=agent_data, 
        user_id=current_user_id
    )
    # Assuming Xano returns the full agent object matching AgentRead structure
    return created_agent

@router.get("/", response_model=List[AgentRead])
async def read_agents(
    current_user_id: int = Depends(get_current_user_id)
):
    """Retrieve agents belonging to the current user."""
    agents = await xano_service.get_agents_from_xano(user_id=current_user_id)
    return agents

@router.get("/{agent_id}", response_model=AgentRead)
async def read_agent(
    *, 
    agent_id: int, 
    current_user_id: int = Depends(get_current_user_id)
):
    """Get a specific agent by ID, ensuring it belongs to the current user."""
    agent = await xano_service.get_agent_by_id_from_xano(agent_id=agent_id, user_id=current_user_id)
    if not agent:
        # This case should technically be handled by the 404 in the service
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    return agent

@router.put("/{agent_id}", response_model=AgentRead)
async def update_agent(
    *, 
    agent_id: int, 
    agent_in: AgentUpdate,
    current_user_id: int = Depends(get_current_user_id)
):
    """Update an agent owned by the current user."""
    # Get update data, excluding unset fields to allow partial updates
    update_data = agent_in.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No update data provided")
        
    updated_agent = await xano_service.update_agent_in_xano(
        agent_id=agent_id, 
        update_data=update_data, 
        user_id=current_user_id
    )
    return updated_agent

@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(
    *, 
    agent_id: int, 
    current_user_id: int = Depends(get_current_user_id)
):
    """Delete an agent owned by the current user."""
    await xano_service.delete_agent_in_xano(agent_id=agent_id, user_id=current_user_id)
    # No content response for successful deletion
    return 