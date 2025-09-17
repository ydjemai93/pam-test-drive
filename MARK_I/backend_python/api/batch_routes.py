"""
Batch Campaign Routes for handling bulk calling operations.
"""

import asyncio
import csv
import io
import json
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, status, Header, UploadFile, File, BackgroundTasks
from pydantic import BaseModel, Field, validator
from supabase import create_client
from gotrue.errors import AuthApiError

from api.config import BaseModel as ConfigBaseModel
from api.db_client import supabase_service_client

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/batch-campaigns", tags=["batch_campaigns"])

# ===== Pydantic Models =====

from typing import ClassVar

class BatchCampaignStatus:
    """Enum-like class for campaign status"""
    DRAFT: ClassVar[str] = "draft"
    SCHEDULED: ClassVar[str] = "scheduled"
    RUNNING: ClassVar[str] = "running"
    COMPLETED: ClassVar[str] = "completed"
    FAILED: ClassVar[str] = "failed"

class BatchCallItemStatus:
    """Enum-like class for call item status"""
    PENDING: ClassVar[str] = "pending"
    CALLING: ClassVar[str] = "calling"
    COMPLETED: ClassVar[str] = "completed"
    FAILED: ClassVar[str] = "failed"
    RETRYING: ClassVar[str] = "retrying"
    CANCELLED: ClassVar[str] = "cancelled"

class BatchCampaignCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="Campaign name")
    description: Optional[str] = Field(None, description="Campaign description")
    agent_id: int = Field(..., description="Agent ID to use for calls")
    concurrency_limit: int = Field(3, ge=1, le=50, description="Max simultaneous calls")
    retry_failed: bool = Field(True, description="Whether to retry failed calls")
    max_retries: int = Field(2, ge=0, le=5, description="Maximum number of retries")

class BatchCallItemCreateRequest(BaseModel):
    phone_number_e164: str = Field(..., description="Phone number in E.164 format")
    contact_name: Optional[str] = Field(None, max_length=255, description="Contact name")
    custom_data: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Custom data for personalization")

    @validator('phone_number_e164')
    def validate_phone_number(cls, v):
        """Basic E.164 validation"""
        if not v.startswith('+'):
            raise ValueError('Phone number must start with +')
        if len(v) < 7 or len(v) > 20:
            raise ValueError('Phone number must be between 7-20 characters')
        # Remove + and check if remaining are digits
        digits_only = v[1:]
        if not digits_only.isdigit():
            raise ValueError('Phone number must contain only digits after +')
        return v

class BatchCampaignUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    concurrency_limit: Optional[int] = Field(None, ge=1, le=50)
    retry_failed: Optional[bool] = None
    max_retries: Optional[int] = Field(None, ge=0, le=5)

class BatchCampaignScheduleRequest(BaseModel):
    scheduled_at: datetime = Field(..., description="When to start the campaign (ISO 8601 format)")
    
    @validator('scheduled_at')
    def validate_scheduled_time(cls, v):
        """Validate that scheduled time is in the future"""
        if v <= datetime.now(timezone.utc):
            raise ValueError('Scheduled time must be in the future')
        return v

class BatchCampaignResponse(BaseModel):
    id: str
    user_id: str
    agent_id: Optional[int]
    name: str
    description: Optional[str]
    status: str
    total_numbers: int
    completed_calls: int
    successful_calls: int
    failed_calls: int
    concurrency_limit: int
    retry_failed: bool
    max_retries: int
    scheduled_at: Optional[datetime]
    started_at: Optional[datetime]  # Campaign started_at, not call initiated_at
    completed_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

class BatchCallItemResponse(BaseModel):
    id: str
    batch_campaign_id: str
    phone_number_e164: str
    contact_name: Optional[str]
    custom_data: Dict[str, Any]
    status: str
    call_id: Optional[str]
    attempts: int
    last_attempt_at: Optional[datetime]
    completed_at: Optional[datetime]
    error_message: Optional[str]
    created_at: datetime
    updated_at: datetime

class CSVUploadResponse(BaseModel):
    total_rows: int
    valid_rows: int
    invalid_rows: int
    errors: List[Dict[str, Any]]
    preview: List[Dict[str, Any]]

class CampaignProgressResponse(BaseModel):
    campaign_id: str
    status: str
    progress_percentage: float
    total_numbers: int
    completed_calls: int
    successful_calls: int
    failed_calls: int
    pending_calls: int
    calling_now: int
    estimated_completion: Optional[datetime]
    created_at: datetime  # Added campaign creation time
    
    # MVP Analytics Enhancement
    call_outcomes: Dict[str, int] = Field(default_factory=dict, description="Breakdown of call outcomes")
    response_rate: float = Field(0.0, description="Percentage of calls that reached humans")
    avg_call_duration: float = Field(0.0, description="Average call duration in seconds")
    total_call_duration: float = Field(0.0, description="Total call time in seconds")
    peak_response_hours: List[str] = Field(default_factory=list, description="Hours when people answer most")
    geographic_performance: Dict[str, Dict[str, int]] = Field(default_factory=dict, description="Performance by region")

# ===== Helper Functions =====

async def verify_user_access_to_campaign(campaign_id: str, user_id: str) -> Dict[str, Any]:
    """Verify user has access to campaign and return campaign data"""
    try:
        campaign_response = supabase_service_client.table("batch_campaigns").select("*").eq("id", campaign_id).eq("user_id", user_id).single().execute()
        
        if not campaign_response.data:
            raise HTTPException(status_code=404, detail="Campaign not found or access denied")
        
        return campaign_response.data
    except Exception as e:
        logger.error(f"Error verifying campaign access: {e}")
        raise HTTPException(status_code=500, detail="Failed to verify campaign access")

async def verify_agent_belongs_to_user(agent_id: int, user_id: str) -> Dict[str, Any]:
    """Verify agent belongs to user and return agent data"""
    try:
        agent_response = supabase_service_client.table("agents").select("*").eq("id", agent_id).eq("user_id", user_id).single().execute()
        
        if not agent_response.data:
            raise HTTPException(status_code=404, detail="Agent not found or access denied")
        
        return agent_response.data
    except Exception as e:
        logger.error(f"Error verifying agent access: {e}")
        raise HTTPException(status_code=500, detail="Failed to verify agent access")

