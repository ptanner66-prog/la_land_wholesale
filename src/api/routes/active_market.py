"""
Active Market API Routes.

These endpoints manage the working area (state + parish) for all operations.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from api.deps import get_db, get_readonly_db
from core.active_market import (
    ActiveMarket,
    get_active_market,
    set_active_market,
    clear_active_market,
    get_available_parishes,
    get_parish_summary,
)
from core.logging_config import get_logger

router = APIRouter()
LOGGER = get_logger(__name__)


class SetActiveMarketRequest(BaseModel):
    """Request to set the active market."""
    state: str = Field(..., description="State code (e.g., LA)")
    parish: str = Field(..., description="Parish/county name (e.g., East Baton Rouge)")


class ActiveMarketResponse(BaseModel):
    """Response containing active market info."""
    active: bool
    state: Optional[str] = None
    parish: Optional[str] = None
    display_name: Optional[str] = None
    market_code: Optional[str] = None


@router.get("")
async def get_current_active_market() -> ActiveMarketResponse:
    """
    Get the currently active market.
    
    Returns:
        Active market info or active=False if none selected.
    """
    market = get_active_market()
    if market is None:
        return ActiveMarketResponse(active=False)
    
    return ActiveMarketResponse(
        active=True,
        state=market.state,
        parish=market.parish,
        display_name=market.display_name,
        market_code=market.market_code,
    )


@router.post("")
async def set_current_active_market(
    request: SetActiveMarketRequest,
    db: Session = Depends(get_readonly_db),
) -> Dict[str, Any]:
    """
    Set the active market (working area).
    
    This MUST be called before accessing:
    - Dashboard
    - Leads
    - Caller sheets
    - Comps
    - Outreach
    """
    # Validate the parish exists in our data
    parishes = get_available_parishes(db, request.state)
    state_parishes = parishes.get(request.state.upper(), [])
    
    parish_names = [p["parish"].lower() for p in state_parishes]
    if request.parish.lower() not in parish_names:
        # Still allow setting it - might be a new parish
        LOGGER.warning(f"Setting active market to parish with no data: {request.parish}, {request.state}")
    
    market = set_active_market(request.state, request.parish)
    
    # Get summary for the selected market
    summary = get_parish_summary(db, market.state, market.parish)
    
    return {
        "success": True,
        "active_market": market.to_dict(),
        "summary": summary,
    }


@router.delete("")
async def clear_current_active_market() -> Dict[str, Any]:
    """Clear the active market."""
    clear_active_market()
    return {"success": True, "message": "Active market cleared"}


@router.get("/parishes")
async def list_available_parishes(
    state: Optional[str] = None,
    db: Session = Depends(get_readonly_db),
) -> Dict[str, Any]:
    """
    List all parishes/counties with lead data.

    If no data exists, returns default parishes from market config.
    """
    parishes = get_available_parishes(db, state)

    # If no data in database, return default parishes from market config
    if not parishes or sum(len(p) for p in parishes.values()) == 0:
        from services.market import MARKET_CONFIGS
        default_parishes = {}
        for code, config in MARKET_CONFIGS.items():
            default_parishes[code] = [{
                "parish": config.default_parish,
                "lead_count": 0,
                "parcel_count": 0,
            }]
        parishes = default_parishes

    return {
        "parishes_by_state": parishes,
        "total_states": len(parishes),
    }


@router.get("/summary")
async def get_active_market_summary(
    db: Session = Depends(get_readonly_db),
) -> Dict[str, Any]:
    """
    Get summary statistics for the active market.
    
    Requires an active market to be set.
    """
    from core.active_market import require_active_market
    
    market = require_active_market()
    summary = get_parish_summary(db, market.state, market.parish)
    
    return {
        "active_market": market.to_dict(),
        "summary": summary,
    }


__all__ = ["router"]

