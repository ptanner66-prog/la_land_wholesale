"""
Deterministic Lead Scoring Engine for Land Wholesaling.

This module implements a deterministic, auditable scoring system that produces
motivation scores (0-100) for land-only wholesaling opportunities.

NO TWILIO. NO OPENAI. NO EXTERNAL CALLS.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from core.logging_config import get_logger
from core.models import Lead, Owner, Parcel, Party, PipelineStage

LOGGER = get_logger(__name__)

# =============================================================================
# THRESHOLDS (EXPOSED FOR CONFIG)
# =============================================================================

CONTACT_THRESHOLD = 45   # Minimum score to contact
HOT_THRESHOLD = 65       # Hot lead threshold
REJECT_THRESHOLD = 30    # Below this = auto-reject

# Government/utility owner types that disqualify
DISQUALIFIED_OWNER_TYPES = frozenset({
    "government", "municipality", "utility", "state", "federal", "county", "city",
    "parish", "school", "church", "nonprofit", "non-profit"
})


@dataclass
class ScoreComponent:
    """A single scoring component with points and explanation."""
    name: str
    points: int
    max_points: int
    reason: str


@dataclass
class DeterministicScore:
    """Complete deterministic score result."""
    lead_id: int
    motivation_score: int
    components: List[ScoreComponent] = field(default_factory=list)
    disqualified: bool = False
    disqualified_reason: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for persistence."""
        return {
            "lead_id": self.lead_id,
            "motivation_score": self.motivation_score,
            "total_score": self.motivation_score,
            "disqualified": self.disqualified,
            "disqualified_reason": self.disqualified_reason,
            "components": {c.name: c.points for c in self.components},
            "factors": [
                {
                    "name": c.name,
                    "label": c.reason,
                    "value": c.points,
                    "max": c.max_points,
                }
                for c in self.components
            ],
        }


def _check_disqualifiers(
    parcel: Parcel,
    owner: Owner,
    party: Party,
) -> Optional[str]:
    """
    Check hard disqualifiers. Returns reason string if disqualified, None otherwise.
    
    HARD DISQUALIFIERS (AUTO SCORE = 0):
    - parcel has improvement value > land value (not vacant land) - IF both values present
    - owner.is_tcpa_safe = false
    - owner.phone_primary IS NULL
    - party.party_type IN government/municipality/utility types
    
    NOTE: Missing acreage/value data is NOT a disqualifier - we score what we have.
    """
    # Check TCPA first (most important for outreach)
    if not owner.is_tcpa_safe:
        return "tcpa_unsafe: owner.is_tcpa_safe is false"
    
    # Check phone (required for SMS outreach)
    if not owner.phone_primary:
        return "no_phone: owner.phone_primary is null"
    
    # Check for improvement > land (not vacant land) - only if we have both values
    land_val = float(parcel.land_assessed_value or 0)
    imp_val = float(parcel.improvement_assessed_value or 0)
    
    if imp_val > 0 and land_val > 0 and imp_val > land_val:
        return "not_vacant_land: improvement_value > land_value"
    
    # Check owner type
    owner_type = (party.party_type or "").lower().strip()
    if owner_type in DISQUALIFIED_OWNER_TYPES:
        return f"government_owner: party_type is '{party.party_type}'"
    
    # Also check if name contains government indicators
    owner_name = (party.display_name or "").lower()
    gov_keywords = ["city of", "state of", "parish of", "county of", "united states", 
                    "department of", "school board", "school district", "housing authority"]
    for kw in gov_keywords:
        if kw in owner_name:
            return f"government_owner: name contains '{kw}'"
    
    return None


def _score_ownership_duration(parcel: Parcel) -> ScoreComponent:
    """
    Score based on ownership duration (MAX 20 points).
    
    Uses years_tax_delinquent as proxy for long-term ownership issues.
    Since we don't have last_sale_date, we use delinquency years as indicator.
    
    NOTE: This is a proxy. If last_sale_date becomes available, replace this.
    """
    # We don't have last_sale_date in schema, so we can't compute years_owned
    # Return 0 points with explanation
    return ScoreComponent(
        name="ownership_duration",
        points=0,
        max_points=20,
        reason="Ownership duration unknown (no last_sale_date)",
    )


