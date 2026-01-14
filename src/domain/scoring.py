"""Scoring domain service - core business logic for lead scoring."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from core.config import get_settings
from core.logging_config import get_logger
from core.models import Lead, Owner, Parcel, PipelineStage
from scoring.deterministic_engine import (
    compute_deterministic_score,
    score_all_leads_deterministic,
    get_parish_median_values,
    DeterministicScore,
    CONTACT_THRESHOLD,
    HOT_THRESHOLD,
    REJECT_THRESHOLD,
)

LOGGER = get_logger(__name__)
SETTINGS = get_settings()


@dataclass
class ScoreBreakdown:
    """Detailed breakdown of a lead's score."""
    
    lead_id: int
    motivation_score: int
    components: Dict[str, int]
    factors: List[Dict[str, Any]]
    parcel_id: str
    is_adjudicated: bool
    years_tax_delinquent: int
    lot_size_acres: Optional[float]
    disqualified: bool = False
    disqualified_reason: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "lead_id": self.lead_id,
            "motivation_score": self.motivation_score,
            "total_score": self.motivation_score,
            "components": self.components,
            "factors": self.factors,
            "parcel_id": self.parcel_id,
            "is_adjudicated": self.is_adjudicated,
            "years_tax_delinquent": self.years_tax_delinquent,
            "lot_size_acres": float(self.lot_size_acres) if self.lot_size_acres else None,
            "disqualified": self.disqualified,
            "disqualified_reason": self.disqualified_reason,
        }
    
    @classmethod
    def from_deterministic(cls, result: DeterministicScore, parcel: Parcel) -> "ScoreBreakdown":
        """Create ScoreBreakdown from DeterministicScore."""
        result_dict = result.to_dict()
        return cls(
            lead_id=result.lead_id,
            motivation_score=result.motivation_score,
            components=result_dict.get("components", {}),
            factors=result_dict.get("factors", []),
            parcel_id=parcel.canonical_parcel_id,
            is_adjudicated=parcel.is_adjudicated,
            years_tax_delinquent=parcel.years_tax_delinquent or 0,
            lot_size_acres=parcel.lot_size_acres,
            disqualified=result.disqualified,
            disqualified_reason=result.disqualified_reason,
        )


@dataclass
class ScoringResult:
    """Result of a batch scoring operation."""
    
    updated: int
    average_score: float
    high_priority_count: int
    duration_seconds: float
    disqualified_count: int = 0
    hot_count: int = 0
    contact_ready_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "updated": self.updated,
            "average_score": round(self.average_score, 1),
            "high_priority_count": self.high_priority_count,
            "duration_seconds": round(self.duration_seconds, 2),
            "disqualified_count": self.disqualified_count,
            "hot_count": self.hot_count,
            "contact_ready_count": self.contact_ready_count,
            "thresholds": {
                "hot": HOT_THRESHOLD,
                "contact": CONTACT_THRESHOLD,
                "reject": REJECT_THRESHOLD,
            },
        }


