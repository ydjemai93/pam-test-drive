# Use an official Python runtime as a parent image
# Using python:3.11 or similar stable version is recommended
FROM python:3.11-slim

# Set environment variables
# Prevents Python from writing pyc files to disc (equivalent to python -B)
ENV PYTHONDONTWRITEBYTECODE 1
# Ensures Python output is sent straight to terminal (useful for logging)
ENV PYTHONUNBUFFERED 1

# Set the working directory in the container
WORKDIR /app

# Install system dependencies if needed (e.g., for libraries with C extensions)
# RUN apt-get update && apt-get install -y --no-install-recommends some-package && rm -rf /var/lib/apt/lists/*

# Copy the updated requirements file into the container
COPY requirements.txt .

# Install Python dependencies
# --no-cache-dir reduces image size
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code into the container
# It assumes your FastAPI code is inside an 'app' directory
COPY ./app /app/app

# Expose the port the app runs on
# Uvicorn default is 8000. Render will map its external port to this.
EXPOSE 8000

# Define the command to run the application
# Use the --host 0.0.0.0 to make it accessible externally
# Render typically injects a PORT env var, but Uvicorn defaults to 8000 if not set.
# We can start with 8000 and adjust if needed based on Render's behavior.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"] 