async def check_and_start_scheduled_campaigns():
    """Background task to check for scheduled campaigns and start them"""
    try:
        logger.info("Checking for scheduled campaigns to start...")
        
        # Get campaigns that are scheduled to start
        current_time = datetime.now(timezone.utc)
        
        scheduled_campaigns_response = supabase_service_client.table("batch_campaigns").select("*").eq("status", "scheduled").lte("scheduled_at", current_time.isoformat()).execute()
        
        scheduled_campaigns = scheduled_campaigns_response.data or []
        
        if not scheduled_campaigns:
            logger.debug("No scheduled campaigns ready to start")
        else:
            logger.info(f"Found {len(scheduled_campaigns)} scheduled campaigns ready to start")
            
            for campaign in scheduled_campaigns:
                campaign_id = campaign["id"]
                try:
                    logger.info(f"Starting scheduled campaign: {campaign_id}")
                    
                    # Update status to running and set started_at
                    supabase_service_client.table("batch_campaigns").update({
                        "status": "running",
                        "started_at": current_time.isoformat()
                    }).eq("id", campaign_id).execute()
                    
                    # Execute the campaign
                    success = await execute_batch_campaign(campaign_id)
                    
                    if success:
                        logger.info(f"Successfully started scheduled campaign: {campaign_id}")
                    else:
                        logger.error(f"Failed to start scheduled campaign: {campaign_id}")
                        # Update status to failed
                        supabase_service_client.table("batch_campaigns").update({
                            "status": "failed"
                        }).eq("id", campaign_id).execute()
                        
                except Exception as e:
                    logger.error(f"Error starting scheduled campaign {campaign_id}: {e}")
                    # Update status to failed
                    try:
                        supabase_service_client.table("batch_campaigns").update({
                            "status": "failed"
                        }).eq("id", campaign_id).execute()
                    except Exception as update_e:
                        logger.error(f"Failed to update campaign status to failed: {update_e}")
        
        # ===== NEW: Check for campaigns to mark as completed =====
        await check_and_complete_finished_campaigns()
                    
    except Exception as e:
        logger.error(f"Error in scheduled campaigns checker: {e}")

async def check_and_complete_finished_campaigns():
    """Check for running campaigns that should be marked as completed"""
    try:
        logger.debug("Checking for campaigns to mark as completed...")
        
        # Get all running campaigns
        running_campaigns_response = supabase_service_client.table("batch_campaigns").select("*").eq("status", "running").execute()
        running_campaigns = running_campaigns_response.data or []
        
        if not running_campaigns:
            return
        
        logger.debug(f"Found {len(running_campaigns)} running campaigns to check")
        
        for campaign in running_campaigns:
            campaign_id = campaign["id"]
            
            try:
                # Get call items for this campaign
                items_response = supabase_service_client.table("batch_call_items").select("id, status").eq("batch_campaign_id", campaign_id).execute()
                call_items = items_response.data or []
                
                if not call_items:
                    logger.warning(f"Campaign {campaign_id} has no call items, marking as completed")
                    # Mark as completed if no items
                    await mark_campaign_completed(campaign_id)
                    continue
                
                # Check if all items are in a final state
                final_statuses = {"completed", "failed", "cancelled"}
                pending_statuses = {"pending", "calling", "retrying"}
                
                total_items = len(call_items)
                final_items = len([item for item in call_items if item.get("status") in final_statuses])
                pending_items = len([item for item in call_items if item.get("status") in pending_statuses])
                
                logger.debug(f"Campaign {campaign_id}: {final_items}/{total_items} items finished, {pending_items} pending")
                
                # If all items are in final state, mark campaign as completed
                if final_items == total_items and pending_items == 0:
                    logger.info(f"All items finished for campaign {campaign_id}, marking as completed")
                    await mark_campaign_completed(campaign_id)
                
            except Exception as e:
                logger.error(f"Error checking completion status for campaign {campaign_id}: {e}")
                
    except Exception as e:
        logger.error(f"Error checking finished campaigns: {e}")

async def mark_campaign_completed(campaign_id: str):
    """Mark a campaign as completed and set completion timestamp"""
    try:
        current_time = datetime.now(timezone.utc).isoformat()
        
        update_response = supabase_service_client.table("batch_campaigns").update({
            "status": "completed",
            "completed_at": current_time
        }).eq("id", campaign_id).execute()
        
        if update_response.data:
            logger.info(f"✅ Marked campaign {campaign_id} as completed")
        else:
            logger.error(f"Failed to mark campaign {campaign_id} as completed")
            
    except Exception as e:
        logger.error(f"Error marking campaign {campaign_id} as completed: {e}")

