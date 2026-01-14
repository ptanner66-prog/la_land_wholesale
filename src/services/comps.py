"""Comps (comparable sales) service with real API wrapper and fallback."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import List, Optional
import random

from sqlalchemy.orm import Session

from core.config import get_settings
from core.logging_config import get_logger
from core.models import Parcel
from core.utils import utcnow, CircuitBreaker

LOGGER = get_logger(__name__)
SETTINGS = get_settings()


@dataclass
class CompSale:
    """A comparable property sale."""
    
    address: str
    sale_date: str  # ISO format
    sale_price: float
    lot_size_acres: float
    price_per_acre: float
    distance_miles: Optional[float] = None
    source: str = "unknown"  # "api", "mock", "cache"
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "address": self.address,
            "sale_date": self.sale_date,
            "sale_price": round(self.sale_price, 2),
            "lot_size_acres": round(self.lot_size_acres, 4),
            "price_per_acre": round(self.price_per_acre, 2),
            "distance_miles": round(self.distance_miles, 2) if self.distance_miles else None,
            "source": self.source,
        }


@dataclass
class CompsResult:
    """Result from comps lookup."""
    
    comps: List[CompSale] = field(default_factory=list)
    avg_price_per_acre: float = 0.0
    min_price_per_acre: float = 0.0
    max_price_per_acre: float = 0.0
    median_price_per_acre: Optional[float] = None
    total_comps_found: int = 0
    is_mock_data: bool = False
    source: str = "unknown"
    error: Optional[str] = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "comps": [c.to_dict() for c in self.comps],
            "avg_price_per_acre": round(self.avg_price_per_acre, 2),
            "min_price_per_acre": round(self.min_price_per_acre, 2),
            "max_price_per_acre": round(self.max_price_per_acre, 2),
            "median_price_per_acre": round(self.median_price_per_acre, 2) if self.median_price_per_acre else None,
            "total_comps_found": self.total_comps_found,
            "is_mock_data": self.is_mock_data,
            "source": self.source,
            "error": self.error,
        }


# Circuit breaker for comps API
_comps_circuit_breaker = CircuitBreaker(
    name="comps_api",
    failure_threshold=3,
    recovery_timeout=300,  # 5 minutes
)


class CompsService:
    """
    Service for fetching and analyzing comparable sales.
    
    FIXED: Now tries real API first, falls back to mock data,
    and clearly marks mock data in results.
    """

    def __init__(self, session: Optional[Session] = None):
        """Initialize the comps service."""
        self.session = session
        self.circuit_breaker = _comps_circuit_breaker

    def get_comps_for_parcel(
        self,
        parcel: Parcel,
        max_comps: int = 5,
        radius_miles: float = 5.0,
        max_age_days: int = 365,
    ) -> CompsResult:
        """
        Get comparable sales for a parcel.
        
        Tries real API first, falls back to mock data if unavailable.
        
        Args:
            parcel: The subject parcel.
            max_comps: Maximum number of comps to return.
            radius_miles: Search radius in miles.
            max_age_days: Maximum age of sales in days.
            
        Returns:
            CompsResult with comparable sales.
        """
        # Try real API first
        if self.circuit_breaker.can_execute():
            try:
                result = self._fetch_from_api(parcel, max_comps, radius_miles, max_age_days)
                if result and result.total_comps_found > 0:
                    self.circuit_breaker.record_success()
                    return result
            except Exception as e:
                self.circuit_breaker.record_failure()
                LOGGER.warning(f"Comps API failed, falling back to mock: {e}")
        
        # Fallback to mock data
        return self._generate_mock_comps_result(parcel, max_comps, max_age_days)

    def _fetch_from_api(
        self,
        parcel: Parcel,
        max_comps: int,
        radius_miles: float,
        max_age_days: int,
    ) -> Optional[CompsResult]:
        """
        Fetch comps from external API.
        
        TODO: Implement actual API integration (ATTOM, CoreLogic, etc.)
        
        Args:
            parcel: Subject parcel.
            max_comps: Max comps to return.
            radius_miles: Search radius.
            max_age_days: Max age of sales.
            
        Returns:
            CompsResult if successful, None otherwise.
        """
        # Check if API is configured
        if not hasattr(SETTINGS, 'comps_api_key') or not SETTINGS.comps_api_key:
            LOGGER.debug("Comps API not configured")
            return None
        
        # TODO: Implement actual API call
        # Example structure for ATTOM API:
        #
        # import httpx
        # 
        # response = httpx.get(
        #     "https://api.attomdata.com/propertyapi/v1.0.0/property/salescomps",
        #     params={
        #         "address": parcel.situs_address,
        #         "radius": radius_miles,
        #         "maxResults": max_comps,
        #     },
        #     headers={"apikey": SETTINGS.comps_api_key},
        #     timeout=30,
        # )
        # 
        # if response.status_code == 200:
        #     data = response.json()
        #     comps = [self._parse_api_comp(c) for c in data.get("comps", [])]
        #     return self._build_result(comps, source="attom")
        
        return None

    def _generate_mock_comps_result(
        self,
        parcel: Parcel,
        max_comps: int,
        max_age_days: int,
    ) -> CompsResult:
        """
        Generate mock comps data (for development/fallback).
        
        FIXED: Clearly marks data as mock.
        """
        base_price_per_acre = self._estimate_base_price(parcel)
        comps = self._generate_mock_comps(parcel, base_price_per_acre, max_comps, max_age_days)
        
        if not comps:
            return CompsResult(
                comps=[],
                avg_price_per_acre=0,
                min_price_per_acre=0,
                max_price_per_acre=0,
                median_price_per_acre=None,
                total_comps_found=0,
                is_mock_data=True,
                source="mock",
                error="No comps available",
            )
        
        prices = [c.price_per_acre for c in comps]
        sorted_prices = sorted(prices)
        n = len(sorted_prices)
        
        # Calculate median
        if n % 2 == 0:
            median = (sorted_prices[n // 2 - 1] + sorted_prices[n // 2]) / 2
        else:
            median = sorted_prices[n // 2]
        
        return CompsResult(
            comps=comps,
            avg_price_per_acre=sum(prices) / len(prices),
            min_price_per_acre=min(prices),
            max_price_per_acre=max(prices),
            median_price_per_acre=median,
            total_comps_found=len(comps),
            is_mock_data=True,
            source="mock",
        )

    def _estimate_base_price(self, parcel: Parcel) -> float:
        """
        Estimate base price per acre from parcel data.
        
        Uses assessed value and location characteristics.
        """
        # Use assessed value if available
        if parcel.land_assessed_value and parcel.land_assessed_value > 0:
            lot_size = parcel.lot_size_acres or 1.0
            # Assessed values are typically 10-20% of market value
            market_value = float(parcel.land_assessed_value) * 5
            return market_value / lot_size
        
        # Default prices by state/market
        market_defaults = {
            "LA": 4500,
            "TX": 6000,
            "MS": 3500,
            "AR": 3000,
            "AL": 4000,
        }
        
        base = market_defaults.get(parcel.market_code, 5000)
        
        # Adjust for location factors
        if parcel.inside_city_limits:
            base *= 1.5
        
        if parcel.is_adjudicated:
            base *= 0.7  # Adjudicated properties sell cheaper
        
        return base

    def _generate_mock_comps(
        self,
        parcel: Parcel,
        base_price: float,
        count: int,
        max_age_days: int,
    ) -> List[CompSale]:
        """Generate realistic mock comps for development."""
        comps = []
        now = utcnow()
        
        for i in range(count):
            # Vary price ±30%
            price_variance = random.uniform(0.7, 1.3)
            price_per_acre = base_price * price_variance
            
            # Vary lot size around subject's size
            subject_size = float(parcel.lot_size_acres or 1.0)
            lot_variance = random.uniform(0.5, 2.0)
            lot_size = max(0.1, subject_size * lot_variance)
            
            # Random sale date within max_age_days
            days_ago = random.randint(30, max_age_days)
            sale_date = now - timedelta(days=days_ago)
            
            # Generate address near subject
            parish = parcel.parish or "Unknown Parish"
            streets = ["Oak St", "Main St", "Pine Ave", "Elm Dr", "Cedar Ln", "Maple Rd"]
            street = random.choice(streets)
            number = random.randint(100, 9999)
            city = parcel.city or "City"
            
            comps.append(CompSale(
                address=f"{number} {street}, {city}, {parcel.state or 'LA'}",
                sale_date=sale_date.isoformat(),
                sale_price=price_per_acre * lot_size,
                lot_size_acres=lot_size,
                price_per_acre=price_per_acre,
                distance_miles=random.uniform(0.5, 5.0),
                source="mock",
            ))
        
        # Sort by date, most recent first
        comps.sort(key=lambda c: c.sale_date, reverse=True)
        
        return comps


# Module-level singleton
_service: Optional[CompsService] = None


def get_comps_service(session: Optional[Session] = None) -> CompsService:
    """Get a CompsService instance."""
    return CompsService(session)


__all__ = [
    "CompsService",
    "CompsResult",
    "CompSale",
    "get_comps_service",
]