def _score_absentee_ownership(parcel: Parcel, party: Party) -> ScoreComponent:
    """
    Score based on absentee ownership (MAX 15 points).
    
    Compare owner mailing address vs parcel location:
    - Out-of-state owner → +15
    - In-state but different parish/county → +10
    - Same parish → +0
    """
    parcel_state = (parcel.state or "").upper().strip()
    parcel_parish = (parcel.parish or "").lower().strip()
    mailing_address = (party.raw_mailing_address or "").upper()
    
    if not parcel_state or not mailing_address:
        return ScoreComponent(
            name="absentee_ownership",
            points=0,
            max_points=15,
            reason="Cannot determine absentee status (missing address data)",
        )
    
    # Check if out of state
    # Look for state abbreviation in mailing address
    # Common patterns: ", LA 70xxx" or " LA 70xxx"
    if parcel_state not in mailing_address:
        return ScoreComponent(
            name="absentee_ownership",
            points=15,
            max_points=15,
            reason=f"Out-of-state owner (parcel in {parcel_state}, mailing elsewhere)",
        )
    
    # In-state - check if different parish
    if parcel_parish and parcel_parish not in mailing_address.lower():
        return ScoreComponent(
            name="absentee_ownership",
            points=10,
            max_points=15,
            reason=f"In-state absentee (different parish from {parcel.parish})",
        )
    
    return ScoreComponent(
        name="absentee_ownership",
        points=0,
        max_points=15,
        reason="Local owner (same parish)",
    )


def _score_tax_distress(parcel: Parcel) -> ScoreComponent:
    """
    Score based on tax distress (MAX 20 points).
    
    - is_adjudicated = true → +20 (property seized for taxes)
    - years_tax_delinquent >= 3 → +20
    - years_tax_delinquent >= 1 → +10
    - else → +0
    """
    if parcel.is_adjudicated:
        return ScoreComponent(
            name="tax_distress",
            points=20,
            max_points=20,
            reason="Adjudicated property (seized for back taxes)",
        )
    
    years = parcel.years_tax_delinquent or 0
    if years >= 3:
        return ScoreComponent(
            name="tax_distress",
            points=20,
            max_points=20,
            reason=f"Severely delinquent ({years} years)",
        )
    elif years >= 1:
        return ScoreComponent(
            name="tax_distress",
            points=10,
            max_points=20,
            reason=f"Tax delinquent ({years} year(s))",
        )
    
    return ScoreComponent(
        name="tax_distress",
        points=0,
        max_points=20,
        reason="Taxes current",
    )


def _score_parcel_liquidity(parcel: Parcel) -> ScoreComponent:
    """
    Score based on parcel liquidity / acreage sweet spot (MAX 15 points).
    
    - 0.25 <= acreage <= 5 → +15 (most liquid)
    - 5 < acreage <= 20 → +10 (good)
    - acreage < 0.25 → +5 (small but sellable)
    - else → +0 (harder to move)
    """
    acres = float(parcel.lot_size_acres or 0)
    
    if 0.25 <= acres <= 5.0:
        return ScoreComponent(
            name="parcel_liquidity",
            points=15,
            max_points=15,
            reason=f"High liquidity lot size ({acres:.2f} ac)",
        )
    elif 5.0 < acres <= 20.0:
        return ScoreComponent(
            name="parcel_liquidity",
            points=10,
            max_points=15,
            reason=f"Good lot size ({acres:.2f} ac)",
        )
    elif 0 < acres < 0.25:
        return ScoreComponent(
            name="parcel_liquidity",
            points=5,
            max_points=15,
            reason=f"Small lot ({acres:.2f} ac)",
        )
    
    return ScoreComponent(
        name="parcel_liquidity",
        points=0,
        max_points=15,
        reason=f"Large/irregular lot size ({acres:.2f} ac) - harder to sell",
    )


