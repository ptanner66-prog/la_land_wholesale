"""Skip Trace Service for Phone/Email Enrichment.

This module provides skip tracing capabilities to enrich leads with:
- Phone numbers (mobile, landline)
- Email addresses
- Alternative contact information

Supports integration with BatchLeads or similar providers.
Configure via environment variables when credentials are available.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx

from core.config import get_settings
from core.exceptions import ExternalServiceError, MissingCredentialsError, RateLimitError
from core.logging_config import get_logger, log_external_call
from core.utils import utcnow
from services.cache import cached
from services.retry import with_retry

LOGGER = get_logger(__name__)
SETTINGS = get_settings()

# BatchLeads API endpoint (placeholder - update when credentials available)
BATCHLEADS_BASE_URL = "https://api.batchleads.io/v1"


@dataclass
class PhoneNumber:
    """Phone number with metadata."""
    number: str
    type: str = "unknown"  # mobile, landline, voip, unknown
    carrier: Optional[str] = None
    is_valid: bool = True
    is_connected: bool = True
    is_dnc: bool = False  # Do Not Call list
    score: int = 0  # Quality score 0-100
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "number": self.number,
            "type": self.type,
            "carrier": self.carrier,
            "is_valid": self.is_valid,
            "is_connected": self.is_connected,
            "is_dnc": self.is_dnc,
            "score": self.score,
        }


@dataclass
class EmailAddress:
    """Email address with metadata."""
    email: str
    type: str = "personal"  # personal, business, unknown
    is_valid: bool = True
    is_deliverable: bool = True
    score: int = 0  # Quality score 0-100
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "email": self.email,
            "type": self.type,
            "is_valid": self.is_valid,
            "is_deliverable": self.is_deliverable,
            "score": self.score,
        }


@dataclass
class SkipTraceResult:
    """Complete skip trace result for an individual."""
    # Input
    name: str
    address: Optional[str] = None
    
    # Contact info
    phones: List[PhoneNumber] = field(default_factory=list)
    emails: List[EmailAddress] = field(default_factory=list)
    
    # Best contacts
    best_phone: Optional[str] = None
    best_email: Optional[str] = None
    
    # Additional info
    age: Optional[int] = None
    relatives: List[str] = field(default_factory=list)
    associates: List[str] = field(default_factory=list)
    
    # Metadata
    found: bool = False
    confidence: float = 0.0
    source: str = "unknown"
    retrieved_at: Optional[str] = None
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "address": self.address,
            "phones": [p.to_dict() for p in self.phones],
            "emails": [e.to_dict() for e in self.emails],
            "best_phone": self.best_phone,
            "best_email": self.best_email,
            "age": self.age,
            "relatives": self.relatives,
            "associates": self.associates,
            "found": self.found,
            "confidence": self.confidence,
            "source": self.source,
            "retrieved_at": self.retrieved_at,
            "error": self.error,
        }


class SkipTraceService:
    """
    Service for skip tracing / contact enrichment.
    
    Provides methods for:
    - Individual person lookup
    - Batch skip tracing
    - Phone validation
    - Email validation
    
    Configure via environment variables:
    - BATCHLEADS_API_KEY: Your BatchLeads API key
    - BATCHLEADS_USER_ID: Your BatchLeads user ID (if required)
    - ENABLE_SKIP_TRACE: Feature flag
    """
    
    TIMEOUT = 30
    MAX_REQUESTS_PER_MINUTE = 30
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        user_id: Optional[str] = None,
    ):
        """Initialize skip trace service."""
        self.api_key = api_key or getattr(SETTINGS, 'batchleads_api_key', None)
        self.user_id = user_id or getattr(SETTINGS, 'batchleads_user_id', None)
        self._client: Optional[httpx.Client] = None
        self._last_request_time = 0.0
    
    def _get_client(self) -> httpx.Client:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.Client(
                timeout=self.TIMEOUT,
                headers=self._get_headers(),
            )
        return self._client
    
    def _get_headers(self) -> Dict[str, str]:
        """Get API request headers."""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        if self.user_id:
            headers["X-User-ID"] = self.user_id
        return headers
    
    def _rate_limit(self) -> None:
        """Apply rate limiting."""
        min_interval = 60.0 / self.MAX_REQUESTS_PER_MINUTE
        elapsed = time.time() - self._last_request_time
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)
        self._last_request_time = time.time()
    
    def is_configured(self) -> bool:
        """Check if skip trace is configured."""
        return bool(self.api_key)
    
    def is_enabled(self) -> bool:
        """Check if skip trace is enabled via feature flag."""
        return getattr(SETTINGS, 'enable_skip_trace', False) and self.is_configured()
    
    @with_retry(max_attempts=3, retry_exceptions=(ConnectionError, TimeoutError, httpx.HTTPError))
    def skip_trace_person(
        self,
        name: str,
        address: Optional[str] = None,
        city: Optional[str] = None,
        state: Optional[str] = None,
        zip_code: Optional[str] = None,
    ) -> SkipTraceResult:
        """
        Skip trace an individual person.
        
        Args:
            name: Full name of the person.
            address: Street address (helps narrow results).
            city: City name.
            state: State code.
            zip_code: ZIP code.
        
        Returns:
            SkipTraceResult with phone numbers, emails, etc.
        """
        if not self.is_enabled():
            LOGGER.debug("Skip trace disabled, returning empty result")
            return self._create_fallback_result(name, address, "Skip trace is disabled")
        
        if not self.api_key:
            return self._create_fallback_result(name, address, "API key not configured")
        
        self._rate_limit()
        start_time = time.perf_counter()
        success = False
        
        try:
            client = self._get_client()
            
            payload = {"name": name}
            if address:
                payload["address"] = address
            if city:
                payload["city"] = city
            if state:
                payload["state"] = state
            if zip_code:
                payload["zip"] = zip_code
            
            response = client.post(
                f"{BATCHLEADS_BASE_URL}/skip-trace",
                json=payload,
            )
            
            if response.status_code == 429:
                raise RateLimitError("Skip trace rate limit exceeded")
            
            response.raise_for_status()
            data = response.json()
            
            success = True
            return self._parse_response(name, address, data)
        
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return self._create_fallback_result(name, address, "Person not found")
            LOGGER.warning(f"Skip trace API error: {e}")
            return self._create_fallback_result(name, address, str(e))
        except httpx.HTTPError as e:
            LOGGER.warning(f"Skip trace HTTP error: {e}")
            return self._create_fallback_result(name, address, str(e))
        finally:
            duration_ms = (time.perf_counter() - start_time) * 1000
            log_external_call(
                LOGGER,
                service="skip_trace",
                operation="skip_trace_person",
                success=success,
                duration_ms=duration_ms,
            )
    
    def skip_trace_batch(
        self,
        records: List[Dict[str, Any]],
    ) -> List[SkipTraceResult]:
        """
        Batch skip trace multiple records.
        
        Args:
            records: List of dicts with 'name', 'address', etc.
        
        Returns:
            List of SkipTraceResult objects.
        """
        results = []
        for record in records:
            result = self.skip_trace_person(
                name=record.get("name", ""),
                address=record.get("address"),
                city=record.get("city"),
                state=record.get("state"),
                zip_code=record.get("zip_code"),
            )
            results.append(result)
        return results
    
    def validate_phone(self, phone: str) -> Dict[str, Any]:
        """
        Validate a phone number.
        
        Args:
            phone: Phone number to validate.
        
        Returns:
            Dict with validation results.
        """
        # Placeholder implementation using regex validation
        import re
        
        # Clean the phone number
        cleaned = re.sub(r'[^\d+]', '', phone)
        
        # Basic validation
        is_valid = len(cleaned) >= 10 and len(cleaned) <= 15
        
        # Determine type (simple heuristic)
        phone_type = "unknown"
        if is_valid:
            # US mobile area codes often start with certain prefixes
            if cleaned.startswith("+1") or cleaned.startswith("1"):
                area_code = cleaned[-10:-7] if len(cleaned) >= 10 else ""
                # This is a simplified check
                phone_type = "mobile"  # Default to mobile for now
        
        return {
            "phone": cleaned,
            "original": phone,
            "is_valid": is_valid,
            "type": phone_type,
            "is_connected": None,  # Would require API call
            "is_dnc": None,  # Would require DNC list check
        }
    
    def validate_email(self, email: str) -> Dict[str, Any]:
        """
        Validate an email address.
        
        Args:
            email: Email address to validate.
        
        Returns:
            Dict with validation results.
        """
        import re
        
        email = email.strip().lower()
        
        # Basic regex validation
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        is_valid = bool(re.match(pattern, email))
        
        # Determine type
        email_type = "personal"
        business_domains = ["company", "corp", "inc", "llc", "enterprise"]
        if any(d in email.split("@")[1] for d in business_domains):
            email_type = "business"
        
        return {
            "email": email,
            "is_valid": is_valid,
            "type": email_type,
            "is_deliverable": None,  # Would require SMTP check
        }
    
    def _parse_response(
        self,
        name: str,
        address: Optional[str],
        data: Dict[str, Any],
    ) -> SkipTraceResult:
        """Parse API response into SkipTraceResult."""
        phones = []
        for p in data.get("phones", []):
            phones.append(PhoneNumber(
                number=p.get("number", ""),
                type=p.get("type", "unknown"),
                carrier=p.get("carrier"),
                is_valid=p.get("is_valid", True),
                is_connected=p.get("is_connected", True),
                is_dnc=p.get("is_dnc", False),
                score=p.get("score", 0),
            ))
        
        emails = []
        for e in data.get("emails", []):
            emails.append(EmailAddress(
                email=e.get("email", ""),
                type=e.get("type", "personal"),
                is_valid=e.get("is_valid", True),
                is_deliverable=e.get("is_deliverable", True),
                score=e.get("score", 0),
            ))
        
        # Determine best contact
        best_phone = None
        if phones:
            # Prefer mobile, highest score
            sorted_phones = sorted(
                phones,
                key=lambda p: (p.type == "mobile", p.score, p.is_connected),
                reverse=True,
            )
            best_phone = sorted_phones[0].number
        
        best_email = None
        if emails:
            sorted_emails = sorted(
                emails,
                key=lambda e: (e.is_deliverable, e.score),
                reverse=True,
            )
            best_email = sorted_emails[0].email
        
        return SkipTraceResult(
            name=name,
            address=address,
            phones=phones,
            emails=emails,
            best_phone=best_phone,
            best_email=best_email,
            age=data.get("age"),
            relatives=data.get("relatives", []),
            associates=data.get("associates", []),
            found=len(phones) > 0 or len(emails) > 0,
            confidence=data.get("confidence", 0.0),
            source="batchleads",
            retrieved_at=utcnow().isoformat(),
        )
    
    def _create_fallback_result(
        self,
        name: str,
        address: Optional[str],
        error: str,
    ) -> SkipTraceResult:
        """Create fallback result when API is unavailable."""
        return SkipTraceResult(
            name=name,
            address=address,
            phones=[],
            emails=[],
            found=False,
            confidence=0.0,
            source="fallback",
            retrieved_at=utcnow().isoformat(),
            error=error,
        )
    
    def close(self) -> None:
        """Close HTTP client."""
        if self._client:
            self._client.close()
            self._client = None


# Module-level singleton
_service: Optional[SkipTraceService] = None


def get_skip_trace_service() -> SkipTraceService:
    """Get the global SkipTraceService instance."""
    global _service
    if _service is None:
        _service = SkipTraceService()
    return _service


def skip_trace_person(
    name: str,
    address: Optional[str] = None,
    city: Optional[str] = None,
    state: Optional[str] = None,
    zip_code: Optional[str] = None,
) -> SkipTraceResult:
    """
    Convenience function for skip tracing a person.
    
    Uses the global service instance with caching.
    """
    service = get_skip_trace_service()
    return service.skip_trace_person(name, address, city, state, zip_code)


__all__ = [
    "SkipTraceService",
    "SkipTraceResult",
    "PhoneNumber",
    "EmailAddress",
    "get_skip_trace_service",
    "skip_trace_person",
]

