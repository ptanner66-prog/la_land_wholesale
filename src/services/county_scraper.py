"""East Baton Rouge Parish county records scraper with fallback support."""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import httpx

from core.config import get_settings
from core.exceptions import ScraperError
from core.logging_config import get_logger, log_external_call
from services.retry import with_retry

LOGGER = get_logger(__name__)

# User agent for web scraping
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# EBR Assessor's site
EBR_ASSESSOR_URL = "https://www.ebrpa.org/"
# EBR Clerk of Court (conveyance records)
EBR_CLERK_URL = "https://www.ebrclerkofcourt.org/"


@dataclass
class CountySaleRecord:
    """A sale record from county records."""

    owner_name: str
    sale_price: Optional[int] = None
    sale_date: Optional[str] = None
    property_address: Optional[str] = None
    parcel_number: Optional[str] = None
    act_number: Optional[str] = None  # Conveyance act number
    doc_link: Optional[str] = None  # Link to document
    instrument_type: Optional[str] = None  # e.g., "Sale", "Donation"
    grantor: Optional[str] = None  # Seller
    grantee: Optional[str] = None  # Buyer
    legal_description: Optional[str] = None
    source: str = "county_records"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "owner_name": self.owner_name,
            "sale_price": self.sale_price,
            "sale_date": self.sale_date,
            "property_address": self.property_address,
            "parcel_number": self.parcel_number,
            "act_number": self.act_number,
            "doc_link": self.doc_link,
            "instrument_type": self.instrument_type,
            "grantor": self.grantor,
            "grantee": self.grantee,
            "legal_description": self.legal_description,
            "source": self.source,
        }


def _create_fallback_result() -> Dict[str, Any]:
    """Create empty fallback result when scraper is disabled or fails."""
    return {
        "records": [],
        "count": 0,
        "available": False,
        "source": "fallback",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    }


