"""Parcel management endpoints."""
from __future__ import annotations

from typing import Dict, Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from api.deps import get_readonly_db
from core.models import Parcel

router = APIRouter()


@router.get("")
async def list_parcels(
    market: Optional[str] = Query(default=None, description="Filter by market code"),
    is_adjudicated: Optional[bool] = Query(default=None, description="Filter by adjudicated status"),
    parish: Optional[str] = Query(default=None, description="Filter by parish"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_readonly_db),
) -> List[Dict[str, Any]]:
    """
    List parcels with filtering and pagination.
    
    Args:
        market: Filter by market code.
        is_adjudicated: Filter by adjudicated status.
        parish: Filter by parish name.
        limit: Maximum number of parcels to return.
        offset: Number of parcels to skip.
    
    Returns:
        List of parcel objects.
    """
    query = db.query(Parcel)
    
    if market:
        query = query.filter(Parcel.market_code == market.upper())
    
    if is_adjudicated is not None:
        query = query.filter(Parcel.is_adjudicated == is_adjudicated)
    
    if parish:
        query = query.filter(Parcel.parish.ilike(f"%{parish}%"))
    
    parcels = query.order_by(Parcel.created_at.desc()).offset(offset).limit(limit).all()
    
    return [
        {
            "id": p.id,
            "canonical_parcel_id": p.canonical_parcel_id,
            "parish": p.parish,
            "market_code": p.market_code,
            "situs_address": p.situs_address,
            "city": p.city,
            "state": p.state,
            "postal_code": p.postal_code,
            "latitude": p.latitude,
            "longitude": p.longitude,
            "zoning_code": p.zoning_code,
            "inside_city_limits": p.inside_city_limits,
            "land_assessed_value": float(p.land_assessed_value) if p.land_assessed_value else None,
            "improvement_assessed_value": float(p.improvement_assessed_value) if p.improvement_assessed_value else None,
            "lot_size_acres": float(p.lot_size_acres) if p.lot_size_acres else None,
            "is_adjudicated": p.is_adjudicated,
            "years_tax_delinquent": p.years_tax_delinquent,
            "created_at": p.created_at.isoformat() if p.created_at else None,
        }
        for p in parcels
    ]


@router.get("/statistics")
async def get_parcel_statistics(
    market: Optional[str] = Query(default=None, description="Filter by market code"),
    db: Session = Depends(get_readonly_db),
) -> Dict[str, Any]:
    """
    Get parcel statistics summary.
    
    Returns:
        Statistics including adjudicated counts.
    """
    base_query = db.query(Parcel)
    if market:
        base_query = base_query.filter(Parcel.market_code == market.upper())
    
    total = base_query.with_entities(func.count(Parcel.id)).scalar() or 0
    adjudicated = base_query.filter(Parcel.is_adjudicated.is_(True)).with_entities(func.count(Parcel.id)).scalar() or 0
    tax_delinquent = base_query.filter(Parcel.years_tax_delinquent > 0).with_entities(func.count(Parcel.id)).scalar() or 0
    
    return {
        "total_parcels": total,
        "adjudicated": adjudicated,
        "tax_delinquent": tax_delinquent,
        "adjudicated_rate": round(adjudicated / total * 100, 1) if total > 0 else 0,
        "market": market or "all",
    }


@router.get("/{parcel_id}")
async def get_parcel(
    parcel_id: str,
    db: Session = Depends(get_readonly_db),
) -> Dict[str, Any]:
    """
    Get detailed information for a specific parcel.
    
    Args:
        parcel_id: The canonical parcel ID.
    
    Returns:
        Parcel details.
    """
    parcel = db.query(Parcel).filter(
        Parcel.canonical_parcel_id == parcel_id
    ).one_or_none()
    
    if parcel is None:
        raise HTTPException(status_code=404, detail="Parcel not found")
    
    return {
        "id": parcel.id,
        "canonical_parcel_id": parcel.canonical_parcel_id,
        "parish": parcel.parish,
        "market_code": parcel.market_code,
        "situs_address": parcel.situs_address,
        "city": parcel.city,
        "state": parcel.state,
        "postal_code": parcel.postal_code,
        "latitude": parcel.latitude,
        "longitude": parcel.longitude,
        "zoning_code": parcel.zoning_code,
        "geom": parcel.geom,
        "inside_city_limits": parcel.inside_city_limits,
        "land_assessed_value": float(parcel.land_assessed_value) if parcel.land_assessed_value else None,
        "improvement_assessed_value": float(parcel.improvement_assessed_value) if parcel.improvement_assessed_value else None,
        "lot_size_acres": float(parcel.lot_size_acres) if parcel.lot_size_acres else None,
        "is_adjudicated": parcel.is_adjudicated,
        "years_tax_delinquent": parcel.years_tax_delinquent,
        "raw_data": parcel.raw_data,
        "created_at": parcel.created_at.isoformat() if parcel.created_at else None,
        "updated_at": parcel.updated_at.isoformat() if parcel.updated_at else None,
    }

