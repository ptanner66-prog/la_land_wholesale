"""Disposition routes for deal sheets, call scripts, AI tools, and manual comps."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from api.deps import get_db, get_readonly_db
from core.logging_config import get_logger
from core.models import ManualComp

router = APIRouter()
LOGGER = get_logger(__name__)


# =============================================================================
# Manual Comp Models
# =============================================================================


class ManualCompCreate(BaseModel):
    """Request body for creating a manual comp."""

    parcel_id: Optional[int] = None
    address: str = Field(..., min_length=1)
    sale_date: str = Field(..., min_length=1, description="ISO date string, e.g. 2025-06-15")
    sale_price: float = Field(..., gt=0)
    lot_size_acres: float = Field(..., gt=0)
    parish: Optional[str] = None
    market_code: str = "LA"
    notes: Optional[str] = None


class ManualCompResponse(BaseModel):
    """Response body for a manual comp."""

    id: int
    parcel_id: Optional[int]
    address: str
    sale_date: str
    sale_price: float
    lot_size_acres: float
    price_per_acre: float
    parish: Optional[str]
    market_code: str
    notes: Optional[str]


# =============================================================================
# Manual Comp Routes
# =============================================================================


@router.get("/comps/manual")
async def list_manual_comps(
    parish: Optional[str] = Query(None),
    market: Optional[str] = Query(None),
    parcel_id: Optional[int] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_readonly_db),
) -> Dict[str, Any]:
    """List manual comps with optional filters."""
    query = db.query(ManualComp)
    if parish:
        query = query.filter(ManualComp.parish == parish)
    if market:
        query = query.filter(ManualComp.market_code == market)
    if parcel_id:
        query = query.filter(ManualComp.parcel_id == parcel_id)

    results = query.order_by(ManualComp.sale_date.desc()).limit(limit).all()

    return {
        "total": len(results),
        "comps": [
            {
                "id": c.id,
                "parcel_id": c.parcel_id,
                "address": c.address,
                "sale_date": c.sale_date,
                "sale_price": c.sale_price,
                "lot_size_acres": c.lot_size_acres,
                "price_per_acre": round(c.sale_price / c.lot_size_acres, 2) if c.lot_size_acres > 0 else 0,
                "parish": c.parish,
                "market_code": c.market_code,
                "notes": c.notes,
            }
            for c in results
        ],
    }


@router.post("/comps/manual", status_code=201)
async def create_manual_comp(
    body: ManualCompCreate,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Add a manual comparable sale."""
    comp = ManualComp(
        parcel_id=body.parcel_id,
        address=body.address,
        sale_date=body.sale_date,
        sale_price=body.sale_price,
        lot_size_acres=body.lot_size_acres,
        parish=body.parish,
        market_code=body.market_code,
        notes=body.notes,
    )
    db.add(comp)
    db.flush()

    LOGGER.info(f"Manual comp created: {comp.address} @ ${comp.sale_price:,.0f}")

    return {
        "id": comp.id,
        "address": comp.address,
        "sale_date": comp.sale_date,
        "sale_price": comp.sale_price,
        "lot_size_acres": comp.lot_size_acres,
        "price_per_acre": round(comp.sale_price / comp.lot_size_acres, 2) if comp.lot_size_acres > 0 else 0,
        "parish": comp.parish,
        "market_code": comp.market_code,
    }


@router.delete("/comps/manual/{comp_id}")
async def delete_manual_comp(
    comp_id: int,
    db: Session = Depends(get_db),
) -> Dict[str, str]:
    """Delete a manual comp."""
    comp = db.query(ManualComp).filter(ManualComp.id == comp_id).first()
    if not comp:
        raise HTTPException(status_code=404, detail="Comp not found")
    db.delete(comp)
    return {"message": "Comp deleted"}


# =============================================================================
# Deal Analysis Models
# =============================================================================


