"""
Active Market Management - First-class market/parish locking.

The Active Market is the single source of truth for area-scoped operations.
All queries, exports, and actions MUST be scoped to the Active Market.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Any
from sqlalchemy import func, distinct
from sqlalchemy.orm import Session

from core.logging_config import get_logger
from core.models import Lead, Parcel

LOGGER = get_logger(__name__)


@dataclass
class ActiveMarket:
    """
    The current working area.
    
    Exactly one Active Market must be selected before:
    - Dashboard access
    - Lead operations
    - Caller sheets
    - Comps
    - Outreach
    """
    state: str  # e.g., "LA"
    parish: str  # e.g., "East Baton Rouge"
    
    @property
    def display_name(self) -> str:
        """Human-readable display name."""
        return f"{self.parish} Parish, {self.state}"
    
    @property
    def market_code(self) -> str:
        """Legacy market code (state)."""
        return self.state.upper()
    
    def to_dict(self) -> Dict[str, str]:
        return {
            "state": self.state,
            "parish": self.parish,
            "display_name": self.display_name,
            "market_code": self.market_code,
        }


# Server-side session storage (simple in-memory for single-instance)
# In production, this would be Redis or DB-backed
_active_market: Optional[ActiveMarket] = None


def get_active_market() -> Optional[ActiveMarket]:
    """Get the currently active market."""
    return _active_market


def set_active_market(state: str, parish: str) -> ActiveMarket:
    """Set the active market."""
    global _active_market
    _active_market = ActiveMarket(state=state.upper(), parish=parish)
    LOGGER.info(f"Active market set to: {_active_market.display_name}")
    return _active_market


def clear_active_market() -> None:
    """Clear the active market."""
    global _active_market
    _active_market = None
    LOGGER.info("Active market cleared")


def require_active_market() -> ActiveMarket:
    """
    Get the active market, raising an error if not set.
    
    Use this in any endpoint that requires area scoping.
    """
    market = get_active_market()
    if market is None:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=400,
            detail={
                "error": "no_active_market",
                "message": "No active market selected. Please select a working area first.",
                "action": "Select a state and parish to continue.",
            }
        )
    return market


def get_available_parishes(session: Session, state: Optional[str] = None) -> Dict[str, List[str]]:
    """
    Get all parishes with data, grouped by state.
    
    Returns:
        Dict mapping state codes to lists of parishes.
    """
    query = (
        session.query(
            Lead.market_code,
            Parcel.parish,
            func.count(Lead.id).label("lead_count")
        )
        .join(Lead.parcel)
        .filter(
            Lead.deleted_at.is_(None),
            Parcel.parish.isnot(None),
            Parcel.parish != "",
        )
        .group_by(Lead.market_code, Parcel.parish)
        .order_by(Lead.market_code, Parcel.parish)
    )
    
    if state:
        query = query.filter(Lead.market_code == state.upper())
    
    results = query.all()
    
    parishes_by_state: Dict[str, List[Dict[str, Any]]] = {}
    for market_code, parish, count in results:
        if market_code not in parishes_by_state:
            parishes_by_state[market_code] = []
        parishes_by_state[market_code].append({
            "parish": parish,
            "lead_count": count,
        })
    
    return parishes_by_state


def get_parish_summary(session: Session, state: str, parish: str) -> Dict[str, Any]:
    """Get summary statistics for a specific parish."""
    from scoring.deterministic_engine import HOT_THRESHOLD, CONTACT_THRESHOLD
    
    base_filter = (
        (Lead.market_code == state.upper()) &
        (Lead.deleted_at.is_(None))
    )
    
    # Join with parcel to filter by parish
    total = (
        session.query(func.count(Lead.id))
        .join(Lead.parcel)
        .filter(base_filter, func.lower(Parcel.parish) == parish.lower())
        .scalar() or 0
    )
    
    hot = (
        session.query(func.count(Lead.id))
        .join(Lead.parcel)
        .filter(
            base_filter,
            func.lower(Parcel.parish) == parish.lower(),
            Lead.motivation_score >= HOT_THRESHOLD
        )
        .scalar() or 0
    )
    
    contact = (
        session.query(func.count(Lead.id))
        .join(Lead.parcel)
        .filter(
            base_filter,
            func.lower(Parcel.parish) == parish.lower(),
            Lead.motivation_score >= CONTACT_THRESHOLD,
            Lead.motivation_score < HOT_THRESHOLD
        )
        .scalar() or 0
    )
    
    # Check if manual comp data exists for this parish/market
    from core.models import ManualComp
    has_sales_data = (
        db.query(func.count(ManualComp.id))
        .filter(
            ManualComp.market_code == state.upper(),
            func.lower(ManualComp.parish) == parish.lower(),
        )
        .scalar() or 0
    ) > 0
    
    return {
        "state": state.upper(),
        "parish": parish,
        "total_leads": total,
        "hot_leads": hot,
        "contact_leads": contact,
        "has_sales_data": has_sales_data,
    }


__all__ = [
    "ActiveMarket",
    "get_active_market",
    "set_active_market",
    "clear_active_market",
    "require_active_market",
    "get_available_parishes",
    "get_parish_summary",
]

