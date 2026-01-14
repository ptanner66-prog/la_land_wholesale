"""Scoring endpoints."""
from __future__ import annotations

from typing import Dict, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from api.deps import get_db, get_readonly_db
from core.config import get_settings
from domain.scoring import ScoringService
from domain.leads import LeadService

router = APIRouter()
SETTINGS = get_settings()


@router.post("/score-all")
async def score_all_leads(
    min_score: Optional[int] = Query(default=None, ge=0, le=100),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Recompute motivation scores for all leads.
    
    Args:
        min_score: Optional minimum score filter.
    
    Returns:
        Scoring summary with statistics.
    """
    service = ScoringService(db)
    result = service.score_all(min_score=min_score)
    return result.to_dict()


@router.get("/lead/{lead_id}")
async def get_lead_score(
    lead_id: int,
    recalculate: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Get or recalculate motivation score for a specific lead.
    
    Args:
        lead_id: The lead ID to score.
        recalculate: If True, recalculate the score.
    
    Returns:
        Score breakdown with component details.
    """
    if recalculate:
        service = ScoringService(db)
        result = service.score_lead(lead_id)
        if result is None:
            raise HTTPException(status_code=404, detail="Lead not found")
        return {
            **result.to_dict(),
            "recalculated": True,
        }
    else:
        # Just get current score without recalculating
        lead_service = LeadService(db)
        lead = lead_service.get_lead(lead_id)
        if lead is None:
            raise HTTPException(status_code=404, detail="Lead not found")
        return {
            "lead_id": lead_id,
            "motivation_score": lead.motivation_score,
            "recalculated": False,
        }


@router.get("/parcel/{parcel_id}")
async def get_parcel_score(
    parcel_id: str,
    recalculate: bool = Query(default=True),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Get or recalculate motivation score for a lead by parcel ID.
    
    Args:
        parcel_id: The canonical parcel ID.
        recalculate: If True, recalculate the score.
    
    Returns:
        Score breakdown with component details.
    """
    service = ScoringService(db)
    result = service.score_parcel(parcel_id)
    
    if result is None:
        raise HTTPException(status_code=404, detail="No lead found for parcel")
    
    return {
        **result.to_dict(),
        "parcel_id": parcel_id,
        "recalculated": recalculate,
    }


@router.get("/distribution")
async def get_score_distribution(
    db: Session = Depends(get_readonly_db),
) -> Dict[str, Any]:
    """
    Get distribution of motivation scores across all leads.
    
    Returns:
        Score distribution with buckets and statistics.
    """
    service = ScoringService(db)
    return service.get_score_distribution()


@router.get("/config")
async def get_scoring_config() -> Dict[str, Any]:
    """
    Get current scoring weight configuration.
    
    Returns:
        Scoring weights and thresholds.
    """
    from scoring.deterministic_engine import CONTACT_THRESHOLD, HOT_THRESHOLD, REJECT_THRESHOLD
    
    return {
        "engine": "deterministic",
        "components": {
            "ownership_duration": {"max": 20, "description": "Years owned (requires last_sale_date)"},
            "absentee_ownership": {"max": 15, "description": "Out-of-state or different parish"},
            "tax_distress": {"max": 20, "description": "Adjudicated or delinquent taxes"},
            "parcel_liquidity": {"max": 15, "description": "Lot size sweet spot (0.25-5 acres)"},
            "undervaluation": {"max": 15, "description": "Below parish median value/acre"},
            "clean_exit_signals": {"max": 15, "description": "Forced sale indicators"},
        },
        "thresholds": {
            "contact": CONTACT_THRESHOLD,
            "hot": HOT_THRESHOLD,
            "reject": REJECT_THRESHOLD,
            "min_motivation_score": SETTINGS.min_motivation_score,
        },
        "disqualifiers": [
            "tcpa_unsafe",
            "no_phone",
            "not_vacant_land (improvement > land value)",
            "government_owner",
        ],
    }


@router.get("/spikes")
async def get_motivation_spikes(
    market: Optional[str] = Query(default=None, description="Filter by market code"),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_readonly_db),
) -> Dict[str, Any]:
    """
    Find leads with motivation spikes.
    
    Detects high-motivation leads based on behavioral signals,
    property indicators, and time-based urgency.
    
    Returns:
        List of leads with motivation spikes, sorted by priority.
    """
    from services.motivation_detector import find_hot_leads
    
    results = find_hot_leads(db, market_code=market, limit=limit)
    
    return {
        "total_spikes": len(results),
        "market": market or "all",
        "leads": [r.to_dict() for r in results],
    }


@router.get("/spike/{lead_id}")
async def get_lead_spike_analysis(
    lead_id: int,
    db: Session = Depends(get_readonly_db),
) -> Dict[str, Any]:
    """
    Analyze motivation spike for a specific lead.
    
    Returns detailed signals and recommendations.
    """
    from services.motivation_detector import detect_spike
    
    result = detect_spike(db, lead_id)
    return result.to_dict()