class ManualDealAnalysisRequest(BaseModel):
    """Request for manual deal analysis without a parcel_id."""
    parcel_id: Optional[int] = None
    acres: float
    zoning: Optional[str] = None
    estimated_value: Optional[float] = None
    comps: Optional[List[float]] = None  # List of comp prices per acre
    purchase_price: Optional[float] = None
    market_code: str = "LA"
    motivation_score: int = 50
    is_adjudicated: bool = False


class DealAnalysisResponse(BaseModel):
    """Response for deal analysis."""
    arv: float  # After Repair Value (retail value)
    mao: float  # Maximum Allowable Offer
    assignment_fee: float
    offer_range: List[float]  # [low, high]
    confidence: float
    notes: List[str]
    full_analysis: Optional[Dict[str, Any]] = None


# =============================================================================
# Deal Sheet Routes
# =============================================================================


@router.get("/dealsheet/{lead_id}")
async def get_deal_sheet(
    lead_id: int,
    force_regenerate: bool = Query(False, description="Force regeneration"),
    db: Session = Depends(get_db),  # Uses write session for caching
) -> Dict[str, Any]:
    """
    Generate or retrieve a deal sheet for a lead.
    
    The deal sheet includes:
    - Property fundamentals (acreage, location, assessed value)
    - Comps summary with price per acre analysis
    - Recommended offer range (low/mid/high)
    - Assignment potential estimate
    - AI-written buyer-facing description
    - Map preview URL
    """
    from services.deal_sheet import get_deal_sheet_service
    
    service = get_deal_sheet_service(db)
    deal_sheet = service.generate_deal_sheet(lead_id, force_regenerate=force_regenerate)
    
    if not deal_sheet:
        raise HTTPException(status_code=404, detail="Lead not found or deal sheet generation failed")
    
    db.commit()
    
    return deal_sheet.to_dict()


# =============================================================================
# Call Script Routes
# =============================================================================


@router.get("/callscript/{lead_id}")
async def get_call_script(
    lead_id: int,
    db: Session = Depends(get_readonly_db),
) -> Dict[str, Any]:
    """
    Generate an AI-powered call script for seller negotiation.
    
    The script includes:
    - Opening line and rapport builder
    - Discovery questions
    - Negotiation angle and price justification
    - Objection handling responses
    - Closing script with urgency creator
    """
    from services.call_script import get_call_script_service
    
    service = get_call_script_service(db)
    script = service.generate_script(lead_id)
    
    if not script:
        raise HTTPException(status_code=404, detail="Lead not found")
    
    return script.to_dict()


# =============================================================================
# AI Tools Routes
# =============================================================================


@router.get("/ai/property-description/{lead_id}")
async def get_ai_property_description(
    lead_id: int,
    db: Session = Depends(get_readonly_db),
) -> Dict[str, Any]:
    """
    Generate an AI property description for marketing.
    """
    from services.deal_sheet import get_deal_sheet_service
    
    service = get_deal_sheet_service(db)
    deal_sheet = service.generate_deal_sheet(lead_id)
    
    if not deal_sheet:
        raise HTTPException(status_code=404, detail="Lead not found")
    
    return {
        "lead_id": lead_id,
        "description": deal_sheet.ai_description,
        "property_summary": {
            "address": deal_sheet.address,
            "acreage": deal_sheet.acreage,
            "county": deal_sheet.county,
            "state": deal_sheet.state,
            "price": deal_sheet.recommended_offer,
        },
    }


@router.get("/ai/negotiation-tips/{lead_id}")
async def get_negotiation_tips(
    lead_id: int,
    db: Session = Depends(get_readonly_db),
) -> Dict[str, Any]:
    """
    Get AI-powered negotiation tips for a lead.
    """
    from services.call_script import get_call_script_service
    
    service = get_call_script_service(db)
    script = service.generate_script(lead_id)
    
    if not script:
        raise HTTPException(status_code=404, detail="Lead not found")
    
    return {
        "lead_id": lead_id,
        "negotiation_angle": script.negotiation_angle,
        "price_justification": script.price_justification,
        "anchor_price": script.anchor_price,
        "walk_away_price": script.walk_away_price,
        "objections": script.objections,
    }


