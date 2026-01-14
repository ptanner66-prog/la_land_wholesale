"""Buyer management routes."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Body
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from api.deps import get_db, get_readonly_db
from core.logging_config import get_logger
from core.models import Buyer, BuyerDeal, BuyerDealStage

router = APIRouter()
LOGGER = get_logger(__name__)


# =============================================================================
# Pydantic Models
# =============================================================================


class BuyerCreate(BaseModel):
    """Request body for creating a buyer."""
    
    name: str = Field(..., min_length=1, description="Buyer's name")
    phone: Optional[str] = Field(None, description="Phone number")
    email: Optional[str] = Field(None, description="Email address")
    market_codes: List[str] = Field(default_factory=list, description="Target markets")
    counties: List[str] = Field(default_factory=list, description="Target counties")
    min_acres: Optional[float] = Field(None, ge=0, description="Minimum acreage")
    max_acres: Optional[float] = Field(None, ge=0, description="Maximum acreage")
    property_types: List[str] = Field(default_factory=list, description="Property types")
    price_min: Optional[float] = Field(None, ge=0, description="Minimum price")
    price_max: Optional[float] = Field(None, ge=0, description="Maximum price")
    target_spread: Optional[float] = Field(None, ge=0, description="Target assignment fee")
    closing_speed_days: Optional[int] = Field(None, ge=1, description="Closing speed in days")
    vip: bool = Field(False, description="VIP buyer status")
    notes: Optional[str] = Field(None, description="Notes")
    pof_url: Optional[str] = Field(None, description="Proof of funds URL")


class BuyerUpdate(BaseModel):
    """Request body for updating a buyer."""
    
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    market_codes: Optional[List[str]] = None
    counties: Optional[List[str]] = None
    min_acres: Optional[float] = None
    max_acres: Optional[float] = None
    property_types: Optional[List[str]] = None
    price_min: Optional[float] = None
    price_max: Optional[float] = None
    target_spread: Optional[float] = None
    closing_speed_days: Optional[int] = None
    vip: Optional[bool] = None
    notes: Optional[str] = None
    pof_url: Optional[str] = None


class POFUpdate(BaseModel):
    """Request body for updating proof of funds."""
    
    pof_url: str = Field(..., description="URL to POF document")
    verified: bool = Field(False, description="Whether POF is verified")


class DealStageUpdate(BaseModel):
    """Request body for updating deal stage."""
    
    stage: str = Field(..., description="New stage")
    offer_amount: Optional[float] = Field(None, description="Offer amount if applicable")
    assignment_fee: Optional[float] = Field(None, description="Assignment fee if applicable")
    notes: Optional[str] = Field(None, description="Notes")


# =============================================================================
# Routes
# =============================================================================


@router.post("")
async def create_buyer(
    body: BuyerCreate,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Create a new buyer."""
    from services.buyer import get_buyer_service, BuyerCreate as BuyerCreateData
    
    service = get_buyer_service(db)
    
    data = BuyerCreateData(
        name=body.name,
        phone=body.phone,
        email=body.email,
        market_codes=body.market_codes,
        counties=body.counties,
        min_acres=body.min_acres,
        max_acres=body.max_acres,
        property_types=body.property_types,
        price_min=body.price_min,
        price_max=body.price_max,
        target_spread=body.target_spread,
        closing_speed_days=body.closing_speed_days,
        vip=body.vip,
        notes=body.notes,
        pof_url=body.pof_url,
    )
    
    buyer = service.create_buyer(data)
    db.commit()
    
    return buyer.to_dict()


@router.get("")
async def list_buyers(
    market: Optional[str] = Query(None, description="Filter by market code"),
    vip_only: bool = Query(False, description="Only VIP buyers"),
    pof_verified_only: bool = Query(False, description="Only POF-verified buyers"),
    search: Optional[str] = Query(None, description="Search by name, phone, email"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_readonly_db),
) -> List[Dict[str, Any]]:
    """List buyers with optional filtering."""
    from services.buyer import get_buyer_service
    
    service = get_buyer_service(db)
    buyers = service.list_buyers(
        market_code=market,
        vip_only=vip_only,
        pof_verified_only=pof_verified_only,
        search=search,
        limit=limit,
        offset=offset,
    )
    
    return [b.to_dict() for b in buyers]


