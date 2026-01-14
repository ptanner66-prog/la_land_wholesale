"""Consolidated phone number utilities for la_land_wholesale."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Optional

import phonenumbers
from phonenumbers import NumberParseException

from core.logging_config import get_logger

LOGGER = get_logger(__name__)

# Common business phone patterns (toll-free, etc.)
BUSINESS_PHONE_PATTERNS = [
    re.compile(r"^1?8(00|33|44|55|66|77|88)"),  # Toll-free prefixes
]


@dataclass(frozen=True, slots=True)
class PhoneValidationResult:
    """Result of phone number validation."""

    original: str
    e164: Optional[str]
    is_valid: bool
    is_mobile: bool
    is_business: bool
    carrier: Optional[str] = None
    error: Optional[str] = None


def normalize_phone_e164(value: Optional[str], default_region: str = "US") -> Optional[str]:
    """
    Normalize a phone number to E.164 format.

    Args:
        value: Raw phone number string.
        default_region: Default region for parsing (ISO 3166-1 alpha-2).

    Returns:
        E.164 formatted phone number if valid, otherwise None.
    """
    if not value:
        return None

    cleaned = re.sub(r"[^\d+]", "", value.strip())
    if not cleaned:
        return None

    try:
        parsed = phonenumbers.parse(value, default_region)
        if phonenumbers.is_valid_number(parsed):
            return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
    except NumberParseException:
        pass

    return None


def validate_phone_for_sms(value: str, default_region: str = "US") -> PhoneValidationResult:
    """
    Validate a phone number for SMS capability.

    Args:
        value: Raw phone number string.
        default_region: Default region for parsing.

    Returns:
        PhoneValidationResult object.
    """
    e164 = normalize_phone_e164(value, default_region)
    
    if not e164:
        return PhoneValidationResult(
            original=value,
            e164=None,
            is_valid=False,
            is_mobile=False,
            is_business=False,
            error="Invalid format",
        )

    # Check for business/toll-free patterns
    # Note: This is a heuristic. Real carrier lookups require Twilio API.
    is_business = any(p.match(e164.lstrip("+")) for p in BUSINESS_PHONE_PATTERNS)

    # For now, we assume valid E.164 numbers are potentially mobile unless known business
    # In a real production system, you'd use Twilio Lookup API to verify line type (mobile/landline/voip)
    is_mobile = not is_business

    return PhoneValidationResult(
        original=value,
        e164=e164,
        is_valid=True,
        is_mobile=is_mobile,
        is_business=is_business,
    )


def is_tcpa_safe(phone_number: str) -> bool:
    """
    Check if a phone number is ostensibly safe for TCPA (basic checks).
    
    This does NOT replace the need for DNC registry checks or litigator scrubbing.
    It primarily ensures the number format is valid and not a known business line.
    
    Args:
        phone_number: Phone number to check.
        
    Returns:
        True if valid and likely mobile, False otherwise.
    """
    result = validate_phone_for_sms(phone_number)
    return result.is_valid and result.is_mobile