@router.get("/assignment-fee/{lead_id}")
async def get_assignment_fee(
    lead_id: int,
    purchase_price: float = Query(..., description="Expected purchase price"),
    db: Session = Depends(get_readonly_db),
) -> Dict[str, Any]:
    """
    Calculate optimal assignment fee for a lead.
    
    Returns recommended fee range based on market conditions,
    buyer demand, and property characteristics.
    """
    from core.models import Lead
    from services.assignment_fee_optimizer import get_assignment_fee_optimizer
    from services.buyer_match import get_buyer_match_service
    from services.comps import get_comps_service
    
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    
    parcel = lead.parcel
    if not parcel:
        raise HTTPException(status_code=400, detail="Lead has no associated parcel")
    
    # Get comps for retail value estimate
    comps_service = get_comps_service(db)
    comps = comps_service.get_comps_for_parcel(parcel)
    
    # Estimate retail value
    lot_acres = float(parcel.lot_size_acres or 1.0)
    if comps and comps.avg_price_per_acre > 0:
        retail_value = lot_acres * comps.avg_price_per_acre
    else:
        # Fallback to assessed value * 2
        retail_value = float(parcel.land_assessed_value or 0) * 2
        if retail_value == 0:
            retail_value = purchase_price * 1.5  # Rough estimate
    
    # Count matched buyers
    match_service = get_buyer_match_service(db)
    matches = match_service.match_buyers(lead, offer_price=purchase_price, limit=20)
    buyer_count = len(matches)
    
    # Calculate fee
    optimizer = get_assignment_fee_optimizer()
    fee_range = optimizer.calculate_assignment_fee(
        purchase_price=purchase_price,
        retail_value=retail_value,
        lot_size_acres=lot_acres,
        market_code=lead.market_code,
        motivation_score=lead.motivation_score,
        buyer_count=buyer_count,
        is_adjudicated=parcel.is_adjudicated,
        comp_price_per_acre=comps.avg_price_per_acre if comps else None,
    )
    
    return {
        "lead_id": lead_id,
        "purchase_price": purchase_price,
        "retail_value": retail_value,
        "buyer_count": buyer_count,
        "fee": fee_range.to_dict(),
    }


@router.get("/deal-analysis/{lead_id}")
async def get_deal_analysis(
    lead_id: int,
    purchase_price: float = Query(..., description="Expected purchase price"),
    db: Session = Depends(get_readonly_db),
) -> Dict[str, Any]:
    """
    Get complete deal analysis including margins and ROI.
    """
    from core.models import Lead
    from services.assignment_fee_optimizer import get_assignment_fee_optimizer
    from services.buyer_match import get_buyer_match_service
    from services.comps import get_comps_service
    
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    
    parcel = lead.parcel
    if not parcel:
        raise HTTPException(status_code=400, detail="Lead has no associated parcel")
    
    # Get comps
    comps_service = get_comps_service(db)
    comps = comps_service.get_comps_for_parcel(parcel)
    
    lot_acres = float(parcel.lot_size_acres or 1.0)
    if comps and comps.avg_price_per_acre > 0:
        retail_value = lot_acres * comps.avg_price_per_acre
    else:
        retail_value = float(parcel.land_assessed_value or 0) * 2
        if retail_value == 0:
            retail_value = purchase_price * 1.5
    
    # Count buyers
    match_service = get_buyer_match_service(db)
    matches = match_service.match_buyers(lead, offer_price=purchase_price, limit=20)
    
    # Analyze deal
    optimizer = get_assignment_fee_optimizer()
    analysis = optimizer.analyze_deal(
        purchase_price=purchase_price,
        retail_value=retail_value,
        lot_size_acres=lot_acres,
        market_code=lead.market_code,
        motivation_score=lead.motivation_score,
        buyer_count=len(matches),
        is_adjudicated=parcel.is_adjudicated,
    )
    
    return {
        "lead_id": lead_id,
        "analysis": analysis.to_dict(),
    }