async def execute_batch_campaign(campaign_id: str) -> bool:
    """Execute a batch campaign by creating individual LiveKit call jobs"""
    try:
        # Get campaign details
        campaign_response = supabase_service_client.table("batch_campaigns").select("*").eq("id", campaign_id).single().execute()
        
        if not campaign_response.data:
            logger.error(f"Campaign {campaign_id} not found")
            return False
        
        campaign = campaign_response.data
        
        # Get agent details
        agent_response = supabase_service_client.table("agents").select("*").eq("id", campaign["agent_id"]).single().execute()
        
        if not agent_response.data:
            logger.error(f"Agent {campaign['agent_id']} not found for campaign {campaign_id}")
            return False
        
        agent = agent_response.data
        
        # Get pending call items for this campaign
        items_response = supabase_service_client.table("batch_call_items").select("*").eq("batch_campaign_id", campaign_id).eq("status", "pending").execute()
        
        call_items = items_response.data or []
        
        if not call_items:
            logger.warning(f"No pending call items found for campaign {campaign_id}")
            return True
        
        # Update campaign status to running
        supabase_service_client.table("batch_campaigns").update({
            "status": "running",
            "started_at": datetime.now(timezone.utc).isoformat()
        }).eq("id", campaign_id).execute()
        
        logger.info(f"Starting execution of campaign {campaign_id} with {len(call_items)} call items")
        
        # Create LiveKit call jobs for each call item (respecting concurrency limit)
        from livekit.api import LiveKitAPI, CreateRoomRequest
        import os
        
        livekit_api = LiveKitAPI(
            url=os.getenv("LIVEKIT_URL"),
            api_key=os.getenv("LIVEKIT_API_KEY"),
            api_secret=os.getenv("LIVEKIT_API_SECRET")
        )
        
        # Process calls with concurrency limit
        concurrency_limit = campaign.get("concurrency_limit", 3)
        active_calls = 0
        
        for item in call_items[:concurrency_limit]:  # Start with first batch
            try:
                # Create room for this call
                room_name = f"batch-call-{item['id']}"
                
                room_request = CreateRoomRequest(
                    name=room_name,
                    empty_timeout=300,  # 5 minutes
                    departure_timeout=60  # 1 minute
                )
                
                room = await livekit_api.room.create_room(room_request)
                
                # Create call record in database
                call_data = {
                    "user_id": campaign["user_id"],
                    "agent_id": campaign["agent_id"],
                    "phone_number_e164": item["phone_number_e164"],
                    "contact_name": item.get("contact_name"),
                    "status": "calling",
                    "room_name": room_name,
                    "call_type": "outbound_batch",
                    "batch_campaign_id": campaign_id,
                    "batch_call_item_id": item["id"]
                }
                
                call_response = supabase_service_client.table("calls").insert(call_data).execute()
                
                if call_response.data:
                    call_id = call_response.data[0]["id"]
                    
                    # Update call item status
                    supabase_service_client.table("batch_call_items").update({
                        "status": "calling",
                        "call_id": str(call_id),
                        "attempts": 1,
                        "last_attempt_at": datetime.now(timezone.utc).isoformat()
                    }).eq("id", item["id"]).execute()
                    
                    # Dispatch agent to the room with batch context
                    job_metadata = {
                        "agent_id": str(campaign["agent_id"]),
                        "phone_number": item["phone_number_e164"],
                        "contact_name": item.get("contact_name", ""),
                        "custom_data": item.get("custom_data", {}),
                        "batch_campaign_id": campaign_id,
                        "batch_call_item_id": item["id"],
                        "supabase_call_id": str(call_id)
                    }
                    
                    # Create a dispatch call job for the LiveKit worker
                    # This creates a SIP outbound call through the existing agent system
                    import httpx
                    try:
                        backend_url = os.getenv("BACKEND_API_URL", "http://localhost:8000")
                        agent_call_payload = {
                            "agent_id": campaign["agent_id"],
                            "phoneNumber": item["phone_number_e164"],
                            "lastName": item.get("contact_name", ""),
                            # Include batch context so the call gets linked properly
                            "batch_campaign_id": campaign_id,
                            "batch_call_item_id": item["id"]
                        }
                        
                        async with httpx.AsyncClient() as client:
                            call_response = await client.post(
                                f"{backend_url}/agents/call",
                                json=agent_call_payload,
                                timeout=30.0
                            )
                            
                        if call_response.status_code == 200:
                            logger.info(f"Successfully dispatched agent call for {item['phone_number_e164']}")
                        else:
                            logger.error(f"Failed to dispatch agent call: {call_response.status_code} - {call_response.text}")
                            
                    except Exception as dispatch_error:
                        logger.error(f"Error dispatching agent call: {dispatch_error}")
                        # Continue with room metadata update as fallback
                        try:
                            await livekit_api.room.update_room_metadata(
                                room=room_name,
                                metadata=json.dumps(job_metadata)
                            )
                        except Exception as metadata_error:
                            logger.error(f"Fallback room metadata update failed: {metadata_error}")
                    
                    logger.info(f"Created call job for {item['phone_number_e164']} in room {room_name}")
                    active_calls += 1
                    
                else:
                    logger.error(f"Failed to create call record for item {item['id']}")
                    
            except Exception as e:
                logger.error(f"Error creating call job for item {item['id']}: {e}")
                
                # Mark call item as failed
                supabase_service_client.table("batch_call_items").update({
                    "status": "failed",
                    "error_message": str(e),
                    "attempts": 1,
                    "last_attempt_at": datetime.now(timezone.utc).isoformat()
                }).eq("id", item["id"]).execute()
        
        logger.info(f"Started {active_calls} calls for campaign {campaign_id}")
        return True
        
    except Exception as e:
        logger.error(f"Error executing batch campaign {campaign_id}: {e}")
        
        # Update campaign status to failed
        try:
            supabase_service_client.table("batch_campaigns").update({
                "status": "failed",
                "completed_at": datetime.now(timezone.utc).isoformat()
            }).eq("id", campaign_id).execute()
        except:
            pass
            
        return False

# Scheduled campaigns functionality removed for simplicity

def parse_csv_content(csv_content: str) -> CSVUploadResponse:
    """Parse CSV content and validate phone numbers"""
    errors = []
    valid_rows = []
    invalid_rows = 0
    
    try:
        # Remove BOM if present
        if csv_content.startswith('\ufeff'):
            csv_content = csv_content[1:]
        
        # Clean up any carriage returns
        csv_content = csv_content.replace('\r\n', '\n').replace('\r', '\n')
        
        # Parse CSV with different potential delimiters
        # First try comma, then semicolon
        csv_reader = None
        detected_delimiter = ','
        
        # Detect delimiter by checking first line
        first_line = csv_content.split('\n')[0] if csv_content else ""
        if ';' in first_line and ',' not in first_line:
            detected_delimiter = ';'
            logger.info(f"Detected semicolon delimiter in CSV")
        elif ',' in first_line:
            detected_delimiter = ','
            logger.info(f"Detected comma delimiter in CSV")
        
        csv_reader = csv.DictReader(io.StringIO(csv_content), delimiter=detected_delimiter)
        
        # Validate headers
        expected_headers = {'phone_number', 'name'}  # Required headers
        # Clean and normalize headers (remove whitespace, convert to lowercase for comparison)
        raw_headers = csv_reader.fieldnames or []
        cleaned_headers = [h.strip().lower() if h else "" for h in raw_headers]
        actual_headers = set(cleaned_headers)
        
        logger.info(f"CSV headers detected (raw): {raw_headers}")
        logger.info(f"CSV headers detected (cleaned): {list(actual_headers)}")
        
        if 'phone_number' not in actual_headers:
            raise HTTPException(
                status_code=400, 
                detail=f"CSV must contain 'phone_number' column. Found headers: {raw_headers}"
            )
        
        # Create a mapping from cleaned headers back to original headers
        header_mapping = {}
        for raw, cleaned in zip(raw_headers, cleaned_headers):
            header_mapping[cleaned] = raw
        
        for row_num, row in enumerate(csv_reader, start=2):  # Start at 2 for header
            # Get values using the header mapping to handle case/whitespace differences
            phone_number_key = header_mapping.get('phone_number')
            name_key = header_mapping.get('name')
            
            phone_number = row.get(phone_number_key, '').strip() if phone_number_key else ''
            name = row.get(name_key, '').strip() if name_key else ''
            
            # Validate phone number
            try:
                # Add + if missing
                if phone_number and not phone_number.startswith('+'):
                    phone_number = '+' + phone_number
                
                # Validate using our model
                item = BatchCallItemCreateRequest(
                    phone_number_e164=phone_number,
                    contact_name=name if name else None,
                    custom_data={k: v for k, v in row.items() if k not in [phone_number_key, name_key] and v}
                )
                valid_rows.append(item.dict())
                
            except Exception as e:
                invalid_rows += 1
                errors.append({
                    "row": row_num,
                    "phone_number": phone_number,
                    "error": str(e)
                })
        
        return CSVUploadResponse(
            total_rows=len(valid_rows) + invalid_rows,
            valid_rows=len(valid_rows),
            invalid_rows=invalid_rows,
            errors=errors,
            preview=valid_rows[:10]  # Show first 10 valid rows as preview
        )
        
    except Exception as e:
        logger.error(f"CSV parsing error: {e}")
        raise HTTPException(status_code=400, detail=f"Failed to parse CSV: {str(e)}")

