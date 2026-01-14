"""USPS Address Verification API integration with fallback support."""
from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any, Dict, Optional

import httpx

from core.config import get_settings
from core.exceptions import MissingCredentialsError, USPSVerificationError
from core.logging_config import get_logger, log_external_call
from src.services.cache import cached, get_usps_cache
from src.services.retry import with_retry

LOGGER = get_logger(__name__)

USPS_API_URL = "https://secure.shippingapis.com/ShippingAPI.dll"


@dataclass
class USPSVerificationResult:
    """Result from USPS Address Verification API."""

    # Standardized address fields
    address1: str  # Street address (e.g., "123 MAIN ST APT 4")
    address2: Optional[str]  # Secondary line (often empty for residential)
    city: str
    state: str
    zip5: str
    zip4: Optional[str]
    
    # Delivery Point Validation
    dpv_confirmation: Optional[str]  # Y=confirmed, N=not confirmed, D=missing secondary, S=missing secondary
    dpv_cmra: Optional[str]  # Y=commercial mail receiving agency
    dpv_vacant: Optional[str]  # Y=vacant
    dpv_no_stat: Optional[str]  # Y=no-stat (undeliverable)
    
    # Additional info
    carrier_route: Optional[str]
    footnotes: Optional[str]
    return_text: Optional[str]
    
    # Metadata
    source: str = "usps"
    verified: bool = True
    
    @property
    def is_valid(self) -> bool:
        """Check if address is confirmed deliverable."""
        return self.dpv_confirmation in ("Y", "D", "S")
    
    @property
    def is_residential(self) -> bool:
        """Check if address is likely residential (not CMRA)."""
        return self.dpv_cmra != "Y"
    
    @property
    def is_vacant(self) -> bool:
        """Check if address is marked as vacant."""
        return self.dpv_vacant == "Y"
    
    @property
    def full_zip(self) -> str:
        """Get full ZIP+4 code."""
        if self.zip4:
            return f"{self.zip5}-{self.zip4}"
        return self.zip5
    
    @property
    def formatted_address(self) -> str:
        """Get formatted address string."""
        parts = [self.address1]
        if self.address2:
            parts.append(self.address2)
        parts.append(f"{self.city}, {self.state} {self.full_zip}")
        return ", ".join(parts)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "address1": self.address1,
            "address2": self.address2,
            "city": self.city,
            "state": self.state,
            "zip5": self.zip5,
            "zip4": self.zip4,
            "full_zip": self.full_zip,
            "formatted_address": self.formatted_address,
            "dpv_confirmation": self.dpv_confirmation,
            "dpv_cmra": self.dpv_cmra,
            "dpv_vacant": self.dpv_vacant,
            "dpv_no_stat": self.dpv_no_stat,
            "carrier_route": self.carrier_route,
            "footnotes": self.footnotes,
            "is_valid": self.is_valid,
            "is_residential": self.is_residential,
            "is_vacant": self.is_vacant,
            "source": self.source,
            "verified": self.verified,
        }


def _create_fallback_result(
    address: str,
    city: str,
    state: str,
    zip_code: Optional[str],
) -> Dict[str, Any]:
    """
    Create a fallback/unverified result when USPS is disabled or fails.
    
    Returns dict with original values and verified=False.
    """
    return {
        "address1": address.upper() if address else "",
        "address2": None,
        "city": city.upper() if city else "",
        "state": state.upper() if state else "",
        "zip5": zip_code or "",
        "zip4": None,
        "full_zip": zip_code or "",
        "formatted_address": f"{address}, {city}, {state} {zip_code or ''}".strip(),
        "dpv_confirmation": None,
        "dpv_cmra": None,
        "dpv_vacant": None,
        "dpv_no_stat": None,
        "carrier_route": None,
        "footnotes": None,
        "is_valid": False,
        "is_residential": True,  # Assume residential by default
        "is_vacant": False,
        "source": "fallback",
        "verified": False,
    }


