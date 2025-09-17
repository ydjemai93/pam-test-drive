"""
Authentication Routes

Handles all authentication-related endpoints including login,
signup, and user management.
"""
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, status, Header
from pydantic import BaseModel
import httpx

from ..config import get_user_id_from_token
from ..db_client import supabase_service_client

# Set up logging
logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/auth", tags=["auth"])

# --- Pydantic Models ---

class UserCreateRequest(BaseModel):
    email: str
    name: str | None = None
    auth_user_id: str | None = None

class UserSignupRequest(BaseModel):
    email: str
    password: str
    name: str | None = None

class UserLoginRequest(BaseModel):
    email: str
    password: str

# --- Route Endpoints ---

@router.post("/signup", status_code=status.HTTP_201_CREATED, summary="Sign up new user")
async def auth_signup(request: UserSignupRequest):
    """
    Sign up a new user using Supabase Auth
    """
    try:
        # Sign up user with Supabase Auth
        auth_response = supabase_service_client.auth.sign_up({
            "email": request.email,
            "password": request.password
        })
        
        if auth_response.user:
            auth_user_id = auth_response.user.id
            logger.info(f"User signed up successfully in Supabase Auth with ID: {auth_user_id}")
            
            # Create user profile in public.users table
            user_data = {
                "id": auth_user_id,  # Use the same ID from auth.users
                "email": request.email,
                "name": request.name or request.email.split('@')[0]  # Default name from email
            }
            
            try:
                profile_response = supabase_service_client.table("users").insert(user_data).execute()
                
                if profile_response.data:
                    logger.info(f"User profile created successfully: {profile_response.data[0]}")
                    
                    return {
                        "message": "User created successfully",
                        "user": profile_response.data[0],
                        "auth_user_id": auth_user_id
                    }
                else:
                    logger.error(f"Failed to create user profile: {profile_response}")
                    # Still return success since auth user was created
                    return {
                        "message": "User created successfully but profile creation failed",
                        "auth_user_id": auth_user_id
                    }
                    
            except Exception as profile_e:
                logger.error(f"Error creating user profile: {profile_e}")
                # Still return success since auth user was created
                return {
                    "message": "User created successfully but profile creation failed",
                    "auth_user_id": auth_user_id,
                    "profile_error": str(profile_e)
                }
        else:
            logger.error(f"Failed to sign up user: {auth_response}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to create user account"
            )
            
    except Exception as e:
        logger.error(f"Signup error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Signup failed: {str(e)}"
        )

@router.post("/login", summary="User login")
async def auth_login(request: UserLoginRequest):
    """
    Authenticate user with Supabase Auth
    """
    try:
        # Authenticate with Supabase
        auth_response = supabase_service_client.auth.sign_in_with_password({
            "email": request.email,
            "password": request.password
        })
        
        if auth_response.user and auth_response.session:
            user_id = auth_response.user.id
            access_token = auth_response.session.access_token
            
            logger.info(f"User {request.email} logged in successfully")
            
            # Get user profile from public.users
            try:
                profile_response = supabase_service_client.table("users").select("*").eq("id", user_id).single().execute()
                user_profile = profile_response.data if profile_response.data else {}
            except Exception as profile_e:
                logger.warning(f"Could not fetch user profile: {profile_e}")
                user_profile = {}
            
            return {
                "message": "Login successful",
                "authToken": access_token,  # Frontend expects authToken field
                "access_token": access_token,  # Keep for backward compatibility
                "user": {
                    "id": user_id,
                    "email": auth_response.user.email,
                    **user_profile
                }
            }
        else:
            logger.warning(f"Login failed for {request.email}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Login failed"
        )

@router.get("/me", summary="Get current user info")
async def get_current_user(authorization: str = Header(None, alias="Authorization")):
    """
    Get current user information from token
    """
    user_id = get_user_id_from_token(authorization)
    
    try:
        # Get user profile from public.users
        response = supabase_service_client.table("users").select("*").eq("id", user_id).single().execute()
        
        if response.data:
            return {
                "user": response.data
            }
        else:
            logger.error(f"User profile not found for ID: {user_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User profile not found"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching user profile: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch user profile"
        )

# Additional route for creating users directly (for admin/system use)
@router.post("/users", status_code=status.HTTP_201_CREATED, summary="Create user directly")
async def create_user_in_public_users(request: UserCreateRequest):
    """
    Create a user directly in the public.users table (admin/system use)
    """
    try:
        user_data = {
            "email": request.email,
            "name": request.name
        }
        
        if request.auth_user_id:
            user_data["id"] = request.auth_user_id
        
        response = supabase_service_client.table("users").insert(user_data).execute()
        
        if response.data:
            logger.info(f"User created successfully: {response.data[0]}")
            return response.data[0]
        else:
            logger.error("Failed to create user - no data returned")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create user"
            )
            
    except Exception as e:
        logger.error(f"Error creating user: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create user: {str(e)}"
        ) 