"""Webhook security and signature verification."""
from __future__ import annotations

import hmac
import hashlib
from typing import Optional
from urllib.parse import urlencode

from fastapi import HTTPException, Request

from core.config import get_settings
from core.logging_config import get_logger

LOGGER = get_logger(__name__)
SETTINGS = get_settings()


class TwilioSignatureValidator:
    """
    Validates Twilio webhook request signatures.
    
    See: https://www.twilio.com/docs/usage/security#validating-requests
    """

    def __init__(self, auth_token: Optional[str] = None):
        """
        Initialize validator.
        
        Args:
            auth_token: Twilio auth token. Uses settings if not provided.
        """
        self.auth_token = auth_token or SETTINGS.twilio_auth_token

    def compute_signature(self, url: str, params: dict) -> str:
        """
        Compute the expected Twilio signature.
        
        Args:
            url: The full webhook URL.
            params: The POST parameters.
        
        Returns:
            Base64-encoded HMAC-SHA1 signature.
        """
        import base64
        
        if not self.auth_token:
            raise ValueError("Twilio auth token not configured")
        
        # Sort parameters and append to URL
        sorted_params = sorted(params.items())
        data = url + urlencode(sorted_params, safe='')
        
        # Compute HMAC-SHA1
        signature = hmac.new(
            self.auth_token.encode('utf-8'),
            data.encode('utf-8'),
            hashlib.sha1
        ).digest()
        
        return base64.b64encode(signature).decode('utf-8')

    def validate(self, url: str, params: dict, signature: str) -> bool:
        """
        Validate a Twilio webhook signature.
        
        Args:
            url: The full webhook URL.
            params: The POST parameters.
            signature: The X-Twilio-Signature header value.
        
        Returns:
            True if signature is valid, False otherwise.
        """
        if not self.auth_token:
            LOGGER.warning("Twilio auth token not configured, skipping signature validation")
            return True  # Allow in development
        
        if not signature:
            LOGGER.warning("No Twilio signature provided")
            return False
        
        expected = self.compute_signature(url, params)
        
        # Use constant-time comparison
        is_valid = hmac.compare_digest(expected, signature)
        
        if not is_valid:
            LOGGER.warning(f"Invalid Twilio signature. Expected: {expected}, Got: {signature}")
        
        return is_valid


async def verify_twilio_signature(request: Request) -> dict:
    """
    FastAPI dependency for verifying Twilio webhook signatures.
    
    Usage:
        @router.post("/webhook")
        async def handle_webhook(params: dict = Depends(verify_twilio_signature)):
            ...
    
    Args:
        request: The FastAPI request.
    
    Returns:
        The form data if valid.
    
    Raises:
        HTTPException: If signature is invalid.
    """
    # Get form data
    form_data = await request.form()
    params = dict(form_data)
    
    # Skip validation in development
    if SETTINGS.dry_run or not SETTINGS.twilio_auth_token:
        return params
    
    # Get signature from header
    signature = request.headers.get("X-Twilio-Signature", "")
    
    # Get full URL
    url = str(request.url)
    
    # For local development, Twilio may send to ngrok etc.
    # Use the forwarded host if present
    forwarded_proto = request.headers.get("X-Forwarded-Proto")
    forwarded_host = request.headers.get("X-Forwarded-Host")
    
    if forwarded_proto and forwarded_host:
        url = f"{forwarded_proto}://{forwarded_host}{request.url.path}"
    
    # Validate
    validator = TwilioSignatureValidator()
    
    if not validator.validate(url, params, signature):
        LOGGER.error("Twilio webhook signature validation failed")
        raise HTTPException(status_code=403, detail="Invalid signature")
    
    return params


__all__ = [
    "TwilioSignatureValidator",
    "verify_twilio_signature",
]

