"""Market routes."""
from __future__ import annotations

from typing import Dict, Any, List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from api.deps import get_readonly_db
from core.logging_config import get_logger
from core.models import Lead, Owner, Parcel, PipelineStage
from src.services.market import MarketService, MarketConfig

router = APIRouter()
LOGGER = get_logger(__name__)


@router.get("")
async def get_all_markets() -> List[Dict[str, Any]]:
    """Get all market configurations."""
    markets = MarketService.get_all_markets()
    return [
        {
            "code": m.code,
            "name": m.name,
            "default_parish": m.default_parish,
            "min_motivation_score": m.min_motivation_score,
            "hot_score_threshold": m.hot_score_threshold,
            "followup_schedule": {
                "day_1": m.followup_day_1,
                "day_2": m.followup_day_2,
                "max_followups": m.max_followups,
            },
            "outreach_window": {
                "start_hour": m.outreach_window_start,
                "end_hour": m.outreach_window_end,
            },
        }
        for m in markets
    ]


@router.get("/codes")
async def get_market_codes() -> List[str]:
    """Get list of all market codes."""
    return MarketService.get_market_codes()


@router.get("/{market_code}")
async def get_market_config(market_code: str) -> Dict[str, Any]:
    """Get configuration for a specific market."""
    config = MarketService.get_market(market_code.upper())
    if not config:
        raise HTTPException(status_code=404, detail="Market not found")
    
    return {
        "code": config.code,
        "name": config.name,
        "default_parish": config.default_parish,
        "min_motivation_score": config.min_motivation_score,
        "hot_score_threshold": config.hot_score_threshold,
        "followup_schedule": {
            "day_1": config.followup_day_1,
            "day_2": config.followup_day_2,
            "max_followups": config.max_followups,
        },
        "outreach_window": {
            "start_hour": config.outreach_window_start,
            "end_hour": config.outreach_window_end,
        },
        "scoring_weights": MarketService.get_scoring_weights(market_code),
    }


@router.get("/{market_code}/stats")
async def get_market_stats(
    market_code: str,
    db: Session = Depends(get_readonly_db),
) -> Dict[str, Any]:
    """
    Get statistics for a specific market.
    
    Uses score-based classification as primary source of truth.
    """
    from scoring.deterministic_engine import CONTACT_THRESHOLD, HOT_THRESHOLD, REJECT_THRESHOLD
    
    if not MarketService.is_valid_market(market_code):
        raise HTTPException(status_code=404, detail="Market not found")
    
    market = market_code.upper()
    base_filter = (Lead.market_code == market) & (Lead.deleted_at.is_(None))
    
    # Count leads by stage (for stage-based views)
    stage_counts = dict(
        db.query(Lead.pipeline_stage, func.count(Lead.id))
        .filter(base_filter)
        .group_by(Lead.pipeline_stage)
        .all()
    )
    
    # Ensure all stages are present
    for stage in PipelineStage:
        if stage.value not in stage_counts:
            stage_counts[stage.value] = 0
    
    # Score-based counts (primary source of truth)
    scored_leads = db.query(func.count(Lead.id)).filter(
        base_filter,
        Lead.motivation_score > 0
    ).scalar() or 0
    
    hot_leads = db.query(func.count(Lead.id)).filter(
        base_filter,
        Lead.motivation_score >= HOT_THRESHOLD
    ).scalar() or 0
    
    contact_leads = db.query(func.count(Lead.id)).filter(
        base_filter,
        Lead.motivation_score >= CONTACT_THRESHOLD,
        Lead.motivation_score < HOT_THRESHOLD
    ).scalar() or 0
    
    low_leads = db.query(func.count(Lead.id)).filter(
        base_filter,
        Lead.motivation_score > 0,
        Lead.motivation_score < CONTACT_THRESHOLD
    ).scalar() or 0
    
    # Total counts
    total_leads = db.query(func.count(Lead.id)).filter(base_filter).scalar() or 0
    total_owners = db.query(func.count(Owner.id)).filter(Owner.market_code == market).scalar() or 0
    total_parcels = db.query(func.count(Parcel.id)).filter(Parcel.market_code == market).scalar() or 0
    
    # Average score (only for scored leads)
    avg_score = db.query(func.avg(Lead.motivation_score)).filter(
        base_filter,
        Lead.motivation_score > 0
    ).scalar() or 0
    
    return {
        "market_code": market,
        "total_leads": total_leads,
        "stage_counts": stage_counts,
        "total_owners": total_owners,
        "total_parcels": total_parcels,
        "avg_motivation_score": round(float(avg_score), 1),
        # Score-based counts (primary)
        "score_based": {
            "scored": scored_leads,
            "hot": hot_leads,
            "contact": contact_leads,
            "low": low_leads,
        },
        "thresholds": {
            "hot": HOT_THRESHOLD,
            "contact": CONTACT_THRESHOLD,
            "reject": REJECT_THRESHOLD,
        },
    }
