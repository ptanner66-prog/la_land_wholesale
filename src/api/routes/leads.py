"""Lead management routes."""
from __future__ import annotations

from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException, Query, Body
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from api.deps import get_db, get_readonly_db
from core.logging_config import get_logger
from core.models import Lead, Owner, Parcel, Party, PipelineStage, MarketCode

router = APIRouter()
LOGGER = get_logger(__name__)


# =============================================================================
# Pydantic Models
# =============================================================================


class ManualLeadCreate(BaseModel):
    """Request body for manual lead creation."""
    
    owner_name: str = Field(..., min_length=1, description="Owner's full name")
    phone: Optional[str] = Field(None, description="Phone number")
    address: str = Field(..., min_length=1, description="Property address")
    city: Optional[str] = Field("Baton Rouge", description="City")
    state: Optional[str] = Field("LA", description="State")
    postal_code: Optional[str] = Field(None, description="ZIP code")
    notes: Optional[str] = Field(None, description="Additional notes")
    parish: Optional[str] = Field("East Baton Rouge", description="Parish/County")
    market_code: Optional[str] = Field("LA", description="Market code")
    enrich: bool = Field(True, description="Run external enrichment (USPS, geocode, comps)")


class ManualLeadResponse(BaseModel):
    """Response for manual lead creation."""
    
    success: bool
    lead_id: Optional[int]
    message: str
    motivation_score: Optional[int]
    enrichment: Optional[Dict[str, Any]] = None


class PipelineStageUpdate(BaseModel):
    """Request body for pipeline stage update."""
    
    stage: str = Field(..., description="Pipeline stage: NEW, CONTACTED, or HOT")


class ScoreDetailsResponse(BaseModel):
    """Response for score details."""
    
    total_score: int
    factors: List[Dict[str, Any]]


class TimelineEventResponse(BaseModel):
    """Response for timeline event."""
    
    id: int
    event_type: str
    title: str
    description: Optional[str]
    metadata: Optional[Dict[str, Any]]
    created_at: str


# =============================================================================
# Routes
# =============================================================================


@router.get("")
async def get_leads(
    market: Optional[str] = Query(default=None, description="Filter by market code"),
    pipeline_stage: Optional[str] = Query(default=None, description="Filter by pipeline stage"),
    min_score: int = Query(default=0, ge=0, le=100),
    status: Optional[str] = Query(default=None),
    tcpa_safe_only: bool = Query(default=False),
    order_by: str = Query(default="score_desc"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_readonly_db),
) -> Dict[str, Any]:
    """Get leads with filtering by market and pipeline stage."""
    from domain.leads import LeadService
    
    service = LeadService(session=db)
    leads = service.list_leads(
        market_code=market,
        pipeline_stage=pipeline_stage,
        min_score=min_score if min_score > 0 else None,
        status=status,
        tcpa_safe_only=tcpa_safe_only,
        order_by=order_by,
        limit=limit,
        offset=offset,
    )
    
    # Get total count for pagination
    total = service.count_leads(
        market_code=market,
        pipeline_stage=pipeline_stage,
        min_score=min_score if min_score > 0 else None,
        status=status,
        tcpa_safe_only=tcpa_safe_only,
    )
    
    return {
        "items": [lead.to_dict() for lead in leads],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/statistics")
async def get_lead_statistics(
    market: Optional[str] = Query(default=None, description="Filter by market code"),
    db: Session = Depends(get_readonly_db),
) -> Dict[str, Any]:
    """Get lead statistics summary."""
    from domain.leads import LeadService
    
    service = LeadService(session=db)
    return service.get_statistics(market_code=market)


@router.get("/search")
async def search_leads(
    q: str = Query(..., min_length=1, description="Search query"),
    market: Optional[str] = Query(default=None, description="Filter by market code"),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_readonly_db),
) -> List[Dict[str, Any]]:
    """Search leads by owner name, address, or parcel ID."""
    from sqlalchemy import or_, and_
    from domain.leads import LeadService
    
    search_term = f"%{q}%"
    
    query = (
        db.query(Lead)
        .join(Lead.owner)
        .join(Owner.party)
        .join(Lead.parcel)
        .filter(
            or_(
                Party.display_name.ilike(search_term),
                Party.normalized_name.ilike(search_term),
                Parcel.situs_address.ilike(search_term),
                Parcel.canonical_parcel_id.ilike(search_term),
            )
        )
    )
    
    if market:
        query = query.filter(Lead.market_code == market)
    
    leads = query.limit(limit).all()
    
    service = LeadService(session=db)
    return [service._lead_to_summary(lead).to_dict() for lead in leads]