@router.post("/deal", response_model=DealAnalysisResponse)
async def analyze_deal_manual(
    request: ManualDealAnalysisRequest,
    db: Session = Depends(get_readonly_db),
) -> DealAnalysisResponse:
    """
    Analyze a deal with manual inputs (no parcel_id required).
    
    This endpoint allows calculating deal metrics for:
    - Properties not yet in the system
    - Quick what-if analysis
    - Manual comps entry
    
    Args:
        request: Manual deal parameters.
    
    Returns:
        DealAnalysisResponse with ARV, MAO, assignment fee, and offer range.
    """
    from services.assignment_fee_optimizer import get_assignment_fee_optimizer
    from services.offer_calculator import get_offer_calculator
    
    notes = []
    
    # Calculate ARV (After Repair Value / Retail Value)
    if request.comps and len(request.comps) > 0:
        # Use provided comps
        avg_price_per_acre = sum(request.comps) / len(request.comps)
        arv = avg_price_per_acre * request.acres
        notes.append(f"ARV calculated from {len(request.comps)} comps @ ${avg_price_per_acre:,.0f}/acre")
    elif request.estimated_value:
        arv = request.estimated_value
        notes.append(f"Using provided estimated value: ${arv:,.0f}")
    else:
        # Default estimate based on market
        default_ppa = {
            "LA": 5000,
            "TX": 7500,
            "MS": 3500,
            "AR": 3000,
            "AL": 4000,
        }
        price_per_acre = default_ppa.get(request.market_code, 5000)
        arv = price_per_acre * request.acres
        notes.append(f"ARV estimated at ${price_per_acre:,.0f}/acre (market default)")
    
    # If parcel_id provided, try to get additional data
    if request.parcel_id:
        from core.models import Parcel, Lead
        parcel = db.query(Parcel).filter(Parcel.id == request.parcel_id).first()
        if parcel:
            # Use actual parcel data if available
            if parcel.lot_size_acres:
                request.acres = float(parcel.lot_size_acres)
                notes.append(f"Using parcel acreage: {request.acres:.2f} acres")
            
            # Get lead for motivation score
            lead = db.query(Lead).filter(Lead.parcel_id == request.parcel_id).first()
            if lead and lead.motivation_score:
                request.motivation_score = lead.motivation_score
                notes.append(f"Using lead motivation score: {request.motivation_score}")
    
    # Calculate purchase price if not provided
    if request.purchase_price:
        purchase_price = request.purchase_price
        notes.append(f"Using provided purchase price: ${purchase_price:,.0f}")
    else:
        # Use offer calculator to determine purchase price
        calculator = get_offer_calculator()
        offer_result = calculator.calculate_offer(
            lot_size_acres=request.acres,
            motivation_score=request.motivation_score,
            comp_avg_price_per_acre=sum(request.comps) / len(request.comps) if request.comps else None,
            is_adjudicated=request.is_adjudicated,
        )
        purchase_price = offer_result.recommended_offer
        notes.append(f"Calculated purchase price: ${purchase_price:,.0f}")
    
    # Calculate MAO (Maximum Allowable Offer)
    # MAO = ARV * 0.70 - assignment_fee (70% rule)
    optimizer = get_assignment_fee_optimizer()
    
    # Get assignment fee
    fee_range = optimizer.calculate_assignment_fee(
        purchase_price=purchase_price,
        retail_value=arv,
        lot_size_acres=request.acres,
        market_code=request.market_code,
        motivation_score=request.motivation_score,
        buyer_count=1,  # Default assumption
        is_adjudicated=request.is_adjudicated,
    )
    
    assignment_fee = fee_range.recommended_fee
    
    # MAO calculation
    mao = (arv * 0.70) - assignment_fee
    notes.append(f"MAO = (ARV × 70%) - Assignment Fee = ${mao:,.0f}")
    
    # Full deal analysis
    analysis = optimizer.analyze_deal(
        purchase_price=purchase_price,
        retail_value=arv,
        lot_size_acres=request.acres,
        market_code=request.market_code,
        motivation_score=request.motivation_score,
        buyer_count=1,
        is_adjudicated=request.is_adjudicated,
    )
    
    # Add risk notes
    if analysis.risk_factors:
        notes.extend([f"Risk: {rf}" for rf in analysis.risk_factors])
    
    # Add fee factors as notes
    for factor in fee_range.factors[:3]:  # Top 3 factors
        notes.append(factor.get("description", ""))
    
    return DealAnalysisResponse(
        arv=round(arv, 2),
        mao=round(mao, 2),
        assignment_fee=round(assignment_fee, 2),
        offer_range=[round(fee_range.conservative_fee, 2), round(fee_range.aggressive_fee, 2)],
        confidence=round(fee_range.confidence, 2),
        notes=notes,
        full_analysis=analysis.to_dict(),
    )


