# File: MARK_I/backend_python/api/webhook_tools_routes.py

import asyncio
import httpx
import json
import logging
import uuid
import time
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any, Union
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, status, Header, BackgroundTasks
from pydantic import BaseModel, Field, validator, HttpUrl
import jsonschema
from jsonschema import validate, ValidationError

from api.config import get_user_id_from_token
from api.db_client import supabase_service_client
from api.webhook_executor import execute_webhook_with_logging

logger = logging.getLogger(__name__)

class WebhookCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="Webhook name")
    description: Optional[str] = Field(None, description="Webhook description")
    webhook_url: HttpUrl = Field(..., description="Webhook URL (must be HTTPS)")
    webhook_method: str = Field("POST", description="HTTP method")
    webhook_headers: Dict[str, str] = Field(default_factory=dict, description="Request headers")
    webhook_timeout_ms: int = Field(5000, ge=1000, le=30000, description="Request timeout in milliseconds")
    parameter_schema: Dict[str, Any] = Field(default_factory=dict, description="JSON schema for parameters")
    response_schema: Dict[str, Any] = Field(default_factory=dict, description="Expected response schema")
    requires_confirmation: bool = Field(False, description="Require agent confirmation")
    allowed_agents: List[str] = Field(default_factory=list, description="Agent UUIDs (empty = all agents)")
    json_body: Optional[str] = Field(None, description="JSON body template for webhook requests")

    @validator('webhook_method')
    def validate_method(cls, v):
        allowed_methods = ['GET', 'POST', 'PUT', 'DELETE', 'PATCH']
        if v.upper() not in allowed_methods:
            raise ValueError(f'Method must be one of: {allowed_methods}')
        return v.upper()

    @validator('webhook_url')
    def validate_https(cls, v):
        if not str(v).startswith('https://'):
            raise ValueError('Webhook URL must use HTTPS')
        return v
    
    @validator('parameter_schema')
    def validate_parameter_schema(cls, v):
        if v:
            try:
                jsonschema.Draft7Validator.check_schema(v)
            except jsonschema.SchemaError as e:
                raise ValueError(f'Invalid parameter schema: {e.message}')
        return v

    @validator('json_body')
    def validate_json_body(cls, v):
        if v and v.strip():
            try:
                json.loads(v)
            except json.JSONDecodeError as e:
                raise ValueError(f'Invalid JSON body: {e.msg}')
        return v

class WebhookUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    webhook_url: Optional[HttpUrl] = None
    webhook_method: Optional[str] = None
    webhook_headers: Optional[Dict[str, str]] = None
    webhook_timeout_ms: Optional[int] = Field(None, ge=1000, le=30000)
    parameter_schema: Optional[Dict[str, Any]] = None
    response_schema: Optional[Dict[str, Any]] = None
    is_enabled: Optional[bool] = None
    requires_confirmation: Optional[bool] = None
    allowed_agents: Optional[List[str]] = None
    json_body: Optional[str] = None

class WebhookResponse(BaseModel):
    id: str
    user_id: str
    name: str
    description: Optional[str]
    webhook_url: str
    webhook_method: str
    webhook_headers: Dict[str, str]
    webhook_timeout_ms: int
    parameter_schema: Dict[str, Any]
    response_schema: Dict[str, Any]
    is_enabled: bool
    requires_confirmation: bool
    allowed_agents: List[str]
    usage_count: int
    last_used_at: Optional[datetime]
    json_body: Optional[str]
    created_at: datetime
    updated_at: datetime

class WebhookExecutionRequest(BaseModel):
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Execution parameters")
    mock_context: Optional[Dict[str, Any]] = Field(None, description="Mock call context for testing")

class WebhookExecutionResponse(BaseModel):
    id: str
    webhook_id: str
    execution_status: str
    execution_time_ms: Optional[int]
    http_status_code: Optional[int]
    webhook_response: Dict[str, Any]
    error_message: Optional[str]
    created_at: datetime
    completed_at: Optional[datetime]

class WebhookTestRequest(BaseModel):
    parameters: Dict[str, Any] = Field(default_factory=dict)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

