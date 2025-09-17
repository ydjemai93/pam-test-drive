"""
User Management Routes

Handles user profile, settings, and phone number management.
"""
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime

from fastapi import APIRouter, HTTPException, status, Header
from pydantic import BaseModel

from ..config import get_user_id_from_token
from ..db_client import supabase_service_client

# Set up logging
logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/users", tags=["users"])

# --- Pydantic Models ---

class UserSettingsUpdateRequest(BaseModel):
    name: Optional[str] = None
    company: Optional[str] = None
    timezone: Optional[str] = None
    language: Optional[str] = None
    emailNotifications: Optional[bool] = None
    callNotifications: Optional[bool] = None
    marketingEmails: Optional[bool] = None
    twoFactorAuth: Optional[bool] = None

# --- Route Endpoints ---

@router.get("/settings", summary="Get user settings")
async def get_user_settings(authorization: str = Header(None, alias="Authorization")):
    """
    Get current user's settings and profile information
    """
    user_id = get_user_id_from_token(authorization)
    
    try:
        # Get user profile from public.users
        response = supabase_service_client.table("users").select("*").eq("id", user_id).single().execute()
        
        if response.data:
            user_data = response.data
            
            # Return settings with default values for missing fields
            settings = {
                "id": user_data.get("id"),
                "email": user_data.get("email"),
                "name": user_data.get("name", ""),
                "company": user_data.get("company", ""),
                "timezone": user_data.get("timezone", "UTC"),
                "language": user_data.get("language", "en"),
                "emailNotifications": user_data.get("email_notifications", True),
                "callNotifications": user_data.get("call_notifications", True),
                "marketingEmails": user_data.get("marketing_emails", False),
                "twoFactorAuth": user_data.get("two_factor_auth", False),
                "created_at": user_data.get("created_at"),
                "updated_at": user_data.get("updated_at")
            }
            
            return {"settings": settings}
        else:
            logger.error(f"User settings not found for ID: {user_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching user settings: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch user settings"
        )

@router.patch("/settings", summary="Update user settings")
async def update_user_settings(
    request: UserSettingsUpdateRequest, 
    authorization: str = Header(None, alias="Authorization")
):
    """
    Update user settings and profile information
    """
    user_id = get_user_id_from_token(authorization)
    
    # Prepare update data (only include non-None values)
    update_data = {}
    
    # Map request fields to database fields
    field_mapping = {
        "name": "name",
        "company": "company", 
        "timezone": "timezone",
        "language": "language",
        "emailNotifications": "email_notifications",
        "callNotifications": "call_notifications",
        "marketingEmails": "marketing_emails",
        "twoFactorAuth": "two_factor_auth"
    }
    
    for request_field, db_field in field_mapping.items():
        value = getattr(request, request_field)
        if value is not None:
            update_data[db_field] = value
    
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields provided for update"
        )
    
    update_data["updated_at"] = datetime.utcnow().isoformat()
    
    try:
        response = supabase_service_client.table("users").update(update_data).eq("id", user_id).execute()
        
        if response.data:
            logger.info(f"User settings updated successfully for user {user_id}")
            return {
                "message": "Settings updated successfully",
                "user": response.data[0]
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating user settings: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update settings: {str(e)}"
        )

@router.get("/phone-numbers", summary="Get user's phone numbers")
async def get_phone_numbers(authorization: str = Header(None, alias="Authorization")):
    """
    Get phone numbers associated with the user
    """
    user_id = get_user_id_from_token(authorization)
    
    try:
        response = supabase_service_client.table("phone_numbers").select("*").eq("user_id", user_id).execute()
        
        if response.data:
            return {"phone_numbers": response.data}
        else:
            return {"phone_numbers": []}
            
    except Exception as e:
        logger.error(f"Error fetching phone numbers for user {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch phone numbers"
        ) 