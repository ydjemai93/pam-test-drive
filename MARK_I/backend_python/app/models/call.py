from pydantic import BaseModel, Field
from typing import Optional
import datetime

# Properties to receive via API to initiate a call
class CallInitiate(BaseModel):
    agent_id: int
    to_phone_number: str = Field(..., pattern=r"^\+[1-9]\d{1,14}$") # E.164 format validation

# Properties returned after initiating a call (example)
class CallInitiateResponse(BaseModel):
    call_control_id: str # Telnyx Call Control ID
    status: str = "initiating"
    # You might add other relevant info here later 

# Pydantic model for the request body when initiating a call
class CallCreate(BaseModel):
    agent_id: int
    to_phone_number: str = Field(..., examples=["+33612345678"])

# Pydantic model for representing a call record (e.g., as returned by Xano/API)
class CallRead(BaseModel):
    id: int # Xano record ID
    agent_id: int
    user_id: int
    telnyx_call_control_id: Optional[str] = None
    telnyx_call_session_id: Optional[str] = None
    to_phone_number: str
    from_phone_number: Optional[str] = None
    status: str
    initiated_at: Optional[datetime.datetime] = None
    answered_at: Optional[datetime.datetime] = None # Add if tracked
    ended_at: Optional[datetime.datetime] = None
    ended_reason: Optional[str] = None
    livekit_sip_uri: Optional[str] = None 
    created_at: Optional[datetime.datetime] = None # Xano default field

    class Config:
        from_attributes = True # Pydantic v2 equivalent of orm_mode 