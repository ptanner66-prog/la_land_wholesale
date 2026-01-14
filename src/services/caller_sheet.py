"""
Caller Sheet Service - Generates work queue for sales calls.

The caller sheet is the primary workflow for this SaaS:
1. Active Market only
2. TCPA-safe phone exists
3. Lead is scored
4. Lead is HOT or CONTACT tier
5. Deterministic ordering (no filters)
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import func, and_, or_
from sqlalchemy.orm import Session, selectinload

from core.active_market import require_active_market, ActiveMarket
from core.logging_config import get_logger
from core.models import Lead, Owner, Parcel, Party, PipelineStage
from scoring.deterministic_engine import HOT_THRESHOLD, CONTACT_THRESHOLD

LOGGER = get_logger(__name__)


@dataclass
class CallerSheetLead:
    """A single lead in the caller sheet."""
    id: int
    owner_name: str
    phone: str
    parcel_id: str
    parish: str
    acreage: Optional[float]
    land_value: Optional[float]
    motivation_score: int
    tier: str  # "HOT" or "CONTACT"
    is_adjudicated: bool
    years_delinquent: int
    property_address: Optional[str]
    mailing_address: Optional[str]
    notes: Optional[str]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "owner_name": self.owner_name,
            "phone": self.phone,
            "parcel_id": self.parcel_id,
            "parish": self.parish,
            "acreage": self.acreage,
            "land_value": self.land_value,
            "motivation_score": self.motivation_score,
            "tier": self.tier,
            "is_adjudicated": self.is_adjudicated,
            "years_delinquent": self.years_delinquent,
            "property_address": self.property_address,
            "mailing_address": self.mailing_address,
            "notes": self.notes,
        }


@dataclass
class CallerSheet:
    """The caller work queue."""
    active_market: Dict[str, str]
    generated_at: str
    leads: List[CallerSheetLead]
    total_eligible: int
    hot_count: int
    contact_count: int
    unavailable_reason: Optional[str]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "active_market": self.active_market,
            "generated_at": self.generated_at,
            "leads": [l.to_dict() for l in self.leads],
            "total_eligible": self.total_eligible,
            "hot_count": self.hot_count,
            "contact_count": self.contact_count,
            "unavailable_reason": self.unavailable_reason,
        }


class CallerSheetService:
    """Service for generating caller work queues."""
    
    def __init__(self, session: Session):
        self.session = session
    
    def generate(self, limit: int = 50) -> CallerSheet:
        """
        Generate a caller sheet for the active market.
        
        Eligibility:
        - Active Market only
        - TCPA-safe phone exists
        - Lead is scored (motivation_score > 0)
        - Lead is HOT (>=65) or CONTACT (>=45) tier
        
        Ordering:
        - HOT leads first (by score DESC)
        - Then CONTACT leads (by score DESC)
        """
        # Require active market
        active_market = require_active_market()
        
        # Build eligibility query
        base_filter = and_(
            Lead.deleted_at.is_(None),
            Lead.market_code == active_market.market_code,
            Lead.motivation_score >= CONTACT_THRESHOLD,
            Owner.phone_primary.isnot(None),
            Owner.is_tcpa_safe == True,
            Owner.opt_out == False,
            func.lower(Parcel.parish) == active_market.parish.lower(),
        )
        
        # Count eligible leads
        total_eligible = (
            self.session.query(func.count(Lead.id))
            .join(Lead.owner)
            .join(Lead.parcel)
            .filter(base_filter)
            .scalar() or 0
        )
        
        # Count by tier
        hot_count = (
            self.session.query(func.count(Lead.id))
            .join(Lead.owner)
            .join(Lead.parcel)
            .filter(base_filter, Lead.motivation_score >= HOT_THRESHOLD)
            .scalar() or 0
        )
        
        contact_count = (
            self.session.query(func.count(Lead.id))
            .join(Lead.owner)
            .join(Lead.parcel)
            .filter(
                base_filter,
                Lead.motivation_score >= CONTACT_THRESHOLD,
                Lead.motivation_score < HOT_THRESHOLD
            )
            .scalar() or 0
        )
        
        # Check if unavailable
        if total_eligible == 0:
            reason = self._diagnose_unavailability(active_market)
            return CallerSheet(
                active_market=active_market.to_dict(),
                generated_at=datetime.now(timezone.utc).isoformat(),
                leads=[],
                total_eligible=0,
                hot_count=0,
                contact_count=0,
                unavailable_reason=reason,
            )
        
        # Fetch leads - HOT first, then CONTACT, ordered by score DESC
        leads = (
            self.session.query(Lead)
            .join(Lead.owner)
            .join(Owner.party)
            .join(Lead.parcel)
            .options(
                selectinload(Lead.owner).selectinload(Owner.party),
                selectinload(Lead.parcel),
            )
            .filter(base_filter)
            .order_by(
                # HOT leads first
                (Lead.motivation_score >= HOT_THRESHOLD).desc(),
                # Then by score
                Lead.motivation_score.desc(),
            )
            .limit(limit)
            .all()
        )
        
        # Convert to CallerSheetLead
        caller_leads = []
        for lead in leads:
            tier = "HOT" if lead.motivation_score >= HOT_THRESHOLD else "CONTACT"
            
            caller_leads.append(CallerSheetLead(
                id=lead.id,
                owner_name=lead.owner.party.display_name if lead.owner and lead.owner.party else "Unknown",
                phone=lead.owner.phone_primary if lead.owner else "",
                parcel_id=lead.parcel.canonical_parcel_id if lead.parcel else "",
                parish=lead.parcel.parish if lead.parcel else "",
                acreage=float(lead.parcel.lot_size_acres) if lead.parcel and lead.parcel.lot_size_acres else None,
                land_value=float(lead.parcel.land_assessed_value) if lead.parcel and lead.parcel.land_assessed_value else None,
                motivation_score=lead.motivation_score,
                tier=tier,
                is_adjudicated=lead.parcel.is_adjudicated if lead.parcel else False,
                years_delinquent=lead.parcel.years_tax_delinquent if lead.parcel else 0,
                property_address=lead.parcel.situs_address if lead.parcel else None,
                mailing_address=lead.owner.party.raw_mailing_address if lead.owner and lead.owner.party else None,
                notes=None,  # Could add tags or notes here
            ))
        
        return CallerSheet(
            active_market=active_market.to_dict(),
            generated_at=datetime.now(timezone.utc).isoformat(),
            leads=caller_leads,
            total_eligible=total_eligible,
            hot_count=hot_count,
            contact_count=contact_count,
            unavailable_reason=None,
        )
    
    def _diagnose_unavailability(self, market: ActiveMarket) -> str:
        """Diagnose why no leads are available."""
        # Check total leads in parish
        total_in_parish = (
            self.session.query(func.count(Lead.id))
            .join(Lead.parcel)
            .filter(
                Lead.deleted_at.is_(None),
                Lead.market_code == market.market_code,
                func.lower(Parcel.parish) == market.parish.lower(),
            )
            .scalar() or 0
        )
        
        if total_in_parish == 0:
            return f"No leads found in {market.display_name}. Ingest data for this parish first."
        
        # Check scored leads
        scored = (
            self.session.query(func.count(Lead.id))
            .join(Lead.parcel)
            .filter(
                Lead.deleted_at.is_(None),
                Lead.market_code == market.market_code,
                func.lower(Parcel.parish) == market.parish.lower(),
                Lead.motivation_score > 0,
            )
            .scalar() or 0
        )
        
        if scored == 0:
            return f"No scored leads in {market.display_name}. Run scoring/enrichment first."
        
        # Check HOT/CONTACT tier
        qualified = (
            self.session.query(func.count(Lead.id))
            .join(Lead.parcel)
            .filter(
                Lead.deleted_at.is_(None),
                Lead.market_code == market.market_code,
                func.lower(Parcel.parish) == market.parish.lower(),
                Lead.motivation_score >= CONTACT_THRESHOLD,
            )
            .scalar() or 0
        )
        
        if qualified == 0:
            return f"No leads scoring >= {CONTACT_THRESHOLD} in {market.display_name}. Enrich more parcels or lower thresholds."
        
        # Check phones
        with_phone = (
            self.session.query(func.count(Lead.id))
            .join(Lead.owner)
            .join(Lead.parcel)
            .filter(
                Lead.deleted_at.is_(None),
                Lead.market_code == market.market_code,
                func.lower(Parcel.parish) == market.parish.lower(),
                Lead.motivation_score >= CONTACT_THRESHOLD,
                Owner.phone_primary.isnot(None),
            )
            .scalar() or 0
        )
        
        if with_phone == 0:
            return f"No qualified leads have phone numbers in {market.display_name}. Add phone numbers via enrichment."
        
        # Check TCPA
        tcpa_safe = (
            self.session.query(func.count(Lead.id))
            .join(Lead.owner)
            .join(Lead.parcel)
            .filter(
                Lead.deleted_at.is_(None),
                Lead.market_code == market.market_code,
                func.lower(Parcel.parish) == market.parish.lower(),
                Lead.motivation_score >= CONTACT_THRESHOLD,
                Owner.phone_primary.isnot(None),
                Owner.is_tcpa_safe == True,
            )
            .scalar() or 0
        )
        
        if tcpa_safe == 0:
            return f"No TCPA-safe leads in {market.display_name}. Verify phone numbers are mobile/consented."
        
        # Check opt-out
        not_opted_out = (
            self.session.query(func.count(Lead.id))
            .join(Lead.owner)
            .join(Lead.parcel)
            .filter(
                Lead.deleted_at.is_(None),
                Lead.market_code == market.market_code,
                func.lower(Parcel.parish) == market.parish.lower(),
                Lead.motivation_score >= CONTACT_THRESHOLD,
                Owner.phone_primary.isnot(None),
                Owner.is_tcpa_safe == True,
                Owner.opt_out == False,
            )
            .scalar() or 0
        )
        
        if not_opted_out == 0:
            return f"All qualified leads have opted out in {market.display_name}."
        
        return "Unknown issue - please contact support."


def get_caller_sheet_service(session: Session) -> CallerSheetService:
    """Factory function for CallerSheetService."""
    return CallerSheetService(session)


__all__ = [
    "CallerSheet",
    "CallerSheetLead",
    "CallerSheetService",
    "get_caller_sheet_service",
]