class USPSService:
    """Service for USPS Web Tools Address Verification API."""

    def __init__(self, user_id: Optional[str] = None):
        """
        Initialize the USPS service.
        
        Args:
            user_id: USPS Web Tools User ID (uses env if not provided).
        """
        settings = get_settings()
        self.user_id = user_id or settings.usps_user_id
        self.timeout = settings.usps_timeout
        self._client: Optional[httpx.Client] = None

    def _get_client(self) -> httpx.Client:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.Client(timeout=self.timeout)
        return self._client

    def _ensure_configured(self) -> None:
        """Ensure service is properly configured."""
        if not self.user_id:
            raise MissingCredentialsError(
                "USPS User ID not configured. Set USPS_USER_ID environment variable. "
                "Register at https://www.usps.com/business/web-tools-apis/"
            )

    def _build_request_xml(
        self,
        address: str,
        city: str,
        state: str,
        zip_code: Optional[str] = None,
    ) -> str:
        """Build the XML request for USPS API."""
        # Parse apartment/unit from address if present
        address1 = ""
        address2 = address

        # Common patterns for secondary address
        secondary_pattern = r"(?:APT|UNIT|STE|SUITE|#)\s*\S+"
        match = re.search(secondary_pattern, address, re.IGNORECASE)
        if match:
            address1 = match.group(0)
            address2 = re.sub(secondary_pattern, "", address, flags=re.IGNORECASE).strip()
            address2 = re.sub(r"\s+", " ", address2)  # Clean up extra spaces

        xml = f"""
        <AddressValidateRequest USERID="{self.user_id}">
            <Revision>1</Revision>
            <Address ID="0">
                <Address1>{address1}</Address1>
                <Address2>{address2}</Address2>
                <City>{city}</City>
                <State>{state}</State>
                <Zip5>{zip_code or ''}</Zip5>
                <Zip4></Zip4>
            </Address>
        </AddressValidateRequest>
        """.strip()

        return xml

    def _parse_response(self, xml_text: str) -> USPSVerificationResult:
        """Parse the USPS API XML response."""
        root = ET.fromstring(xml_text)

        # Check for error
        error = root.find(".//Error")
        if error is not None:
            error_desc = error.findtext("Description", "Unknown error")
            raise USPSVerificationError(f"USPS API error: {error_desc}")

        # Parse address
        address = root.find(".//Address")
        if address is None:
            raise USPSVerificationError("No address in USPS response")

        # Check for address-level error
        addr_error = address.find("Error")
        if addr_error is not None:
            error_desc = addr_error.findtext("Description", "Address error")
            raise USPSVerificationError(f"Address validation failed: {error_desc}")

        return USPSVerificationResult(
            # Note: USPS swaps Address1/Address2 in response (Address2 is primary)
            address1=address.findtext("Address2", ""),
            address2=address.findtext("Address1") or None,
            city=address.findtext("City", ""),
            state=address.findtext("State", ""),
            zip5=address.findtext("Zip5", ""),
            zip4=address.findtext("Zip4") or None,
            dpv_confirmation=address.findtext("DPVConfirmation") or None,
            dpv_cmra=address.findtext("DPVCMRA") or None,
            dpv_vacant=address.findtext("Vacant") or None,
            dpv_no_stat=address.findtext("DPVNoStat") or None,
            carrier_route=address.findtext("CarrierRoute") or None,
            footnotes=address.findtext("Footnotes") or None,
            return_text=address.findtext("ReturnText") or None,
        )

    @with_retry(max_attempts=3, retry_exceptions=(ConnectionError, TimeoutError, httpx.HTTPError))
    def verify_address(
        self,
        address: str,
        city: str,
        state: str,
        zip_code: Optional[str] = None,
    ) -> USPSVerificationResult:
        """
        Verify and standardize an address using USPS.
        
        Args:
            address: Street address line.
            city: City name.
            state: 2-letter state code.
            zip_code: Optional ZIP code.
            
        Returns:
            USPSVerificationResult with standardized address and DPV info.
            
        Raises:
            USPSVerificationError: If verification fails.
            MissingCredentialsError: If API credentials not configured.
        """
        self._ensure_configured()

        start_time = time.perf_counter()
        success = False

        try:
            client = self._get_client()
            request_xml = self._build_request_xml(address, city, state, zip_code)

            response = client.get(
                USPS_API_URL,
                params={
                    "API": "Verify",
                    "XML": request_xml,
                },
            )
            response.raise_for_status()

            result = self._parse_response(response.text)
            success = True
            return result

        except httpx.HTTPError as e:
            raise USPSVerificationError(f"HTTP error during USPS verification: {e}") from e

        finally:
            duration_ms = (time.perf_counter() - start_time) * 1000
            log_external_call(
                LOGGER,
                service="usps",
                operation="verify_address",
                success=success,
                duration_ms=duration_ms,
                city=city,
                state=state,
            )

    def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            self._client.close()
            self._client = None


# Module-level singleton
_service: Optional[USPSService] = None


def get_usps_service() -> USPSService:
    """Get the global USPSService instance."""
    global _service
    if _service is None:
        _service = USPSService()
    return _service


# Convenience function with caching and fallback
@cached(get_usps_cache(), ttl_seconds=168 * 3600, key_prefix="usps_verify")
def verify_address(
    address: str,
    city: str,
    state: str,
    zip_code: Optional[str] = None,
    fallback_on_error: bool = True,
) -> Dict[str, Any]:
    """
    Verify and standardize an address using USPS (cached, with fallback).
    
    Args:
        address: Street address line.
        city: City name.
        state: 2-letter state code.
        zip_code: Optional ZIP code.
        fallback_on_error: If True, return unverified fallback on errors.
        
    Returns:
        Dictionary with standardized address and DPV info.
        If disabled or error: returns fallback dict with verified=False.
    """
    settings = get_settings()
    
    # Check if service is enabled
    if not settings.is_usps_enabled():
        LOGGER.debug("USPS integration is disabled, returning unverified fallback")
        return _create_fallback_result(address, city, state, zip_code)

    try:
        service = get_usps_service()
        result = service.verify_address(address, city, state, zip_code)
        return result.to_dict()
    except (USPSVerificationError, MissingCredentialsError) as e:
        LOGGER.warning(f"USPS verification failed: {e}")
        if fallback_on_error:
            return _create_fallback_result(address, city, state, zip_code)
        raise


__all__ = [
    "USPSService",
    "USPSVerificationResult",
    "verify_address",
    "get_usps_service",
]