@router.get("/{lead_id}")
async def get_lead(
    lead_id: int,
    db: Session = Depends(get_readonly_db),
) -> Dict[str, Any]:
    """Get detailed information for a specific lead."""
    from domain.leads import LeadService
    
    service = LeadService(session=db)
    lead = service.get_lead(lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead not found")
    return lead.to_dict()


@router.post("/{lead_id}/stage")
async def update_pipeline_stage(
    lead_id: int,
    body: PipelineStageUpdate,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Update a lead's pipeline stage."""
    from services.timeline import TimelineService
    
    # Validate stage
    stage = body.stage.upper()
    valid_stages = [s.value for s in PipelineStage]
    if stage not in valid_stages:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid stage. Must be one of: {valid_stages}"
        )
    
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    
    old_stage = lead.pipeline_stage
    lead.pipeline_stage = stage
    
    # Log timeline event
    timeline = TimelineService(db)
    timeline.log_stage_change(lead_id, old_stage, stage, "Manual stage update")
    
    db.commit()
    
    return {
        "id": lead.id,
        "old_stage": old_stage,
        "new_stage": stage,
        "success": True,
    }


@router.patch("/{lead_id}/status")
async def update_lead_status(
    lead_id: int,
    status: str = Query(..., description="New status value"),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Update a lead's status."""
    from domain.leads import LeadService
    
    service = LeadService(session=db)
    lead = service.update_lead_status(lead_id, status)
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead not found")
    return lead.to_dict()


@router.get("/{lead_id}/score_details")
async def get_score_details(
    lead_id: int,
    db: Session = Depends(get_readonly_db),
) -> Dict[str, Any]:
    """Get detailed score breakdown for a lead."""
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    
    if lead.score_details:
        return lead.score_details
    
    # Generate on-demand if not stored
    return {
        "total_score": lead.motivation_score,
        "factors": [
            {"name": "motivation_score", "label": "Total Score", "value": lead.motivation_score}
        ],
    }


@router.post("/{lead_id}/rescore")
async def rescore_lead(
    lead_id: int,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Rescore a specific lead and update score_details."""
    from domain.scoring import ScoringService
    from services.timeline import TimelineService
    
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    
    old_score = lead.motivation_score
    
    # Rescore
    scoring = ScoringService(db)
    result = scoring.score_lead(lead)
    
    # Log to timeline
    if lead.motivation_score != old_score:
        timeline = TimelineService(db)
        timeline.log_score_update(lead_id, old_score, lead.motivation_score, lead.score_details)
    
    db.commit()
    
    return {
        "id": lead.id,
        "old_score": old_score,
        "new_score": lead.motivation_score,
        "score_details": lead.score_details,
    }


@router.get("/{lead_id}/timeline")
async def get_lead_timeline(
    lead_id: int,
    limit: int = Query(default=50, ge=1, le=200),
    event_type: Optional[str] = Query(default=None),
    db: Session = Depends(get_readonly_db),
) -> List[Dict[str, Any]]:
    """Get timeline events for a lead."""
    from services.timeline import TimelineService
    
    # Verify lead exists
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    
    timeline = TimelineService(db)
    events = timeline.get_lead_timeline(lead_id, limit=limit, event_type=event_type)
    
    return [
        {
            "id": e.id,
            "event_type": e.event_type,
            "title": e.title,
            "description": e.description,
            "metadata": e.event_metadata,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in events
    ]


@router.get("/{lead_id}/comps")
async def get_lead_comps(
    lead_id: int,
    max_comps: int = Query(default=5, ge=1, le=10),
    db: Session = Depends(get_readonly_db),
) -> Dict[str, Any]:
    """
    Get comparable sales for a lead's parcel.
    
    NOTE: This is a read-only endpoint. Timeline logging is done only on
    operations that modify data (offer calculations, rescoring, etc.)
    """
    from services.comps import get_comps_service
    
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    
    if not lead.parcel:
        raise HTTPException(status_code=400, detail="Lead has no associated parcel")
    
    comps_service = get_comps_service(db)
    result = comps_service.get_comps_for_parcel(lead.parcel, max_comps=max_comps)
    
    # NOTE: No timeline logging on read-only endpoint
    
    return result.to_dict()


@router.get("/{lead_id}/offer")
async def get_lead_offer(
    lead_id: int,
    db: Session = Depends(get_db),  # FIXED: Use write session for timeline
) -> Dict[str, Any]:
    """
    Calculate a recommended offer for a lead.
    
    FIXED: Uses write session so timeline events are persisted.
    """
    from services.offer_calculator import get_offer_calculator
    from services.comps import get_comps_service
    from services.timeline import TimelineService
    
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    
    if not lead.parcel:
        raise HTTPException(status_code=400, detail="Lead has no associated parcel")
    
    # Get comps for pricing
    comps_service = get_comps_service(db)
    comps = comps_service.get_comps_for_parcel(lead.parcel)
    
    # Calculate offer
    calculator = get_offer_calculator()
    result = calculator.calculate_offer(
        lot_size_acres=float(lead.parcel.lot_size_acres or 1.0),
        motivation_score=lead.motivation_score,
        comp_avg_price_per_acre=comps.avg_price_per_acre if comps.total_comps_found > 0 else None,
        land_assessed_value=float(lead.parcel.land_assessed_value) if lead.parcel.land_assessed_value else None,
        is_adjudicated=lead.parcel.is_adjudicated,
    )
    
    # Log to timeline (now persists with write session)
    timeline = TimelineService(db)
    timeline.log_offer_calculated(lead_id, result.recommended_offer, result.low_offer, result.high_offer)
    
    db.commit()
    
    return result.to_dict()


@router.get("/{lead_id}/map")
async def get_lead_map_data(
    lead_id: int,
    db: Session = Depends(get_readonly_db),
) -> Dict[str, Any]:
    """Get map data for a lead's parcel."""
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    
    if not lead.parcel:
        raise HTTPException(status_code=400, detail="Lead has no associated parcel")
    
    parcel = lead.parcel
    
    return {
        "address": parcel.situs_address,
        "city": parcel.city,
        "state": parcel.state,
        "postal_code": parcel.postal_code,
        "latitude": parcel.latitude,
        "longitude": parcel.longitude,
        "parcel_id": parcel.canonical_parcel_id,
        "lot_size_acres": float(parcel.lot_size_acres) if parcel.lot_size_acres else None,
        "geojson": parcel.geom if parcel.geom else None,
    }


@router.post("/score")
async def score_leads(
    background_tasks: BackgroundTasks,
    market: Optional[str] = Query(default=None, description="Filter by market code"),
    db: Session = Depends(get_db),
) -> Dict[str, str]:
    """Trigger lead scoring in background."""
    def _run() -> None:
        from core.db import SessionLocal
        from domain.scoring import ScoringService
        
        session = SessionLocal()
        try:
            service = ScoringService(session)
            result = service.score_all(market_code=market)
            session.commit()
            LOGGER.info(f"Scoring complete: {result.updated} leads updated")
        except Exception as e:
            session.rollback()
            LOGGER.error(f"Background scoring failed: {e}")
        finally:
            session.close()

    background_tasks.add_task(_run)
    return {"message": "Scoring started in background", "market": market or "all"}


@router.post("/score-sync")
async def score_leads_sync(
    market: Optional[str] = Query(default=None, description="Filter by market code"),
    min_score: Optional[int] = Query(default=None, ge=0, le=100),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Run lead scoring synchronously and return results."""
    from domain.scoring import ScoringService
    
    service = ScoringService(db)
    result = service.score_all(min_score=min_score, market_code=market)
    return result.to_dict()


@router.delete("/{lead_id}")
async def delete_lead(
    lead_id: int,
    hard: bool = Query(default=False, description="If true, permanently delete. Otherwise soft-delete."),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Delete a lead.
    
    By default (soft delete):
    - Sets deleted_at timestamp
    - Lead is hidden from queries but data preserved
    
    With ?hard=true:
    - Remove all outreach attempts for the lead
    - Remove all timeline events for the lead
    - Remove the lead itself permanently
    
    Owner and parcel records are preserved for deduplication purposes.
    """
    from datetime import datetime, timezone
    
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    
    if hard:
        # Hard delete - use existing service
        from services.lead_cleanup import delete_lead as do_delete
        result = do_delete(db, lead_id)
        if not result["success"]:
            raise HTTPException(status_code=404, detail=result.get("error", "Lead not found"))
        return result
    else:
        # Soft delete - just set deleted_at
        lead.deleted_at = datetime.now(timezone.utc)
        db.commit()
        LOGGER.info(f"Soft-deleted lead {lead_id}")
        return {"success": True, "message": f"Lead {lead_id} soft-deleted", "lead_id": lead_id}


@router.post("/manual", response_model=ManualLeadResponse)
async def create_manual_lead(
    lead_data: ManualLeadCreate,
    db: Session = Depends(get_db),
) -> ManualLeadResponse:
    """
    Create a lead manually with address and owner information.
    
    This endpoint:
    1. Optionally verifies address with USPS
    2. Optionally geocodes with Google Maps
    3. Optionally fetches comparable sales
    4. Creates/finds a Party for the owner
    5. Creates/finds an Owner record
    6. Creates a Parcel for the address
    7. Creates a Lead linking owner to parcel
    8. Scores the lead immediately
    
    Returns the created lead with its motivation score and enrichment data.
    """
    from domain.leads import LeadService
    from services.timeline import TimelineService
    
    try:
        service = LeadService(session=db)
        
        lead_detail = service.create_manual_lead(
            owner_name=lead_data.owner_name,
            address=lead_data.address,
            city=lead_data.city or "Baton Rouge",
            state=lead_data.state or "LA",
            postal_code=lead_data.postal_code,
            parish=lead_data.parish or "East Baton Rouge",
            phone=lead_data.phone,
            notes=lead_data.notes,
            tcpa_safe=False,
            enrich=lead_data.enrich,
            market_code=lead_data.market_code or "LA",
        )
        
        # Log to timeline
        lead = db.query(Lead).filter(Lead.id == lead_detail.id).first()
        if lead:
            timeline = TimelineService(db)
            timeline.log_lead_created(lead)
        
        db.commit()
        
        LOGGER.info(f"Created manual lead {lead_detail.id} with score {lead_detail.motivation_score}")
        
        return ManualLeadResponse(
            success=True,
            lead_id=lead_detail.id,
            message="Lead created successfully",
            motivation_score=lead_detail.motivation_score,
            enrichment=lead_detail.enrichment_data,
        )
        
    except ValueError as e:
        LOGGER.warning(f"Validation error creating manual lead: {e}")
        return ManualLeadResponse(
            success=False,
            lead_id=None,
            message=str(e),
            motivation_score=None,
            enrichment=None,
        )
    except Exception as e:
        db.rollback()
        LOGGER.error(f"Failed to create manual lead: {e}")
        return ManualLeadResponse(
            success=False,
            lead_id=None,
            message=f"Failed to create lead: {str(e)}",
            motivation_score=None,
            enrichment=None,
        )
