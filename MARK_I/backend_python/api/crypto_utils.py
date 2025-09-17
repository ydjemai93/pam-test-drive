"""
Encryption utilities for securely storing and retrieving app credentials
"""
from cryptography.fernet import Fernet
import os
import json
import base64
from typing import Dict, Any
from datetime import datetime

# Get encryption key from environment
ENCRYPTION_KEY = os.getenv("INTEGRATION_ENCRYPTION_KEY")

def get_or_generate_encryption_key():
    """Get or generate a valid Fernet encryption key"""
    key = os.getenv("INTEGRATION_ENCRYPTION_KEY")
    
    if not key:
        # Generate a key for development (DO NOT USE IN PRODUCTION)
        key = Fernet.generate_key().decode()
        print(f"Warning: Using generated encryption key for development")
        print("Set INTEGRATION_ENCRYPTION_KEY environment variable for production")
        return key.encode()
    
    try:
        # Fernet keys should be 44-character base64url encoded strings
        if isinstance(key, str) and len(key) == 44:
            # Test if it's a valid Fernet key
            test_cipher = Fernet(key.encode())
            return key.encode()
        elif isinstance(key, bytes):
            # If it's already bytes, test directly
            test_cipher = Fernet(key)
            return key
        else:
            raise ValueError(f"Key must be 44 characters, got {len(key) if isinstance(key, str) else 'bytes'}")
            
    except Exception as e:
        print(f"Invalid encryption key format: {e}")
        print("Generating new key for development...")
        # Generate a new valid key
        new_key = Fernet.generate_key().decode()
        print(f"Generated key: {new_key}")
        print("Please set this in your INTEGRATION_ENCRYPTION_KEY environment variable")
        return new_key.encode()

# Initialize cipher suite with validated key
ENCRYPTION_KEY = get_or_generate_encryption_key()
cipher_suite = Fernet(ENCRYPTION_KEY)

def encrypt_credentials(credentials: Dict[str, Any]) -> str:
    """
    Encrypt app credentials before storing in database
    
    Args:
        credentials: Dictionary containing OAuth tokens and related data
        
    Returns:
        Encrypted string that can be safely stored in database
    """
    try:
        # Add encryption metadata
        encrypted_data = {
            "data": credentials,
            "encrypted_at": datetime.utcnow().isoformat(),
            "version": "1.0"
        }
        
        # Convert to JSON string
        json_str = json.dumps(encrypted_data, default=str)
        
        # Encrypt the JSON string
        encrypted_bytes = cipher_suite.encrypt(json_str.encode())
        
        # Return base64 encoded string for database storage
        return base64.b64encode(encrypted_bytes).decode()
        
    except Exception as e:
        raise Exception(f"Failed to encrypt credentials: {str(e)}")

def decrypt_credentials(encrypted_credentials: str) -> Dict[str, Any]:
    """
    Decrypt app credentials from database storage
    
    Args:
        encrypted_credentials: Base64 encoded encrypted string from database
        
    Returns:
        Dictionary containing decrypted OAuth tokens and related data
    """
    try:
        # Decode from base64
        encrypted_bytes = base64.b64decode(encrypted_credentials.encode())
        
        # Decrypt the data
        decrypted_bytes = cipher_suite.decrypt(encrypted_bytes)
        
        # Parse JSON
        decrypted_data = json.loads(decrypted_bytes.decode())
        
        # Return just the credentials data (strip metadata)
        return decrypted_data.get("data", decrypted_data)
        
    except Exception as e:
        raise Exception(f"Failed to decrypt credentials: {str(e)}")

def is_token_expired(credentials: Dict[str, Any]) -> bool:
    """
    Check if OAuth token is expired
    
    Args:
        credentials: Decrypted credentials dictionary
        
    Returns:
        True if token is expired, False otherwise
    """
    try:
        expires_at_str = credentials.get("expires_at")
        if not expires_at_str:
            # If no expiration info, assume token is still valid
            return False
            
        expires_at = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
        
        # Add 5 minute buffer to avoid edge cases
        from datetime import timedelta
        buffer_time = timedelta(minutes=5)
        
        return datetime.utcnow() >= (expires_at - buffer_time)
        
    except Exception:
        # If we can't parse expiration, assume expired to be safe
        return True

def generate_encryption_key() -> str:
    """
    Generate a new encryption key for development/setup
    
    Returns:
        Base64 encoded encryption key
    """
    return Fernet.generate_key().decode()

def validate_encryption_key(key: str) -> bool:
    """
    Validate that an encryption key is properly formatted
    
    Args:
        key: Encryption key to validate
        
    Returns:
        True if key is valid, False otherwise
    """
    try:
        if isinstance(key, str):
            key = key.encode()
        Fernet(key)
        return True
    except Exception:
        return False

# Test functions for development
def test_encryption():
    """Test encryption/decryption functionality"""
    test_credentials = {
        "access_token": "test_access_token_12345",
        "refresh_token": "test_refresh_token_67890", 
        "expires_at": "2024-12-31T23:59:59",
        "scope": "contacts deals calendar",
        "token_type": "Bearer"
    }
    
    print("Testing credential encryption...")
    
    # Test encryption
    encrypted = encrypt_credentials(test_credentials)
    print(f"Encrypted: {encrypted[:50]}...")
    
    # Test decryption
    decrypted = decrypt_credentials(encrypted)
    print(f"Decrypted: {decrypted}")
    
    # Verify data integrity
    assert decrypted["access_token"] == test_credentials["access_token"]
    assert decrypted["refresh_token"] == test_credentials["refresh_token"]
    
    print("✅ Encryption test passed!")

if __name__ == "__main__":
    test_encryption() 