@router.get("/statistics")
async def get_buyer_statistics(
    db: Session = Depends(get_readonly_db),
) -> Dict[str, Any]:
    """Get buyer statistics."""
    from services.buyer import get_buyer_service
    
    service = get_buyer_service(db)
    return service.get_statistics()


@router.get("/{buyer_id}")
async def get_buyer(
    buyer_id: int,
    db: Session = Depends(get_readonly_db),
) -> Dict[str, Any]:
    """Get a buyer by ID."""
    from services.buyer import get_buyer_service
    
    service = get_buyer_service(db)
    buyer = service.get_buyer(buyer_id)
    
    if not buyer:
        raise HTTPException(status_code=404, detail="Buyer not found")
    
    return buyer.to_dict()


@router.put("/{buyer_id}")
async def update_buyer(
    buyer_id: int,
    body: BuyerUpdate,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Update a buyer."""
    from services.buyer import get_buyer_service
    
    service = get_buyer_service(db)
    
    # Filter out None values
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    
    buyer = service.update_buyer(buyer_id, updates)
    
    if not buyer:
        raise HTTPException(status_code=404, detail="Buyer not found")
    
    db.commit()
    return buyer.to_dict()


@router.delete("/{buyer_id}")
async def delete_buyer(
    buyer_id: int,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Delete a buyer."""
    from services.buyer import get_buyer_service
    
    service = get_buyer_service(db)
    success = service.delete_buyer(buyer_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="Buyer not found")
    
    db.commit()
    return {"success": True, "buyer_id": buyer_id}


@router.post("/{buyer_id}/pof")
async def update_pof(
    buyer_id: int,
    body: POFUpdate,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Update buyer's proof of funds."""
    from services.buyer import get_buyer_service
    
    service = get_buyer_service(db)
    buyer = service.update_pof(buyer_id, body.pof_url, body.verified)
    
    if not buyer:
        raise HTTPException(status_code=404, detail="Buyer not found")
    
    db.commit()
    return buyer.to_dict()


@router.get("/{buyer_id}/deals")
async def get_buyer_deals(
    buyer_id: int,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_readonly_db),
) -> List[Dict[str, Any]]:
    """Get deals for a buyer."""
    from services.buyer import get_buyer_service
    
    service = get_buyer_service(db)
    return service.get_buyer_deals(buyer_id, limit)


@router.post("/match/{lead_id}")
async def match_buyers_to_lead(
    lead_id: int,
    offer_price: Optional[float] = Query(None, description="Anticipated offer price"),
    min_score: float = Query(30.0, ge=0, le=100, description="Minimum match score"),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_readonly_db),
) -> Dict[str, Any]:
    """Match buyers to a lead."""
    from services.buyer_match import get_buyer_match_service
    from core.models import Lead
    
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    
    service = get_buyer_match_service(db)
    matches = service.match_buyers(lead, offer_price=offer_price, limit=limit, min_score=min_score)
    
    return {
        "lead_id": lead_id,
        "total_matches": len(matches),
        "matches": [m.to_dict() for m in matches],
    }


