"""Owner management endpoints."""
from __future__ import annotations

from typing import Dict, Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from api.deps import get_db, get_readonly_db
from core.models import Owner, Party, Lead

router = APIRouter()


@router.get("")
async def list_owners(
    market: Optional[str] = Query(default=None, description="Filter by market code"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    tcpa_safe_only: bool = Query(default=False),
    has_phone: bool = Query(default=False),
    db: Session = Depends(get_readonly_db),
) -> List[Dict[str, Any]]:
    """
    List owners with filtering and pagination.
    
    Args:
        market: Filter by market code.
        limit: Maximum number of owners to return.
        offset: Number of owners to skip.
        tcpa_safe_only: Only return TCPA-safe owners.
        has_phone: Only return owners with phone numbers.
    
    Returns:
        List of owner objects.
    """
    query = (
        db.query(Owner)
        .join(Owner.party)
        .options(selectinload(Owner.party))
    )
    
    if market:
        query = query.filter(Owner.market_code == market.upper())
    
    if tcpa_safe_only:
        query = query.filter(Owner.is_tcpa_safe.is_(True))
    
    if has_phone:
        query = query.filter(
            Owner.phone_primary.isnot(None),
            Owner.phone_primary != "",
        )
    
    owners = query.offset(offset).limit(limit).all()
    
    result = []
    for owner in owners:
        result.append({
            "id": owner.id,
            "party_id": owner.party_id,
            "name": owner.party.display_name or owner.party.normalized_name,
            "phone_primary": owner.phone_primary,
            "phone_secondary": owner.phone_secondary,
            "email": owner.email,
            "market_code": owner.market_code,
            "is_tcpa_safe": owner.is_tcpa_safe,
            "is_dnr": owner.is_dnr,
            "opt_out": owner.opt_out,
            "mailing_address": owner.party.raw_mailing_address,
            "created_at": owner.created_at.isoformat() if owner.created_at else None,
        })
    
    return result


@router.get("/statistics")
async def get_owner_statistics(
    market: Optional[str] = Query(default=None, description="Filter by market code"),
    db: Session = Depends(get_readonly_db),
) -> Dict[str, Any]:
    """
    Get owner statistics summary.
    
    Returns:
        Statistics including TCPA counts.
    """
    base_query = db.query(Owner)
    if market:
        base_query = base_query.filter(Owner.market_code == market.upper())
    
    total = base_query.with_entities(func.count(Owner.id)).scalar() or 0
    tcpa_safe = base_query.filter(Owner.is_tcpa_safe.is_(True)).with_entities(func.count(Owner.id)).scalar() or 0
    with_phone = base_query.filter(
        Owner.phone_primary.isnot(None),
        Owner.phone_primary != "",
    ).with_entities(func.count(Owner.id)).scalar() or 0
    dnr_count = base_query.filter(Owner.is_dnr.is_(True)).with_entities(func.count(Owner.id)).scalar() or 0
    
    return {
        "total_owners": total,
        "tcpa_safe": tcpa_safe,
        "with_phone": with_phone,
        "dnr_flagged": dnr_count,
        "tcpa_rate": round(tcpa_safe / total * 100, 1) if total > 0 else 0,
        "market": market or "all",
    }


@router.get("/{owner_id}")
async def get_owner(
    owner_id: int,
    db: Session = Depends(get_readonly_db),
) -> Dict[str, Any]:
    """
    Get detailed information for a specific owner.
    
    Args:
        owner_id: The owner ID to fetch.
    
    Returns:
        Owner details including leads.
    """
    owner = (
        db.query(Owner)
        .options(
            selectinload(Owner.party),
            selectinload(Owner.leads).selectinload(Lead.parcel),
        )
        .filter(Owner.id == owner_id)
        .one_or_none()
    )
    
    if owner is None:
        raise HTTPException(status_code=404, detail="Owner not found")
    
    leads_data = []
    for lead in owner.leads:
        leads_data.append({
            "lead_id": lead.id,
            "parcel_id": lead.parcel.canonical_parcel_id,
            "parish": lead.parcel.parish,
            "motivation_score": lead.motivation_score,
            "pipeline_stage": lead.pipeline_stage,
            "status": lead.status,
        })
    
    return {
        "id": owner.id,
        "party_id": owner.party_id,
        "name": owner.party.display_name or owner.party.normalized_name,
        "normalized_name": owner.party.normalized_name,
        "phone_primary": owner.phone_primary,
        "phone_secondary": owner.phone_secondary,
        "email": owner.email,
        "market_code": owner.market_code,
        "is_tcpa_safe": owner.is_tcpa_safe,
        "is_dnr": owner.is_dnr,
        "opt_out": owner.opt_out,
        "mailing_address": owner.party.raw_mailing_address,
        "leads": leads_data,
        "lead_count": len(leads_data),
    }


@router.patch("/{owner_id}/dnr")
async def set_owner_dnr(
    owner_id: int,
    is_dnr: bool = Query(..., description="Do Not Reach flag"),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Set or clear the Do Not Reach flag for an owner.
    
    Args:
        owner_id: The owner ID to update.
        is_dnr: New DNR flag value.
    
    Returns:
        Updated owner details.
    """
    owner = db.query(Owner).filter(Owner.id == owner_id).one_or_none()
    
    if owner is None:
        raise HTTPException(status_code=404, detail="Owner not found")
    
    owner.is_dnr = is_dnr
    db.flush()
    
    return {
        "id": owner.id,
        "is_dnr": owner.is_dnr,
        "message": f"DNR flag {'set' if is_dnr else 'cleared'} for owner {owner_id}",
    }


@router.patch("/{owner_id}/tcpa")
async def set_owner_tcpa(
    owner_id: int,
    is_tcpa_safe: bool = Query(..., description="TCPA safe flag"),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Set or clear the TCPA safe flag for an owner.
    
    Args:
        owner_id: The owner ID to update.
        is_tcpa_safe: New TCPA safe flag value.
    
    Returns:
        Updated owner details.
    """
    owner = db.query(Owner).filter(Owner.id == owner_id).one_or_none()
    
    if owner is None:
        raise HTTPException(status_code=404, detail="Owner not found")
    
    owner.is_tcpa_safe = is_tcpa_safe
    db.flush()
    
    return {
        "id": owner.id,
        "is_tcpa_safe": owner.is_tcpa_safe,
        "message": f"TCPA flag {'set' if is_tcpa_safe else 'cleared'} for owner {owner_id}",
    }