def _score_undervaluation(
    parcel: Parcel,
    parish_median_value_per_acre: Optional[float],
) -> ScoreComponent:
    """
    Score based on undervaluation signal (MAX 15 points).
    
    Compare value_per_acre against parish median:
    - < 60% of median → +15
    - < 80% of median → +8
    - else → +0
    
    If median unavailable, add 0 points (do not guess).
    """
    if parish_median_value_per_acre is None or parish_median_value_per_acre <= 0:
        return ScoreComponent(
            name="undervaluation",
            points=0,
            max_points=15,
            reason="Parish median not available",
        )
    
    land_val = float(parcel.land_assessed_value or 0)
    acres = float(parcel.lot_size_acres or 0)
    
    if acres <= 0:
        return ScoreComponent(
            name="undervaluation",
            points=0,
            max_points=15,
            reason="Cannot compute value/acre (no acreage)",
        )
    
    value_per_acre = land_val / acres
    ratio = value_per_acre / parish_median_value_per_acre
    
    if ratio < 0.60:
        return ScoreComponent(
            name="undervaluation",
            points=15,
            max_points=15,
            reason=f"Significantly undervalued ({ratio:.0%} of parish median)",
        )
    elif ratio < 0.80:
        return ScoreComponent(
            name="undervaluation",
            points=8,
            max_points=15,
            reason=f"Moderately undervalued ({ratio:.0%} of parish median)",
        )
    
    return ScoreComponent(
        name="undervaluation",
        points=0,
        max_points=15,
        reason=f"At or above market ({ratio:.0%} of parish median)",
    )


def _score_clean_exit_signals(parcel: Parcel) -> ScoreComponent:
    """
    Score based on clean exit signals (MAX 15 points).
    
    Since we don't have deed_type in schema, we use adjudicated status
    and tax delinquency as proxy for motivated sellers.
    
    - is_adjudicated → +15 (forced sale situation)
    - years_tax_delinquent >= 5 → +10 (long-term distress)
    - else → +0
    
    NOTE: If deed_type becomes available, add: quitclaim/succession/trustee → +15
    """
    if parcel.is_adjudicated:
        return ScoreComponent(
            name="clean_exit_signals",
            points=15,
            max_points=15,
            reason="Adjudicated - forced sale situation",
        )
    
    years = parcel.years_tax_delinquent or 0
    if years >= 5:
        return ScoreComponent(
            name="clean_exit_signals",
            points=10,
            max_points=15,
            reason=f"Long-term distress ({years} years delinquent)",
        )
    
    return ScoreComponent(
        name="clean_exit_signals",
        points=0,
        max_points=15,
        reason="No clear exit signals detected",
    )


def compute_deterministic_score(
    lead: Lead,
    parish_median_value_per_acre: Optional[float] = None,
) -> DeterministicScore:
    """
    Compute deterministic motivation score for a lead.
    
    Args:
        lead: Lead object with parcel, owner, and party loaded.
        parish_median_value_per_acre: Pre-computed median for the parish.
    
    Returns:
        DeterministicScore with breakdown.
    """
    parcel = lead.parcel
    owner = lead.owner
    party = owner.party
    
    # Check disqualifiers first
    disqualified_reason = _check_disqualifiers(parcel, owner, party)
    if disqualified_reason:
        return DeterministicScore(
            lead_id=lead.id,
            motivation_score=0,
            components=[],
            disqualified=True,
            disqualified_reason=disqualified_reason,
        )
    
    # Calculate all components
    components = [
        _score_ownership_duration(parcel),
        _score_absentee_ownership(parcel, party),
        _score_tax_distress(parcel),
        _score_parcel_liquidity(parcel),
        _score_undervaluation(parcel, parish_median_value_per_acre),
        _score_clean_exit_signals(parcel),
    ]
    
    # Sum and cap at 100
    total = sum(c.points for c in components)
    total = min(100, max(0, total))
    
    return DeterministicScore(
        lead_id=lead.id,
        motivation_score=total,
        components=components,
        disqualified=False,
        disqualified_reason=None,
    )


def get_parish_median_values(session: Session) -> Dict[str, float]:
    """
    Compute median value_per_acre for each parish.
    
    Returns:
        Dict mapping parish name (lowercase) to median value/acre.
    """
    # Get all parcels with valid land value and acreage
    results = (
        session.query(
            Parcel.parish,
            func.avg(Parcel.land_assessed_value / Parcel.lot_size_acres).label("avg_value_per_acre"),
        )
        .filter(
            Parcel.land_assessed_value > 0,
            Parcel.lot_size_acres > 0,
        )
        .group_by(Parcel.parish)
        .all()
    )
    
    return {
        (parish or "").lower().strip(): float(avg or 0)
        for parish, avg in results
        if parish and avg
    }


