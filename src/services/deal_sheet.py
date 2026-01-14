"""Deal sheet generation service."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from core.logging_config import get_logger
from core.models import Lead, DealSheet
from core.utils import utcnow, ensure_aware, CircuitBreaker
from src.services.comps import get_comps_service
from src.services.offer_calculator import get_offer_calculator
from src.services.timeline import TimelineService

LOGGER = get_logger(__name__)

# Circuit breaker for AI description generation
_ai_circuit = CircuitBreaker(
    name="deal_sheet_ai",
    failure_threshold=3,
    recovery_timeout=120,
)


@dataclass
class DealSheetContent:
    """Generated deal sheet content."""
    
    # Property fundamentals
    parcel_id: str
    address: str
    city: Optional[str]
    state: str
    county: str
    market_code: str
    
    # Size and value
    acreage: float
    land_assessed_value: Optional[float]
    
    # Comps summary
    comp_count: int
    avg_price_per_acre: Optional[float]
    min_price_per_acre: Optional[float]
    max_price_per_acre: Optional[float]
    comps_is_mock: bool
    
    # Offer analysis
    recommended_offer: float
    low_offer: float
    high_offer: float
    price_per_acre: float
    
    # Assignment potential
    retail_estimate: float
    assignment_potential: float
    assignment_percentage: float
    
    # Property characteristics
    is_adjudicated: bool
    years_tax_delinquent: int
    motivation_score: int
    
    # Owner info (sanitized for buyer)
    owner_situation: str  # e.g., "Motivated seller - tax delinquent"
    
    # AI description
    ai_description: Optional[str] = None
    
    # Map
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    map_url: Optional[str] = None
    
    # Metadata
    generated_at: str = ""
    lead_id: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "parcel_id": self.parcel_id,
            "address": self.address,
            "city": self.city,
            "state": self.state,
            "county": self.county,
            "market_code": self.market_code,
            "acreage": round(self.acreage, 2),
            "land_assessed_value": self.land_assessed_value,
            "comp_count": self.comp_count,
            "avg_price_per_acre": round(self.avg_price_per_acre, 2) if self.avg_price_per_acre else None,
            "min_price_per_acre": round(self.min_price_per_acre, 2) if self.min_price_per_acre else None,
            "max_price_per_acre": round(self.max_price_per_acre, 2) if self.max_price_per_acre else None,
            "comps_is_mock": self.comps_is_mock,
            "recommended_offer": round(self.recommended_offer, 2),
            "low_offer": round(self.low_offer, 2),
            "high_offer": round(self.high_offer, 2),
            "price_per_acre": round(self.price_per_acre, 2),
            "retail_estimate": round(self.retail_estimate, 2),
            "assignment_potential": round(self.assignment_potential, 2),
            "assignment_percentage": round(self.assignment_percentage, 1),
            "is_adjudicated": self.is_adjudicated,
            "years_tax_delinquent": self.years_tax_delinquent,
            "motivation_score": self.motivation_score,
            "owner_situation": self.owner_situation,
            "ai_description": self.ai_description,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "map_url": self.map_url,
            "generated_at": self.generated_at,
            "lead_id": self.lead_id,
        }


class DealSheetService:
    """Service for generating deal sheets."""

    # Cache duration in hours
    CACHE_HOURS = 24

    def __init__(self, session: Session):
        """Initialize the deal sheet service."""
        self.session = session
        self.comps_service = get_comps_service(session)
        self.offer_calc = get_offer_calculator()
        self.timeline = TimelineService(session)
        self.ai_circuit = _ai_circuit

    def generate_deal_sheet(
        self,
        lead_id: int,
        force_regenerate: bool = False,
    ) -> Optional[DealSheetContent]:
        """
        Generate a deal sheet for a lead.
        
        Args:
            lead_id: The lead ID.
            force_regenerate: Regenerate even if cached.
            
        Returns:
            Deal sheet content or None if lead not found.
        """
        lead = self.session.query(Lead).filter(Lead.id == lead_id).first()
        if not lead:
            LOGGER.warning(f"Lead {lead_id} not found for deal sheet")
            return None
        
        # Check cache
        if not force_regenerate:
            cached = self._get_cached(lead_id)
            if cached:
                LOGGER.debug(f"Using cached deal sheet for lead {lead_id}")
                return cached
        
        # Generate new deal sheet
        content = self._generate(lead)
        
        # Cache it
        self._cache(lead_id, content)
        
        # Log to timeline
        self.timeline.add_event(
            lead_id=lead_id,
            event_type="deal_sheet_generated",
            title="Deal sheet generated",
            description=f"Retail estimate: ${content.retail_estimate:,.0f}",
            metadata={
                "recommended_offer": content.recommended_offer,
                "assignment_potential": content.assignment_potential,
            },
        )
        
        return content

    def _get_cached(self, lead_id: int) -> Optional[DealSheetContent]:
        """Get cached deal sheet if still valid."""
        cached = self.session.query(DealSheet).filter(
            DealSheet.lead_id == lead_id
        ).first()
        
        if not cached:
            return None
        
        # Check expiry - ensure datetime is timezone-aware for comparison
        # ROOT CAUSE FIX: SQLite stores naive datetimes, but utcnow() is aware.
        # We use ensure_aware() to make the comparison safe.
        now = utcnow()
        expires_at_aware = ensure_aware(cached.expires_at)
        if expires_at_aware and now > expires_at_aware:
            LOGGER.debug(f"Cached deal sheet for lead {lead_id} has expired")
            return None
        
        # Reconstruct from JSON
        content = cached.content
        return DealSheetContent(
            parcel_id=content.get("parcel_id", ""),
            address=content.get("address", ""),
            city=content.get("city"),
            state=content.get("state", ""),
            county=content.get("county", ""),
            market_code=content.get("market_code", ""),
            acreage=content.get("acreage", 0),
            land_assessed_value=content.get("land_assessed_value"),
            comp_count=content.get("comp_count", 0),
            avg_price_per_acre=content.get("avg_price_per_acre"),
            min_price_per_acre=content.get("min_price_per_acre"),
            max_price_per_acre=content.get("max_price_per_acre"),
            comps_is_mock=content.get("comps_is_mock", False),
            recommended_offer=content.get("recommended_offer", 0),
            low_offer=content.get("low_offer", 0),
            high_offer=content.get("high_offer", 0),
            price_per_acre=content.get("price_per_acre", 0),
            retail_estimate=content.get("retail_estimate", 0),
            assignment_potential=content.get("assignment_potential", 0),
            assignment_percentage=content.get("assignment_percentage", 0),
            is_adjudicated=content.get("is_adjudicated", False),
            years_tax_delinquent=content.get("years_tax_delinquent", 0),
            motivation_score=content.get("motivation_score", 0),
            owner_situation=content.get("owner_situation", ""),
            ai_description=cached.ai_description,
            latitude=content.get("latitude"),
            longitude=content.get("longitude"),
            map_url=content.get("map_url"),
            generated_at=cached.generated_at.isoformat() if cached.generated_at else "",
            lead_id=lead_id,
        )

    def _generate(self, lead: Lead) -> DealSheetContent:
        """Generate fresh deal sheet content."""
        parcel = lead.parcel
        
        # Get parcel data
        acreage = float(parcel.lot_size_acres or 1.0) if parcel else 1.0
        county = parcel.parish if parcel else "Unknown"
        address = parcel.situs_address if parcel else "Unknown"
        city = parcel.city if parcel else None
        state = parcel.state or lead.market_code
        land_value = float(parcel.land_assessed_value) if parcel and parcel.land_assessed_value else None
        
        # Get comps
        comps_result = self.comps_service.get_comps_for_parcel(parcel) if parcel else None
        
        comp_count = comps_result.total_comps_found if comps_result else 0
        avg_ppa = comps_result.avg_price_per_acre if comps_result else None
        min_ppa = comps_result.min_price_per_acre if comps_result else None
        max_ppa = comps_result.max_price_per_acre if comps_result else None
        comps_mock = comps_result.is_mock_data if comps_result else True
        
        # Calculate offer
        offer_result = self.offer_calc.calculate_offer(
            lot_size_acres=acreage,
            motivation_score=lead.motivation_score,
            comp_avg_price_per_acre=avg_ppa,
            land_assessed_value=land_value,
            is_adjudicated=parcel.is_adjudicated if parcel else False,
        )
        
        # Estimate retail and assignment potential
        # Retail is typically 1.3-1.5x wholesale offer
        retail_multiplier = 1.4
        retail_estimate = offer_result.recommended_offer * retail_multiplier
        assignment_potential = retail_estimate - offer_result.recommended_offer
        assignment_percentage = (assignment_potential / offer_result.recommended_offer * 100) if offer_result.recommended_offer > 0 else 0
        
        # Generate owner situation summary
        owner_situation = self._generate_owner_situation(lead, parcel)
        
        # Generate AI description
        ai_description = self._generate_ai_description(lead, parcel, offer_result)
        
        # Map URL
        lat = parcel.latitude if parcel else None
        lng = parcel.longitude if parcel else None
        map_url = f"https://www.google.com/maps?q={lat},{lng}" if lat and lng else None
        
        return DealSheetContent(
            parcel_id=parcel.canonical_parcel_id if parcel else "Unknown",
            address=address,
            city=city,
            state=state,
            county=county,
            market_code=lead.market_code,
            acreage=acreage,
            land_assessed_value=land_value,
            comp_count=comp_count,
            avg_price_per_acre=avg_ppa,
            min_price_per_acre=min_ppa,
            max_price_per_acre=max_ppa,
            comps_is_mock=comps_mock,
            recommended_offer=offer_result.recommended_offer,
            low_offer=offer_result.low_offer,
            high_offer=offer_result.high_offer,
            price_per_acre=offer_result.price_per_acre,
            retail_estimate=retail_estimate,
            assignment_potential=assignment_potential,
            assignment_percentage=assignment_percentage,
            is_adjudicated=parcel.is_adjudicated if parcel else False,
            years_tax_delinquent=parcel.years_tax_delinquent if parcel else 0,
            motivation_score=lead.motivation_score,
            owner_situation=owner_situation,
            ai_description=ai_description,
            latitude=lat,
            longitude=lng,
            map_url=map_url,
            generated_at=utcnow().isoformat(),
            lead_id=lead.id,
        )

    def _generate_owner_situation(self, lead: Lead, parcel) -> str:
        """Generate owner situation summary for buyers."""
        factors = []
        
        if parcel and parcel.is_adjudicated:
            factors.append("Adjudicated property")
        
        if parcel and parcel.years_tax_delinquent > 0:
            factors.append(f"{parcel.years_tax_delinquent} years tax delinquent")
        
        if lead.motivation_score >= 75:
            factors.append("Highly motivated seller")
        elif lead.motivation_score >= 50:
            factors.append("Motivated seller")
        
        if lead.pipeline_stage == "HOT":
            factors.append("Seller engaged and responsive")
        
        return " • ".join(factors) if factors else "Standard acquisition opportunity"

    def _generate_ai_description(self, lead: Lead, parcel, offer_result) -> Optional[str]:
        """Generate AI description for buyer outreach."""
        if not self.ai_circuit.can_execute():
            LOGGER.warning("AI circuit breaker open, skipping description generation")
            return None
        
        try:
            # Build prompt
            from core.exceptions import LLMTimeoutError
            acreage = float(parcel.lot_size_acres or 0) if parcel else 0
            county = parcel.parish if parcel else "Unknown"
            state = parcel.state or lead.market_code
            
            prompt = f"""Write a brief, compelling 2-3 sentence description of this land deal for investor buyers:

