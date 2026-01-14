"""PropStream API integration for property data enrichment.

This module provides a complete client architecture for PropStream API integration.
Credentials should be configured via environment variables when available.

PropStream provides:
- Property details by address or APN
- Owner information and contact data
- Comparable sales (comps)
- Tax and lien history
- Property characteristics
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

import httpx

from core.config import get_settings
from core.exceptions import ExternalServiceError, MissingCredentialsError, RateLimitError
from core.logging_config import get_logger, log_external_call
from src.services.cache import cached
from src.services.retry import with_retry

LOGGER = get_logger(__name__)

# PropStream API endpoints (placeholder - update when credentials available)
PROPSTREAM_BASE_URL = "https://api.propstream.com/v1"


class PropertyType(str, Enum):
    """Property type classifications from PropStream."""
    SINGLE_FAMILY = "SFR"
    MULTI_FAMILY = "MFR"
    VACANT_LAND = "LAND"
    MOBILE_HOME = "MOBILE"
    COMMERCIAL = "COMMERCIAL"
    CONDO = "CONDO"
    TOWNHOUSE = "TOWNHOUSE"
    UNKNOWN = "UNKNOWN"


@dataclass
class PropStreamOwner:
    """Owner information from PropStream."""
    name: str
    mailing_address: Optional[str] = None
    mailing_city: Optional[str] = None
    mailing_state: Optional[str] = None
    mailing_zip: Optional[str] = None
    phone_numbers: List[str] = field(default_factory=list)
    emails: List[str] = field(default_factory=list)
    owner_type: str = "individual"  # individual, corporate, trust, etc.
    is_absentee: bool = False
    years_owned: Optional[int] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "mailing_address": self.mailing_address,
            "mailing_city": self.mailing_city,
            "mailing_state": self.mailing_state,
            "mailing_zip": self.mailing_zip,
            "phone_numbers": self.phone_numbers,
            "emails": self.emails,
            "owner_type": self.owner_type,
            "is_absentee": self.is_absentee,
            "years_owned": self.years_owned,
        }


@dataclass
class PropStreamTaxInfo:
    """Tax information from PropStream."""
    assessed_value: Optional[float] = None
    land_value: Optional[float] = None
    improvement_value: Optional[float] = None
    tax_amount: Optional[float] = None
    tax_year: Optional[int] = None
    is_delinquent: bool = False
    years_delinquent: int = 0
    delinquent_amount: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "assessed_value": self.assessed_value,
            "land_value": self.land_value,
            "improvement_value": self.improvement_value,
            "tax_amount": self.tax_amount,
            "tax_year": self.tax_year,
            "is_delinquent": self.is_delinquent,
            "years_delinquent": self.years_delinquent,
            "delinquent_amount": self.delinquent_amount,
        }


@dataclass
class PropStreamLien:
    """Lien information from PropStream."""
    lien_type: str  # tax, mortgage, mechanic, judgment, etc.
    amount: Optional[float] = None
    holder: Optional[str] = None
    recording_date: Optional[str] = None
    status: str = "active"  # active, released, unknown
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "lien_type": self.lien_type,
            "amount": self.amount,
            "holder": self.holder,
            "recording_date": self.recording_date,
            "status": self.status,
        }


@dataclass
class PropStreamComp:
    """Comparable sale from PropStream."""
    address: str
    sale_price: float
    sale_date: str
    lot_size_acres: Optional[float] = None
    distance_miles: Optional[float] = None
    price_per_acre: Optional[float] = None
    property_type: str = "LAND"
    days_on_market: Optional[int] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "address": self.address,
            "sale_price": self.sale_price,
            "sale_date": self.sale_date,
            "lot_size_acres": self.lot_size_acres,
            "distance_miles": self.distance_miles,
            "price_per_acre": self.price_per_acre,
            "property_type": self.property_type,
            "days_on_market": self.days_on_market,
        }


@dataclass
class PropStreamProperty:
    """Complete property data from PropStream."""
    # Identification
    apn: str
    address: str
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    county: Optional[str] = None
    
    # Property characteristics
    property_type: PropertyType = PropertyType.UNKNOWN
    lot_size_sqft: Optional[float] = None
    lot_size_acres: Optional[float] = None
    building_sqft: Optional[float] = None
    year_built: Optional[int] = None
    bedrooms: Optional[int] = None
    bathrooms: Optional[float] = None
    zoning: Optional[str] = None
    
    # Values
    estimated_value: Optional[float] = None
    last_sale_price: Optional[float] = None
    last_sale_date: Optional[str] = None
    
    # Coordinates
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    
    # Related data
    owner: Optional[PropStreamOwner] = None
    tax_info: Optional[PropStreamTaxInfo] = None
    liens: List[PropStreamLien] = field(default_factory=list)
    comps: List[PropStreamComp] = field(default_factory=list)
    
    # Distress indicators
    is_vacant: bool = False
    is_pre_foreclosure: bool = False
    is_reo: bool = False
    is_probate: bool = False
    is_bankruptcy: bool = False
    
    # Metadata
    source: str = "propstream"
    retrieved_at: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "apn": self.apn,
            "address": self.address,
            "city": self.city,
            "state": self.state,
            "zip_code": self.zip_code,
            "county": self.county,
            "property_type": self.property_type.value,
            "lot_size_sqft": self.lot_size_sqft,
            "lot_size_acres": self.lot_size_acres,
            "building_sqft": self.building_sqft,
            "year_built": self.year_built,
            "bedrooms": self.bedrooms,
            "bathrooms": self.bathrooms,
            "zoning": self.zoning,
            "estimated_value": self.estimated_value,
            "last_sale_price": self.last_sale_price,
            "last_sale_date": self.last_sale_date,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "owner": self.owner.to_dict() if self.owner else None,
            "tax_info": self.tax_info.to_dict() if self.tax_info else None,
            "liens": [l.to_dict() for l in self.liens],
            "comps": [c.to_dict() for c in self.comps],
            "is_vacant": self.is_vacant,
            "is_pre_foreclosure": self.is_pre_foreclosure,
            "is_reo": self.is_reo,
            "is_probate": self.is_probate,
            "is_bankruptcy": self.is_bankruptcy,
            "source": self.source,
            "retrieved_at": self.retrieved_at,
        }


class PropStreamService:
    """
    Service for PropStream API integration.
    
    Provides methods for:
    - Property lookup by address or APN
    - Owner data retrieval
    - Comparable sales lookup
    - Tax and lien history
    
    Configure via environment variables:
    - PROPSTREAM_API_KEY: Your PropStream API key
    - PROPSTREAM_USER_ID: Your PropStream user ID (if required)
    """

    # API timeout in seconds
    TIMEOUT = 30
    
    # Rate limiting
    MAX_REQUESTS_PER_MINUTE = 60

    def __init__(
        self,
        api_key: Optional[str] = None,
        user_id: Optional[str] = None,
    ):
        """
        Initialize the PropStream service.
        
        Args:
            api_key: PropStream API key (uses env if not provided).
            user_id: PropStream user ID (uses env if not provided).
        """
        settings = get_settings()
        
        # Get credentials from settings or parameters
        # NOTE: Add these to your Settings class when you have PropStream credentials
        self.api_key = api_key or getattr(settings, 'propstream_api_key', None)
        self.user_id = user_id or getattr(settings, 'propstream_user_id', None)
        
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

    def _ensure_configured(self) -> None:
        """Ensure service is properly configured."""
        if not self.api_key:
            raise MissingCredentialsError(
                "PropStream API key not configured. Set PROPSTREAM_API_KEY environment variable."
            )

    def _rate_limit(self) -> None:
        """Apply rate limiting between requests."""
        min_interval = 60.0 / self.MAX_REQUESTS_PER_MINUTE
        elapsed = time.time() - self._last_request_time
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)
        self._last_request_time = time.time()

    def is_configured(self) -> bool:
        """Check if PropStream credentials are configured."""
        return bool(self.api_key)

    @with_retry(max_attempts=3, retry_exceptions=(ConnectionError, TimeoutError, httpx.HTTPError))
    def get_property_by_address(
        self,
        address: str,
        city: str,
        state: str,
        zip_code: Optional[str] = None,
    ) -> Optional[PropStreamProperty]:
        """
        Look up a property by address.
        
        Args:
            address: Street address.
            city: City name.
            state: 2-letter state code.
            zip_code: Optional ZIP code.
            
        Returns:
            PropStreamProperty with full property data, or None if not found.
            
        Raises:
            ExternalServiceError: If the API call fails.
            MissingCredentialsError: If credentials not configured.
        """
        self._ensure_configured()
        self._rate_limit()

        start_time = time.perf_counter()
        success = False

        try:
            client = self._get_client()
            
            # Build request payload
            payload = {
                "address": address,
                "city": city,
                "state": state,
            }
            if zip_code:
                payload["zip"] = zip_code

            response = client.post(
                f"{PROPSTREAM_BASE_URL}/property/address",
                json=payload,
            )
            
            if response.status_code == 429:
                raise RateLimitError("PropStream rate limit exceeded")
            
            response.raise_for_status()
            data = response.json()
            
            success = True
            return self._parse_property_response(data)

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise ExternalServiceError(f"PropStream API error: {e}") from e
        except httpx.HTTPError as e:
            raise ExternalServiceError(f"PropStream HTTP error: {e}") from e
        finally:
            duration_ms = (time.perf_counter() - start_time) * 1000
            log_external_call(
                LOGGER,
                service="propstream",
                operation="get_property_by_address",
                success=success,
                duration_ms=duration_ms,
                address=address[:50] if address else None,
            )

    @with_retry(max_attempts=3, retry_exceptions=(ConnectionError, TimeoutError, httpx.HTTPError))
    def get_property_by_apn(
        self,
        apn: str,
        county: str,
        state: str,
    ) -> Optional[PropStreamProperty]:
        """
        Look up a property by APN (Assessor's Parcel Number).
        
        Args:
            apn: The parcel number.
            county: County name.
            state: 2-letter state code.
            
        Returns:
            PropStreamProperty with full property data, or None if not found.
        """
        self._ensure_configured()
        self._rate_limit()

        start_time = time.perf_counter()
        success = False

        try:
            client = self._get_client()
            
            payload = {
                "apn": apn,
                "county": county,
                "state": state,
            }

            response = client.post(
                f"{PROPSTREAM_BASE_URL}/property/apn",
                json=payload,
            )
            
            if response.status_code == 429:
                raise RateLimitError("PropStream rate limit exceeded")
            
            response.raise_for_status()
            data = response.json()
            
            success = True
            return self._parse_property_response(data)

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise ExternalServiceError(f"PropStream API error: {e}") from e
        except httpx.HTTPError as e:
            raise ExternalServiceError(f"PropStream HTTP error: {e}") from e
        finally:
            duration_ms = (time.perf_counter() - start_time) * 1000
            log_external_call(
                LOGGER,
                service="propstream",
                operation="get_property_by_apn",
                success=success,
                duration_ms=duration_ms,
                apn=apn,
            )

    @with_retry(max_attempts=3, retry_exceptions=(ConnectionError, TimeoutError, httpx.HTTPError))
    def get_owner_data(
        self,
        apn: str,
        county: str,
        state: str,
    ) -> Optional[PropStreamOwner]:
        """
        Get owner information for a property.
        
        Args:
            apn: The parcel number.
            county: County name.
            state: 2-letter state code.
            
        Returns:
            PropStreamOwner with owner details, or None if not found.
        """
        self._ensure_configured()
        self._rate_limit()

        start_time = time.perf_counter()
        success = False

        try:
            client = self._get_client()
            
            payload = {
                "apn": apn,
                "county": county,
                "state": state,
            }

            response = client.post(
                f"{PROPSTREAM_BASE_URL}/owner",
                json=payload,
            )
            
            response.raise_for_status()
            data = response.json()
            
            success = True
            return self._parse_owner_response(data)

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise ExternalServiceError(f"PropStream API error: {e}") from e
        except httpx.HTTPError as e:
            raise ExternalServiceError(f"PropStream HTTP error: {e}") from e
        finally:
            duration_ms = (time.perf_counter() - start_time) * 1000
            log_external_call(
                LOGGER,
                service="propstream",
                operation="get_owner_data",
                success=success,
                duration_ms=duration_ms,
            )

    @with_retry(max_attempts=3, retry_exceptions=(ConnectionError, TimeoutError, httpx.HTTPError))
    def get_comps(
        self,
        address: str,
        city: str,
        state: str,
        radius_miles: float = 3.0,
        max_results: int = 10,
        property_type: Optional[str] = None,
        months_back: int = 12,
    ) -> List[PropStreamComp]:
        """
        Get comparable sales for a property.
        
        Args:
            address: Subject property address.
            city: City name.
            state: 2-letter state code.
            radius_miles: Search radius in miles.
            max_results: Maximum comps to return.
            property_type: Filter by property type.
            months_back: How far back to search for sales.
            
        Returns:
            List of PropStreamComp objects.
        """
        self._ensure_configured()
        self._rate_limit()

        start_time = time.perf_counter()
        success = False

        try:
            client = self._get_client()
            
            payload = {
                "address": address,
                "city": city,
                "state": state,
                "radius_miles": radius_miles,
                "max_results": max_results,
                "months_back": months_back,
            }
            
            if property_type:
                payload["property_type"] = property_type

            response = client.post(
                f"{PROPSTREAM_BASE_URL}/comps",
                json=payload,
            )
            
            response.raise_for_status()
            data = response.json()
            
            success = True
            return self._parse_comps_response(data)

        except httpx.HTTPError as e:
            raise ExternalServiceError(f"PropStream HTTP error: {e}") from e
        finally:
            duration_ms = (time.perf_counter() - start_time) * 1000
            log_external_call(
                LOGGER,
                service="propstream",
                operation="get_comps",
                success=success,
                duration_ms=duration_ms,
            )

    @with_retry(max_attempts=3, retry_exceptions=(ConnectionError, TimeoutError, httpx.HTTPError))
    def get_tax_history(
        self,
        apn: str,
        county: str,
        state: str,
    ) -> Optional[PropStreamTaxInfo]:
        """
        Get tax history for a property.
        
        Args:
            apn: The parcel number.
            county: County name.
            state: 2-letter state code.
            
        Returns:
            PropStreamTaxInfo with tax details.
        """
        self._ensure_configured()
        self._rate_limit()

        start_time = time.perf_counter()
        success = False

        try:
            client = self._get_client()
            
            payload = {
                "apn": apn,
                "county": county,
                "state": state,
            }

            response = client.post(
                f"{PROPSTREAM_BASE_URL}/tax",
                json=payload,
            )
            
            response.raise_for_status()
            data = response.json()
            
            success = True
            return self._parse_tax_response(data)

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise ExternalServiceError(f"PropStream API error: {e}") from e
        except httpx.HTTPError as e:
            raise ExternalServiceError(f"PropStream HTTP error: {e}") from e
        finally:
            duration_ms = (time.perf_counter() - start_time) * 1000
            log_external_call(
                LOGGER,
                service="propstream",
                operation="get_tax_history",
                success=success,
                duration_ms=duration_ms,
            )

    @with_retry(max_attempts=3, retry_exceptions=(ConnectionError, TimeoutError, httpx.HTTPError))
    def get_liens(
        self,
        apn: str,
        county: str,
        state: str,
    ) -> List[PropStreamLien]:
        """
        Get liens on a property.
        
        Args:
            apn: The parcel number.
            county: County name.
            state: 2-letter state code.
            
        Returns:
            List of PropStreamLien objects.
        """
        self._ensure_configured()
        self._rate_limit()

        start_time = time.perf_counter()
        success = False

        try:
            client = self._get_client()
            
            payload = {
                "apn": apn,
                "county": county,
                "state": state,
            }

            response = client.post(
                f"{PROPSTREAM_BASE_URL}/liens",
                json=payload,
            )
            
            response.raise_for_status()
            data = response.json()
            
            success = True
            return self._parse_liens_response(data)

        except httpx.HTTPError as e:
            raise ExternalServiceError(f"PropStream HTTP error: {e}") from e
        finally:
            duration_ms = (time.perf_counter() - start_time) * 1000
            log_external_call(
                LOGGER,
                service="propstream",
                operation="get_liens",
                success=success,
                duration_ms=duration_ms,
            )

    def _parse_property_response(self, data: Dict[str, Any]) -> PropStreamProperty:
        """Parse property API response into PropStreamProperty."""
        # Map property type
        prop_type_str = data.get("property_type", "UNKNOWN").upper()
        try:
            prop_type = PropertyType(prop_type_str)
        except ValueError:
            prop_type = PropertyType.UNKNOWN

        # Calculate acres from sqft if needed
        lot_sqft = data.get("lot_size_sqft")
        lot_acres = data.get("lot_size_acres")
        if lot_sqft and not lot_acres:
            lot_acres = lot_sqft / 43560

        # Parse owner if present
        owner = None
        if "owner" in data:
            owner = self._parse_owner_response(data["owner"])

        # Parse tax info if present
        tax_info = None
        if "tax" in data:
            tax_info = self._parse_tax_response(data["tax"])

        # Parse liens if present
        liens = []
        if "liens" in data:
            liens = self._parse_liens_response(data["liens"])

        # Parse comps if present
        comps = []
        if "comps" in data:
            comps = self._parse_comps_response(data["comps"])

        return PropStreamProperty(
            apn=data.get("apn", ""),
            address=data.get("address", ""),
            city=data.get("city"),
            state=data.get("state"),
            zip_code=data.get("zip"),
            county=data.get("county"),
            property_type=prop_type,
            lot_size_sqft=lot_sqft,
            lot_size_acres=lot_acres,
            building_sqft=data.get("building_sqft"),
            year_built=data.get("year_built"),
            bedrooms=data.get("bedrooms"),
            bathrooms=data.get("bathrooms"),
            zoning=data.get("zoning"),
            estimated_value=data.get("estimated_value"),
            last_sale_price=data.get("last_sale_price"),
            last_sale_date=data.get("last_sale_date"),
            latitude=data.get("latitude"),
            longitude=data.get("longitude"),
            owner=owner,
            tax_info=tax_info,
            liens=liens,
            comps=comps,
            is_vacant=data.get("is_vacant", False),
            is_pre_foreclosure=data.get("is_pre_foreclosure", False),
            is_reo=data.get("is_reo", False),
            is_probate=data.get("is_probate", False),
            is_bankruptcy=data.get("is_bankruptcy", False),
            retrieved_at=datetime.utcnow().isoformat(),
        )

    def _parse_owner_response(self, data: Dict[str, Any]) -> PropStreamOwner:
        """Parse owner data from API response."""
        return PropStreamOwner(
            name=data.get("name", "Unknown"),
            mailing_address=data.get("mailing_address"),
            mailing_city=data.get("mailing_city"),
            mailing_state=data.get("mailing_state"),
            mailing_zip=data.get("mailing_zip"),
            phone_numbers=data.get("phone_numbers", []),
            emails=data.get("emails", []),
            owner_type=data.get("owner_type", "individual"),
            is_absentee=data.get("is_absentee", False),
            years_owned=data.get("years_owned"),
        )

    def _parse_tax_response(self, data: Dict[str, Any]) -> PropStreamTaxInfo:
        """Parse tax data from API response."""
        return PropStreamTaxInfo(
            assessed_value=data.get("assessed_value"),
            land_value=data.get("land_value"),
            improvement_value=data.get("improvement_value"),
            tax_amount=data.get("tax_amount"),
            tax_year=data.get("tax_year"),
            is_delinquent=data.get("is_delinquent", False),
            years_delinquent=data.get("years_delinquent", 0),
            delinquent_amount=data.get("delinquent_amount"),
        )

    def _parse_liens_response(self, data: Any) -> List[PropStreamLien]:
        """Parse liens data from API response."""
        if not isinstance(data, list):
            data = data.get("liens", []) if isinstance(data, dict) else []
        
        liens = []
        for item in data:
            liens.append(PropStreamLien(
                lien_type=item.get("lien_type", "unknown"),
                amount=item.get("amount"),
                holder=item.get("holder"),
                recording_date=item.get("recording_date"),
                status=item.get("status", "active"),
            ))
        return liens

    def _parse_comps_response(self, data: Any) -> List[PropStreamComp]:
        """Parse comps data from API response."""
        if not isinstance(data, list):
            data = data.get("comps", []) if isinstance(data, dict) else []
        
        comps = []
        for item in data:
            lot_acres = item.get("lot_size_acres")
            sale_price = item.get("sale_price", 0)
            
            # Calculate price per acre
            ppa = None
            if lot_acres and lot_acres > 0 and sale_price:
                ppa = sale_price / lot_acres
            
            comps.append(PropStreamComp(
                address=item.get("address", "Unknown"),
                sale_price=sale_price,
                sale_date=item.get("sale_date", ""),
                lot_size_acres=lot_acres,
                distance_miles=item.get("distance_miles"),
                price_per_acre=ppa,
                property_type=item.get("property_type", "LAND"),
                days_on_market=item.get("days_on_market"),
            ))
        return comps

    def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            self._client.close()
            self._client = None


# Module-level singleton
_service: Optional[PropStreamService] = None


def get_propstream_service() -> PropStreamService:
    """Get the global PropStreamService instance."""
    global _service
    if _service is None:
        _service = PropStreamService()
    return _service


def is_propstream_available() -> bool:
    """Check if PropStream is configured and available."""
    service = get_propstream_service()
    return service.is_configured()


# =============================================================================
# PropStream Ingestion Interface
# =============================================================================
# This provides a unified interface for PropStream data ingestion.
# When PropStream credentials are available, paste the API key into .env
# and the system will automatically enable real comps data.

@dataclass
class PropStreamIngestionResult:
    """Result of PropStream data ingestion."""
    success: bool
    parcels_enriched: int
    comps_fetched: int
    errors: List[str] = field(default_factory=list)
    duration_seconds: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "parcels_enriched": self.parcels_enriched,
            "comps_fetched": self.comps_fetched,
            "errors": self.errors,
            "duration_seconds": self.duration_seconds,
        }


class PropStreamIngestion:
    """
    Unified interface for PropStream data ingestion.
    
    This class provides a ready-to-use pipeline for enriching leads
    with PropStream data. When PropStream credentials are configured,
    it will automatically fetch:
    - Property details and characteristics
    - Owner contact information
    - Comparable sales data
    - Tax and lien history
    
    Configuration:
        Set in .env:
        - PROPSTREAM_API_KEY=your_api_key
        - PROPSTREAM_USER_ID=your_user_id (if required)
        - ENABLE_PROPSTREAM=true
    """

    def __init__(self, session: Optional[Any] = None):
        """
        Initialize the PropStream ingestion interface.
        
        Args:
            session: Optional database session for persisting data.
        """
        self.session = session
        self.service = get_propstream_service()
        self._errors: List[str] = []

    def is_enabled(self) -> bool:
        """Check if PropStream ingestion is enabled and configured."""
        settings = get_settings()
        return settings.is_propstream_enabled() and self.service.is_configured()

    def enrich_parcel(
        self,
        parcel_id: str,
        address: str,
        city: str,
        state: str,
        county: str,
    ) -> Optional[PropStreamProperty]:
        """
        Enrich a single parcel with PropStream data.
        
        Args:
            parcel_id: The canonical parcel ID (APN).
            address: Street address.
            city: City name.
            state: 2-letter state code.
            county: County/parish name.
            
        Returns:
            PropStreamProperty with enriched data, or None if not found.
        """
        if not self.is_enabled():
            LOGGER.debug("PropStream not enabled, skipping enrichment")
            return None
        
        try:
            # Try by APN first
            result = self.service.get_property_by_apn(
                apn=parcel_id,
                county=county,
                state=state,
            )
            
            if result:
                return result
            
            # Fall back to address lookup
            return self.service.get_property_by_address(
                address=address,
                city=city,
                state=state,
            )
        except Exception as e:
            LOGGER.warning(f"PropStream enrichment failed for {parcel_id}: {e}")
            self._errors.append(f"{parcel_id}: {str(e)}")
            return None

    def get_comps(
        self,
        address: str,
        city: str,
        state: str,
        radius_miles: float = 3.0,
        months_back: int = 12,
    ) -> List[PropStreamComp]:
        """
        Get comparable sales for a property.
        
        Args:
            address: Subject property address.
            city: City name.
            state: 2-letter state code.
            radius_miles: Search radius.
            months_back: How far back to search.
            
        Returns:
            List of comparable sales.
        """
        if not self.is_enabled():
            return []
        
        try:
            return self.service.get_comps(
                address=address,
                city=city,
                state=state,
                radius_miles=radius_miles,
                months_back=months_back,
                property_type="LAND",
            )
        except Exception as e:
            LOGGER.warning(f"PropStream comps fetch failed: {e}")
            self._errors.append(f"comps: {str(e)}")
            return []

    def run_batch_enrichment(
        self,
        parcels: List[Dict[str, str]],
        fetch_comps: bool = True,
    ) -> PropStreamIngestionResult:
        """
        Run batch enrichment on multiple parcels.
        
        Args:
            parcels: List of dicts with parcel_id, address, city, state, county.
            fetch_comps: Whether to also fetch comps for each parcel.
            
        Returns:
            PropStreamIngestionResult with summary.
        """
        import time
        start_time = time.perf_counter()
        
        if not self.is_enabled():
            return PropStreamIngestionResult(
                success=False,
                parcels_enriched=0,
                comps_fetched=0,
                errors=["PropStream not enabled or configured"],
            )
        
        enriched = 0
        comps_count = 0
        self._errors = []
        
        for parcel in parcels:
            try:
                result = self.enrich_parcel(
                    parcel_id=parcel.get("parcel_id", ""),
                    address=parcel.get("address", ""),
                    city=parcel.get("city", ""),
                    state=parcel.get("state", ""),
                    county=parcel.get("county", ""),
                )
                
                if result:
                    enriched += 1
                    
                    # Fetch comps if requested
                    if fetch_comps and result.address:
                        comps = self.get_comps(
                            address=result.address,
                            city=result.city or "",
                            state=result.state or "",
                        )
                        comps_count += len(comps)
                        
            except Exception as e:
                self._errors.append(f"Batch error: {str(e)}")
        
        duration = time.perf_counter() - start_time
        
        return PropStreamIngestionResult(
            success=len(self._errors) == 0,
            parcels_enriched=enriched,
            comps_fetched=comps_count,
            errors=self._errors,
            duration_seconds=duration,
        )


def get_propstream_ingestion(session: Optional[Any] = None) -> PropStreamIngestion:
    """Get a PropStreamIngestion instance."""
    return PropStreamIngestion(session)


__all__ = [
    "PropStreamService",
    "PropStreamProperty",
    "PropStreamOwner",
    "PropStreamTaxInfo",
    "PropStreamLien",
    "PropStreamComp",
    "PropertyType",
    "PropStreamIngestion",
    "PropStreamIngestionResult",
    "get_propstream_service",
    "get_propstream_ingestion",
    "is_propstream_available",
]

