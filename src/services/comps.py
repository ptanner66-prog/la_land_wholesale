"""Comps (comparable sales) service with manual entry and optional API integration."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from sqlalchemy.orm import Session

from core.config import get_settings
from core.logging_config import get_logger
from core.models import ManualComp, Parcel

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
    source: str = "unknown"

    def to_dict(self) -> dict:
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
    source: str = "none"
    message: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "comps": [c.to_dict() for c in self.comps],
            "avg_price_per_acre": round(self.avg_price_per_acre, 2),
            "min_price_per_acre": round(self.min_price_per_acre, 2),
            "max_price_per_acre": round(self.max_price_per_acre, 2),
            "median_price_per_acre": round(self.median_price_per_acre, 2) if self.median_price_per_acre else None,
            "total_comps_found": self.total_comps_found,
            "is_mock_data": self.is_mock_data,
            "source": self.source,
            "message": self.message,
        }


class CompsService:
    """
    Service for fetching and analyzing comparable sales.

    Uses a provider chain controlled by COMPS_PROVIDER env var:
    - "manual"  — manual comps from the database (default)
    - "attom"   — ATTOM API (requires COMPS_API_KEY)

    If no comps are found, returns an empty result with a message
    suggesting manual entry. Never returns fake data.
    """

    def __init__(self, session: Optional[Session] = None):
        self.session = session

    def get_comps_for_parcel(
        self,
        parcel: Parcel,
        max_comps: int = 10,
        radius_miles: float = 5.0,
        max_age_days: int = 365,
    ) -> CompsResult:
        """
        Get comparable sales for a parcel.

        Tries configured provider, then manual comps from DB.
        Returns empty result (never fake data) if nothing is found.
        """
        provider = SETTINGS.comps_provider.lower()

        # Try ATTOM API if configured
        if provider == "attom" and SETTINGS.comps_api_key:
            result = self._fetch_from_attom(parcel, max_comps, radius_miles, max_age_days)
            if result and result.total_comps_found > 0:
                return result

        # Always check manual comps from the database
        if self.session:
            manual = self._fetch_manual_comps(parcel, max_comps)
            if manual and manual.total_comps_found > 0:
                return manual

        # No comps found from any source
        return CompsResult(
            comps=[],
            total_comps_found=0,
            is_mock_data=False,
            source="none",
            message="No verified comps found. Add comps manually or expand search radius.",
        )

    def _fetch_from_attom(
        self,
        parcel: Parcel,
        max_comps: int,
        radius_miles: float,
        max_age_days: int,
    ) -> Optional[CompsResult]:
        """Fetch comps from ATTOM API."""
        if not SETTINGS.comps_api_key:
            return None

        try:
            import httpx

            params = {
                "radius": str(radius_miles),
                "maxResults": str(max_comps),
            }
            if parcel.situs_address:
                params["address"] = parcel.situs_address
            if parcel.postal_code:
                params["postalcode"] = parcel.postal_code

            response = httpx.get(
                "https://api.gateway.attomdata.com/propertyapi/v1.0.0/sale/comparables",
                params=params,
                headers={
                    "apikey": SETTINGS.comps_api_key,
                    "Accept": "application/json",
                },
                timeout=SETTINGS.comps_timeout,
            )

            if response.status_code != 200:
                LOGGER.warning(f"ATTOM API returned {response.status_code}")
                return None

            data = response.json()
            sales = data.get("property", [])
            comps = []
            for sale in sales[:max_comps]:
                addr = sale.get("address", {})
                sale_info = sale.get("sale", {}).get("amount", {})
                lot_info = sale.get("lot", {})

                price = float(sale_info.get("saleamt", 0))
                acres = float(lot_info.get("lotsize1", 0)) / 43560.0  # sqft to acres
                if acres <= 0 or price <= 0:
                    continue

                comps.append(CompSale(
                    address=f"{addr.get('line1', '')} {addr.get('line2', '')}".strip(),
                    sale_date=sale.get("sale", {}).get("saleTransDate", ""),
                    sale_price=price,
                    lot_size_acres=acres,
                    price_per_acre=price / acres,
                    source="attom",
                ))

            if comps:
                return self._build_result(comps, source="attom")
            return None

        except Exception as e:
            LOGGER.warning(f"ATTOM API error: {e}")
            return None

    def _fetch_manual_comps(self, parcel: Parcel, max_comps: int) -> Optional[CompsResult]:
        """Fetch manually entered comps from the database."""
        if not self.session:
            return None

        query = self.session.query(ManualComp)

        # Match by parcel_id first
        if parcel.id:
            direct = query.filter(ManualComp.parcel_id == parcel.id).all()
            if direct:
                comps = [self._manual_to_comp(m) for m in direct[:max_comps]]
                return self._build_result(comps, source="manual")

        # Fall back to parish + market match
        filters = [ManualComp.market_code == parcel.market_code]
        if parcel.parish:
            filters.append(ManualComp.parish == parcel.parish)

        results = query.filter(*filters).order_by(ManualComp.sale_date.desc()).limit(max_comps).all()
        if results:
            comps = [self._manual_to_comp(m) for m in results]
            return self._build_result(comps, source="manual")

        return None

    @staticmethod
    def _manual_to_comp(m: ManualComp) -> CompSale:
        ppa = m.sale_price / m.lot_size_acres if m.lot_size_acres > 0 else 0
        return CompSale(
            address=m.address,
            sale_date=m.sale_date,
            sale_price=m.sale_price,
            lot_size_acres=m.lot_size_acres,
            price_per_acre=ppa,
            source="manual",
        )

    @staticmethod
    def _build_result(comps: List[CompSale], source: str) -> CompsResult:
        if not comps:
            return CompsResult(source=source, message="No comps found.")

        prices = [c.price_per_acre for c in comps if c.price_per_acre > 0]
        if not prices:
            return CompsResult(comps=comps, total_comps_found=len(comps), source=source)

        sorted_prices = sorted(prices)
        n = len(sorted_prices)
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
            is_mock_data=False,
            source=source,
        )


def get_comps_service(session: Optional[Session] = None) -> CompsService:
    """Get a CompsService instance."""
    return CompsService(session)


__all__ = [
    "CompsService",
    "CompsResult",
    "CompSale",
    "get_comps_service",
]
