'''
Configuration partagée pour l'application API.
'''
import os
import logging
from pydantic import BaseModel as PydanticBaseModel
# from typing import Optional # Optional not used after Xano removal
from pathlib import Path
from dotenv import load_dotenv
from fastapi import HTTPException, status

# Logger spécifique pour le chargement des .env et la configuration
logger_config = logging.getLogger(__name__ + ".config_loader") 
# logging.basicConfig(level=logging.INFO) # BasicConfig is usually called once at app startup in main.py

# Load environment variables from the outbound directory .env.local file
# config.py is in 'MARK_I/backend_python/api/'
# We need to go to the outbound directory
script_dir = Path(__file__).parent  # api directory
outbound_dir = script_dir.parent / "outbound"  # outbound directory
env_file = outbound_dir / '.env.local'

print(f"[CONFIG DEBUG] Attempting to load .env.local from: {env_file}")
print(f"[CONFIG DEBUG] File exists: {env_file.exists()}")

loaded = load_dotenv(env_file, encoding='utf-8', override=True)
if loaded:
    print(f"[CONFIG DEBUG] Successfully loaded: {env_file}")
else:
    print(f"[CONFIG DEBUG] Failed to load or file not found: {env_file}")

# Debug: Check what Supabase environment variables are available
supabase_url = os.getenv("SUPABASE_URL")
supabase_anon = os.getenv("SUPABASE_ANON_KEY")
supabase_service = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

print(f"[CONFIG DEBUG] SUPABASE_URL: {'SET' if supabase_url else 'NOT SET'}")
print(f"[CONFIG DEBUG] SUPABASE_ANON_KEY: {'SET' if supabase_anon else 'NOT SET'}")
print(f"[CONFIG DEBUG] SUPABASE_SERVICE_ROLE_KEY: {'SET' if supabase_service else 'NOT SET'}")

if supabase_url:
    print(f"[CONFIG DEBUG] SUPABASE_URL value: {supabase_url}")

# Modèle de base Pydantic pour être utilisé à travers l'API
class BaseModel(PydanticBaseModel):
    pass

# Utility function for getting user ID from authorization token
def get_user_id_from_token(authorization: str) -> str:
    """Extract user ID from authorization token"""
    from .db_client import supabase_service_client
    
    logger_config.info(f"[AUTH DEBUG] get_user_id_from_token called")
    logger_config.info(f"[AUTH DEBUG] authorization parameter: {authorization[:50] if authorization else 'None'}...")
    
    if not authorization or not authorization.startswith("Bearer "):
        logger_config.warning(f"[AUTH DEBUG] Invalid authorization header format")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing or invalid authorization header")
    
    token = authorization.replace("Bearer ", "")
    logger_config.info(f"[AUTH DEBUG] Extracted token length: {len(token)}")
    logger_config.info(f"[AUTH DEBUG] Token parts count: {len(token.split('.'))}")
    logger_config.info(f"[AUTH DEBUG] Token first 50 chars: {token[:50]}...")
    
    try:
        # Verify token with Supabase using service client
        logger_config.info(f"[AUTH DEBUG] Attempting to verify token with Supabase...")
        user_response = supabase_service_client.auth.get_user(token)
        
        if not user_response.user:
            logger_config.warning(f"[AUTH DEBUG] Supabase returned no user for token")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        
        logger_config.info(f"[AUTH DEBUG] Successfully verified user: {user_response.user.id}")
        return user_response.user.id
        
    except Exception as e:
        logger_config.error(f"[AUTH DEBUG] Error validating token: {e}")
        logger_config.error(f"[AUTH DEBUG] Exception type: {type(e).__name__}")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

# Example: If you wanted to make Supabase URL/keys available via this config
# SUPABASE_URL = os.getenv("SUPABASE_URL")
# SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")
# SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

# if not all([SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_SERVICE_ROLE_KEY]):
#     logger_config.warning("Une ou plusieurs variables d'environnement Supabase ne sont pas définies!")
# else:
#     logger_config.info("Variables d'environnement Supabase chargées (si définies).") 