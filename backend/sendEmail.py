import os
import base64
import json
import logging
import logging.config
import re
from pathlib import Path
from datetime import datetime
from email.mime.text import MIMEText
from typing import Dict, Any, List, Optional
from functools import lru_cache
from dataclasses import dataclass

# Third-party imports
import pytz
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient import errors as google_errors
from tenacity import retry, stop_after_attempt, wait_exponential

# Constants
MAX_RETRIES = 3
TOKEN_EXPIRY_BUFFER = 300  # 5 minutes buffer for token expiration
EMAIL_REGEX = r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$'

# Configuration
@dataclass(frozen=True)
class ServiceConfig:
    """Immutable service configuration parameters"""
    SCOPES: List[str] = (
        'https://www.googleapis.com/auth/gmail.send',
        'https://www.googleapis.com/auth/gmail.compose',
        "https://www.googleapis.com/auth/calendar"
    )
    LOG_LEVEL: str = "INFO"
    MAX_CONTENT_LENGTH: int = 1024 * 1024  # 1MB
    TOKEN_REFRESH_THRESHOLD: int = TOKEN_EXPIRY_BUFFER

@dataclass(frozen=True)
class PathConfig:
    """Immutable path configuration"""
    BASE_DIR: Path = Path(__file__).resolve().parent
    CREDENTIALS_PATH: Path = BASE_DIR / 'credentials.json'
    TOKEN_PATH: Path = BASE_DIR / 'token.json'
    LOG_CONFIG_PATH: Path = BASE_DIR / 'logging.json'

class EmailServiceError(Exception):
    """Base exception for email service errors"""
    pass

class EmailValidationError(EmailServiceError):
    """Exception raised for email validation errors"""
    pass

# Logging configuration
def setup_logging() -> None:
    """Configure structured logging with rotation"""
    logging.config.dictConfig({
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'json': {
                '()': 'pythonjsonlogger.jsonlogger.JsonFormatter',
                'format': '''
                    {
                        "timestamp": "%(asctime)s",
                        "level": "%(levelname)s",
                        "name": "%(name)s",
                        "message": "%(message)s",
                        "module": "%(module)s",
                        "function": "%(funcName)s"
                    }
                '''
            }
        },
        'handlers': {
            'console': {
                'class': 'logging.StreamHandler',
                'formatter': 'json',
                'level': 'INFO'
            },
            'file': {
                'class': 'logging.handlers.RotatingFileHandler',
                'filename': 'email_service.log',
                'maxBytes': 10 * 1024 * 1024,  # 10MB
                'backupCount': 5,
                'formatter': 'json',
                'level': 'INFO'
            }
        },
        'loggers': {
            '': {  # Root logger
                'handlers': ['console', 'file'],
                'level': 'INFO',
                'propagate': True
            }
        }
    })

logger = logging.getLogger(__name__)

