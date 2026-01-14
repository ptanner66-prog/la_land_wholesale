"""
Call Prep Pack API Routes

Everything needed to quote and close a lead:
- Property location
- Offer range with justification
- Call script with live injection
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from api.deps import get_db, get_readonly_db
from core.logging_config import get_logger
from core.models import Lead
from core.address_utils import compute_display_location, compute_mailing_address, format_lead_location_summary
from src.services.offer_helper import compute_offer_range, DEFAULT_DISCOUNT_LOW, DEFAULT_DISCOUNT_HIGH
from src.services.call_script import generate_call_script

router = APIRouter()
LOGGER = get_logger(__name__)


class OfferParamsRequest(BaseModel):
    """Custom offer parameters."""
    discount_low: float = Field(DEFAULT_DISCOUNT_LOW, ge=0.1, le=0.95)
    discount_high: float = Field(DEFAULT_DISCOUNT_HIGH, ge=0.15, le=1.0)


@router.get("/{lead_id}/location")
async def get_lead_location(
    lead_id: int,
    db: Session = Depends(get_readonly_db),
) -> Dict[str, Any]:
    """
    Get normalized location for a lead.
    
    Returns:
    - property_location: Where the land is (situs address or fallback)
    - mailing_address: Where to send mail (owner's address)
    
    These are SEPARATE and should never be confused.
    """
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    
    return format_lead_location_summary(lead)


@router.get("/{lead_id}/offer")
async def get_offer_range(
    lead_id: int,
    discount_low: float = Query(DEFAULT_DISCOUNT_LOW, ge=0.1, le=0.95),
    discount_high: float = Query(DEFAULT_DISCOUNT_HIGH, ge=0.15, le=1.0),
    db: Session = Depends(get_readonly_db),
) -> Dict[str, Any]:
    """
    Get computed offer range for a lead.
    
    NOT comps-dependent. Uses:
    - Land assessed value as basis
    - Acreage for per-acre calculations
    - Condition flags for adjustments
    
    Returns a RANGE with justification bullets (never a single number).
    """
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    
    offer = compute_offer_range(lead, discount_low, discount_high)
    return offer.to_dict()


@router.get("/{lead_id}/script")
async def get_call_script(
    lead_id: int,
    discount_low: float = Query(DEFAULT_DISCOUNT_LOW, ge=0.1, le=0.95),
    discount_high: float = Query(DEFAULT_DISCOUNT_HIGH, ge=0.15, le=1.0),
    db: Session = Depends(get_readonly_db),
) -> Dict[str, Any]:
    """
    Generate call script for a lead.
    
    All values are injected from lead data:
    - Property location
    - Acreage
    - Offer range
    
    Script updates live when discount params change.
    """
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    
    script = generate_call_script(lead, discount_low, discount_high)
    return script.to_dict()


@router.get("/{lead_id}/prep-pack")
async def get_call_prep_pack(
    lead_id: int,
    discount_low: float = Query(DEFAULT_DISCOUNT_LOW, ge=0.1, le=0.95),
    discount_high: float = Query(DEFAULT_DISCOUNT_HIGH, ge=0.15, le=1.0),
    db: Session = Depends(get_readonly_db),
) -> Dict[str, Any]:
    """
    Get complete Call Prep Pack for a lead.
    
    Everything needed to quote and close in one response:
    - Location (property + mailing, clearly separated)
    - Parcel snapshot
    - Offer range with justification
    - Call script with live injection
    - Map data
    """
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    
    # Get all components
    location = format_lead_location_summary(lead)
    offer = compute_offer_range(lead, discount_low, discount_high)
    script = generate_call_script(lead, discount_low, discount_high)
    
    # Parcel snapshot
    parcel = lead.parcel
    parcel_snapshot = {
        "parcel_id": parcel.canonical_parcel_id if parcel else None,
        "parish": parcel.parish if parcel else None,
        "acreage": float(parcel.lot_size_acres) if parcel and parcel.lot_size_acres else None,
        "land_value": float(parcel.land_assessed_value) if parcel and parcel.land_assessed_value else None,
        "is_adjudicated": parcel.is_adjudicated if parcel else False,
        "years_tax_delinquent": parcel.years_tax_delinquent if parcel else 0,
    }
    
    # Map data
    map_data = {
        "has_coordinates": bool(parcel and parcel.latitude and parcel.longitude),
        "latitude": parcel.latitude if parcel else None,
        "longitude": parcel.longitude if parcel else None,
        "geocode_needed": parcel and not parcel.latitude and not parcel.longitude,
    }
    
    # Owner info
    owner = lead.owner
    party = owner.party if owner else None
    owner_info = {
        "name": party.display_name if party else "Unknown",
        "phone": owner.phone_primary if owner else None,
        "email": owner.email if owner else None,
        "is_tcpa_safe": owner.is_tcpa_safe if owner else False,
    }
    
    return {
        "lead_id": lead.id,
        "motivation_score": lead.motivation_score,
        "pipeline_stage": lead.pipeline_stage,
        "owner": owner_info,
        "location": location,
        "parcel": parcel_snapshot,
        "offer": offer.to_dict(),
        "script": script.to_dict(),
        "map": map_data,
    }


__all__ = ["router"]