class CountyScraperService:
    """Service for scraping EBR county records."""

    def __init__(self):
        """Initialize the scraper service."""
        settings = get_settings()
        self.timeout = settings.scraper_request_timeout
        self._client: Optional[httpx.Client] = None

    def _get_client(self) -> httpx.Client:
        """Get or create HTTP client with appropriate headers."""
        if self._client is None:
            self._client = httpx.Client(
                timeout=self.timeout,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.5",
                    "Connection": "keep-alive",
                },
                follow_redirects=True,
            )
        return self._client

    def _parse_price(self, text: str) -> Optional[int]:
        """Parse price from text like '$250,000'."""
        if not text:
            return None
        cleaned = re.sub(r"[$,\s]", "", text.strip())
        try:
            return int(float(cleaned))
        except ValueError:
            return None

    def _parse_date(self, text: str) -> Optional[str]:
        """Parse date from various formats to YYYY-MM-DD."""
        if not text:
            return None
        
        # Try common formats
        formats = [
            "%m/%d/%Y",
            "%m-%d-%Y",
            "%Y-%m-%d",
            "%m/%d/%y",
            "%B %d, %Y",
            "%b %d, %Y",
        ]
        
        cleaned = text.strip()
        for fmt in formats:
            try:
                dt = datetime.strptime(cleaned, fmt)
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                continue
        
        return None

    @with_retry(max_attempts=2, retry_exceptions=(ConnectionError, TimeoutError, httpx.HTTPError))
    def _search_assessor(self, owner_name: Optional[str] = None, parcel_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Search EBR Assessor records.
        
        Note: This is a placeholder - the actual implementation would need to
        interact with the assessor's search form which may require session handling.
        """
        results: List[Dict[str, Any]] = []
        
        try:
            LOGGER.info(f"Searching EBR assessor for owner={owner_name}, parcel={parcel_id}")
            
            # Placeholder - return empty for now
            # In production, you would:
            # 1. GET the search page to get any CSRF tokens
            # 2. POST the search form with owner_name or parcel_id
            # 3. Parse the results table
            
        except Exception as e:
            LOGGER.warning(f"EBR assessor search failed: {e}")

        return results

    @with_retry(max_attempts=2, retry_exceptions=(ConnectionError, TimeoutError, httpx.HTTPError))
    def _search_clerk_conveyances(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        instrument_type: str = "Sale",
    ) -> List[CountySaleRecord]:
        """
        Search EBR Clerk of Court conveyance records.
        
        Note: This is a simplified implementation. The actual Clerk site may
        require more complex interaction.
        """
        records: List[CountySaleRecord] = []
        
        try:
            LOGGER.info(
                f"Searching EBR clerk conveyances: "
                f"start={start_date}, end={end_date}, type={instrument_type}"
            )
            
            # Placeholder implementation
            # In production:
            # 1. Navigate to conveyance search
            # 2. Fill form with date range and instrument type
            # 3. Parse results
            
        except Exception as e:
            LOGGER.warning(f"EBR clerk search failed: {e}")

        return records

    def scrape_recent_sales(
        self,
        days_back: int = 30,
        limit: int = 100,
    ) -> List[CountySaleRecord]:
        """
        Scrape recent sales from EBR public records.
        
        This attempts to get recent property sales by:
        1. Checking the clerk of court conveyance records
        2. Cross-referencing with assessor data
        
        Args:
            days_back: Number of days to look back.
            limit: Maximum number of records to return.
            
        Returns:
            List of CountySaleRecord objects.
            
        Note: Due to the complexity of government websites, this may return
        limited or no data if the sites change their structure.
        """
        start_time = time.perf_counter()
        records: List[CountySaleRecord] = []

        try:
            # Calculate date range
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days_back)
            
            LOGGER.info(f"Scraping EBR sales for last {days_back} days")
            
            # In a real implementation, you would:
            # 1. Access the conveyance search page
            # 2. Submit search with date range and "Sale" instrument type
            # 3. Parse results into CountySaleRecord objects
            # 4. Optionally cross-reference with assessor for property details
            
            LOGGER.warning(
                "County scraper placeholder - implement site-specific scraping "
                "based on actual EBR website structure"
            )

        except Exception as e:
            LOGGER.error(f"County scraping failed: {e}")

        finally:
            duration_ms = (time.perf_counter() - start_time) * 1000
            log_external_call(
                LOGGER,
                service="county_scraper",
                operation="scrape_recent_sales",
                success=len(records) > 0,
                duration_ms=duration_ms,
                days_back=days_back,
                record_count=len(records),
            )

        return records[:limit]

    def search_by_owner(self, owner_name: str) -> List[CountySaleRecord]:
        """
        Search county records by owner name.
        
        Args:
            owner_name: Owner name to search for.
            
        Returns:
            List of matching sale records.
        """
        start_time = time.perf_counter()
        records: List[CountySaleRecord] = []

        try:
            LOGGER.info(f"Searching county records for owner: {owner_name}")
            
            # Placeholder - would search assessor and/or clerk records
            
        except Exception as e:
            LOGGER.error(f"Owner search failed: {e}")

        finally:
            duration_ms = (time.perf_counter() - start_time) * 1000
            log_external_call(
                LOGGER,
                service="county_scraper",
                operation="search_by_owner",
                success=len(records) > 0,
                duration_ms=duration_ms,
                owner_name=owner_name[:20] if owner_name else None,
            )

        return records

    def search_by_parcel(self, parcel_id: str) -> List[CountySaleRecord]:
        """
        Search county records by parcel ID.
        
        Args:
            parcel_id: Parcel ID to search for.
            
        Returns:
            List of matching sale records.
        """
        start_time = time.perf_counter()
        records: List[CountySaleRecord] = []

        try:
            LOGGER.info(f"Searching county records for parcel: {parcel_id}")
            
            # Placeholder - would search assessor records
            
        except Exception as e:
            LOGGER.error(f"Parcel search failed: {e}")

        finally:
            duration_ms = (time.perf_counter() - start_time) * 1000
            log_external_call(
                LOGGER,
                service="county_scraper",
                operation="search_by_parcel",
                success=len(records) > 0,
                duration_ms=duration_ms,
                parcel_id=parcel_id,
            )

        return records

    def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            self._client.close()
            self._client = None


# Module-level singleton
_service: Optional[CountyScraperService] = None


def get_county_scraper_service() -> CountyScraperService:
    """Get the global CountyScraperService instance."""
    global _service
    if _service is None:
        _service = CountyScraperService()
    return _service


def scrape_recent_sales(days_back: int = 30, limit: int = 100) -> Dict[str, Any]:
    """
    Scrape recent EBR sales (convenience function with fallback).
    
    Args:
        days_back: Number of days to look back.
        limit: Maximum number of records.
        
    Returns:
        Dictionary with records list.
        If disabled or error: returns fallback with available=False.
    """
    settings = get_settings()
    
    # Check if service is enabled
    if not settings.is_county_scraper_enabled():
        LOGGER.debug("County scraper is disabled, returning empty fallback")
        return _create_fallback_result()

    try:
        service = get_county_scraper_service()
        records = service.scrape_recent_sales(days_back=days_back, limit=limit)
        return {
            "records": [r.to_dict() for r in records],
            "count": len(records),
            "available": True,
            "source": "county_records",
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
    except ScraperError as e:
        LOGGER.warning(f"County scraping failed: {e}")
        return _create_fallback_result()


__all__ = [
    "CountyScraperService",
    "CountySaleRecord",
    "scrape_recent_sales",
    "get_county_scraper_service",
]