# ===== API Endpoints =====

@router.post("/", response_model=BatchCampaignResponse, status_code=status.HTTP_201_CREATED)
async def create_batch_campaign(
    request: BatchCampaignCreateRequest,
    authorization: str = Header(None, alias="Authorization")
):
    """Create a new batch campaign"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
    
    token = authorization.replace("Bearer ", "")
    
    try:
        # Verify token
        user_response = supabase_service_client.auth.get_user(token)
        if not user_response.user:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        user_id = user_response.user.id
        
        # Verify agent belongs to user
        await verify_agent_belongs_to_user(request.agent_id, user_id)
        
        # Create campaign - always starts as draft (no scheduling for now)
        status = "draft"
        
        campaign_data = {
            "user_id": user_id,
            "agent_id": request.agent_id,
            "name": request.name,
            "description": request.description,
            "concurrency_limit": request.concurrency_limit,
            "retry_failed": request.retry_failed,
            "max_retries": request.max_retries,
            "status": status
        }
        
        response = supabase_service_client.table("batch_campaigns").insert(campaign_data).execute()
        
        if not response.data:
            raise HTTPException(status_code=500, detail="Failed to create campaign")
        
        created_campaign = response.data[0]
        logger.info(f"Created batch campaign {created_campaign['id']} for user {user_id}")
        
        return BatchCampaignResponse(**created_campaign)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating batch campaign: {e}")
        raise HTTPException(status_code=500, detail="Failed to create batch campaign")

@router.get("/", response_model=List[BatchCampaignResponse])
async def list_batch_campaigns(
    authorization: str = Header(None, alias="Authorization"),
    status_filter: Optional[str] = None,
    limit: int = 50,
    offset: int = 0
):
    """List user's batch campaigns"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
    
    token = authorization.replace("Bearer ", "")
    
    try:
        # Verify token
        user_response = supabase_service_client.auth.get_user(token)
        if not user_response.user:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        user_id = user_response.user.id
        
        # Build query
        query = supabase_service_client.table("batch_campaigns").select("*").eq("user_id", user_id)
        
        if status_filter:
            query = query.eq("status", status_filter)
        
        query = query.order("created_at", desc=True).range(offset, offset + limit - 1)
        
        response = query.execute()
        
        campaigns = [BatchCampaignResponse(**campaign) for campaign in response.data or []]
        
        logger.info(f"Retrieved {len(campaigns)} campaigns for user {user_id}")
        return campaigns
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing campaigns: {e}")
        raise HTTPException(status_code=500, detail="Failed to list campaigns")

