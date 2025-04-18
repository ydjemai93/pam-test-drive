from fastapi import FastAPI

app = FastAPI(
    title="MARK_I Backend",
    description="API Backend for the MARK_I SaaS project.",
    version="0.1.0",
)

@app.get("/health", tags=["Health Check"], summary="Check if the API is running")
def health_check():
    """Check if the API is running."""
    return {"status": "ok"}

# Include the API router
from app.api.v1.api import api_router
app.include_router(api_router, prefix="/api/v1") 