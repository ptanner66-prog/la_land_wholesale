"""External Data Service Orchestrator with full fallback support.

Coordinates all external data enrichment services:
- USPS Address Verification
- Google Maps Geocoding
- Comparable Sales (Zillow/Redfin)
- County Records Scraping

All services are wrapped with:
- Feature flag checks
- Graceful fallbacks (one failing service does NOT break the pipeline)
- Structured logging
- Error isolation
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.config import get_settings
from core.logging_config import get_logger, log_external_call

LOGGER = get_logger(__name__)


@dataclass
class EnrichmentSummary:
    """
    Summary of enrichment operations performed.
    
    Tracks which services were called, which succeeded, and timing.
    """
    
    services_called: List[str] = field(default_factory=list)
    services_succeeded: List[str] = field(default_factory=list)
    services_failed: List[str] = field(default_factory=list)
    services_skipped: List[str] = field(default_factory=list)
    total_duration_ms: float = 0.0
    timestamp: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "services_called": self.services_called,
            "services_succeeded": self.services_succeeded,
            "services_failed": self.services_failed,
            "services_skipped": self.services_skipped,
            "total_duration_ms": round(self.total_duration_ms, 2),
            "timestamp": self.timestamp,
            "success_rate": self._success_rate(),
        }
    
    def _success_rate(self) -> float:
        """Calculate success rate."""
        total = len(self.services_called)
        if total == 0:
            return 1.0
        return len(self.services_succeeded) / total


@dataclass
class EnrichedLeadData:
    """
    Enriched data collected from external services.
    
    Contains all available external data for a lead/property.
    Each field has a verified flag to indicate data quality.
    """
    
    # Original input
    original_address: str
    original_city: str
    original_state: str
    original_zip: Optional[str]
    
    # USPS Verification
    usps_verified: bool = False
    usps_standardized_address: Optional[str] = None
    usps_city: Optional[str] = None
    usps_state: Optional[str] = None
    usps_zip5: Optional[str] = None
    usps_zip4: Optional[str] = None
    usps_dpv_confirmed: bool = False
    usps_is_residential: bool = True
    usps_is_vacant: bool = False
    
    # Geocoding
    geocoded: bool = False
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    geocode_formatted_address: Optional[str] = None
    geocode_county: Optional[str] = None
    
    # Comparable Sales
    comps_available: bool = False
    comp_count: int = 0
    median_estimated_value: Optional[int] = None
    median_sold_price: Optional[int] = None
    avg_price_per_sqft: Optional[float] = None
    comps_data: List[Dict[str, Any]] = field(default_factory=list)
    
    # County Records
    county_records_available: bool = False
    county_sale_records: List[Dict[str, Any]] = field(default_factory=list)
    
    # Enrichment metadata
    summary: Optional[EnrichmentSummary] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            # Original
            "original": {
                "address": self.original_address,
                "city": self.original_city,
                "state": self.original_state,
                "zip": self.original_zip,
            },
            # USPS
            "usps": {
                "verified": self.usps_verified,
                "standardized_address": self.usps_standardized_address,
                "city": self.usps_city,
                "state": self.usps_state,
                "zip5": self.usps_zip5,
                "zip4": self.usps_zip4,
                "dpv_confirmed": self.usps_dpv_confirmed,
                "is_residential": self.usps_is_residential,
                "is_vacant": self.usps_is_vacant,
            },
            # Geocoding
            "geocode": {
                "success": self.geocoded,
                "latitude": self.latitude,
                "longitude": self.longitude,
                "formatted_address": self.geocode_formatted_address,
                "county": self.geocode_county,
            },
            # Comps
            "comps": {
                "available": self.comps_available,
                "count": self.comp_count,
                "median_estimated_value": self.median_estimated_value,
                "median_sold_price": self.median_sold_price,
                "avg_price_per_sqft": self.avg_price_per_sqft,
                "properties": self.comps_data,
            },
            # County
            "county_records": {
                "available": self.county_records_available,
                "records": self.county_sale_records,
            },
            # Metadata
            "summary": self.summary.to_dict() if self.summary else None,
        }
    
    @property
    def best_address(self) -> str:
        """Get the best available standardized address."""
        if self.usps_verified and self.usps_standardized_address:
            return self.usps_standardized_address
        if self.geocode_formatted_address:
            return self.geocode_formatted_address
        return f"{self.original_address}, {self.original_city}, {self.original_state} {self.original_zip or ''}"
    
    @property
    def best_city(self) -> str:
        """Get the best available city."""
        if self.usps_verified and self.usps_city:
            return self.usps_city
        return self.original_city
    
    @property
    def best_state(self) -> str:
        """Get the best available state."""
        if self.usps_verified and self.usps_state:
            return self.usps_state
        return self.original_state
    
    @property
    def best_zip(self) -> Optional[str]:
        """Get the best available ZIP code."""
        if self.usps_verified and self.usps_zip5:
            return self.usps_zip5
        return self.original_zip
    
    @property
    def has_coordinates(self) -> bool:
        """Check if we have geocoded coordinates."""
        return self.latitude is not None and self.longitude is not None
    
    @property
    def is_verified(self) -> bool:
        """Check if address was verified by any source."""
        return self.usps_verified or self.geocoded


class ExternalDataService:
    """
    Orchestrator for external data enrichment services.
    
    Coordinates calls to USPS, Google Maps, Comps, and County services
    with proper error handling, caching, and feature flag checks.
    
    IMPORTANT: One failing service does NOT break the pipeline.
    Each service call is isolated and wrapped with try/except.
    """

    def __init__(self):
        """Initialize the external data service."""
        self.settings = get_settings()

    def _run_usps_verification(
        self,
        result: EnrichedLeadData,
        summary: EnrichmentSummary,
        address: str,
        city: str,
        state: str,
        zip_code: Optional[str],
    ) -> tuple[str, str, str, Optional[str]]:
        """
        Run USPS verification and update result.
        
        Returns: (lookup_address, lookup_city, lookup_state, lookup_zip)
        """
        lookup_address = address
        lookup_city = city
        lookup_state = state
        lookup_zip = zip_code
        
        if not self.settings.is_usps_enabled():
            summary.services_skipped.append("usps")
            LOGGER.debug("USPS disabled, skipping")
            return lookup_address, lookup_city, lookup_state, lookup_zip
        
        summary.services_called.append("usps")
        
        try:
            from services.usps import verify_address
            
            usps_result = verify_address(address, city, state, zip_code, fallback_on_error=True)
            
            if usps_result and usps_result.get("verified", False):
                result.usps_verified = True
                result.usps_standardized_address = usps_result.get("address1")
                result.usps_city = usps_result.get("city")
                result.usps_state = usps_result.get("state")
                result.usps_zip5 = usps_result.get("zip5")
                result.usps_zip4 = usps_result.get("zip4")
                result.usps_dpv_confirmed = usps_result.get("is_valid", False)
                result.usps_is_residential = usps_result.get("is_residential", True)
                result.usps_is_vacant = usps_result.get("is_vacant", False)
                
                # Use standardized address for subsequent lookups
                if result.usps_standardized_address:
                    lookup_address = result.usps_standardized_address
                if result.usps_city:
                    lookup_city = result.usps_city
                if result.usps_state:
                    lookup_state = result.usps_state
                if result.usps_zip5:
                    lookup_zip = result.usps_zip5
                
                summary.services_succeeded.append("usps")
                LOGGER.info(f"USPS verified: {result.usps_standardized_address}")
            else:
                # Got fallback result, record as partial success
                summary.services_succeeded.append("usps")
                LOGGER.info("USPS returned fallback (unverified)")
                
        except Exception as e:
            summary.services_failed.append("usps")
            LOGGER.warning(f"USPS verification failed: {e}")
        
        return lookup_address, lookup_city, lookup_state, lookup_zip

    def _run_geocoding(
        self,
        result: EnrichedLeadData,
        summary: EnrichmentSummary,
        address: str,
        city: str,
        state: str,
        zip_code: Optional[str],
    ) -> None:
        """Run Google Maps geocoding and update result."""
        if not self.settings.is_google_enabled():
            summary.services_skipped.append("google_maps")
            LOGGER.debug("Google Maps disabled, skipping")
            return
        
        summary.services_called.append("google_maps")
        
        try:
            from services.google_maps import geocode
            
            full_address = f"{address}, {city}, {state} {zip_code or ''}"
            geocode_result = geocode(full_address, fallback_on_error=True)
            
            if geocode_result:
                # Check if we got real data or fallback
                if geocode_result.get("verified", False):
                    result.geocoded = True
                    result.latitude = geocode_result.get("lat")
                    result.longitude = geocode_result.get("lng")
                    result.geocode_formatted_address = geocode_result.get("formatted_address")
                    result.geocode_county = geocode_result.get("county")
                    summary.services_succeeded.append("google_maps")
                    LOGGER.info(f"Geocoded to: ({result.latitude}, {result.longitude})")
                else:
                    # Fallback result
                    summary.services_succeeded.append("google_maps")
                    LOGGER.info("Google Maps returned fallback")
                    
        except Exception as e:
            summary.services_failed.append("google_maps")
            LOGGER.warning(f"Geocoding failed: {e}")

    def _run_comps(
        self,
        result: EnrichedLeadData,
        summary: EnrichmentSummary,
        address: str,
        zip_code: Optional[str],
    ) -> None:
        """Run comps lookup and update result."""
        if not self.settings.is_comps_enabled():
            summary.services_skipped.append("comps")
            LOGGER.debug("Comps disabled, skipping")
            return
        
        if not zip_code:
            summary.services_skipped.append("comps")
            LOGGER.debug("No ZIP code, skipping comps")
            return
        
        summary.services_called.append("comps")
        
        try:
            from services.comps import get_comps
            
            comps_result = get_comps(address, zip_code, fallback_on_error=True)
            
            if comps_result and comps_result.get("available", False):
                result.comps_available = True
                result.comp_count = comps_result.get("comp_count", 0)
                result.median_estimated_value = comps_result.get("median_estimated_value")
                result.median_sold_price = comps_result.get("median_sold_price")
                result.avg_price_per_sqft = comps_result.get("avg_price_per_sqft")
                result.comps_data = comps_result.get("comps", [])
                summary.services_succeeded.append("comps")
                LOGGER.info(f"Found {result.comp_count} comps")
            else:
                # Fallback result
                summary.services_succeeded.append("comps")
                LOGGER.info("Comps returned fallback (empty)")
                
        except Exception as e:
            summary.services_failed.append("comps")
            LOGGER.warning(f"Comps lookup failed: {e}")

    def _run_county_scraper(
        self,
        result: EnrichedLeadData,
        summary: EnrichmentSummary,
    ) -> None:
        """Run county records scraper and update result."""
        if not self.settings.is_county_scraper_enabled():
            summary.services_skipped.append("county_scraper")
            LOGGER.debug("County scraper disabled, skipping")
            return
        
        summary.services_called.append("county_scraper")
        
        try:
            from services.county_scraper import scrape_recent_sales
            
            county_result = scrape_recent_sales(days_back=30, limit=10)
            
            if county_result and county_result.get("available", False):
                result.county_records_available = True
                result.county_sale_records = county_result.get("records", [])
                summary.services_succeeded.append("county_scraper")
                LOGGER.info(f"Found {len(result.county_sale_records)} county records")
            else:
                summary.services_succeeded.append("county_scraper")
                LOGGER.info("County scraper returned fallback")
                
        except Exception as e:
            summary.services_failed.append("county_scraper")
            LOGGER.warning(f"County scraping failed: {e}")

    def enrich_address(
        self,
        address: str,
        city: str,
        state: str,
        zip_code: Optional[str] = None,
        include_usps: bool = True,
        include_geocode: bool = True,
        include_comps: bool = True,
        include_county: bool = False,
    ) -> EnrichedLeadData:
        """
        Enrich an address with all available external data.
        
        Each service is called independently with proper error isolation.
        One failing service does NOT break the pipeline.
        
        Args:
            address: Street address.
            city: City name.
            state: State code (2 letters).
            zip_code: ZIP code (optional).
            include_usps: Whether to verify with USPS.
            include_geocode: Whether to geocode the address.
            include_comps: Whether to fetch comparable sales.
            include_county: Whether to check county records.
            
        Returns:
            EnrichedLeadData with all available enrichment data.
        """
        start_time = time.perf_counter()
        
        # Initialize result
        result = EnrichedLeadData(
            original_address=address,
            original_city=city,
            original_state=state,
            original_zip=zip_code,
        )
        
        # Initialize summary
        summary = EnrichmentSummary()
        
        # Use the address for lookups (may be updated by USPS)
        lookup_address = address
        lookup_city = city
        lookup_state = state
        lookup_zip = zip_code

        # 1. USPS Verification (first, as it standardizes the address)
        if include_usps:
            lookup_address, lookup_city, lookup_state, lookup_zip = self._run_usps_verification(
                result, summary, address, city, state, zip_code
            )

        # 2. Google Maps Geocoding (uses standardized address if available)
        if include_geocode:
            self._run_geocoding(
                result, summary, lookup_address, lookup_city, lookup_state, lookup_zip
            )

        # 3. Comparable Sales
        if include_comps:
            self._run_comps(result, summary, lookup_address, lookup_zip)

        # 4. County Records (optional, typically slower)
        if include_county:
            self._run_county_scraper(result, summary)

        # Finalize summary
        summary.total_duration_ms = (time.perf_counter() - start_time) * 1000
        summary.timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ")
        result.summary = summary
        
        log_external_call(
            LOGGER,
            service="external_data",
            operation="enrich_address",
            success=len(summary.services_failed) == 0,
            duration_ms=summary.total_duration_ms,
            services_called=len(summary.services_called),
            services_succeeded=len(summary.services_succeeded),
            services_failed=len(summary.services_failed),
        )
        
        return result

    def quick_verify(
        self,
        address: str,
        city: str,
        state: str,
        zip_code: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Quick verification with USPS only.
        
        For fast address standardization without full enrichment.
        """
        result = self.enrich_address(
            address=address,
            city=city,
            state=state,
            zip_code=zip_code,
            include_usps=True,
            include_geocode=False,
            include_comps=False,
            include_county=False,
        )
        
        return {
            "valid": result.usps_verified and result.usps_dpv_confirmed,
            "standardized_address": result.best_address,
            "city": result.best_city,
            "state": result.best_state,
            "zip": result.best_zip,
            "is_residential": result.usps_is_residential,
            "is_vacant": result.usps_is_vacant,
        }

    def get_coordinates(
        self,
        address: str,
        city: str,
        state: str,
        zip_code: Optional[str] = None,
    ) -> Optional[Dict[str, float]]:
        """
        Get coordinates for an address.
        
        Returns dict with 'lat' and 'lng' keys, or None if not found.
        """
        result = self.enrich_address(
            address=address,
            city=city,
            state=state,
            zip_code=zip_code,
            include_usps=True,  # For better address
            include_geocode=True,
            include_comps=False,
            include_county=False,
        )
        
        if result.has_coordinates:
            return {"lat": result.latitude, "lng": result.longitude}
        return None

    def get_property_value_estimate(
        self,
        address: str,
        city: str,
        state: str,
        zip_code: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Get property value estimate from comps.
        
        Returns estimated value data or None if not available.
        """
        result = self.enrich_address(
            address=address,
            city=city,
            state=state,
            zip_code=zip_code,
            include_usps=False,
            include_geocode=False,
            include_comps=True,
            include_county=False,
        )
        
        if result.comps_available:
            return {
                "median_estimated_value": result.median_estimated_value,
                "median_sold_price": result.median_sold_price,
                "avg_price_per_sqft": result.avg_price_per_sqft,
                "comp_count": result.comp_count,
            }
        return None


# Module-level singleton
_service: Optional[ExternalDataService] = None


def get_external_data_service() -> ExternalDataService:
    """Get the global ExternalDataService instance."""
    global _service
    if _service is None:
        _service = ExternalDataService()
    return _service


__all__ = [
    "ExternalDataService",
    "EnrichedLeadData",
    "EnrichmentSummary",
    "get_external_data_service",
]
