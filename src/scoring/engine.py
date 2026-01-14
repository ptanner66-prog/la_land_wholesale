"""Lead scoring engine - delegates to deterministic engine."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.config import get_settings
from core.logging_config import get_logger
from core.models import Lead, Owner, Parcel
from scoring.deterministic_engine import (
    compute_deterministic_score,
    score_all_leads_deterministic,
    get_parish_median_values,
    CONTACT_THRESHOLD,
    HOT_THRESHOLD,
)

LOGGER = get_logger(__name__)
SETTINGS = get_settings()


@dataclass
class ScoringSummary:
    """Summary of a scoring run."""
    
    leads_scored: int
    average_score: float
    high_priority_count: int


def compute_motivation_score(
    parcel: Parcel,
    owner: Owner,
    is_adjudicated: bool,
    parish_median_value_per_acre: Optional[float] = None,
) -> int:
    """
    Calculate motivation score (0-100) for a single lead.
    
    This is a compatibility wrapper around the deterministic engine.
    For full score details, use compute_deterministic_score() directly.
    
    Args:
        parcel: Parcel object.
        owner: Owner object.
        is_adjudicated: Whether the property is adjudicated (ignored, read from parcel).
        parish_median_value_per_acre: Optional parish median for undervaluation calc.
        
    Returns:
        Integer score between 0 and 100.
    """
    # Create a minimal Lead-like object for the deterministic engine
    # This is for backward compatibility with existing callers
    
    from scoring.deterministic_engine import (
        _check_disqualifiers,
        _score_ownership_duration,
        _score_absentee_ownership,
        _score_tax_distress,
        _score_parcel_liquidity,
        _score_undervaluation,
        _score_clean_exit_signals,
    )
    
    party = owner.party
    
    # Check disqualifiers
    disqualified = _check_disqualifiers(parcel, owner, party)
    if disqualified:
        return 0
    
    # Calculate components
    components = [
        _score_ownership_duration(parcel),
        _score_absentee_ownership(parcel, party),
        _score_tax_distress(parcel),
        _score_parcel_liquidity(parcel),
        _score_undervaluation(parcel, parish_median_value_per_acre),
        _score_clean_exit_signals(parcel),
    ]
    
    total = sum(c.points for c in components)
    return min(100, max(0, total))


def _calculate_motivation_score(lead: Lead, parish_median: Optional[float] = None) -> int:
    """Internal helper to calculate score from a Lead object."""
    return compute_motivation_score(
        parcel=lead.parcel,
        owner=lead.owner,
        is_adjudicated=lead.parcel.is_adjudicated,
        parish_median_value_per_acre=parish_median,
    )


def score_all_leads(session: Session, min_score: Optional[int] = None) -> ScoringSummary:
    """
    Re-score all leads in the database using deterministic scoring.
    
    Args:
        session: Database session.
        min_score: Optional filter for summary stats.
        
    Returns:
        ScoringSummary object.
    """
    LOGGER.info("Starting deterministic batch scoring of all leads...")
    
    result = score_all_leads_deterministic(session)
    
    threshold = min_score if min_score is not None else CONTACT_THRESHOLD
    
    # Count high priority based on threshold
    high_priority = result["hot_leads"]
    if threshold <= CONTACT_THRESHOLD:
        high_priority += result["contact_ready"]
    
    return ScoringSummary(
        leads_scored=result["total_processed"],
        average_score=result["average_score"],
        high_priority_count=high_priority,
    )
