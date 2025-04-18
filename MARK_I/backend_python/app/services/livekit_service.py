from livekit import api # Import the api module as shown in the example
import time
from datetime import timedelta # Import timedelta

from app.core.config import settings

def create_livekit_token(agent_identity: str, agent_name: str, room_name: str | None = None) -> str:
    """Generates a LiveKit access token for a specific agent identity, following official examples."""
    if not all([settings.LIVEKIT_URL, settings.LIVEKIT_API_KEY, settings.LIVEKIT_API_SECRET]):
         raise ValueError("LiveKit configuration missing in environment variables (LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET).")

    # Use agent_identity as room name if not provided
    effective_room_name = room_name if room_name else agent_identity

    # Define the permissions using api.VideoGrants (plural)
    grant = api.VideoGrants(
        room_join=True,
        room=effective_room_name,
        can_publish=True,
        can_subscribe=True,
        can_publish_data=True,
        # hidden=True, # Might be useful for agents
    )

    # Create the access token using api.AccessToken and keyword arguments for claims
    # Note: The AccessToken constructor itself might not take identity, grants etc directly
    # Instead, we chain methods like .with_identity(), .with_grants()
    token_builder = api.AccessToken(settings.LIVEKIT_API_KEY, settings.LIVEKIT_API_SECRET)
    
    # Chain methods to add claims and grants
    token_builder = token_builder.with_identity(agent_identity)
    token_builder = token_builder.with_name(agent_name)
    token_builder = token_builder.with_ttl(timedelta(seconds=3600)) # Pass timedelta explicitly
    token_builder = token_builder.with_metadata(f'{{"agent_id": "{agent_identity.split("_")[1] if "_" in agent_identity else 'unknown'}"}}')
    token_builder = token_builder.with_grants(grant)

    # Generate the JWT
    return token_builder.to_jwt()

    # --- Removed Placeholder --- 
    # print(f"[PLACEHOLDER] Would generate LiveKit token for identity: {agent_identity}")
    # return f"fake_livekit_token_for_{agent_identity}"
    # --- End Placeholder ---