class ScoringService:
    """Service for lead scoring operations using deterministic engine."""
    
    def __init__(self, session: Session) -> None:
        """Initialize the scoring service with a database session."""
        self.session = session
        self._parish_medians: Optional[Dict[str, float]] = None
    
    def _get_parish_medians(self) -> Dict[str, float]:
        """Get or compute parish median values (cached)."""
        if self._parish_medians is None:
            self._parish_medians = get_parish_median_values(self.session)
        return self._parish_medians
    
    def _calculate_score_breakdown(self, lead: Lead) -> ScoreBreakdown:
        """Calculate score with component breakdown for a single lead."""
        parish = (lead.parcel.parish or "").lower().strip()
        parish_median = self._get_parish_medians().get(parish)
        
        result = compute_deterministic_score(lead, parish_median)
        return ScoreBreakdown.from_deterministic(result, lead.parcel)
    
    def score_lead(self, lead: Lead) -> ScoreBreakdown:
        """
        Score a specific lead and update score_details + pipeline_stage atomically.
        
        Args:
            lead: The Lead object to score.
        
        Returns:
            ScoreBreakdown with details.
        """
        from core.models import PipelineStage
        
        breakdown = self._calculate_score_breakdown(lead)
        
        # Update the lead's score and details
        lead.motivation_score = breakdown.motivation_score
        lead.score_details = breakdown.to_dict()
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
            if breakdown.disqualified:
                lead.pipeline_stage = PipelineStage.INGESTED.value
            elif breakdown.motivation_score >= HOT_THRESHOLD:
                lead.pipeline_stage = PipelineStage.HOT.value
            elif breakdown.motivation_score >= CONTACT_THRESHOLD:
                lead.pipeline_stage = PipelineStage.NEW.value
            else:
                lead.pipeline_stage = PipelineStage.PRE_SCORE.value
        
        self.session.flush()
        
        return breakdown
    
    def score_lead_by_id(self, lead_id: int) -> Optional[ScoreBreakdown]:
        """
        Score a specific lead by ID and return breakdown.
        
        Args:
            lead_id: The lead ID to score.
        
        Returns:
            ScoreBreakdown or None if lead not found.
        """
        lead = (
            self.session.query(Lead)
            .join(Lead.parcel)
            .join(Lead.owner)
            .filter(Lead.id == lead_id)
            .one_or_none()
        )
        
        if lead is None:
            return None
        
        return self.score_lead(lead)
    
    def score_parcel(self, parcel_id: str) -> Optional[ScoreBreakdown]:
        """
        Score a lead by its parcel ID.
        
        Args:
            parcel_id: The canonical parcel ID.
        
        Returns:
            ScoreBreakdown or None if not found.
        """
        lead = (
            self.session.query(Lead)
            .join(Lead.parcel)
            .join(Lead.owner)
            .filter(Parcel.canonical_parcel_id == parcel_id)
            .first()
        )
        
        if lead is None:
            return None
        
        return self.score_lead(lead)
    
    def score_all(
        self,
        min_score: Optional[int] = None,
        market_code: Optional[str] = None,
        batch_size: int = 1000,
    ) -> ScoringResult:
        """
        Re-score all leads in the database using deterministic scoring.
        
        Args:
            min_score: Optional filter for high-priority count.
            market_code: Optional filter by market.
            batch_size: Number of leads to process per batch.
        
        Returns:
            ScoringResult with statistics.
        """
        result = score_all_leads_deterministic(
            self.session,
            market_code=market_code,
            batch_size=batch_size,
        )
        
        threshold = min_score if min_score is not None else CONTACT_THRESHOLD
        high_priority = result["hot_leads"]
        if threshold <= CONTACT_THRESHOLD:
            high_priority += result["contact_ready"]
        
        return ScoringResult(
            updated=result["total_processed"],
            average_score=result["average_score"],
            high_priority_count=high_priority,
            duration_seconds=result["duration_seconds"],
            disqualified_count=result["disqualified"],
            hot_count=result["hot_leads"],
            contact_ready_count=result["contact_ready"],
        )
    
    def get_score_distribution(self, market_code: Optional[str] = None) -> Dict[str, Any]:
        """
        Get distribution of scores across all leads.
        
        Args:
            market_code: Optional filter by market.
        
        Returns:
            Distribution data with buckets.
        """
        # Score buckets aligned with thresholds
        buckets = {
            f"0-{REJECT_THRESHOLD-1}": 0,      # Reject
            f"{REJECT_THRESHOLD}-{CONTACT_THRESHOLD-1}": 0,  # Low
            f"{CONTACT_THRESHOLD}-{HOT_THRESHOLD-1}": 0,     # Contact
            f"{HOT_THRESHOLD}-100": 0,          # Hot
        }
        
        query = self.session.query(Lead.motivation_score).filter(Lead.deleted_at.is_(None))
        if market_code:
            query = query.filter(Lead.market_code == market_code.upper())
        
        leads = query.all()
        
        for (score,) in leads:
            if score < REJECT_THRESHOLD:
                buckets[f"0-{REJECT_THRESHOLD-1}"] += 1
            elif score < CONTACT_THRESHOLD:
                buckets[f"{REJECT_THRESHOLD}-{CONTACT_THRESHOLD-1}"] += 1
            elif score < HOT_THRESHOLD:
                buckets[f"{CONTACT_THRESHOLD}-{HOT_THRESHOLD-1}"] += 1
            else:
                buckets[f"{HOT_THRESHOLD}-100"] += 1
        
        total = len(leads)
        avg = sum(s for (s,) in leads) / total if total > 0 else 0
        
        return {
            "total_leads": total,
            "average_score": round(avg, 1),
            "distribution": buckets,
            "thresholds": {
                "reject": REJECT_THRESHOLD,
                "contact": CONTACT_THRESHOLD,
                "hot": HOT_THRESHOLD,
            },
            "market": market_code or "all",
        }


__all__ = ["ScoringService", "ScoreBreakdown", "ScoringResult"]
