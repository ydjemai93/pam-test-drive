"""
API Routes Module

Centralizes all route imports for the API.
"""

from .auth import router as auth_router
from .agents import router as agents_router  
from .calls import router as calls_router
from .users import router as users_router

# Import existing route modules
from ..batch_routes import router as batch_router
from ..pathway_routes import router as pathway_router
from ..integrations_routes import router as integrations_router
from ..telnyx_routes import router as telnyx_router
from ..webhook_tools_routes import router as webhook_tools_router

__all__ = [
    "auth_router",
    "agents_router", 
    "calls_router",
    "users_router",
    "batch_router",
    "pathway_router", 
    "integrations_router",
    "telnyx_router",
    "webhook_tools_router"
] 