@router.get("/matches/{lead_id}")
async def get_buyer_matches(
    lead_id: int,
    offer_price: float = Query(None, description="Offer price for matching"),
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_readonly_db),
) -> Dict[str, Any]:
    """
    Get matched buyers for a lead.
    """
    from core.models import Lead
    from services.buyer_match import get_buyer_match_service
    
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    
    service = get_buyer_match_service(db)
    matches = service.match_buyers(lead, offer_price=offer_price, limit=limit)
    
    return {
        "lead_id": lead_id,
        "total_matches": len(matches),
        "matches": [m.to_dict() for m in matches],
    }


@router.get("/lead/{lead_id}/disposition-summary")
async def get_disposition_summary(
    lead_id: int,
    db: Session = Depends(get_readonly_db),
) -> Dict[str, Any]:
    """
    Get a complete disposition summary for a lead.
    
    Combines deal sheet, matched buyers, and buyer deals.
    
    This endpoint is null-safe:
    - If deal sheet generation fails, returns deal_sheet=None
    - If no buyers match, returns empty matched_buyers list
    - All optional fields have sensible defaults
    """
    from core.models import Lead, BuyerDeal
    from services.deal_sheet import get_deal_sheet_service
    from services.buyer_match import get_buyer_match_service
    
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    
    # Get deal sheet - handle potential errors gracefully
    deal_sheet = None
    deal_sheet_dict = None
    try:
        deal_sheet_service = get_deal_sheet_service(db)
        deal_sheet = deal_sheet_service.generate_deal_sheet(lead_id)
        if deal_sheet:
            deal_sheet_dict = deal_sheet.to_dict()
    except Exception as e:
        LOGGER.warning(f"Failed to generate deal sheet for lead {lead_id}: {e}")
        # Continue without deal sheet rather than failing the whole request
    
    # Get matched buyers - handle empty list gracefully
    matches = []
    try:
        match_service = get_buyer_match_service(db)
        offer_price = deal_sheet.recommended_offer if deal_sheet else None
        matches = match_service.match_buyers(
            lead,
            offer_price=offer_price,
            limit=10,
            min_score=30,
        )
    except Exception as e:
        LOGGER.warning(f"Failed to match buyers for lead {lead_id}: {e}")
        # Return empty matches rather than failing
    
    # Get existing buyer deals
    deals = []
    try:
        deals = db.query(BuyerDeal).filter(BuyerDeal.lead_id == lead_id).all()
    except Exception as e:
        LOGGER.warning(f"Failed to fetch buyer deals for lead {lead_id}: {e}")
    
    # Build response with safe defaults
    top_matches = [m.to_dict() for m in matches[:5]] if matches else []
    active_deals = []
    for d in deals:
        try:
            active_deals.append({
                "id": d.id,
                "buyer_id": d.buyer_id,
                "buyer_name": d.buyer.name if d.buyer else None,
                "stage": d.stage,
                "match_score": d.match_score,
            })
        except Exception:
            # Skip malformed deal records
            pass
    
    # Calculate can_blast safely
    high_matches = [m for m in matches if m.match_percentage >= 50] if matches else []
    
    return {
        "lead_id": lead_id,
        "deal_sheet": deal_sheet_dict,
        "matched_buyers_count": len(matches),
        "top_matches": top_matches,
        "active_deals": active_deals,
        "can_blast": len(high_matches) > 0,
    }