Property: {acreage:.2f} acres in {county}, {state}
Wholesale Price: ${offer_result.recommended_offer:,.0f}
Price Per Acre: ${offer_result.price_per_acre:,.0f}
Estimated Retail Value: ${offer_result.recommended_offer * 1.4:,.0f}

Focus on the investment opportunity. Be factual and professional. Do not use exclamation marks."""

            from llm.client import get_llm_client
            
            llm_client = get_llm_client()
            result = llm_client.generate_completion(
                prompt=prompt,
                max_tokens=150,
                temperature=0.7,
                timeout=15,
            )
            
            self.ai_circuit.record_success()
            return result.strip()
        
        except LLMTimeoutError as e:
            self.ai_circuit.record_failure()
            LOGGER.warning(f"AI description generation timed out: {e}")
            return None
        except Exception as e:
            self.ai_circuit.record_failure()
            LOGGER.error(f"Failed to generate AI description: {e}")
            return None

    def _cache(self, lead_id: int, content: DealSheetContent) -> None:
        """Cache the deal sheet."""
        now = utcnow()
        expires = now + timedelta(hours=self.CACHE_HOURS)
        
        # Check for existing
        existing = self.session.query(DealSheet).filter(
            DealSheet.lead_id == lead_id
        ).first()
        
        if existing:
            existing.content = content.to_dict()
            existing.ai_description = content.ai_description
            existing.generated_at = now
            existing.expires_at = expires
        else:
            deal_sheet = DealSheet(
                lead_id=lead_id,
                content=content.to_dict(),
                ai_description=content.ai_description,
                generated_at=now,
                expires_at=expires,
            )
            self.session.add(deal_sheet)
        
        self.session.flush()


def get_deal_sheet_service(session: Session) -> DealSheetService:
    """Get a DealSheetService instance."""
    return DealSheetService(session)


__all__ = [
    "DealSheetService",
    "DealSheetContent",
    "get_deal_sheet_service",
]

