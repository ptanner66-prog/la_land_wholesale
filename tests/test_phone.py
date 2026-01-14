"""Test phone normalization."""
from __future__ import annotations

import sys
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from outreach.phone import normalize_phone_e164, is_tcpa_safe, validate_phone_for_sms


def test_normalize_phone_valid():
    """Test valid phone number normalization."""
    assert normalize_phone_e164("225-555-0100") == "+12255550100"
    assert normalize_phone_e164("(225) 555-0100") == "+12255550100"
    assert normalize_phone_e164("225.555.0100") == "+12255550100"
    assert normalize_phone_e164("+1 225 555 0100") == "+12255550100"
    assert normalize_phone_e164("12255550100") == "+12255550100"


def test_normalize_phone_invalid():
    """Test invalid phone number handling."""
    assert normalize_phone_e164("123") is None
    assert normalize_phone_e164("invalid") is None
    assert normalize_phone_e164("") is None
    assert normalize_phone_e164(None) is None


def test_normalize_phone_with_extensions():
    """Test phone numbers with extensions."""
    # Extensions are typically stripped
    result = normalize_phone_e164("225-555-0100 ext 123")
    # This might parse or fail depending on phonenumbers behavior
    # Just verify it doesn't crash
    assert result is None or result.startswith("+1")


def test_is_tcpa_safe_valid():
    """Test TCPA safety check for valid numbers."""
    # Valid mobile-format number
    assert is_tcpa_safe("+12255550100") is True


def test_is_tcpa_safe_toll_free():
    """Test that toll-free numbers are not TCPA safe."""
    # Toll-free numbers are considered business lines
    assert is_tcpa_safe("+18005551234") is False
    assert is_tcpa_safe("+18885551234") is False


def test_is_tcpa_safe_invalid():
    """Test TCPA safety check for invalid numbers."""
    assert is_tcpa_safe("invalid") is False
    assert is_tcpa_safe("123") is False


def test_validate_phone_for_sms():
    """Test full phone validation."""
    result = validate_phone_for_sms("225-555-0100")
    
    assert result.is_valid is True
    assert result.e164 == "+12255550100"
    assert result.original == "225-555-0100"
    assert result.is_business is False


def test_validate_phone_for_sms_invalid():
    """Test validation of invalid phone."""
    result = validate_phone_for_sms("invalid")
    
    assert result.is_valid is False
    assert result.e164 is None
    assert result.error is not None


def test_validate_phone_toll_free():
    """Test validation of toll-free numbers."""
    result = validate_phone_for_sms("1-800-555-1234")
    
    assert result.is_valid is True
    assert result.is_business is True
    assert result.is_mobile is False
