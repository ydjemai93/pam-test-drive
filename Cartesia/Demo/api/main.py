from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel
import subprocess
import json
import logging
import os
from dotenv import load_dotenv

# Load environment variables from .env files
load_dotenv(dotenv_path="../outbound/.env.local") # Adjust path as needed
load_dotenv(dotenv_path="../outbound/.env") # Load base .env if local exists or not

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# --- Pydantic Models ---
class CallRequest(BaseModel):
    firstName: str
    lastName: str
    phoneNumber: str

# --- API Endpoints ---
@app.post("/call")
async def initiate_call(request: CallRequest):
    logger.info(f"Received call request for {request.firstName} {request.lastName} at {request.phoneNumber}")

    # Prepare metadata for the agent
    metadata = {
        "firstName": request.firstName,
        "lastName": request.lastName,
        "phoneNumber": request.phoneNumber,
    }
    metadata_json = json.dumps(metadata)

    # Construct the lk dispatch command
    # Assumes 'lk' is in the system's PATH or uses the full path
    # Assumes necessary LiveKit environment variables (LK_URL, LK_API_KEY, LK_API_SECRET) are set
    # in the environment where this API runs or loaded from .env
    command = [
        "lk",
        "dispatch",
        "create",
        "--new-room",
        "--agent-name", "outbound-caller", # Ensure this matches your agent name
        "--metadata", metadata_json
    ]

    try:
        # Execute the command
        logger.info(f"Executing command: {' '.join(command)}")
        result = subprocess.run(command, capture_output=True, text=True, check=True, shell=True) # Use shell=True for Windows compatibility if needed, but be cautious
        logger.info(f"lk dispatch command output: {result.stdout}")
        logger.info(f"lk dispatch command stderr: {result.stderr}")

        # Check for specific success indicators in stdout if needed,
        # but check=True already raises an exception on non-zero exit codes.
        if "Dispatch created" not in result.stdout:
             logger.warning("Dispatch command executed but success message not found in output.")
             # Decide if this is still considered a success or should raise an error

        return {"message": "Call initiated successfully", "dispatch_details": result.stdout}

    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to execute lk dispatch command: {e}")
        logger.error(f"Command output (stdout): {e.stdout}")
        logger.error(f"Command output (stderr): {e.stderr}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initiate call: {e.stderr or e.stdout or 'Unknown error'}",
        )
    except FileNotFoundError:
        logger.error("Error: 'lk' command not found. Make sure LiveKit CLI is installed and in PATH.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="'lk' command not found. Server configuration issue."
        )
    except Exception as e:
        logger.exception("An unexpected error occurred") # Log the full traceback
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred: {str(e)}",
        )

# --- Root endpoint for testing ---
@app.get("/")
def read_root():
    return {"message": "API is running"}

# --- To run the server (for development) ---
# Use uvicorn: uvicorn api.main:app --reload --port 8000
# Ensure you are in the root directory (pam-testdrive) when running this
if __name__ == "__main__":
    import uvicorn
    # Make sure to run this from the root directory (pam-testdrive)
    # using 'python -m api.main' won't work directly due to relative paths
    # Best practice is to use uvicorn command directly from the terminal
    logger.warning("Running uvicorn directly from script is for debugging only.")
    logger.warning("Use: 'uvicorn api.main:app --reload --port 8000' from the 'pam-testdrive' directory.")
    # uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True) # This line might have issues with relative paths

# </rewritten_file> 