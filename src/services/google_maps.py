"""Google Maps Geocoding API integration with fallback support."""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

import httpx

from core.config import get_settings
from core.exceptions import GeocodeError, MissingCredentialsError, RateLimitError
from core.logging_config import get_logger, log_external_call
from src.services.cache import cached, get_geocode_cache
from src.services.retry import with_retry

LOGGER = get_logger(__name__)

GEOCODE_BASE_URL = "https://maps.googleapis.com/maps/api/geocode/json"


@dataclass
class GeocodeResult:
    """Result from Google Maps Geocoding API."""

    lat: float
    lng: float
    formatted_address: str
    place_id: Optional[str] = None
    street_number: Optional[str] = None
    route: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    county: Optional[str] = None
    country: str = "US"
    source: str = "google_maps"
    verified: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "lat": self.lat,
            "lng": self.lng,
            "formatted_address": self.formatted_address,
            "place_id": self.place_id,
            "street_number": self.street_number,
            "route": self.route,
            "city": self.city,
            "state": self.state,
            "postal_code": self.postal_code,
            "county": self.county,
            "country": self.country,
            "source": self.source,
            "verified": self.verified,
        }


def _create_fallback_result(address: str) -> Dict[str, Any]:
    """
    Create a fallback result when geocoding is disabled or fails.
    
    Returns dict with lat/lng as None and verified=False.
    """
    return {
        "lat": None,
        "lng": None,
        "formatted_address": address,
        "place_id": None,
        "street_number": None,
        "route": None,
        "city": None,
        "state": None,
        "postal_code": None,
        "county": None,
        "country": "US",
        "source": "fallback",
        "verified": False,
    }


