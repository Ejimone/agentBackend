import os
from google.oauth2 import service_account
from exceptions import SecurityError

def validate_credentials():
    """Validate and return Google credentials"""
    creds_path = "./credentials.json"
    if not os.path.exists(creds_path):
        raise SecurityError("Invalid credentials configuration")
    
    try:
        return service_account.Credentials.from_service_account_file(creds_path)
    except Exception as e:
        raise SecurityError(f"Failed to load credentials: {str(e)}")