# Supabase client is imported directly from db_client

async def safe_background_task_wrapper(func, *args, **kwargs):
    """Wrapper for background tasks to ensure proper error handling"""
    try:
        logger.info(f"Starting background task: {func.__name__}")
        result = await func(*args, **kwargs)
        logger.info(f"Background task completed successfully: {func.__name__}")
        return result
    except Exception as e:
        logger.error(f"Background task {func.__name__} failed: {e}", exc_info=True)
        # Don't re-raise the exception to prevent crashing the background task system
        return None

async def validate_webhook_url(url: str) -> bool:
    """Validate webhook URL accessibility"""
    try:
        parsed = urlparse(url)
        if parsed.scheme != 'https':
            raise ValueError("Webhook URL must use HTTPS")
        
        # Optional: Test URL accessibility
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.head(url)
            return True
    except Exception as e:
        logger.warning(f"Webhook URL validation failed for {url}: {e}")
        return False

def sanitize_webhook_headers(headers: Dict[str, str]) -> Dict[str, str]:
    """Sanitize and validate webhook headers"""
    sanitized = {}
    forbidden_headers = ['host', 'content-length', 'connection']
    
    for key, value in headers.items():
        if key.lower() not in forbidden_headers:
            sanitized[key] = str(value)[:1000]  # Limit header value length
    
    return sanitized

@router.post("/", response_model=WebhookResponse, status_code=status.HTTP_201_CREATED)
async def create_webhook(
    request: WebhookCreateRequest,
    authorization: str = Header(None, alias="Authorization")
):
    """Create a new webhook"""
    user_id = get_user_id_from_token(authorization)
    
    # Check for duplicate webhook name
    existing_webhook = supabase_service_client.table("webhooks").select("id").eq("user_id", user_id).eq("name", request.name).execute()
    if existing_webhook.data:
        raise HTTPException(status_code=400, detail="Webhook name already exists")
    
    # Sanitize headers
    sanitized_headers = sanitize_webhook_headers(request.webhook_headers)
    
    # Create webhook record
    webhook_data = {
        "user_id": user_id,
        "name": request.name,
        "description": request.description,
        "webhook_url": str(request.webhook_url),
        "webhook_method": request.webhook_method,
        "webhook_headers": sanitized_headers,
        "webhook_timeout_ms": request.webhook_timeout_ms,
        "parameter_schema": request.parameter_schema,
        "response_schema": request.response_schema,
        "requires_confirmation": request.requires_confirmation,
        "allowed_agents": request.allowed_agents,
        "json_body": request.json_body,
    }
    
    result = supabase_service_client.table("webhooks").insert(webhook_data).execute()
    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to create webhook")
    
    return WebhookResponse(**result.data[0])

@router.get("/", response_model=List[WebhookResponse])
async def list_webhooks(
    authorization: str = Header(None, alias="Authorization"),
    enabled_only: Optional[bool] = None,
    limit: int = 50,
    offset: int = 0
):
    """List user's webhooks"""
    user_id = get_user_id_from_token(authorization)
    
    query = supabase_service_client.table("webhooks").select("*").eq("user_id", user_id)
    
    if enabled_only is not None:
        query = query.eq("is_enabled", enabled_only)
    
    result = query.order("created_at", desc=True).range(offset, offset + limit - 1).execute()
    
    return [WebhookResponse(**webhook) for webhook in result.data]

@router.get("/{webhook_id}", response_model=WebhookResponse)
async def get_webhook(
    webhook_id: str,
    authorization: str = Header(None, alias="Authorization")
):
    """Get webhook details"""
    user_id = get_user_id_from_token(authorization)
    
    result = supabase_service_client.table("webhooks").select("*").eq("id", webhook_id).eq("user_id", user_id).single().execute()
    
    if not result.data:
        raise HTTPException(status_code=404, detail="Webhook not found")
    
    return WebhookResponse(**result.data)

