import os
from supabase import create_client, Client
import logging

# Import config to ensure environment variables are loaded
try:
    import api.config as config
except ImportError:
    try:
        import config
    except ImportError:
        # If running standalone, just load env directly
        from dotenv import load_dotenv
        load_dotenv()

logger = logging.getLogger(__name__)

# Debug: Print what environment variables we see
print(f"[DB_CLIENT DEBUG] SUPABASE_URL: {os.getenv('SUPABASE_URL')}")
print(f"[DB_CLIENT DEBUG] SUPABASE_ANON_KEY: {'SET' if os.getenv('SUPABASE_ANON_KEY') else 'NOT SET'}")
print(f"[DB_CLIENT DEBUG] SUPABASE_SERVICE_ROLE_KEY: {'SET' if os.getenv('SUPABASE_SERVICE_ROLE_KEY') else 'NOT SET'}")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

if not SUPABASE_URL:
    print(f"[DB_CLIENT DEBUG] ERROR: SUPABASE_URL environment variable is not set.")
    logger.error("SUPABASE_URL environment variable is not set.")
    raise ValueError("SUPABASE_URL environment variable is not set.")
if not SUPABASE_ANON_KEY: # Though service role might be used more from backend
    print(f"[DB_CLIENT DEBUG] WARNING: SUPABASE_ANON_KEY environment variable is not set.")
    logger.warning("SUPABASE_ANON_KEY environment variable is not set. Operations requiring anon key might fail.")
if not SUPABASE_SERVICE_ROLE_KEY:
    print(f"[DB_CLIENT DEBUG] ERROR: SUPABASE_SERVICE_ROLE_KEY environment variable is not set.")
    logger.error("SUPABASE_SERVICE_ROLE_KEY environment variable is not set. Backend operations requiring service role will fail.")
    # Depending on your app's needs, you might want to raise an error here too
    # if the service role key is essential for all backend operations.
    # raise ValueError("SUPABASE_SERVICE_ROLE_KEY environment variable is not set.")


# Client for operations using the service_role key (bypasses RLS)
# This client should be used for most backend-to-database interactions
# unless you are specifically acting on behalf of a user and want RLS applied.
try:
    print(f"[DB_CLIENT DEBUG] Creating Supabase service client with URL: {SUPABASE_URL}")
    supabase_service_client: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
    print(f"[DB_CLIENT DEBUG] Supabase service client created successfully!")
    logger.info("Supabase service client initialized successfully.")
except Exception as e:
    print(f"[DB_CLIENT DEBUG] FAILED to create Supabase service client: {e}")
    logger.critical(f"Failed to initialize Supabase service client: {e}", exc_info=True)
    # Depending on how critical the DB connection is at startup,
    # you might re-raise or handle this to prevent app from starting.
    # For now, we'll let it be and calls using it will fail.
    supabase_service_client = None # type: ignore


# Optional: A function to get a client configured with the anon key
# This would be used if you plan to make requests from the backend
# that should respect RLS policies based on a user's JWT (which you'd set per request).
def get_supabase_anon_client() -> Client:
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        raise ValueError("Supabase URL or Anon Key not configured for anon client.")
    return create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

# Primarily, you'll import and use supabase_service_client from this module
# for backend operations that need elevated privileges or don't have a user context. 