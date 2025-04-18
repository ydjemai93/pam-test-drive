from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from app.services import xano_service

# This tells FastAPI to look for a token in the Authorization header 
# with the value "Bearer <token>".
# The tokenUrl is just a dummy value here, as authentication happens via Xano.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

async def get_current_user_id(token: str = Depends(oauth2_scheme)) -> int:
    """
    Dependency to verify the token with Xano and return the user ID.
    Raises HTTPException 401 if the token is invalid.
    """
    try:
        user_data = await xano_service.verify_xano_token(token)
        user_id = user_data.get('id')
        if user_id is None:
             raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, # Or maybe 401?
                detail="User ID not found in token payload from Xano",
            )
        return user_id
    except HTTPException as e:
        # Re-raise the HTTPException from verify_xano_token
        raise e
    except Exception as e:
        # Catch any other unexpected errors
        print(f"Unexpected error during token verification: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred during authentication.",
        ) 