@router.patch("/{webhook_id}", response_model=WebhookResponse)
async def update_webhook(
    webhook_id: str,
    request: WebhookUpdateRequest,
    authorization: str = Header(None, alias="Authorization")
):
    """Update webhook configuration"""
    user_id = get_user_id_from_token(authorization)
    
    # Verify webhook ownership
    webhook = supabase_service_client.table("webhooks").select("*").eq("id", webhook_id).eq("user_id", user_id).single().execute()
    if not webhook.data:
        raise HTTPException(status_code=404, detail="Webhook not found")
    
    # Prepare update data
    update_data = {}
    for field, value in request.dict(exclude_unset=True).items():
        if value is not None:
            if field == "webhook_headers":
                update_data[field] = sanitize_webhook_headers(value)
            elif field == "webhook_url":
                update_data[field] = str(value)
            else:
                update_data[field] = value
    
    if not update_data:
        return WebhookResponse(**webhook.data)
    
    # Check name uniqueness if name is being updated
    if 'name' in update_data:
        existing = supabase_service_client.table("webhooks").select("id").eq("user_id", user_id).eq("name", update_data['name']).neq("id", webhook_id).execute()
        if existing.data:
            raise HTTPException(status_code=400, detail="Webhook name already exists")
    
    # Update webhook
    result = supabase_service_client.table("webhooks").update(update_data).eq("id", webhook_id).execute()
    
    return WebhookResponse(**result.data[0])

@router.delete("/{webhook_id}")
async def delete_webhook(
    webhook_id: str,
    authorization: str = Header(None, alias="Authorization")
):
    """Delete a webhook"""
    user_id = get_user_id_from_token(authorization)
    
    # Verify webhook ownership and delete
    result = supabase_service_client.table("webhooks").delete().eq("id", webhook_id).eq("user_id", user_id).execute()
    
    if not result.data:
        raise HTTPException(status_code=404, detail="Webhook not found")
    
    return {"message": "Webhook deleted successfully"}

