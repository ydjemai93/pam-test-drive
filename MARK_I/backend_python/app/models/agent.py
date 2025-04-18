from pydantic import BaseModel, Field

# Shared properties
class AgentBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = None
    telnyx_api_key: str = Field(..., min_length=10) # Assuming a minimum length
    telnyx_connection_id: str = Field(..., min_length=10) # Assuming a minimum length
    livekit_api_key: str = Field(..., min_length=10) # Assuming a minimum length
    livekit_api_secret: str = Field(..., min_length=10) # Assuming a minimum length

# Properties to receive via API on creation
class AgentCreate(AgentBase):
    pass

# Properties to receive via API on update
class AgentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = None
    telnyx_api_key: str | None = Field(default=None, min_length=10)
    telnyx_connection_id: str | None = Field(default=None, min_length=10)
    livekit_api_key: str | None = Field(default=None, min_length=10)
    livekit_api_secret: str | None = Field(default=None, min_length=10)

# Properties stored in DB (returned by API)
class AgentRead(AgentBase):
    id: int
    user_id: int
    # Optional: Add created_at, updated_at if needed in the response
    # created_at: datetime
    # updated_at: datetime

    class Config:
        orm_mode = True # Or from_attributes = True for Pydantic v2 