@router.post("/blast/{lead_id}")
async def send_buyer_blast(
    lead_id: int,
    buyer_ids: Optional[List[int]] = Body(None, description="Specific buyer IDs"),
    min_match_score: float = Body(50.0, ge=0, le=100),
    max_buyers: int = Body(10, ge=1, le=50),
    dry_run: bool = Body(False),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Send deal blast to matched buyers."""
    from services.buyer_blast import get_buyer_blast_service
    
    service = get_buyer_blast_service(db)
    result = service.send_blast(
        lead_id=lead_id,
        buyer_ids=buyer_ids,
        min_match_score=min_match_score,
        max_buyers=max_buyers,
        dry_run=dry_run,
    )
    
    db.commit()
    return result.to_dict()


@router.get("/blast/{lead_id}/preview")
async def preview_buyer_blast(
    lead_id: int,
    min_match_score: float = Query(50.0, ge=0, le=100),
    max_buyers: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_readonly_db),
) -> Dict[str, Any]:
    """Preview buyer blast without sending."""
    from services.buyer_blast import get_buyer_blast_service
    
    service = get_buyer_blast_service(db)
    return service.preview_blast(
        lead_id=lead_id,
        max_buyers=max_buyers,
        min_match_score=min_match_score,
    )


# =============================================================================
# Buyer Deal Routes
# =============================================================================


@router.get("/deals/by-lead/{lead_id}")
async def get_deals_for_lead(
    lead_id: int,
    db: Session = Depends(get_readonly_db),
) -> List[Dict[str, Any]]:
    """Get all buyer deals for a lead."""
    deals = db.query(BuyerDeal).filter(BuyerDeal.lead_id == lead_id).all()
    
    return [
        {
            "id": d.id,
            "buyer_id": d.buyer_id,
            "buyer_name": d.buyer.name if d.buyer else None,
            "lead_id": d.lead_id,
            "stage": d.stage,
            "match_score": d.match_score,
            "offer_amount": d.offer_amount,
            "assignment_fee": d.assignment_fee,
            "blast_sent_at": d.blast_sent_at.isoformat() if d.blast_sent_at else None,
            "created_at": d.created_at.isoformat() if d.created_at else None,
        }
        for d in deals
    ]


@router.post("/deals/{deal_id}/stage")
async def update_deal_stage(
    deal_id: int,
    body: DealStageUpdate,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Update a buyer deal's stage."""
    from services.timeline import TimelineService
    from core.utils import utcnow
    
    deal = db.query(BuyerDeal).filter(BuyerDeal.id == deal_id).first()
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
    
    # Validate stage
    valid_stages = [s.value for s in BuyerDealStage]
    if body.stage.upper() not in valid_stages:
        raise HTTPException(status_code=400, detail=f"Invalid stage. Must be one of: {valid_stages}")
    
    old_stage = deal.stage
    deal.stage = body.stage.upper()
    
    if body.offer_amount is not None:
        deal.offer_amount = body.offer_amount
    if body.assignment_fee is not None:
        deal.assignment_fee = body.assignment_fee
    if body.notes:
        deal.notes = body.notes
    
    # Update timestamps based on stage
    if deal.stage == BuyerDealStage.VIEWED.value and not deal.viewed_at:
        deal.viewed_at = utcnow()
    elif deal.stage == BuyerDealStage.INTERESTED.value and not deal.responded_at:
        deal.responded_at = utcnow()
    elif deal.stage == BuyerDealStage.CLOSED.value and not deal.closed_at:
        deal.closed_at = utcnow()
    
    # Log to timeline
    timeline = TimelineService(db)
    timeline.add_event(
        lead_id=deal.lead_id,
        event_type="buyer_deal_stage_change",
        title=f"Buyer deal stage: {old_stage} → {deal.stage}",
        description=f"Buyer: {deal.buyer.name if deal.buyer else 'Unknown'}",
        metadata={
            "deal_id": deal.id,
            "buyer_id": deal.buyer_id,
            "old_stage": old_stage,
            "new_stage": deal.stage,
        },
    )
    
    db.commit()
    
    return {
        "id": deal.id,
        "old_stage": old_stage,
        "new_stage": deal.stage,
        "success": True,
    }


@router.get("/pipeline")
async def get_buyer_pipeline(
    stage: Optional[str] = Query(None, description="Filter by stage"),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_readonly_db),
) -> Dict[str, Any]:
    """Get buyer deals pipeline overview."""
    from sqlalchemy import func
    
    # Get stage counts
    stage_counts = dict(
        db.query(BuyerDeal.stage, func.count(BuyerDeal.id))
        .group_by(BuyerDeal.stage)
        .all()
    )
    
    # Ensure all stages present
    for s in BuyerDealStage:
        if s.value not in stage_counts:
            stage_counts[s.value] = 0
    
    # Get recent deals
    query = db.query(BuyerDeal)
    if stage:
        query = query.filter(BuyerDeal.stage == stage.upper())
    
    deals = query.order_by(BuyerDeal.updated_at.desc()).limit(limit).all()
    
    return {
        "stage_counts": stage_counts,
        "total_deals": sum(stage_counts.values()),
        "deals": [
            {
                "id": d.id,
                "buyer_id": d.buyer_id,
                "buyer_name": d.buyer.name if d.buyer else None,
                "lead_id": d.lead_id,
                "stage": d.stage,
                "match_score": d.match_score,
                "offer_amount": d.offer_amount,
                "assignment_fee": d.assignment_fee,
                "created_at": d.created_at.isoformat() if d.created_at else None,
                "updated_at": d.updated_at.isoformat() if d.updated_at else None,
            }
            for d in deals
        ],
    }

