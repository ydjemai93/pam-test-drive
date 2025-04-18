from fastapi import APIRouter

from app.api.v1.endpoints import agents, calls # Import calls

api_router = APIRouter()

# Include endpoint routers here
api_router.include_router(agents.router, prefix="/agents", tags=["Agents"])
api_router.include_router(calls.router, prefix="/calls", tags=["Calls"]) # Add calls router 