class EmailService:
    """Secure email service with Gmail API integration"""
    
    def __init__(self, config: ServiceConfig = ServiceConfig()):
        self.config = config
        self._validate_environment()
        self.gmail_service = self._initialize_gmail_service()

    def _validate_environment(self) -> None:
        """Validate required environment setup"""
        if not PathConfig.CREDENTIALS_PATH.exists():
            raise EmailServiceError("Missing credentials file")
        
        if not PathConfig.CREDENTIALS_PATH.stat().st_size > 0:
            raise EmailServiceError("Empty credentials file")

    @retry(
        stop=stop_after_attempt(MAX_RETRIES),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True
    )
    def _initialize_gmail_service(self) -> Any:
        """Initialize and return authenticated Gmail service"""
        try:
            creds = self._get_valid_credentials()
            return build('gmail', 'v1', credentials=creds, cache_discovery=False)
        except Exception as e:
            logger.error(f"Gmail service initialization failed: {str(e)}")
            raise EmailServiceError("Failed to initialize Gmail service") from e

    def _get_valid_credentials(self) -> Credentials:
        """Obtain valid credentials with secure token management"""
        creds = self._load_existing_credentials()
        
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                self._refresh_credentials(creds)
            else:
                creds = self._create_new_credentials()
            
            self._store_credentials(creds)
        
        return creds

    def _load_existing_credentials(self) -> Optional[Credentials]:
        """Load existing credentials from secure storage"""
        try:
            if PathConfig.TOKEN_PATH.exists():
                with PathConfig.TOKEN_PATH.open('r') as token_file:
                    return Credentials.from_authorized_user_info(json.load(token_file))
        except Exception as e:
            logger.warning(f"Failed to load credentials: {str(e)}")
        return None

    def _refresh_credentials(self, creds: Credentials) -> None:
        """Refresh expired credentials"""
        try:
            creds.refresh(Request())
        except Exception as e:
            logger.error(f"Credentials refresh failed: {str(e)}")
            raise EmailServiceError("Credentials refresh failed") from e

    def _create_new_credentials(self) -> Credentials:
        """Create new credentials through OAuth flow"""
        try:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(PathConfig.CREDENTIALS_PATH),
                scopes=self.config.SCOPES
            )
            return flow.run_local_server(port=0)
        except Exception as e:
            logger.error(f"OAuth flow failed: {str(e)}")
            raise EmailServiceError("OAuth authentication failed") from e

    def _store_credentials(self, creds: Credentials) -> None:
        """Securely store credentials"""
        try:
            token_data = {
                'token': creds.token,
                'refresh_token': creds.refresh_token,
                'token_uri': creds.token_uri,
                'client_id': creds.client_id,
                'client_secret': creds.client_secret,
                'scopes': creds.scopes
            }
            with PathConfig.TOKEN_PATH.open('w') as token_file:
                json.dump(token_data, token_file)
        except Exception as e:
            logger.error(f"Failed to store credentials: {str(e)}")
            raise EmailServiceError("Credential storage failed") from e

    def _validate_email_components(self, to: str, subject: str, body: str) -> None:
        """Validate email components before sending"""
        if not re.match(EMAIL_REGEX, to):
            raise EmailValidationError(f"Invalid email address: {to}")
        
        if len(subject) > 150:
            raise EmailValidationError("Subject line too long")
        
        if len(body) > self.config.MAX_CONTENT_LENGTH:
            raise EmailValidationError("Email body exceeds maximum allowed size")

    def construct_message(self, to: str, subject: str, body: str) -> Dict[str, Any]:
        """Construct MIME email message with validation"""
        self._validate_email_components(to, subject, body)
        
        try:
            message = MIMEText(body)
            message['to'] = to
            message['subject'] = subject
            return {
                'raw': base64.urlsafe_b64encode(message.as_bytes()).decode()
            }
        except Exception as e:
            logger.error(f"Message construction failed: {str(e)}")
            raise EmailServiceError("Failed to construct email message") from e

    @retry(
        stop=stop_after_attempt(MAX_RETRIES),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True
    )
    def send_email(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Send email through Gmail API with retry logic"""
        try:
            result = self.gmail_service.users().messages().send(
                userId='me',
                body=message
            ).execute()
            
            logger.info(
                "Email sent successfully",
                extra={'message_id': result.get('id'), 'service': 'gmail'}
            )
            return {
                'status': 'success',
                'message_id': result.get('id'),
                'service': 'gmail'
            }
        except google_errors.HttpError as e:
            logger.error(f"Gmail API error: {str(e)}")
            raise EmailServiceError("Gmail API communication failed") from e
        except Exception as e:
            logger.error(f"Unexpected error sending email: {str(e)}")
            raise EmailServiceError("Email sending failed") from e

    @lru_cache(maxsize=128)
    def get_current_time(self, timezone: str = 'UTC') -> str:
        """Get current time for a given timezone with caching"""
        try:
            tz = pytz.timezone(timezone)
            return datetime.now(tz).strftime('%Y-%m-%d %H:%M:%S %Z')
        except pytz.UnknownTimeZoneError:
            logger.warning(f"Unknown timezone requested: {timezone}")
            return datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')

    def check_connection(self) -> bool:
        """Check if the email service is properly configured and connected"""
        try:
            # Verify credentials and service initialization
            if not self.gmail_service:
                return False
                
            # Test connection by getting user profile
            self.gmail_service.users().getProfile(userId='me').execute()
            return True
            
        except Exception as e:
            logger.error(f"Connection check failed: {str(e)}")
            return False

    async def handle_email_request(self, prompt: str) -> Dict[str, Any]:
        """Handle natural language email requests"""
        try:
            # Use interactive email sending for now
            send_email_interactive(self)
            return {
                "status": "success",
                "message": "Email sent successfully"
            }
        except Exception as e:
            logger.error(f"Error handling email request: {str(e)}")
            return {
                "status": "error",
                "message": f"Failed to process email request: {str(e)}"
            }


def send_email_interactive(service: EmailService) -> None:
    """
    Interactive email sending function with validation
    """
    print("\n" + "="*40)
    print("Email Composition Interface".center(40))
    print("="*40 + "\n")

    # Email address validation
    while True:
        recipient = input("Enter recipient's email address: ").strip()
        if re.match(EMAIL_REGEX, recipient):
            break
        print("❌ Invalid email format. Please try again.")

    # Subject validation
    while True:
        subject = input("Enter email subject (max 150 chars): ").strip()
        if len(subject) > 150:
            print("❌ Subject exceeds 150 character limit")
        elif subject:
            break
        else:
            print("❌ Subject cannot be empty")

    # Body composition with multi-line support
    print("\nCompose your email body (type 'END' on a new line to finish):")
    body_lines = []
    while True:
        try:
            line = input()
            if line.strip().upper() == 'END':
                break
            body_lines.append(line)
        except EOFError:
            break

    body = '\n'.join(body_lines).strip()
    if not body:
        print("❌ Email body cannot be empty")
        return

    # Final confirmation
    print("\n" + "-"*40)
    print(f"To: {recipient}")
    print(f"Subject: {subject}")
    print("\nBody Preview:")
    print(body[:500] + ("..." if len(body) > 500 else ""))
    print("-"*40 + "\n")

    confirmation = input("Send this email? (y/N): ").strip().lower()
    if confirmation != 'y':
        print("🚫 Email cancelled")
        return

    try:
        message = service.construct_message(
            to=recipient,
            subject=subject,
            body=body
        )
        result = service.send_email(message)
        print(f"\n✅ Email sent successfully! Message ID: {result['message_id']}")
    except EmailValidationError as e:
        print(f"\n❌ Validation error: {str(e)}")
    except EmailServiceError as e:
        print(f"\n❌ Service error: {str(e)}")
    except Exception as e:
        print(f"\n❌ Unexpected error: {str(e)}")
        logger.error(f"Unexpected error in interactive send: {str(e)}")






if __name__ == "__main__":
    try:
        setup_logging()
        service = EmailService()
        
        while True:
            send_email_interactive(service)
            if input("\nSend another email? (y/N): ").strip().lower() != 'y':
                break
                
    except Exception as e:
        logger.error(f"Critical failure: {str(e)}")
        print(f"💥 Critical error: {str(e)}")




















# Example usage

# if __name__ == "__main__":
#     try:
#         setup_logging()
#         service = EmailService()
        
#         # Example email send
#         message = service.construct_message(
#             to="recipient@example.com",
#             subject="Service Test",
#             body="This is a test email from the production email service"
#         )
#         result = service.send_email(message)
#         print(f"Email sent successfully: {result['message_id']}")
        
#     except EmailServiceError as e:
#         logger.error(f"Email service error: {str(e)}")
#         print(f"Service error: {str(e)}")
#     except Exception as e:
#         logger.error(f"Unexpected error: {str(e)}")
#         print(f"Unexpected error: {str(e)}")