class GoogleMapsService:
    """Service for Google Maps Geocoding API."""

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the Google Maps service.
        
        Args:
            api_key: Google Maps API key (uses env if not provided).
        """
        settings = get_settings()
        self.api_key = api_key or settings.google_maps_api_key
        self.timeout = settings.google_geocode_timeout
        self._client: Optional[httpx.Client] = None

    def _get_client(self) -> httpx.Client:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.Client(timeout=self.timeout)
        return self._client

    def _ensure_configured(self) -> None:
        """Ensure service is properly configured."""
        if not self.api_key:
            raise MissingCredentialsError(
                "Google Maps API key not configured. Set GOOGLE_MAPS_API_KEY environment variable."
            )

    def _parse_address_components(self, components: list[Dict[str, Any]]) -> Dict[str, str]:
        """Parse address components from Google response."""
        result: Dict[str, str] = {}
        
        type_mapping = {
            "street_number": "street_number",
            "route": "route",
            "locality": "city",
            "administrative_area_level_1": "state",
            "administrative_area_level_2": "county",
            "postal_code": "postal_code",
            "country": "country",
        }

        for component in components:
            for comp_type in component.get("types", []):
                if comp_type in type_mapping:
                    result[type_mapping[comp_type]] = component.get("short_name", "")
                    break

        return result

    @with_retry(max_attempts=3, retry_exceptions=(ConnectionError, TimeoutError, httpx.HTTPError))
    def geocode(self, address: str) -> Optional[GeocodeResult]:
        """
        Geocode an address to coordinates.
        
        Args:
            address: Full address string to geocode.
            
        Returns:
            GeocodeResult with coordinates and parsed address, or None if not found.
            
        Raises:
            GeocodeError: If the API returns an error.
            MissingCredentialsError: If API key is not configured.
        """
        self._ensure_configured()

        start_time = time.perf_counter()
        success = False

        try:
            client = self._get_client()
            response = client.get(
                GEOCODE_BASE_URL,
                params={
                    "address": address,
                    "key": self.api_key,
                    "components": "country:US",
                },
            )
            response.raise_for_status()
            data = response.json()

            status = data.get("status")
            if status == "OK":
                results = data.get("results", [])
                if results:
                    result = results[0]
                    location = result["geometry"]["location"]
                    components = self._parse_address_components(
                        result.get("address_components", [])
                    )

                    success = True
                    return GeocodeResult(
                        lat=location["lat"],
                        lng=location["lng"],
                        formatted_address=result.get("formatted_address", address),
                        place_id=result.get("place_id"),
                        **components,
                    )

            elif status == "ZERO_RESULTS":
                LOGGER.warning(f"No geocode results for address: {address}")
                success = True  # Not an error, just no results
                return None

            elif status == "OVER_QUERY_LIMIT":
                raise RateLimitError("Google Maps API quota exceeded")

            elif status in ("REQUEST_DENIED", "INVALID_REQUEST"):
                error_msg = data.get("error_message", status)
                raise GeocodeError(f"Google Maps API error: {error_msg}")

            else:
                raise GeocodeError(f"Unexpected status from Google Maps API: {status}")

        except httpx.HTTPError as e:
            raise GeocodeError(f"HTTP error during geocoding: {e}") from e

        finally:
            duration_ms = (time.perf_counter() - start_time) * 1000
            log_external_call(
                LOGGER,
                service="google_maps",
                operation="geocode",
                success=success,
                duration_ms=duration_ms,
                address=address[:50] if address else None,
            )

    @with_retry(max_attempts=3, retry_exceptions=(ConnectionError, TimeoutError, httpx.HTTPError))
    def reverse_geocode(self, lat: float, lng: float) -> Optional[GeocodeResult]:
        """
        Reverse geocode coordinates to an address.
        
        Args:
            lat: Latitude.
            lng: Longitude.
            
        Returns:
            GeocodeResult with address details, or None if not found.
            
        Raises:
            GeocodeError: If the API returns an error.
            MissingCredentialsError: If API key is not configured.
        """
        self._ensure_configured()

        start_time = time.perf_counter()
        success = False

        try:
            client = self._get_client()
            response = client.get(
                GEOCODE_BASE_URL,
                params={
                    "latlng": f"{lat},{lng}",
                    "key": self.api_key,
                },
            )
            response.raise_for_status()
            data = response.json()

            status = data.get("status")
            if status == "OK":
                results = data.get("results", [])
                if results:
                    result = results[0]
                    components = self._parse_address_components(
                        result.get("address_components", [])
                    )

                    success = True
                    return GeocodeResult(
                        lat=lat,
                        lng=lng,
                        formatted_address=result.get("formatted_address", ""),
                        place_id=result.get("place_id"),
                        **components,
                    )

            elif status == "ZERO_RESULTS":
                success = True
                return None

            elif status == "OVER_QUERY_LIMIT":
                raise RateLimitError("Google Maps API quota exceeded")

            else:
                raise GeocodeError(f"Google Maps API error: {status}")

        except httpx.HTTPError as e:
            raise GeocodeError(f"HTTP error during reverse geocoding: {e}") from e

        finally:
            duration_ms = (time.perf_counter() - start_time) * 1000
            log_external_call(
                LOGGER,
                service="google_maps",
                operation="reverse_geocode",
                success=success,
                duration_ms=duration_ms,
                lat=lat,
                lng=lng,
            )

    def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            self._client.close()
            self._client = None


# Module-level singleton
_service: Optional[GoogleMapsService] = None


def get_google_maps_service() -> GoogleMapsService:
    """Get the global GoogleMapsService instance."""
    global _service
    if _service is None:
        _service = GoogleMapsService()
    return _service


# Convenience functions with caching and fallback
@cached(get_geocode_cache(), ttl_seconds=168 * 3600, key_prefix="geocode")
def geocode(address: str, fallback_on_error: bool = True) -> Optional[Dict[str, Any]]:
    """
    Geocode an address (cached, with fallback support).
    
    Args:
        address: Full address string.
        fallback_on_error: If True, return fallback result on errors instead of None.
        
    Returns:
        Dictionary with geocode results.
        If disabled or error: returns fallback dict with lat/lng=None if fallback_on_error=True.
    """
    settings = get_settings()
    
    # Check if service is enabled
    if not settings.is_google_enabled():
        LOGGER.debug("Google Maps integration is disabled, returning fallback")
        return _create_fallback_result(address) if fallback_on_error else None

    try:
        service = get_google_maps_service()
        result = service.geocode(address)
        return result.to_dict() if result else (_create_fallback_result(address) if fallback_on_error else None)
    except (GeocodeError, MissingCredentialsError) as e:
        LOGGER.warning(f"Geocoding failed: {e}")
        return _create_fallback_result(address) if fallback_on_error else None


@cached(get_geocode_cache(), ttl_seconds=168 * 3600, key_prefix="reverse_geocode")
def reverse_geocode(lat: float, lng: float) -> Optional[Dict[str, Any]]:
    """
    Reverse geocode coordinates (cached).
    
    Args:
        lat: Latitude.
        lng: Longitude.
        
    Returns:
        Dictionary with address details, or None if not found/disabled.
    """
    settings = get_settings()
    
    if not settings.is_google_enabled():
        LOGGER.debug("Google Maps integration is disabled")
        return None

    try:
        service = get_google_maps_service()
        result = service.reverse_geocode(lat, lng)
        return result.to_dict() if result else None
    except (GeocodeError, MissingCredentialsError) as e:
        LOGGER.warning(f"Reverse geocoding failed: {e}")
        return None


__all__ = [
    "GoogleMapsService",
    "GeocodeResult",
    "geocode",
    "reverse_geocode",
    "get_google_maps_service",
]