def score_all_leads_deterministic(
    session: Session,
    market_code: Optional[str] = None,
    batch_size: int = 1000,
) -> Dict[str, Any]:
    """
    Re-score all leads using deterministic scoring.
    
    Args:
        session: Database session.
        market_code: Optional filter by market.
        batch_size: Leads per batch.
    
    Returns:
        Summary statistics.
    """
    from datetime import timezone
    
    start = datetime.now(timezone.utc)
    
    # Pre-compute parish medians
    LOGGER.info("Computing parish median values...")
    parish_medians = get_parish_median_values(session)
    LOGGER.info(f"Computed medians for {len(parish_medians)} parishes")
    
    # Count total
    count_query = (
        session.query(func.count(Lead.id))
        .join(Lead.parcel)
        .join(Lead.owner)
        .filter(Lead.deleted_at.is_(None))
    )
    if market_code:
        count_query = count_query.filter(Lead.market_code == market_code.upper())
    total_count = count_query.scalar() or 0
    
    LOGGER.info(f"Scoring {total_count} leads...")
    
    # Stats
    processed = 0
    disqualified = 0
    total_score = 0
    hot_count = 0
    contact_count = 0
    
    # Process in batches
    offset = 0
    while offset < total_count:
        query = (
            session.query(Lead)
            .join(Lead.parcel)
            .join(Lead.owner)
            .filter(Lead.deleted_at.is_(None))
        )
        if market_code:
            query = query.filter(Lead.market_code == market_code.upper())
        
        leads = query.offset(offset).limit(batch_size).all()
        
        for lead in leads:
            # Get parish median
            parish = (lead.parcel.parish or "").lower().strip()
            parish_median = parish_medians.get(parish)
            
            # Compute score
            result = compute_deterministic_score(lead, parish_median)
            
            # Update lead score
            lead.motivation_score = result.motivation_score
            lead.score_details = result.to_dict()
            lead.updated_at = datetime.now(timezone.utc)
            
            # Update pipeline stage based on score
            # Only update if not manually advanced (CONTACTED, REVIEW, OFFER, CONTRACT)
            manual_stages = {
                PipelineStage.CONTACTED.value, 
                PipelineStage.REVIEW.value,
                PipelineStage.OFFER.value, 
                PipelineStage.CONTRACT.value
            }
            
            if lead.pipeline_stage not in manual_stages:
                if result.disqualified:
                    lead.pipeline_stage = PipelineStage.INGESTED.value
                elif result.motivation_score >= HOT_THRESHOLD:
                    lead.pipeline_stage = PipelineStage.HOT.value
                elif result.motivation_score >= CONTACT_THRESHOLD:
                    lead.pipeline_stage = PipelineStage.NEW.value
                else:
                    lead.pipeline_stage = PipelineStage.PRE_SCORE.value
            
            # Update stats
            processed += 1
            if result.disqualified:
                disqualified += 1
            else:
                total_score += result.motivation_score
                if result.motivation_score >= HOT_THRESHOLD:
                    hot_count += 1
                elif result.motivation_score >= CONTACT_THRESHOLD:
                    contact_count += 1
        
        # Commit batch
        session.commit()
        offset += batch_size
        
        if processed % 10000 == 0:
            LOGGER.info(f"Scored {processed}/{total_count} leads...")
    
    end = datetime.now(timezone.utc)
    duration = (end - start).total_seconds()
    
    qualified_count = processed - disqualified
    avg_score = total_score / qualified_count if qualified_count > 0 else 0.0
    
    summary = {
        "total_processed": processed,
        "disqualified": disqualified,
        "qualified": qualified_count,
        "hot_leads": hot_count,
        "contact_ready": contact_count,
        "average_score": round(avg_score, 1),
        "duration_seconds": round(duration, 2),
        "thresholds": {
            "hot": HOT_THRESHOLD,
            "contact": CONTACT_THRESHOLD,
            "reject": REJECT_THRESHOLD,
        },
    }
    
    LOGGER.info(
        "Deterministic scoring complete: %d processed, %d hot, %d contact-ready, avg=%.1f",
        processed, hot_count, contact_count, avg_score
    )
    
    return summary


__all__ = [
    "compute_deterministic_score",
    "score_all_leads_deterministic",
    "get_parish_median_values",
    "DeterministicScore",
    "ScoreComponent",
    "CONTACT_THRESHOLD",
    "HOT_THRESHOLD",
    "REJECT_THRESHOLD",
]

