"""
Address Normalization Utilities - PRODUCTION HARDENED

Single source of truth for address display logic.

CRITICAL TRUST RULES:
1. PROPERTY LOCATION (highest trust):
   - Parcel centroid (lat/lng) from GIS
   - Parcel polygon from GIS
   - Situs address from parcel/GIS records
   
2. OWNER CONTACT (lower trust):
   - Mailing address
   - Owner city/state
   - Phone numbers

🚨 MAILING DATA IS NEVER ALLOWED TO SUBSTITUTE FOR PARCEL DATA

If data is missing, the UI MUST say so explicitly.
No silent fallbacks. No "best guess" maps. No demo shortcuts.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, TYPE_CHECKING

if TYPE_CHECKING:
    from core.models import Lead, Parcel, Owner, Party


class DataTrust(str, Enum):
    """Trust level for data sources."""
    VERIFIED_GIS = "verified_gis"  # From parcel/GIS records - highest trust
    PARCEL_RECORD = "parcel_record"  # From tax roll / parcel data
    DERIVED = "derived"  # Computed from other fields
    OWNER_PROVIDED = "owner_provided"  # From mailing/owner records - lower trust
    MISSING = "missing"  # No data available
    

class DataWarning(str, Enum):
    """Explicit warnings for data quality issues."""
    NO_SITUS_ADDRESS = "no_situs_address"
    NO_COORDINATES = "no_coordinates"
    NO_PARCEL = "no_parcel"
    NO_GEOMETRY = "no_geometry"
    GEOCODE_NEEDED = "geocode_needed"
    MAILING_ONLY = "mailing_only"  # Only mailing address available
    UNVERIFIED_LOCATION = "unverified_location"


# US State abbreviations for normalization
STATE_ABBREVIATIONS = {
    'LOUISIANA': 'LA', 'TEXAS': 'TX', 'MISSISSIPPI': 'MS', 
    'ARKANSAS': 'AR', 'ALABAMA': 'AL', 'FLORIDA': 'FL',
    'GEORGIA': 'GA', 'TENNESSEE': 'TN', 'OKLAHOMA': 'OK',
}


def normalize_state(state: Optional[str]) -> Optional[str]:
    """Normalize state to 2-letter abbreviation."""
    if not state:
        return None
    state = state.strip().upper()
    # Already 2-letter
    if len(state) == 2:
        return state
    # Full name
    return STATE_ABBREVIATIONS.get(state, state[:2] if len(state) >= 2 else state)


def normalize_zip(postal_code: Optional[str]) -> Optional[str]:
    """Normalize ZIP to 5 digits."""
    if not postal_code:
        return None
    # Extract just digits
    digits = re.sub(r'[^0-9]', '', str(postal_code))
    # Return first 5 digits if available
    return digits[:5] if len(digits) >= 5 else digits if digits else None


def clean_address_string(raw: Optional[str], state_hint: Optional[str] = None) -> str:
    """
    Clean an address string:
    - Remove duplicate state codes
    - Remove extra commas and spaces
    - Normalize formatting
    """
    if not raw:
        return ""
    
    # Normalize whitespace
    cleaned = ' '.join(raw.split())
    
    # Remove trailing commas
    cleaned = cleaned.rstrip(',').strip()
    
    # If we have a state hint, remove duplicate state at end
    if state_hint:
        state_upper = state_hint.upper()
        # Pattern: ends with ", LA" or " LA" after already having state
        # e.g., "123 Main St, Baton Rouge, LA 70805, LA" -> remove trailing ", LA"
        patterns = [
            rf',\s*{state_upper}\s*$',  # ", LA" at end
            rf'\s+{state_upper}\s*$',   # " LA" at end (if preceded by zip)
        ]
        
        # Count occurrences of state
        state_count = len(re.findall(rf'\b{state_upper}\b', cleaned.upper()))
        if state_count > 1:
            # Remove the last occurrence
            for pattern in patterns:
                new_cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
                if new_cleaned != cleaned:
                    cleaned = new_cleaned.rstrip(',').strip()
                    break
    
    return cleaned


@dataclass
class DisplayLocation:
    """
    Computed display location for a lead.
    
    PRODUCTION RULES:
    1. Property location ONLY comes from parcel/GIS data
    2. If missing, explicitly say so with parcel ID
    3. NEVER show mailing address as property location
    4. NEVER silently fall back to lower-trust data
    """
    # Property location (where the land is) - ONLY from parcel data
    address_line1: Optional[str]
    city: Optional[str]
    state: Optional[str]
    postal_code: Optional[str]
    
    # Parcel identifiers (always required)
    parish: str
    parcel_id: str
    
    # Coordinates for map (only from parcel/GIS)
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    
    # Trust and quality indicators
    data_trust: DataTrust = DataTrust.MISSING
    has_situs_address: bool = False
    has_coordinates: bool = False
    has_geometry: bool = False
    
    # Explicit warnings
    warnings: List[DataWarning] = field(default_factory=list)
    
    @property
    def full_address(self) -> str:
        """
        Full formatted property address.
        
        PRODUCTION BEHAVIOR:
        - If situs exists: show it
        - If missing: EXPLICITLY say "No situs address on file"
        - NEVER guess or substitute mailing address
        """
        if self.has_situs_address and self.address_line1:
            parts = [self.address_line1]
            if self.city:
                parts.append(self.city)
            if self.state and self.postal_code:
                parts.append(f"{self.state} {self.postal_code}")
            elif self.state:
                parts.append(self.state)
            elif self.postal_code:
                parts.append(self.postal_code)
            return ", ".join(parts)
        else:
            # EXPLICIT: No guessing, no fallbacks
            return f"{self.parish} Parish - Parcel {self.parcel_id}"
    
    @property
    def short_address(self) -> str:
        """Short version for list views."""
        if self.has_situs_address and self.address_line1:
            return self.address_line1
        else:
            return f"Parcel {self.parcel_id}"
    
    @property
    def location_descriptor(self) -> str:
        """Location for scripts - ONLY parcel-sourced data."""
        if self.has_situs_address and self.address_line1:
            parts = [self.address_line1]
            if self.city:
                parts.append(self.city)
            if self.state:
                parts.append(self.state)
            return ", ".join(parts)
        else:
            # EXPLICIT: Parcel-only location
            return f"{self.parish} Parish, {self.state or 'LA'}"
    
    @property
    def map_query(self) -> Optional[str]:
        """
        Query string for map search.
        
        PRODUCTION RULES:
        1. If coordinates exist → use them
        2. If situs address exists → use it
        3. Otherwise → return None (no guessing!)
        
        Mailing address is NEVER used for map queries.
        """
        if self.has_coordinates and self.latitude and self.longitude:
            return f"{self.latitude},{self.longitude}"
        elif self.has_situs_address and self.address_line1:
            return self.location_descriptor
        else:
            # NO FALLBACK - return None to indicate map cannot be shown
            return None
    
    @property
    def assessor_search_query(self) -> str:
        """Query for parish assessor search - always available."""
        return f"{self.parish} parish parcel {self.parcel_id}"
    
    @property
    def can_show_map(self) -> bool:
        """
        Whether we can show a verified map for this location.
        
        PRODUCTION RULE: Only if we have coordinates or situs address.
        NEVER based on mailing address or city/state guessing.
        """
        return self.has_coordinates or self.has_situs_address
    
    @property
    def map_trust_level(self) -> str:
        """Human-readable trust level for map display."""
        if self.has_coordinates:
            return "Verified coordinates from parcel records"
        elif self.has_situs_address:
            return "Based on situs address from parcel records"
        else:
            return "No verified location data"
    
    @property
    def missing_data_message(self) -> Optional[str]:
        """
        Explicit message about what data is missing.
        Returns None if all data is present.
        """
        if not self.warnings:
            return None
        
        messages = []
        if DataWarning.NO_SITUS_ADDRESS in self.warnings:
            messages.append("No situs address on file")
        if DataWarning.NO_COORDINATES in self.warnings:
            messages.append("No coordinates available")
        if DataWarning.NO_GEOMETRY in self.warnings:
            messages.append("No parcel boundary available")
        
        return ". ".join(messages) if messages else None
    
    def to_dict(self) -> dict:
        return {
            "address_line1": self.address_line1,
            "city": self.city,
            "state": self.state,
            "postal_code": self.postal_code,
            "parish": self.parish,
            "parcel_id": self.parcel_id,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "data_trust": self.data_trust.value,
            "has_situs_address": self.has_situs_address,
            "has_coordinates": self.has_coordinates,
            "has_geometry": self.has_geometry,
            "full_address": self.full_address,
            "short_address": self.short_address,
            "location_descriptor": self.location_descriptor,
            "map_query": self.map_query,
            "assessor_search_query": self.assessor_search_query,
            "can_show_map": self.can_show_map,
            "map_trust_level": self.map_trust_level,
            "missing_data_message": self.missing_data_message,
            "warnings": [w.value for w in self.warnings],
        }


@dataclass
class MailingAddress:
    """
    Owner mailing address (separate from property location).
    
    CRITICAL: This is for MAIL ONLY - never for property identification.
    """
    # Parsed components
    line1: Optional[str] = None
    line2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    
    # Raw (for fallback)
    raw_address: Optional[str] = None
    
    # Trust indicator
    data_trust: DataTrust = DataTrust.OWNER_PROVIDED
    
    @property
    def display(self) -> str:
        """Clean formatted display."""
        if self.line1:
            parts = [self.line1]
            if self.line2:
                parts.append(self.line2)
            if self.city:
                city_state_zip = self.city
                if self.state:
                    city_state_zip += f", {self.state}"
                if self.postal_code:
                    city_state_zip += f" {self.postal_code}"
                parts.append(city_state_zip)
            elif self.state or self.postal_code:
                parts.append(f"{self.state or ''} {self.postal_code or ''}".strip())
            return ", ".join(parts)
        elif self.raw_address:
            # Clean the raw address
            return clean_address_string(self.raw_address, self.state)
        return "No mailing address on file"
    
    @property
    def is_available(self) -> bool:
        return bool((self.line1 or self.raw_address) and (self.line1 or self.raw_address).strip())
    
    def to_dict(self) -> dict:
        return {
            "line1": self.line1,
            "line2": self.line2,
            "city": self.city,
            "state": self.state,
            "postal_code": self.postal_code,
            "raw_address": self.raw_address,
            "display": self.display,
            "is_available": self.is_available,
            "data_trust": self.data_trust.value,
            # EXPLICIT: This is mailing address, not property location
            "_warning": "This is the owner's mailing address, NOT the property location",
        }


def parse_raw_mailing_address(raw: Optional[str], state_hint: Optional[str] = None) -> MailingAddress:
    """
    Parse a raw mailing address string into components.
    Handles common formats and removes duplicates.
    """
    if not raw or not raw.strip():
        return MailingAddress(data_trust=DataTrust.MISSING)
    
    # Clean the raw string first
    cleaned = clean_address_string(raw, state_hint)
    
    # Try to parse components
    # Common format: "123 Main St, City, ST 12345"
    parts = [p.strip() for p in cleaned.split(',')]
    
    if len(parts) >= 3:
        # Has at least street, city, state/zip
        line1 = parts[0]
        city = parts[1] if len(parts) > 1 else None
        
        # Last part might be "ST 12345" or just "12345"
        last_part = parts[-1] if len(parts) > 2 else ""
        state_zip_match = re.match(r'^([A-Z]{2})\s*(\d{5})?', last_part.upper())
        
        if state_zip_match:
            state = state_zip_match.group(1)
            postal_code = state_zip_match.group(2)
        else:
            # Try to extract just zip
            zip_match = re.search(r'\d{5}', last_part)
            postal_code = zip_match.group(0) if zip_match else None
            state = state_hint
        
        return MailingAddress(
            line1=line1,
            city=city,
            state=normalize_state(state),
            postal_code=normalize_zip(postal_code),
            raw_address=cleaned,
            data_trust=DataTrust.OWNER_PROVIDED,
        )
    elif len(parts) == 2:
        # Might be "123 Main St, City ST 12345"
        line1 = parts[0]
        rest = parts[1]
        
        # Try to parse city/state/zip from rest
        match = re.match(r'^(.+?)\s+([A-Z]{2})\s*(\d{5})?$', rest.upper())
        if match:
            city = rest[:len(match.group(1))]  # Preserve original case
            state = match.group(2)
            postal_code = match.group(3)
        else:
            city = rest
            state = state_hint
            postal_code = None
        
        return MailingAddress(
            line1=line1,
            city=city,
            state=normalize_state(state),
            postal_code=normalize_zip(postal_code),
            raw_address=cleaned,
            data_trust=DataTrust.OWNER_PROVIDED,
        )
    else:
        # Just one part - use as line1
        return MailingAddress(
            line1=cleaned,
            state=normalize_state(state_hint),
            raw_address=cleaned,
            data_trust=DataTrust.OWNER_PROVIDED,
        )


def compute_display_location(lead: "Lead") -> DisplayLocation:
    """
    Compute the display location for a lead.
    
    This is the SINGLE SOURCE OF TRUTH for property location display.
    Use this everywhere: Lead Detail, Deal Sheet, Call Script, Inbox rows.
    
    PRODUCTION RULES:
    1. Property location ONLY from parcel situs address
    2. If missing, EXPLICITLY show parish + parcel id + warning
    3. NEVER show mailing address as property location
    4. NEVER silently fall back or guess
    """
    parcel = lead.parcel
    warnings: List[DataWarning] = []
    
    if parcel:
        # Check data availability
        has_situs = bool(parcel.situs_address and parcel.situs_address.strip())
        has_coords = bool(parcel.latitude and parcel.longitude)
        has_geometry = bool(parcel.geom)
        
        # Build explicit warnings
        if not has_situs:
            warnings.append(DataWarning.NO_SITUS_ADDRESS)
        if not has_coords:
            warnings.append(DataWarning.NO_COORDINATES)
            if has_situs:
                warnings.append(DataWarning.GEOCODE_NEEDED)
        if not has_geometry:
            warnings.append(DataWarning.NO_GEOMETRY)
        
        # Determine trust level
        if has_coords:
            data_trust = DataTrust.VERIFIED_GIS
        elif has_situs:
            data_trust = DataTrust.PARCEL_RECORD
        else:
            data_trust = DataTrust.DERIVED
        
        return DisplayLocation(
            address_line1=parcel.situs_address.strip() if has_situs else None,
            city=parcel.city.strip() if parcel.city else None,
            state=normalize_state(parcel.state) or lead.market_code,
            postal_code=normalize_zip(parcel.postal_code),
            parish=parcel.parish or "Unknown",
            parcel_id=parcel.canonical_parcel_id,
            latitude=parcel.latitude if has_coords else None,
            longitude=parcel.longitude if has_coords else None,
            data_trust=data_trust,
            has_situs_address=has_situs,
            has_coordinates=has_coords,
            has_geometry=has_geometry,
            warnings=warnings,
        )
    else:
        # No parcel - CRITICAL: This is a data quality issue
        return DisplayLocation(
            address_line1=None,
            city=None,
            state=lead.market_code,
            postal_code=None,
            parish="Unknown",
            parcel_id="Unknown",
            data_trust=DataTrust.MISSING,
            has_situs_address=False,
            has_coordinates=False,
            has_geometry=False,
            warnings=[DataWarning.NO_PARCEL],
        )


def compute_mailing_address(lead: "Lead") -> MailingAddress:
    """
    Get the owner's mailing address.
    
    CRITICAL: This is SEPARATE from property location.
    Used for direct mail outreach only.
    NEVER use this for property identification or maps.
    """
    owner = lead.owner
    party = owner.party if owner else None
    
    raw_address = party.raw_mailing_address if party else None
    state_hint = lead.market_code if lead else None
    
    return parse_raw_mailing_address(raw_address, state_hint)


def format_lead_location_summary(lead: "Lead") -> dict:
    """
    Complete location summary for API responses.
    
    Returns both property location and mailing address,
    clearly separated with explicit trust indicators.
    """
    location = compute_display_location(lead)
    mailing = compute_mailing_address(lead)
    
    return {
        "property_location": location.to_dict(),
        "mailing_address": mailing.to_dict(),
        # EXPLICIT: Warn if there's a risk of confusion
        "_trust_warning": (
            "property_location is from parcel/GIS records. "
            "mailing_address is the owner's mail address - NEVER use for property identification."
        ),
    }


# =============================================================================
# REGRESSION GUARDS - These assertions catch trust violations
# =============================================================================

def assert_property_location_not_mailing(
    property_location: DisplayLocation,
    mailing_address: MailingAddress,
) -> None:
    """
    REGRESSION GUARD: Ensure property location is not derived from mailing address.
    
    Raises AssertionError if mailing address appears to be used as property location.
    """
    if not property_location.has_situs_address:
        # If no situs, property should show parcel ID only
        assert property_location.address_line1 is None, \
            "Property location has address_line1 but no situs - possible mailing address leak"
    
    if property_location.address_line1 and mailing_address.line1:
        # If both have addresses, they should not be identical
        prop_clean = property_location.address_line1.lower().strip()
        mail_clean = mailing_address.line1.lower().strip()
        
        # Allow some similarity (owner may live at property) but flag if identical
        if prop_clean == mail_clean:
            # This is OK if situs actually exists
            assert property_location.has_situs_address, \
                "Property address matches mailing address but no situs flag - possible data leak"


def assert_map_not_from_mailing(
    property_location: DisplayLocation,
    mailing_address: MailingAddress,
) -> None:
    """
    REGRESSION GUARD: Ensure map query is not derived from mailing address.
    
    Raises AssertionError if map query appears to use mailing data.
    """
    map_query = property_location.map_query
    
    if map_query and mailing_address.line1:
        mail_clean = mailing_address.line1.lower().strip()
        
        # Map query should never contain mailing address (unless it's also situs)
        if mail_clean in map_query.lower() and not property_location.has_situs_address:
            raise AssertionError(
                f"Map query contains mailing address but no situs: {map_query}"
            )


__all__ = [
    "DataTrust",
    "DataWarning",
    "DisplayLocation",
    "MailingAddress",
    "compute_display_location",
    "compute_mailing_address",
    "format_lead_location_summary",
    "parse_raw_mailing_address",
    "clean_address_string",
    "normalize_state",
    "normalize_zip",
    "assert_property_location_not_mailing",
    "assert_map_not_from_mailing",
]
