from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv
import os

# Explicitly load .env file from the 'app' directory
dotenv_path = os.path.join(os.path.dirname(__file__), '../.env') # Points to app/.env
load_dotenv(dotenv_path=dotenv_path)

class Settings(BaseSettings):
    # Pydantic will now read directly from the environment variables 
    # (which should have been loaded by load_dotenv above)
    # We remove the env_file directive here as dotenv handles it.
    model_config = SettingsConfigDict(extra='ignore') 

    XANO_API_BASE_URL: str
    XANO_API_KEY: str # For Backend -> Xano communication

    LIVEKIT_API_KEY: str | None = None
    LIVEKIT_API_SECRET: str | None = None
    LIVEKIT_URL: str | None = None

    TELNYX_API_KEY: str | None = None
    TELNYX_CONNECTION_ID: str | None = None
    TELNYX_PUBLIC_SIP_URI: str | None = None

    # Add the missing field for LiveKit inbound SIP URI
    LIVEKIT_INBOUND_SIP_URI: str | None = None

# Create a single instance of the settings to be imported elsewhere
settings = Settings() 