@router.get("/{campaign_id}", response_model=BatchCampaignResponse)
async def get_batch_campaign(
    campaign_id: str,
    authorization: str = Header(None, alias="Authorization")
):
    """Get specific batch campaign details"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
    
    token = authorization.replace("Bearer ", "")
    
    try:
        # Verify token
        user_response = supabase_service_client.auth.get_user(token)
        if not user_response.user:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        user_id = user_response.user.id
        
        # Get campaign and verify access
        campaign_data = await verify_user_access_to_campaign(campaign_id, user_id)
        
        return BatchCampaignResponse(**campaign_data)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting campaign {campaign_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to get campaign")

@router.patch("/{campaign_id}", response_model=BatchCampaignResponse)
async def update_batch_campaign(
    campaign_id: str,
    request: BatchCampaignUpdateRequest,
    authorization: str = Header(None, alias="Authorization")
):
    """Update batch campaign"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
    
    token = authorization.replace("Bearer ", "")
    
    try:
        # Verify token
        user_response = supabase_service_client.auth.get_user(token)
        if not user_response.user:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        user_id = user_response.user.id
        
        # Verify access to campaign
        campaign_data = await verify_user_access_to_campaign(campaign_id, user_id)
        
        # Check if campaign can be updated
        if campaign_data.get("status") in ["running", "completed", "failed"]:
            raise HTTPException(status_code=400, detail="Cannot update campaigns that are running, completed, or failed")
        
        # Build update data
        update_data = {}
        for field, value in request.dict(exclude_unset=True).items():
            if value is not None:
                update_data[field] = value
        
        if not update_data:
            raise HTTPException(status_code=400, detail="No fields to update")
        
        # Update campaign
        response = supabase_service_client.table("batch_campaigns").update(update_data).eq("id", campaign_id).execute()
        
        if not response.data:
            raise HTTPException(status_code=500, detail="Failed to update campaign")
        
        updated_campaign = response.data[0]
        logger.info(f"Updated batch campaign {campaign_id}")
        
        return BatchCampaignResponse(**updated_campaign)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating campaign {campaign_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to update campaign")

@router.delete("/{campaign_id}")
async def delete_batch_campaign(
    campaign_id: str,
    authorization: str = Header(None, alias="Authorization")
):
    """Delete batch campaign"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
    
    token = authorization.replace("Bearer ", "")
    
    try:
        # Verify token
        user_response = supabase_service_client.auth.get_user(token)
        if not user_response.user:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        user_id = user_response.user.id
        
        # Verify access to campaign
        campaign_data = await verify_user_access_to_campaign(campaign_id, user_id)
        
        # Check if campaign can be deleted
        if campaign_data.get("status") == "running":
            raise HTTPException(status_code=400, detail="Cannot delete running campaign.")
        
        # Delete campaign (cascade will delete call items)
        response = supabase_service_client.table("batch_campaigns").delete().eq("id", campaign_id).execute()
        
        if not response.data:
            raise HTTPException(status_code=500, detail="Failed to delete campaign")
        
        logger.info(f"Deleted batch campaign {campaign_id}")
        
        return {"message": f"Campaign {campaign_data.get('name', campaign_id)} deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting campaign {campaign_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete campaign")

@router.post("/{campaign_id}/start")
async def start_batch_campaign(
    campaign_id: str,
    authorization: str = Header(None, alias="Authorization")
):
    """Manually start a batch campaign"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
    
    token = authorization.replace("Bearer ", "")
    
    try:
        # Verify token
        user_response = supabase_service_client.auth.get_user(token)
        if not user_response.user:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        user_id = user_response.user.id
        
        # Verify access to campaign
        campaign_data = await verify_user_access_to_campaign(campaign_id, user_id)
        
        # Check if campaign can be started
        if campaign_data.get("status") != "draft":
            raise HTTPException(
                status_code=400, 
                detail=f"Cannot start campaign with status '{campaign_data.get('status')}'. Campaign must be in draft status."
            )
        
        # Check if campaign has call items
        items_response = supabase_service_client.table("batch_call_items").select("id").eq("batch_campaign_id", campaign_id).limit(1).execute()
        
        if not items_response.data:
            raise HTTPException(status_code=400, detail="Campaign has no phone numbers to call")
        
        # Start the campaign
        success = await execute_batch_campaign(campaign_id)
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to start campaign")
        
        logger.info(f"Manually started batch campaign {campaign_id}")
        
        return {"message": f"Campaign '{campaign_data.get('name', campaign_id)}' started successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting campaign {campaign_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to start campaign")

@router.post("/{campaign_id}/schedule")
async def schedule_batch_campaign(
    campaign_id: str,
    request: BatchCampaignScheduleRequest,
    authorization: str = Header(None, alias="Authorization")
):
    """Schedule a batch campaign to start at a specific time"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
    
    token = authorization.replace("Bearer ", "")
    
    try:
        # Verify token
        user_response = supabase_service_client.auth.get_user(token)
        if not user_response.user:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        user_id = user_response.user.id
        
        # Verify access to campaign
        campaign_data = await verify_user_access_to_campaign(campaign_id, user_id)
        
        # Check if campaign can be scheduled
        if campaign_data.get("status") not in ["draft"]:
            raise HTTPException(
                status_code=400, 
                detail=f"Cannot schedule campaign with status '{campaign_data.get('status')}'. Campaign must be in draft status."
            )
        
        # Check if campaign has call items
        items_response = supabase_service_client.table("batch_call_items").select("id").eq("batch_campaign_id", campaign_id).limit(1).execute()
        
        if not items_response.data:
            raise HTTPException(status_code=400, detail="Campaign has no phone numbers to call")
        
        # Update campaign to scheduled status
        update_response = supabase_service_client.table("batch_campaigns").update({
            "status": "scheduled",
            "scheduled_at": request.scheduled_at.isoformat()
        }).eq("id", campaign_id).execute()
        
        if not update_response.data:
            raise HTTPException(status_code=500, detail="Failed to schedule campaign")
        
        logger.info(f"Scheduled batch campaign {campaign_id} for {request.scheduled_at}")
        
        return {
            "message": f"Campaign '{campaign_data.get('name', campaign_id)}' scheduled successfully",
            "scheduled_at": request.scheduled_at
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error scheduling campaign {campaign_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to schedule campaign")

@router.post("/{campaign_id}/complete")
async def complete_batch_campaign(
    campaign_id: str,
    authorization: str = Header(None, alias="Authorization")
):
    """Manually mark a batch campaign as completed"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
    
    token = authorization.replace("Bearer ", "")
    
    try:
        # Verify token
        user_response = supabase_service_client.auth.get_user(token)
        if not user_response.user:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        user_id = user_response.user.id
        
        # Verify access to campaign
        campaign_data = await verify_user_access_to_campaign(campaign_id, user_id)
        
        # Check if campaign can be completed
        current_status = campaign_data.get("status")
        if current_status == "completed":
            raise HTTPException(status_code=400, detail="Campaign is already completed")
        elif current_status not in ["running", "failed"]:
            raise HTTPException(
                status_code=400, 
                detail=f"Cannot complete campaign with status '{current_status}'. Campaign must be running or failed."
            )
        
        # Mark campaign as completed
        await mark_campaign_completed(campaign_id)
        
        logger.info(f"Manually completed batch campaign {campaign_id}")
        
        return {"message": f"Campaign '{campaign_data.get('name', campaign_id)}' marked as completed"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error completing campaign {campaign_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to complete campaign")

# Pause functionality removed for simplicity

@router.post("/upload-csv", response_model=CSVUploadResponse)
async def upload_csv(
    file: UploadFile = File(...),
    authorization: str = Header(None, alias="Authorization")
):
    """Upload and validate CSV file for batch campaign"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
    
    # Validate file type
    if not file.filename or not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="File must be a CSV")
    
    try:
        # Read file content
        content = await file.read()
        csv_content = content.decode('utf-8')
        
        # Parse and validate
        result = parse_csv_content(csv_content)
        
        logger.info(f"CSV upload processed: {result.valid_rows} valid, {result.invalid_rows} invalid rows")
        return result
        
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File must be UTF-8 encoded")
    except Exception as e:
        logger.error(f"CSV upload error: {e}")
        raise HTTPException(status_code=500, detail="Failed to process CSV file")

@router.post("/{campaign_id}/items", response_model=List[BatchCallItemResponse])
async def add_call_items_to_campaign(
    campaign_id: str,
    items: List[BatchCallItemCreateRequest],
    authorization: str = Header(None, alias="Authorization")
):
    """Add call items to a batch campaign"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
    
    token = authorization.replace("Bearer ", "")
    
    try:
        # Verify token
        user_response = supabase_service_client.auth.get_user(token)
        if not user_response.user:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        user_id = user_response.user.id
        
        # Verify access to campaign
        campaign_data = await verify_user_access_to_campaign(campaign_id, user_id)
        
        # Check if campaign can be modified
        if campaign_data.get("status") in ["running", "completed", "failed"]:
            raise HTTPException(status_code=400, detail="Cannot add items to campaigns that are running, completed, or failed")
        
        # Prepare call items for insertion
        call_items_data = []
        for item in items:
            call_items_data.append({
                "batch_campaign_id": campaign_id,
                "phone_number_e164": item.phone_number_e164,
                "contact_name": item.contact_name,
                "custom_data": item.custom_data
            })
        
        # Insert call items
        response = supabase_service_client.table("batch_call_items").insert(call_items_data).execute()
        
        if not response.data:
            raise HTTPException(status_code=500, detail="Failed to add call items")
        
        created_items = [BatchCallItemResponse(**item) for item in response.data]
        
        logger.info(f"Added {len(created_items)} call items to campaign {campaign_id}")
        return created_items
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding call items to campaign {campaign_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to add call items")

@router.get("/{campaign_id}/progress", response_model=CampaignProgressResponse)
async def get_campaign_progress(
    campaign_id: str,
    authorization: str = Header(None, alias="Authorization")
):
    """Get real-time progress and analytics of a batch campaign"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
    
    token = authorization.replace("Bearer ", "")
    
    try:
        # Verify token
        try:
            user_response = supabase_service_client.auth.get_user(token)
            if not user_response.user:
                raise HTTPException(status_code=401, detail="Invalid token")
        except Exception as auth_error:
            logger.debug(f"Auth error for token: {auth_error}")
            raise HTTPException(status_code=401, detail="Invalid token")
        
        user_id = user_response.user.id
        
        # Verify access to campaign
        campaign_data = await verify_user_access_to_campaign(campaign_id, user_id)
        
        # Get call items status breakdown
        items_response = supabase_service_client.table("batch_call_items").select("status").eq("batch_campaign_id", campaign_id).execute()
        
        # Count statuses
        status_counts = {}
        for item in items_response.data or []:
            status = item.get("status", "pending")
            status_counts[status] = status_counts.get(status, 0) + 1
        
        total_numbers = campaign_data.get("total_numbers", 0)
        completed_calls = campaign_data.get("completed_calls", 0)
        successful_calls = campaign_data.get("successful_calls", 0)
        failed_calls = campaign_data.get("failed_calls", 0)
        
        pending_calls = status_counts.get("pending", 0) + status_counts.get("retrying", 0)
        calling_now = status_counts.get("calling", 0)
        
        # Calculate progress percentage
        progress_percentage = (completed_calls / total_numbers * 100) if total_numbers > 0 else 0
        
        # Estimate completion time (rough calculation)
        estimated_completion = None
        if campaign_data.get("status") == "running" and pending_calls > 0:
            # Rough estimate based on current concurrency
            concurrency = campaign_data.get("concurrency_limit", 3)
            avg_call_duration = 120  # 2 minutes average
            estimated_seconds = (pending_calls / concurrency) * avg_call_duration
            estimated_completion = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(seconds=estimated_seconds)
        
        # ===== MVP ANALYTICS ENHANCEMENT =====
        
        # Get detailed call analytics from the calls table
        # Fix column names - use the correct ones from the database
        calls_response = supabase_service_client.table("calls").select(
            "id, status, call_duration, phone_number_e164, created_at, initiated_at, answered_at, ended_at"
        ).eq("batch_campaign_id", campaign_id).execute()
        
        calls_data = calls_response.data or []
        
        # Calculate call outcomes
        call_outcomes = {
            "connected": 0,
            "voicemail": 0,
            "no_answer": 0,
            "busy": 0,
            "failed": 0
        }
        
        total_call_duration = 0
        valid_durations = []
        peak_hours = {}
        
        for call in calls_data:
            # Map call statuses to outcomes
            status = (call.get("status") or "failed").lower()
            duration = call.get("call_duration", 0) or 0
            
            if status in ["completed", "ended"]:
                if duration > 30:  # Calls over 30 seconds likely reached humans
                    call_outcomes["connected"] += 1
                elif duration > 5:  # Short calls might be voicemail
                    call_outcomes["voicemail"] += 1
                else:
                    call_outcomes["no_answer"] += 1
            elif status in ["busy"]:
                call_outcomes["busy"] += 1
            elif status in ["no_answer", "timeout"]:
                call_outcomes["no_answer"] += 1
            else:
                call_outcomes["failed"] += 1
            
            # Track call durations
            if duration > 0:
                total_call_duration += duration
                valid_durations.append(duration)
            
            # Track peak response hours
            if call.get("initiated_at") and status in ["completed", "ended"]:
                try:
                    initiated_at = datetime.fromisoformat(call["initiated_at"].replace('Z', '+00:00'))
                    hour = initiated_at.hour
                    peak_hours[hour] = peak_hours.get(hour, 0) + 1
                except:
                    pass
        
        # Calculate response rate (calls that reached humans)
        connected_calls = call_outcomes["connected"]
        response_rate = (connected_calls / total_numbers * 100) if total_numbers > 0 else 0
        
        # Calculate average call duration
        avg_call_duration = sum(valid_durations) / len(valid_durations) if valid_durations else 0
        
        # Find peak response hours (top 3)
        peak_response_hours = []
        if peak_hours:
            sorted_hours = sorted(peak_hours.items(), key=lambda x: x[1], reverse=True)[:3]
            peak_response_hours = [f"{hour:02d}:00-{hour+1:02d}:00" for hour, _ in sorted_hours]
        
        # Geographic performance (simplified - by country code)
        geographic_performance = {}
        for call in calls_data:
            phone_number = call.get("phone_number_e164", "") or ""
            if phone_number.startswith("+1"):
                country = "US/CA"
            elif phone_number.startswith("+33"):
                country = "France"
            elif phone_number.startswith("+44"):
                country = "UK"
            else:
                country = "Other"
            
            if country not in geographic_performance:
                geographic_performance[country] = {"total": 0, "connected": 0}
            
            geographic_performance[country]["total"] += 1
            if (call.get("status") or "").lower() in ["completed", "ended"] and (call.get("call_duration", 0) or 0) > 30:
                geographic_performance[country]["connected"] += 1
        
        return CampaignProgressResponse(
            campaign_id=campaign_id,
            status=campaign_data.get("status", "draft"),
            progress_percentage=round(progress_percentage, 2),
            total_numbers=total_numbers,
            completed_calls=completed_calls,
            successful_calls=successful_calls,
            failed_calls=failed_calls,
            pending_calls=pending_calls,
            calling_now=calling_now,
            estimated_completion=estimated_completion,
            created_at=campaign_data.get("created_at"),
            # MVP Analytics
            call_outcomes=call_outcomes,
            response_rate=round(response_rate, 2),
            avg_call_duration=round(avg_call_duration, 2),
            total_call_duration=round(total_call_duration, 2),
            peak_response_hours=peak_response_hours,
            geographic_performance=geographic_performance
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting campaign progress {campaign_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to get campaign progress")

@router.get("/{campaign_id}/analytics", response_model=Dict[str, Any])
async def get_campaign_analytics(
    campaign_id: str,
    authorization: str = Header(None, alias="Authorization")
):
    """Get detailed analytics for a completed or running batch campaign"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
    
    token = authorization.replace("Bearer ", "")
    
    try:
        # Verify token
        try:
            user_response = supabase_service_client.auth.get_user(token)
            if not user_response.user:
                raise HTTPException(status_code=401, detail="Invalid token")
        except Exception as auth_error:
            logger.debug(f"Auth error for token: {auth_error}")
            raise HTTPException(status_code=401, detail="Invalid token")
        
        user_id = user_response.user.id
        
        # Verify access to campaign
        campaign_data = await verify_user_access_to_campaign(campaign_id, user_id)
        
        # Get all calls for this campaign
        calls_response = supabase_service_client.table("calls").select(
            "id, status, call_duration, phone_number_e164, created_at, initiated_at, answered_at, ended_at, call_control_id"
        ).eq("batch_campaign_id", campaign_id).execute()
        
        calls_data = calls_response.data or []
        
        # Get call items for additional context
        items_response = supabase_service_client.table("batch_call_items").select(
            "id, phone_number_e164, contact_name, status, attempts, last_attempt_at, completed_at, error_message"
        ).eq("batch_campaign_id", campaign_id).execute()
        
        items_data = items_response.data or []
        
        # Detailed Analytics Calculations
        analytics = {
            "campaign_summary": {
                "campaign_id": campaign_id,
                "campaign_name": campaign_data.get("name", "Unknown"),
                "status": campaign_data.get("status", "draft"),
                "total_numbers": len(items_data),
                "total_calls_made": len(calls_data),
                "created_at": campaign_data.get("created_at"),
                "started_at": campaign_data.get("started_at"),
                "completed_at": campaign_data.get("completed_at")
            },
            
            "performance_metrics": {
                "connection_rate": 0.0,
                "answer_rate": 0.0,
                "completion_rate": 0.0,
                "avg_call_duration": 0.0,
                "avg_attempts_per_number": 0.0
            },
            
            "call_outcomes": {
                "connected_human": 0,
                "reached_voicemail": 0,
                "no_answer": 0,
                "busy_signal": 0,
                "failed_calls": 0,
                "still_calling": 0
            },
            
            "time_analysis": {
                "peak_hours": {},
                "daily_breakdown": {},
                "avg_call_duration_by_hour": {}
            },
            
            "geographic_breakdown": {},
            
            "retry_analysis": {
                "numbers_requiring_retries": 0,
                "avg_retries_per_failed_number": 0.0,
                "retry_success_rate": 0.0
            }
        }
        
        # Process calls data
        total_duration = 0
        connected_calls = 0
        completed_calls = len([c for c in calls_data if c.get("status", "").lower() in ["completed", "ended"]])
        
        for call in calls_data:
            status = (call.get("status") or "failed").lower()
            duration = call.get("call_duration", 0) or 0
            total_duration += duration
            
            # Categorize call outcomes
            if status in ["completed", "ended"]:
                if duration > 30:  # Likely human conversation
                    analytics["call_outcomes"]["connected_human"] += 1
                    connected_calls += 1
                elif duration > 5:  # Likely voicemail
                    analytics["call_outcomes"]["reached_voicemail"] += 1
                else:
                    analytics["call_outcomes"]["no_answer"] += 1
            elif status == "busy":
                analytics["call_outcomes"]["busy_signal"] += 1
            elif status == "calling":
                analytics["call_outcomes"]["still_calling"] += 1
            elif status in ["no_answer", "timeout"]:
                analytics["call_outcomes"]["no_answer"] += 1
            else:
                analytics["call_outcomes"]["failed_calls"] += 1
            
            # Time analysis
            if call.get("initiated_at"):
                try:
                    initiated_at = datetime.fromisoformat(call["initiated_at"].replace('Z', '+00:00'))
                    hour = initiated_at.hour
                    date = initiated_at.date().isoformat()
                    
                    # Peak hours
                    hour_key = f"{hour:02d}:00-{hour+1:02d}:00"
                    analytics["time_analysis"]["peak_hours"][hour_key] = analytics["time_analysis"]["peak_hours"].get(hour_key, 0) + 1
                    
                    # Daily breakdown
                    analytics["time_analysis"]["daily_breakdown"][date] = analytics["time_analysis"]["daily_breakdown"].get(date, 0) + 1
                    
                    # Average duration by hour
                    if hour_key not in analytics["time_analysis"]["avg_call_duration_by_hour"]:
                        analytics["time_analysis"]["avg_call_duration_by_hour"][hour_key] = []
                    if duration > 0:
                        analytics["time_analysis"]["avg_call_duration_by_hour"][hour_key].append(duration)
                except:
                    pass
            
            # Geographic analysis
            phone_number = call.get("phone_number_e164", "") or ""
            if phone_number.startswith("+1"):
                country = "US/CA"
            elif phone_number.startswith("+33"):
                country = "France"
            elif phone_number.startswith("+44"):
                country = "UK"
            else:
                country = "Other"
            
            if country not in analytics["geographic_breakdown"]:
                analytics["geographic_breakdown"][country] = {
                    "total_calls": 0,
                    "connected": 0,
                    "avg_duration": 0.0,
                    "durations": []
                }
            
            analytics["geographic_breakdown"][country]["total_calls"] += 1
            if status in ["completed", "ended"] and duration > 30:
                analytics["geographic_breakdown"][country]["connected"] += 1
            if duration > 0:
                analytics["geographic_breakdown"][country]["durations"].append(duration)
        
        # Calculate performance metrics
        total_numbers = len(items_data)
        total_calls = len(calls_data)
        
        if total_numbers > 0:
            analytics["performance_metrics"]["connection_rate"] = round((connected_calls / total_numbers) * 100, 2)
            analytics["performance_metrics"]["completion_rate"] = round((completed_calls / total_numbers) * 100, 2)
        
        if total_calls > 0:
            analytics["performance_metrics"]["avg_call_duration"] = round(total_duration / total_calls, 2)
            analytics["performance_metrics"]["answer_rate"] = round(((connected_calls + analytics["call_outcomes"]["reached_voicemail"]) / total_calls) * 100, 2)
        
        # Calculate average attempts
        total_attempts = sum(item.get("attempts", 1) for item in items_data)
        if total_numbers > 0:
            analytics["performance_metrics"]["avg_attempts_per_number"] = round(total_attempts / total_numbers, 2)
        
        # Calculate average durations by hour
        for hour_key, durations in analytics["time_analysis"]["avg_call_duration_by_hour"].items():
            if durations:
                analytics["time_analysis"]["avg_call_duration_by_hour"][hour_key] = round(sum(durations) / len(durations), 2)
            else:
                analytics["time_analysis"]["avg_call_duration_by_hour"][hour_key] = 0.0
        
        # Calculate geographic averages
        for country_data in analytics["geographic_breakdown"].values():
            if country_data["durations"]:
                country_data["avg_duration"] = round(sum(country_data["durations"]) / len(country_data["durations"]), 2)
            del country_data["durations"]  # Remove raw data from response
        
        # Retry analysis
        retry_items = [item for item in items_data if item.get("attempts", 1) > 1]
        analytics["retry_analysis"]["numbers_requiring_retries"] = len(retry_items)
        
        if retry_items:
            total_retry_attempts = sum(item.get("attempts", 1) - 1 for item in retry_items)
            analytics["retry_analysis"]["avg_retries_per_failed_number"] = round(total_retry_attempts / len(retry_items), 2)
            
            successful_after_retry = len([item for item in retry_items if item.get("status") == "completed"])
            analytics["retry_analysis"]["retry_success_rate"] = round((successful_after_retry / len(retry_items)) * 100, 2)
        
        return analytics
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting campaign analytics {campaign_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to get campaign analytics")

@router.get("/{campaign_id}/items", response_model=List[BatchCallItemResponse])
async def get_campaign_call_items(
    campaign_id: str,
    authorization: str = Header(None, alias="Authorization"),
    status_filter: Optional[str] = None,
    limit: int = 100,
    offset: int = 0
):
    """Get call items for a batch campaign"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
    
    token = authorization.replace("Bearer ", "")
    
    try:
        # Verify token
        try:
            user_response = supabase_service_client.auth.get_user(token)
            if not user_response.user:
                raise HTTPException(status_code=401, detail="Invalid token")
        except Exception as auth_error:
            logger.debug(f"Auth error for token: {auth_error}")
            raise HTTPException(status_code=401, detail="Invalid token")
        
        user_id = user_response.user.id
        
        # Verify access to campaign
        await verify_user_access_to_campaign(campaign_id, user_id)
        
        # Build query for call items
        query = supabase_service_client.table("batch_call_items").select(
            "id, batch_campaign_id, phone_number_e164, contact_name, custom_data, status, call_id, attempts, last_attempt_at, completed_at, error_message, created_at, updated_at"
        ).eq("batch_campaign_id", campaign_id)
        
        if status_filter:
            query = query.eq("status", status_filter)
        
        query = query.order("created_at", desc=False).range(offset, offset + limit - 1)
        
        response = query.execute()
        
        call_items = [BatchCallItemResponse(**item) for item in response.data or []]
        
        logger.info(f"Retrieved {len(call_items)} call items for campaign {campaign_id}")
        return call_items
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting call items for campaign {campaign_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to get call items")

@router.post("/check-completions")
async def trigger_campaign_completion_check(
    authorization: str = Header(None, alias="Authorization")
):
    """Manually trigger completion check for all running campaigns (for troubleshooting)"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
    
    try:
        await check_and_complete_finished_campaigns()
        return {"message": "Campaign completion check triggered successfully"}
        
    except Exception as e:
        logger.error(f"Error triggering campaign completion check: {e}")
        raise HTTPException(status_code=500, detail="Failed to trigger completion check")

async def update_batch_call_item_from_call_status(call_id: str, call_status: str, call_duration: Optional[int] = None):
    """Update batch call item status based on call completion"""
    try:
        # Get the call to find the associated batch call item
        call_response = supabase_service_client.table("calls").select(
            "id, batch_call_item_id, batch_campaign_id, status, call_duration"
        ).eq("id", call_id).single().execute()
        
        if not call_response.data:
            logger.debug(f"Call {call_id} not found or not a batch call")
            return
        
        call_data = call_response.data
        batch_call_item_id = call_data.get("batch_call_item_id")
        batch_campaign_id = call_data.get("batch_campaign_id")
        
        if not batch_call_item_id or not batch_campaign_id:
            logger.debug(f"Call {call_id} is not associated with a batch campaign")
            return
        
        # Map call status to batch call item status
        if call_status.lower() in ["completed", "ended"]:
            item_status = "completed"
        elif call_status.lower() in ["failed", "busy", "no_answer", "timeout"]:
            item_status = "failed"
        else:
            # Don't update for intermediate statuses like "calling"
            return
        
        # Update the batch call item
        update_data = {
            "status": item_status,
            "completed_at": datetime.now(timezone.utc).isoformat()
        }
        
        # If the call failed, we might want to retry
        if item_status == "failed":
            # Get current attempts
            item_response = supabase_service_client.table("batch_call_items").select(
                "attempts, batch_campaign_id"
            ).eq("id", batch_call_item_id).single().execute()
            
            if item_response.data:
                current_attempts = item_response.data.get("attempts", 1)
                
                # Get campaign retry settings
                campaign_response = supabase_service_client.table("batch_campaigns").select(
                    "retry_failed, max_retries"
                ).eq("id", batch_campaign_id).single().execute()
                
                if campaign_response.data:
                    retry_failed = campaign_response.data.get("retry_failed", False)
                    max_retries = campaign_response.data.get("max_retries", 2)
                    
                    if retry_failed and current_attempts < max_retries + 1:
                        # Set to retry instead of failed
                        item_status = "pending"  # Will be retried
                        update_data["status"] = "pending"
                        update_data["attempts"] = current_attempts + 1
                        del update_data["completed_at"]  # Don't mark as completed if retrying
        
        # Update the batch call item
        supabase_service_client.table("batch_call_items").update(update_data).eq("id", batch_call_item_id).execute()
        
        logger.info(f"Updated batch call item {batch_call_item_id} to status '{item_status}' for call {call_id}")
        
        # Trigger a check to see if the campaign should be completed
        if item_status in ["completed", "failed"]:
            await check_specific_campaign_completion(batch_campaign_id)
            
    except Exception as e:
        logger.error(f"Error updating batch call item for call {call_id}: {e}")

async def check_specific_campaign_completion(campaign_id: str):
    """Check if a specific campaign should be marked as completed"""
    try:
        # Get campaign status
        campaign_response = supabase_service_client.table("batch_campaigns").select("status").eq("id", campaign_id).single().execute()
        
        if not campaign_response.data or campaign_response.data.get("status") != "running":
            return
        
        # Get call items for this campaign
        items_response = supabase_service_client.table("batch_call_items").select("id, status").eq("batch_campaign_id", campaign_id).execute()
        call_items = items_response.data or []
        
        if not call_items:
            return
        
        # Check if all items are in a final state
        final_statuses = {"completed", "failed", "cancelled"}
        pending_statuses = {"pending", "calling", "retrying"}
        
        total_items = len(call_items)
        final_items = len([item for item in call_items if item.get("status") in final_statuses])
        pending_items = len([item for item in call_items if item.get("status") in pending_statuses])
        
        logger.debug(f"Campaign {campaign_id}: {final_items}/{total_items} items finished, {pending_items} pending")
        
        # If all items are in final state, mark campaign as completed
        if final_items == total_items and pending_items == 0:
            logger.info(f"All items finished for campaign {campaign_id}, marking as completed")
            await mark_campaign_completed(campaign_id)
            
    except Exception as e:
        logger.error(f"Error checking specific campaign completion for {campaign_id}: {e}") 