@router.post("/{webhook_id}/test", response_model=Dict[str, str])
async def test_webhook(
    webhook_id: str,
    request: WebhookTestRequest,
    authorization: str = Header(None, alias="Authorization"),
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    """Test webhook execution with mock data"""
    user_id = get_user_id_from_token(authorization)
    
    # Get webhook details
    webhook_result = supabase_service_client.table("webhooks").select("*").eq("id", webhook_id).eq("user_id", user_id).single().execute()
    if not webhook_result.data:
        raise HTTPException(status_code=404, detail="Webhook not found")
    
    webhook = webhook_result.data
    
    # Validate parameters against schema
    if webhook['parameter_schema']:
        try:
            validate(instance=request.parameters, schema=webhook['parameter_schema'])
        except ValidationError as e:
            raise HTTPException(status_code=400, detail=f"Parameter validation failed: {e.message}")
    
    # Execute webhook in background with safe wrapper
    execution_id = str(uuid.uuid4())
    background_tasks.add_task(
        safe_background_task_wrapper,
        execute_webhook_with_logging,
        execution_id,
        webhook,
        request.parameters,
        {},  # Empty call context for webhook testing
        is_test=True
    )
    
    return {"execution_id": execution_id, "status": "started"}

@router.post("/{webhook_id}/execute", response_model=Dict[str, str])
async def execute_webhook(
    webhook_id: str,
    request: WebhookExecutionRequest,
    authorization: str = Header(None, alias="Authorization"),
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    """Execute webhook in production context"""
    user_id = get_user_id_from_token(authorization)
    
    # Get webhook details
    webhook_result = supabase_service_client.table("webhooks").select("*").eq("id", webhook_id).eq("user_id", user_id).single().execute()
    if not webhook_result.data:
        raise HTTPException(status_code=404, detail="Webhook not found")
    
    webhook = webhook_result.data
    
    if not webhook['is_enabled']:
        raise HTTPException(status_code=400, detail="Webhook is disabled")
    
    # Execute webhook with safe wrapper
    execution_id = str(uuid.uuid4())
    background_tasks.add_task(
        safe_background_task_wrapper,
        execute_webhook_with_logging,
        execution_id,
        webhook,
        request.parameters,
        request.mock_context or {},
        is_test=False
    )
    
    return {"execution_id": execution_id, "status": "started"}

@router.get("/{webhook_id}/executions", response_model=List[WebhookExecutionResponse])
async def get_webhook_executions(
    webhook_id: str,
    authorization: str = Header(None, alias="Authorization"),
    status_filter: Optional[str] = None,
    limit: int = 50,
    offset: int = 0
):
    """Get webhook execution history"""
    user_id = get_user_id_from_token(authorization)
    
    # Verify webhook ownership
    webhook = supabase_service_client.table("webhooks").select("id").eq("id", webhook_id).eq("user_id", user_id).single().execute()
    if not webhook.data:
        raise HTTPException(status_code=404, detail="Webhook not found")
    
    query = supabase_service_client.table("webhook_executions").select("*").eq("webhook_id", webhook_id)
    
    if status_filter:
        query = query.eq("execution_status", status_filter)
    
    result = query.order("created_at", desc=True).range(offset, offset + limit - 1).execute()
    
    return [WebhookExecutionResponse(**execution) for execution in result.data]

@router.get("/analytics/usage")
async def get_webhooks_usage_analytics(
    authorization: str = Header(None, alias="Authorization"),
    days: int = 30
):
    """Get webhooks usage analytics"""
    user_id = get_user_id_from_token(authorization)
    
    # Get usage statistics
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=days)
    
    # Get user's webhooks
    user_webhooks = supabase_service_client.table("webhooks").select("id").eq("user_id", user_id).execute()
    user_webhook_ids = [webhook["id"] for webhook in user_webhooks.data]
    
    if not user_webhook_ids:
        return {
            "period_days": days,
            "total_executions": 0,
            "webhooks_stats": {}
        }
    
    # Webhook execution stats  
    execution_stats = supabase_service_client.table("webhook_executions").select(
        "webhook_id, execution_status, created_at"
    ).in_("webhook_id", user_webhook_ids).gte("created_at", start_date.isoformat()).execute()
    
    # Process stats by webhook
    stats_by_webhook = {}
    for execution in execution_stats.data:
        webhook_id = execution["webhook_id"]
        if webhook_id not in stats_by_webhook:
            stats_by_webhook[webhook_id] = {"total": 0, "success": 0, "failed": 0}
        
        stats_by_webhook[webhook_id]["total"] += 1
        if execution["execution_status"] == "success":
            stats_by_webhook[webhook_id]["success"] += 1
        else:
            stats_by_webhook[webhook_id]["failed"] += 1
    
    return {
        "period_days": days,
        "total_executions": len(execution_stats.data),
        "webhooks_stats": stats_by_webhook
    }

# Agent webhooks management endpoints
@router.get("/agents/{agent_id}/webhooks", response_model=List[WebhookResponse])
async def get_agent_webhooks(
    agent_id: str,
    authorization: str = Header(None, alias="Authorization")
):
    """Get webhooks available to a specific agent"""
    user_id = get_user_id_from_token(authorization)
    
    # Get all enabled webhooks for user
    result = supabase_service_client.table("webhooks").select("*").eq("user_id", user_id).eq("is_enabled", True).execute()
    
    available_webhooks = []
    for webhook in result.data:
        # Check if webhook is allowed for this agent
        allowed_agents = webhook.get("allowed_agents", [])
        if not allowed_agents or agent_id in allowed_agents:
            available_webhooks.append(WebhookResponse(**webhook))
    
    return available_webhooks

@router.post("/agents/{agent_id}/webhooks")
async def assign_webhooks_to_agent(
    agent_id: str,
    webhook_ids: List[str],
    authorization: str = Header(None, alias="Authorization")
):
    """Assign specific webhooks to an agent"""
    user_id = get_user_id_from_token(authorization)
    
    # Verify agent ownership (if agent exists in agents table)
    try:
        agent = supabase_service_client.table("agents").select("id").eq("id", agent_id).eq("user_id", user_id).single().execute()
        if not agent.data:
            raise HTTPException(status_code=404, detail="Agent not found")
    except:
        # If agent doesn't exist or there's an error, continue anyway
        pass
    
    # Update webhooks to include this agent
    for webhook_id in webhook_ids:
        webhook = supabase_service_client.table("webhooks").select("allowed_agents").eq("id", webhook_id).eq("user_id", user_id).single().execute()
        if webhook.data:
            current_agents = webhook.data.get("allowed_agents", [])
            if agent_id not in current_agents:
                current_agents.append(agent_id)
                supabase_service_client.table("webhooks").update({"allowed_agents": current_agents}).eq("id", webhook_id).execute()
    
    return {"message": "Webhooks assigned successfully"}

@router.delete("/agents/{agent_id}/webhooks/{webhook_id}")
async def remove_webhook_from_agent(
    agent_id: str,
    webhook_id: str,
    authorization: str = Header(None, alias="Authorization")
):
    """Remove webhook from agent"""
    user_id = get_user_id_from_token(authorization)
    
    # Get webhook and update allowed_agents
    webhook = supabase_service_client.table("webhooks").select("allowed_agents").eq("id", webhook_id).eq("user_id", user_id).single().execute()
    if not webhook.data:
        raise HTTPException(status_code=404, detail="Webhook not found")
    
    current_agents = webhook.data.get("allowed_agents", [])
    if agent_id in current_agents:
        current_agents.remove(agent_id)
        supabase_service_client.table("webhooks").update({"allowed_agents": current_agents}).eq("id", webhook_id).execute()
    
    return {"message": "Webhook removed from agent successfully"} 

@router.get("/executions/{execution_id}", response_model=WebhookExecutionResponse)
async def get_execution_result(
    execution_id: str,
    authorization: str = Header(None, alias="Authorization")
):
    """Get execution result by execution ID"""
    try:
        logger.info(f"Getting execution result for ID: {execution_id}")
        user_id = get_user_id_from_token(authorization)
        logger.info(f"User ID: {user_id}")
        
        # Get execution result
        logger.info(f"Querying webhook_executions table for execution_id: {execution_id}")
        result = supabase_service_client.table("webhook_executions").select("*").eq("id", execution_id).single().execute()
        
        logger.info(f"Query result: {result}")
        
        if not result.data:
            logger.warning(f"Execution not found: {execution_id}")
            raise HTTPException(status_code=404, detail="Execution not found")
        
        execution_data = result.data
        logger.info(f"Found execution data: {execution_data}")
        
        # Verify user has access to this execution (check via webhook ownership)
        webhook_id = execution_data["webhook_id"]
        logger.info(f"Checking webhook ownership for webhook_id: {webhook_id}")
        
        webhook_result = supabase_service_client.table("webhooks").select("user_id").eq("id", webhook_id).single().execute()
        logger.info(f"Webhook ownership query result: {webhook_result}")
        
        if not webhook_result.data or webhook_result.data["user_id"] != user_id:
            logger.warning(f"User {user_id} does not have access to webhook {webhook_id}")
            raise HTTPException(status_code=404, detail="Execution not found")
        
        logger.info("Creating ToolExecutionResponse...")
        
        # Handle datetime fields properly to prevent serialization issues
        processed_data = execution_data.copy()
        
        # Parse datetime strings if they come as strings from the database
        if isinstance(processed_data.get("created_at"), str):
            try:
                processed_data["created_at"] = datetime.fromisoformat(processed_data["created_at"].replace('Z', '+00:00'))
            except (ValueError, AttributeError) as e:
                logger.warning(f"Error parsing created_at datetime: {e}")
                
        if processed_data.get("completed_at") and isinstance(processed_data.get("completed_at"), str):
            try:
                processed_data["completed_at"] = datetime.fromisoformat(processed_data["completed_at"].replace('Z', '+00:00'))
            except (ValueError, AttributeError) as e:
                logger.warning(f"Error parsing completed_at datetime: {e}")
                processed_data["completed_at"] = None
        
        # Ensure required fields have safe defaults
        processed_data.setdefault("execution_status", "unknown")
        processed_data.setdefault("webhook_response", {})
        
        response = WebhookExecutionResponse(**processed_data)
        logger.info(f"Response created successfully: {response}")
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in get_execution_result: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}") 