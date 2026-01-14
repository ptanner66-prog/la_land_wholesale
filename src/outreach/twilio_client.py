"""Twilio client for SMS and voice operations.

Provides a unified interface for Twilio operations with:
- Rate limiting
- Error handling
- Circuit breaker pattern
- Webhook signature validation
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client
from twilio.request_validator import RequestValidator

from core.config import get_settings
from core.exceptions import TwilioError
from core.logging_config import get_logger
from core.utils import CircuitBreaker, RateLimiter

LOGGER = get_logger(__name__)
SETTINGS = get_settings()

# Circuit breaker for Twilio API
_twilio_circuit = CircuitBreaker(
    name="twilio_api",
    failure_threshold=5,
    recovery_timeout=60,
)

# Rate limiter based on settings
_rate_limiter = RateLimiter(
    max_calls=int(SETTINGS.twilio_max_messages_per_second * 60),
    period_seconds=60,
)


@dataclass
class SMSResult:
    """Result from sending an SMS."""
    success: bool
    sid: Optional[str] = None
    status: str = "unknown"
    error_code: Optional[int] = None
    error_message: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "sid": self.sid,
            "status": self.status,
            "error_code": self.error_code,
            "error_message": self.error_message,
        }


class TwilioClient:
    """
    Unified Twilio client with rate limiting and error handling.
    
    Usage:
        client = get_twilio_client()
        result = client.send_sms(to="+1234567890", body="Hello!")
    """

    def __init__(
        self,
        account_sid: Optional[str] = None,
        auth_token: Optional[str] = None,
        from_number: Optional[str] = None,
        messaging_service_sid: Optional[str] = None,
    ):
        """
        Initialize the Twilio client.
        
        Args:
            account_sid: Twilio Account SID (uses env if not provided).
            auth_token: Twilio Auth Token (uses env if not provided).
            from_number: Default from phone number.
            messaging_service_sid: Messaging Service SID for high-volume sending.
        """
        self.account_sid = account_sid or SETTINGS.twilio_account_sid
        self.auth_token = auth_token or SETTINGS.twilio_auth_token
        self.from_number = from_number or SETTINGS.twilio_from_number
        self.messaging_service_sid = messaging_service_sid or SETTINGS.twilio_messaging_service_sid
        
        self._client: Optional[Client] = None
        self._validator: Optional[RequestValidator] = None
        self.circuit = _twilio_circuit
        self.rate_limiter = _rate_limiter

    def _get_client(self) -> Client:
        """Get or create the Twilio REST client."""
        if self._client is None:
            if not self.account_sid or not self.auth_token:
                raise TwilioError("Twilio credentials not configured")
            self._client = Client(self.account_sid, self.auth_token)
        return self._client

    def _get_validator(self) -> RequestValidator:
        """Get or create the webhook validator."""
        if self._validator is None:
            if not self.auth_token:
                raise TwilioError("Auth token required for webhook validation")
            self._validator = RequestValidator(self.auth_token)
        return self._validator

    def is_configured(self) -> bool:
        """Check if Twilio is properly configured."""
        return bool(self.account_sid and self.auth_token and self.from_number)

    def send_sms(
        self,
        to: str,
        body: str,
        from_number: Optional[str] = None,
        use_messaging_service: bool = True,
        status_callback: Optional[str] = None,
    ) -> SMSResult:
        """
        Send an SMS message.
        
        Args:
            to: Recipient phone number (E.164 format).
            body: Message content.
            from_number: Override default from number.
            use_messaging_service: Use messaging service SID if available.
            status_callback: Webhook URL for delivery status updates.
            
        Returns:
            SMSResult with send outcome.
        """
        # Check circuit breaker
        if not self.circuit.can_execute():
            LOGGER.warning("Twilio circuit breaker is open")
            return SMSResult(
                success=False,
                status="circuit_open",
                error_message="Service temporarily unavailable",
            )
        
        # Check rate limit
        if not self.rate_limiter.can_proceed():
            wait_time = self.rate_limiter.wait_time()
            LOGGER.warning(f"Rate limit hit, waiting {wait_time:.1f}s")
            time.sleep(min(wait_time, 5))  # Wait up to 5 seconds
        
        try:
            client = self._get_client()
            
            # Build message params
            params: Dict[str, Any] = {
                "to": to,
                "body": body,
            }
            
            # Use messaging service or from number
            if use_messaging_service and self.messaging_service_sid:
                params["messaging_service_sid"] = self.messaging_service_sid
            else:
                params["from_"] = from_number or self.from_number
            
            # Add status callback if provided
            if status_callback:
                params["status_callback"] = status_callback
            
            # Send message
            message = client.messages.create(**params)
            
            self.circuit.record_success()
            self.rate_limiter.record_call()
            
            LOGGER.info(f"Sent SMS to {to}, SID: {message.sid}")
            
            return SMSResult(
                success=True,
                sid=message.sid,
                status=message.status,
            )
            
        except TwilioRestException as e:
            self.circuit.record_failure()
            LOGGER.error(f"Twilio error sending to {to}: {e}")
            
            return SMSResult(
                success=False,
                status="failed",
                error_code=e.code,
                error_message=str(e.msg),
            )
            
        except Exception as e:
            self.circuit.record_failure()
            LOGGER.exception(f"Unexpected error sending SMS to {to}")
            
            return SMSResult(
                success=False,
                status="error",
                error_message=str(e),
            )

    def get_message(self, sid: str) -> Optional[Dict[str, Any]]:
        """
        Get message details by SID.
        
        Args:
            sid: Twilio message SID.
            
        Returns:
            Message details dict or None.
        """
        try:
            client = self._get_client()
            message = client.messages(sid).fetch()
            
            return {
                "sid": message.sid,
                "status": message.status,
                "to": message.to,
                "from": message.from_,
                "body": message.body,
                "date_sent": message.date_sent.isoformat() if message.date_sent else None,
                "error_code": message.error_code,
                "error_message": message.error_message,
            }
        except TwilioRestException as e:
            LOGGER.error(f"Error fetching message {sid}: {e}")
            return None

    def validate_webhook(
        self,
        url: str,
        params: Dict[str, str],
        signature: str,
    ) -> bool:
        """
        Validate a Twilio webhook signature.
        
        Args:
            url: Full webhook URL.
            params: Request parameters.
            signature: X-Twilio-Signature header value.
            
        Returns:
            True if signature is valid.
        """
        try:
            validator = self._get_validator()
            return validator.validate(url, params, signature)
        except Exception as e:
            LOGGER.error(f"Webhook validation error: {e}")
            return False

    def lookup_phone(self, phone_number: str) -> Optional[Dict[str, Any]]:
        """
        Look up phone number details using Twilio Lookup API.
        
        Args:
            phone_number: Phone number to look up.
            
        Returns:
            Lookup details or None.
        """
        try:
            client = self._get_client()
            lookup = client.lookups.v2.phone_numbers(phone_number).fetch()
            
            return {
                "phone_number": lookup.phone_number,
                "national_format": lookup.national_format,
                "country_code": lookup.country_code,
                "valid": lookup.valid,
                "calling_country_code": lookup.calling_country_code,
            }
        except TwilioRestException as e:
            LOGGER.error(f"Phone lookup error for {phone_number}: {e}")
            return None


# Module-level singleton
_client: Optional[TwilioClient] = None


def get_twilio_client() -> TwilioClient:
    """Get the global TwilioClient instance."""
    global _client
    if _client is None:
        _client = TwilioClient()
    return _client


def reset_twilio_client() -> None:
    """Reset the global Twilio client (useful for testing)."""
    global _client
    _client = None


__all__ = [
    "TwilioClient",
    "SMSResult",
    "get_twilio_client",
    "reset_twilio_client",
]

