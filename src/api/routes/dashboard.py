"""
Dashboard API Integration Layer

Comprehensive endpoints powering the React dashboard:
- Pipeline overview and statistics
- Lead management and filtering
- Buyer management
- Deal tracking
- Conversation history
- Analytics and metrics
- Contract management
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, desc, and_, or_
from sqlalchemy.orm import Session

from api.deps import get_db
from core.config import get_settings
from core.logging_config import get_logger
from core.models import (
    Lead, Owner, Parcel, Party, OutreachAttempt, TimelineEvent,
    Buyer, BuyerDeal, DealSheet, BackgroundTask, AlertConfig,
    PipelineStage, ReplyClassification, BuyerDealStage,
)
from core.utils import utcnow
from services.buyer_match import get_buyer_match_service
from services.deal_sheet import get_deal_sheet_service
from services.enrichment_pipeline import get_enrichment_pipeline
from services.contract_generator import get_contract_generator

router = APIRouter()
LOGGER = get_logger(__name__)
SETTINGS = get_settings()


# =============================================================================
# Request/Response Models
# =============================================================================

class PipelineStats(BaseModel):
    """Pipeline statistics response."""
    total_leads: int
    new_leads: int
    contacted_leads: int
    hot_leads: int
    avg_motivation_score: float
    leads_by_market: Dict[str, int]
    leads_by_stage: Dict[str, int]
    recent_activity_count: int


class LeadSummary(BaseModel):
    """Lead summary for list views."""
    id: int
    owner_name: Optional[str]
    property_address: Optional[str]
    parish: Optional[str]
    market_code: str
    motivation_score: int
    pipeline_stage: str
    acreage: Optional[float]
    is_adjudicated: bool
    created_at: str
    last_contact_at: Optional[str]
    outreach_count: int


class LeadDetail(BaseModel):
    """Detailed lead information."""
    id: int
    market_code: str
    motivation_score: int
    pipeline_stage: str
    status: str
    score_details: Optional[Dict[str, Any]]
    created_at: str
    updated_at: str
    
    # Owner info
    owner: Optional[Dict[str, Any]]
    
    # Property info
    parcel: Optional[Dict[str, Any]]
    
    # Outreach history
    outreach_attempts: List[Dict[str, Any]]
    
    # Timeline
    timeline_events: List[Dict[str, Any]]
    
    # Deal info
    deal_sheet: Optional[Dict[str, Any]]
    buyer_deals: List[Dict[str, Any]]


class BuyerSummary(BaseModel):
    """Buyer summary for list views."""
    id: int
    name: str
    phone: Optional[str]
    email: Optional[str]
    market_codes: List[str]
    counties: List[str]
    vip: bool
    pof_verified: bool
    deals_count: int
    response_rate: Optional[float]


class DealSummary(BaseModel):
    """Deal summary for pipeline views."""
    id: int
    buyer_name: str
    lead_id: int
    property_address: Optional[str]
    stage: str
    match_score: Optional[float]
    offer_amount: Optional[float]
    assignment_fee: Optional[float]
    created_at: str


class ConversationMessage(BaseModel):
    """Single conversation message."""
    id: int
    direction: str  # inbound, outbound
    message: str
    timestamp: str
    status: Optional[str]
    classification: Optional[str]


class AnalyticsSummary(BaseModel):
    """Analytics summary response."""
    period: str
    total_leads_created: int
    total_outreach_sent: int
    total_responses: int
    response_rate: float
    hot_leads_generated: int
    deals_created: int
    avg_time_to_response_hours: Optional[float]


class EnrichmentRequest(BaseModel):
    """Request to enrich a lead."""
    lead_id: int
    skip_external: bool = False
    force_refresh: bool = False


class ContractRequest(BaseModel):
    """Request to generate a contract."""
    lead_id: int
    contract_type: str  # purchase_agreement, assignment
    buyer_id: Optional[int] = None
    offer_amount: float
    earnest_money: float = 1000.0
    closing_days: int = 30
    assignment_fee: Optional[float] = None


# =============================================================================
# Pipeline Overview Endpoints
# =============================================================================

@router.get("/pipeline/stats", response_model=PipelineStats)
async def get_pipeline_stats(
    market_code: Optional[str] = None,
    days: int = Query(default=30, ge=1, le=365),
    db: Session = Depends(get_db),
) -> PipelineStats:
    """
    Get pipeline statistics for the dashboard.
    
    Provides overview metrics for leads, stages, and activity.
    Uses score-based classification as primary source of truth.
    """
    from scoring.deterministic_engine import CONTACT_THRESHOLD, HOT_THRESHOLD
    
    # Base query
    base_filter = Lead.deleted_at.is_(None)
    if market_code:
        base_filter = and_(base_filter, Lead.market_code == market_code)
    
    # Calculate date range
    since_date = utcnow() - timedelta(days=days)
    
    # Total leads
    total_leads = db.query(Lead).filter(base_filter).count()
    
    # Score-based classification (primary)
    hot_by_score = db.query(Lead).filter(
        base_filter,
        Lead.motivation_score >= HOT_THRESHOLD
    ).count()
    
    contact_by_score = db.query(Lead).filter(
        base_filter,
        Lead.motivation_score >= CONTACT_THRESHOLD,
        Lead.motivation_score < HOT_THRESHOLD
    ).count()
    
    # Leads by stage (for stage-based views)
    stage_counts = db.query(
        Lead.pipeline_stage,
        func.count(Lead.id)
    ).filter(base_filter).group_by(Lead.pipeline_stage)
    
    leads_by_stage = {stage: count for stage, count in stage_counts.all()}
    
    # Enrich leads_by_stage with score-based counts
    leads_by_stage["HOT_BY_SCORE"] = hot_by_score
    leads_by_stage["CONTACT_BY_SCORE"] = contact_by_score
    leads_by_stage["SCORED"] = db.query(Lead).filter(base_filter, Lead.motivation_score > 0).count()
    
    # Leads by market
    market_counts = db.query(
        Lead.market_code,
        func.count(Lead.id)
    ).filter(base_filter).group_by(Lead.market_code).all()
    leads_by_market = {market: count for market, count in market_counts}
    
    # Average motivation score (only for scored leads)
    avg_score = db.query(func.avg(Lead.motivation_score)).filter(
        base_filter,
        Lead.motivation_score > 0
    ).scalar() or 0
    
    # Recent activity (outreach in last N days)
    recent_activity = db.query(OutreachAttempt).filter(
        OutreachAttempt.created_at >= since_date
    ).count()
    
    # Use score-based counts as primary, fallback to stage-based
    hot_count = hot_by_score if hot_by_score > 0 else leads_by_stage.get("HOT", 0)
    new_count = contact_by_score if contact_by_score > 0 else leads_by_stage.get("NEW", 0)
    
    return PipelineStats(
        total_leads=total_leads,
        new_leads=new_count,
        contacted_leads=leads_by_stage.get("CONTACTED", 0),
        hot_leads=hot_count,
        avg_motivation_score=round(float(avg_score), 1),
        leads_by_market=leads_by_market,
        leads_by_stage=leads_by_stage,
        recent_activity_count=recent_activity,
    )


@router.get("/pipeline/funnel")
async def get_pipeline_funnel(
    market_code: Optional[str] = None,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Get funnel visualization data.
    
    Shows lead progression through pipeline stages.
    Uses score-based classification as primary source of truth.
    """
    from scoring.deterministic_engine import CONTACT_THRESHOLD, HOT_THRESHOLD, REJECT_THRESHOLD
    
    base_filter = Lead.deleted_at.is_(None)
    if market_code:
        base_filter = and_(base_filter, Lead.market_code == market_code)
    
    total = db.query(Lead).filter(base_filter).count()
    
    # Score-based funnel (more accurate than stage-based)
    scored = db.query(Lead).filter(base_filter, Lead.motivation_score > 0).count()
    hot_by_score = db.query(Lead).filter(base_filter, Lead.motivation_score >= HOT_THRESHOLD).count()
    contact_by_score = db.query(Lead).filter(
        base_filter, 
        Lead.motivation_score >= CONTACT_THRESHOLD,
        Lead.motivation_score < HOT_THRESHOLD
    ).count()
    low_by_score = db.query(Lead).filter(
        base_filter,
        Lead.motivation_score >= REJECT_THRESHOLD,
        Lead.motivation_score < CONTACT_THRESHOLD
    ).count()
    
    # Stage-based counts (for manual progression)
    contacted = db.query(Lead).filter(
        base_filter,
        Lead.pipeline_stage == PipelineStage.CONTACTED.value
    ).count()
    offers = db.query(Lead).filter(
        base_filter,
        Lead.pipeline_stage == PipelineStage.OFFER.value
    ).count()
    contracts = db.query(Lead).filter(
        base_filter,
        Lead.pipeline_stage == PipelineStage.CONTRACT.value
    ).count()
    
    stages = [
        {
            "stage": "TOTAL",
            "label": "Total Leads",
            "count": total,
            "percentage": 100.0,
        },
        {
            "stage": "SCORED",
            "label": "Scored (>0)",
            "count": scored,
            "percentage": round(scored / total * 100, 1) if total > 0 else 0,
        },
        {
            "stage": "HOT",
            "label": f"Hot (>={HOT_THRESHOLD})",
            "count": hot_by_score,
            "percentage": round(hot_by_score / total * 100, 1) if total > 0 else 0,
        },
        {
            "stage": "CONTACT",
            "label": f"Contact ({CONTACT_THRESHOLD}-{HOT_THRESHOLD-1})",
            "count": contact_by_score,
            "percentage": round(contact_by_score / total * 100, 1) if total > 0 else 0,
        },
        {
            "stage": "CONTACTED",
            "label": "Contacted",
            "count": contacted,
            "percentage": round(contacted / total * 100, 1) if total > 0 else 0,
        },
        {
            "stage": "OFFER",
            "label": "Offer Sent",
            "count": offers,
            "percentage": round(offers / total * 100, 1) if total > 0 else 0,
        },
        {
            "stage": "CONTRACT",
            "label": "Under Contract",
            "count": contracts,
            "percentage": round(contracts / total * 100, 1) if total > 0 else 0,
        },
    ]
    
    # Add buyer deals
    deals_count = db.query(BuyerDeal).count()
    stages.append({
        "stage": "DEALS",
        "label": "Deals",
        "count": deals_count,
        "percentage": round(deals_count / total * 100, 1) if total > 0 else 0
    })
    
    return {
        "total_leads": total,
        "scored_leads": scored,
        "hot_leads": hot_by_score,
        "contact_ready": contact_by_score,
        "stages": stages,
        "thresholds": {
            "hot": HOT_THRESHOLD,
            "contact": CONTACT_THRESHOLD,
            "reject": REJECT_THRESHOLD,
        },
    }


# =============================================================================
# Lead Management Endpoints
# =============================================================================

@router.get("/leads", response_model=List[LeadSummary])
async def list_leads(
    market_code: Optional[str] = None,
    pipeline_stage: Optional[str] = None,
    min_score: Optional[int] = None,
    search: Optional[str] = None,
    skip: int = 0,
    limit: int = Query(default=50, le=200),
    sort_by: str = "created_at",
    sort_order: str = "desc",
    db: Session = Depends(get_db),
) -> List[LeadSummary]:
    """
    List leads with filtering and pagination.
    """
    query = db.query(Lead).join(Lead.owner, isouter=True).join(Lead.parcel, isouter=True)
    
    # Apply filters
    if market_code:
        query = query.filter(Lead.market_code == market_code)
    if pipeline_stage:
        query = query.filter(Lead.pipeline_stage == pipeline_stage)
    if min_score is not None:
        query = query.filter(Lead.motivation_score >= min_score)
    if search:
        search_term = f"%{search}%"
        query = query.join(Owner.party, isouter=True).filter(
            or_(
                Party.display_name.ilike(search_term),
                Parcel.situs_address.ilike(search_term),
                Parcel.canonical_parcel_id.ilike(search_term),
            )
        )
    
    # Apply sorting
    sort_column = getattr(Lead, sort_by, Lead.created_at)
    if sort_order == "desc":
        query = query.order_by(desc(sort_column))
    else:
        query = query.order_by(sort_column)
    
    # Pagination
    leads = query.offset(skip).limit(limit).all()
    
    results = []
    for lead in leads:
        parcel = lead.parcel
        owner = lead.owner
        party = owner.party if owner else None
        
        # Get outreach count
        outreach_count = db.query(OutreachAttempt).filter(
            OutreachAttempt.lead_id == lead.id
        ).count()
        
        # Get last contact
        last_outreach = db.query(OutreachAttempt).filter(
            OutreachAttempt.lead_id == lead.id
        ).order_by(desc(OutreachAttempt.created_at)).first()
        
        results.append(LeadSummary(
            id=lead.id,
            owner_name=party.display_name if party else None,
            property_address=parcel.situs_address if parcel else None,
            parish=parcel.parish if parcel else None,
            market_code=lead.market_code,
            motivation_score=lead.motivation_score,
            pipeline_stage=lead.pipeline_stage,
            acreage=float(parcel.lot_size_acres) if parcel and parcel.lot_size_acres else None,
            is_adjudicated=parcel.is_adjudicated if parcel else False,
            created_at=lead.created_at.isoformat() if lead.created_at else "",
            last_contact_at=last_outreach.created_at.isoformat() if last_outreach else None,
            outreach_count=outreach_count,
        ))
    
    return results


@router.get("/leads/{lead_id}", response_model=LeadDetail)
async def get_lead_detail(
    lead_id: int,
    db: Session = Depends(get_db),
) -> LeadDetail:
    """
    Get detailed lead information.
    """
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    
    parcel = lead.parcel
    owner = lead.owner
    party = owner.party if owner else None
    
    # Build owner dict
    owner_dict = None
    if owner:
        owner_dict = {
            "id": owner.id,
            "name": party.display_name if party else None,
            "phone_primary": owner.phone_primary,
            "email": owner.email,
            "is_tcpa_safe": owner.is_tcpa_safe,
            "opt_out": owner.opt_out,
            "party_type": party.party_type if party else None,
        }
    
    # Build parcel dict
    parcel_dict = None
    if parcel:
        parcel_dict = {
            "id": parcel.id,
            "canonical_parcel_id": parcel.canonical_parcel_id,
            "situs_address": parcel.situs_address,
            "city": parcel.city,
            "state": parcel.state,
            "parish": parcel.parish,
            "lot_size_acres": float(parcel.lot_size_acres) if parcel.lot_size_acres else None,
            "land_assessed_value": float(parcel.land_assessed_value) if parcel.land_assessed_value else None,
            "is_adjudicated": parcel.is_adjudicated,
            "years_tax_delinquent": parcel.years_tax_delinquent,
            "latitude": parcel.latitude,
            "longitude": parcel.longitude,
            "zoning_code": parcel.zoning_code,
        }
    
    # Get outreach history
    outreach = db.query(OutreachAttempt).filter(
        OutreachAttempt.lead_id == lead_id
    ).order_by(desc(OutreachAttempt.created_at)).limit(20).all()
    
    outreach_list = [
        {
            "id": a.id,
            "channel": a.channel,
            "message_body": a.message_body,
            "message_context": a.message_context,
            "status": a.status,
            "sent_at": a.sent_at.isoformat() if a.sent_at else None,
            "response_body": a.response_body,
            "reply_classification": a.reply_classification,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in outreach
    ]
    
    # Get timeline events
    timeline = db.query(TimelineEvent).filter(
        TimelineEvent.lead_id == lead_id
    ).order_by(desc(TimelineEvent.created_at)).limit(20).all()
    
    timeline_list = [
        {
            "id": e.id,
            "event_type": e.event_type,
            "title": e.title,
            "description": e.description,
            "metadata": e.event_metadata,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in timeline
    ]
    
    # Get deal sheet
    deal_sheet = db.query(DealSheet).filter(DealSheet.lead_id == lead_id).first()
    deal_sheet_dict = None
    if deal_sheet:
        deal_sheet_dict = {
            "id": deal_sheet.id,
            "content": deal_sheet.content,
            "ai_description": deal_sheet.ai_description,
            "generated_at": deal_sheet.generated_at.isoformat() if deal_sheet.generated_at else None,
        }
    
    # Get buyer deals
    buyer_deals = db.query(BuyerDeal).filter(
        BuyerDeal.lead_id == lead_id
    ).all()
    
    buyer_deals_list = [
        {
            "id": d.id,
            "buyer_id": d.buyer_id,
            "buyer_name": d.buyer.name if d.buyer else None,
            "stage": d.stage,
            "match_score": d.match_score,
            "offer_amount": d.offer_amount,
            "assignment_fee": d.assignment_fee,
            "created_at": d.created_at.isoformat() if d.created_at else None,
        }
        for d in buyer_deals
    ]
    
    return LeadDetail(
        id=lead.id,
        market_code=lead.market_code,
        motivation_score=lead.motivation_score,
        pipeline_stage=lead.pipeline_stage,
        status=lead.status,
        score_details=lead.score_details,
        created_at=lead.created_at.isoformat() if lead.created_at else "",
        updated_at=lead.updated_at.isoformat() if lead.updated_at else "",
        owner=owner_dict,
        parcel=parcel_dict,
        outreach_attempts=outreach_list,
        timeline_events=timeline_list,
        deal_sheet=deal_sheet_dict,
        buyer_deals=buyer_deals_list,
    )


@router.post("/leads/{lead_id}/enrich")
async def enrich_lead(
    lead_id: int,
    request: EnrichmentRequest,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Run enrichment pipeline on a lead.
    """
    pipeline = get_enrichment_pipeline(db)
    result = pipeline.enrich_lead(
        lead_id=lead_id,
        skip_external=request.skip_external,
        force_refresh=request.force_refresh,
    )
    
    return result.to_dict()


# =============================================================================
# Buyer Management Endpoints
# =============================================================================

@router.get("/buyers", response_model=List[BuyerSummary])
async def list_buyers(
    market_code: Optional[str] = None,
    vip_only: bool = False,
    skip: int = 0,
    limit: int = Query(default=50, le=200),
    db: Session = Depends(get_db),
) -> List[BuyerSummary]:
    """
    List buyers with filtering.
    """
    query = db.query(Buyer)
    
    if vip_only:
        query = query.filter(Buyer.vip == True)
    
    # Filter by market if provided
    if market_code:
        # JSON array contains - this works for SQLite/PostgreSQL
        query = query.filter(Buyer.market_codes.contains([market_code]))
    
    buyers = query.order_by(desc(Buyer.vip), Buyer.name).offset(skip).limit(limit).all()
    
    return [
        BuyerSummary(
            id=b.id,
            name=b.name,
            phone=b.phone,
            email=b.email,
            market_codes=b.market_codes or [],
            counties=b.counties or [],
            vip=b.vip,
            pof_verified=b.pof_verified,
            deals_count=b.deals_count,
            response_rate=b.response_rate,
        )
        for b in buyers
    ]


@router.get("/buyers/{buyer_id}/matches")
async def get_buyer_matches(
    buyer_id: int,
    limit: int = Query(default=20, le=50),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Get matching leads for a buyer.
    """
    buyer = db.query(Buyer).filter(Buyer.id == buyer_id).first()
    if not buyer:
        raise HTTPException(status_code=404, detail="Buyer not found")
    
    # Get HOT leads in buyer's markets
    query = db.query(Lead).filter(
        Lead.pipeline_stage == "HOT",
        Lead.market_code.in_(buyer.market_codes or []),
    ).order_by(desc(Lead.motivation_score)).limit(limit)
    
    leads = query.all()
    
    # Score each lead
    match_service = get_buyer_match_service(db)
    
    matches = []
    for lead in leads:
        match = match_service._score_buyer(
            buyer=buyer,
            lead=lead,
            market=lead.market_code,
            county=lead.parcel.parish if lead.parcel else None,
            acreage=float(lead.parcel.lot_size_acres or 0) if lead.parcel else 0,
            offer_price=None,
        )
        matches.append(match.to_dict())
    
    # Sort by score
    matches.sort(key=lambda x: x["total_score"], reverse=True)
    
    return {
        "buyer_id": buyer_id,
        "buyer_name": buyer.name,
        "matches": matches,
    }


# =============================================================================
# Deal Tracking Endpoints
# =============================================================================

@router.get("/deals", response_model=List[DealSummary])
async def list_deals(
    stage: Optional[str] = None,
    buyer_id: Optional[int] = None,
    skip: int = 0,
    limit: int = Query(default=50, le=200),
    db: Session = Depends(get_db),
) -> List[DealSummary]:
    """
    List deals in the disposition pipeline.
    """
    query = db.query(BuyerDeal).join(Buyer).join(Lead)
    
    if stage:
        query = query.filter(BuyerDeal.stage == stage)
    if buyer_id:
        query = query.filter(BuyerDeal.buyer_id == buyer_id)
    
    deals = query.order_by(desc(BuyerDeal.created_at)).offset(skip).limit(limit).all()
    
    results = []
    for deal in deals:
        lead = deal.lead
        parcel = lead.parcel if lead else None
        
        results.append(DealSummary(
            id=deal.id,
            buyer_name=deal.buyer.name if deal.buyer else "Unknown",
            lead_id=deal.lead_id,
            property_address=parcel.situs_address if parcel else None,
            stage=deal.stage,
            match_score=deal.match_score,
            offer_amount=deal.offer_amount,
            assignment_fee=deal.assignment_fee,
            created_at=deal.created_at.isoformat() if deal.created_at else "",
        ))
    
    return results


@router.get("/deals/pipeline")
async def get_deals_pipeline(
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Get deal pipeline summary by stage.
    """
    stages = [s.value for s in BuyerDealStage]
    
    pipeline = {}
    for stage in stages:
        count = db.query(BuyerDeal).filter(BuyerDeal.stage == stage).count()
        total_value = db.query(func.sum(BuyerDeal.offer_amount)).filter(
            BuyerDeal.stage == stage
        ).scalar() or 0
        
        pipeline[stage] = {
            "count": count,
            "total_value": float(total_value),
        }
    
    return {
        "stages": pipeline,
        "total_deals": sum(p["count"] for p in pipeline.values()),
        "total_pipeline_value": sum(p["total_value"] for p in pipeline.values()),
    }


# =============================================================================
# Conversation Endpoints
# =============================================================================

@router.get("/conversations/{lead_id}", response_model=List[ConversationMessage])
async def get_conversation(
    lead_id: int,
    db: Session = Depends(get_db),
) -> List[ConversationMessage]:
    """
    Get conversation history for a lead.
    """
    attempts = db.query(OutreachAttempt).filter(
        OutreachAttempt.lead_id == lead_id
    ).order_by(OutreachAttempt.created_at).all()
    
    messages = []
    for a in attempts:
        # Outbound message
        if a.message_body:
            messages.append(ConversationMessage(
                id=a.id,
                direction="outbound",
                message=a.message_body,
                timestamp=a.sent_at.isoformat() if a.sent_at else a.created_at.isoformat(),
                status=a.status,
                classification=None,
            ))
        
        # Inbound response
        if a.response_body:
            messages.append(ConversationMessage(
                id=a.id,
                direction="inbound",
                message=a.response_body,
                timestamp=a.response_received_at.isoformat() if a.response_received_at else a.created_at.isoformat(),
                status="received",
                classification=a.reply_classification,
            ))
    
    return messages


# =============================================================================
# Analytics Endpoints
# =============================================================================

@router.get("/analytics/summary", response_model=AnalyticsSummary)
async def get_analytics_summary(
    days: int = Query(default=30, ge=1, le=365),
    market_code: Optional[str] = None,
    db: Session = Depends(get_db),
) -> AnalyticsSummary:
    """
    Get analytics summary for the specified period.
    """
    since = utcnow() - timedelta(days=days)
    
    # Leads created
    leads_query = db.query(Lead).filter(Lead.created_at >= since)
    if market_code:
        leads_query = leads_query.filter(Lead.market_code == market_code)
    total_leads = leads_query.count()
    
    # Outreach sent
    outreach_query = db.query(OutreachAttempt).filter(
        OutreachAttempt.created_at >= since
    )
    total_outreach = outreach_query.count()
    
    # Responses received
    responses_query = db.query(OutreachAttempt).filter(
        OutreachAttempt.created_at >= since,
        OutreachAttempt.response_body.isnot(None),
    )
    total_responses = responses_query.count()
    
    # Response rate
    response_rate = total_responses / total_outreach * 100 if total_outreach > 0 else 0
    
    # Hot leads generated (use score-based classification)
    from scoring.deterministic_engine import HOT_THRESHOLD
    hot_leads = db.query(Lead).filter(
        Lead.created_at >= since,
        Lead.deleted_at.is_(None),
        Lead.motivation_score >= HOT_THRESHOLD,
    )
    if market_code:
        hot_leads = hot_leads.filter(Lead.market_code == market_code)
    hot_leads_count = hot_leads.count()
    
    # Deals created
    deals_created = db.query(BuyerDeal).filter(
        BuyerDeal.created_at >= since
    ).count()
    
    return AnalyticsSummary(
        period=f"{days} days",
        total_leads_created=total_leads,
        total_outreach_sent=total_outreach,
        total_responses=total_responses,
        response_rate=round(response_rate, 1),
        hot_leads_generated=hot_leads_count,
        deals_created=deals_created,
        avg_time_to_response_hours=None,  # TODO: Calculate this
    )


@router.get("/analytics/daily")
async def get_daily_analytics(
    days: int = Query(default=30, ge=1, le=90),
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    """
    Get daily analytics breakdown.
    """
    since = utcnow() - timedelta(days=days)
    
    # Group by date
    daily_leads = db.query(
        func.date(Lead.created_at).label("date"),
        func.count(Lead.id).label("count"),
    ).filter(
        Lead.created_at >= since
    ).group_by(func.date(Lead.created_at)).all()
    
    daily_outreach = db.query(
        func.date(OutreachAttempt.created_at).label("date"),
        func.count(OutreachAttempt.id).label("count"),
    ).filter(
        OutreachAttempt.created_at >= since
    ).group_by(func.date(OutreachAttempt.created_at)).all()
    
    # Merge into daily records
    leads_by_date = {str(d.date): d.count for d in daily_leads}
    outreach_by_date = {str(d.date): d.count for d in daily_outreach}
    
    results = []
    for i in range(days):
        date = (utcnow() - timedelta(days=i)).strftime("%Y-%m-%d")
        results.append({
            "date": date,
            "leads_created": leads_by_date.get(date, 0),
            "outreach_sent": outreach_by_date.get(date, 0),
        })
    
    return list(reversed(results))


# =============================================================================
# Contract Endpoints
# =============================================================================

@router.get("/contracts")
async def list_contracts(
    lead_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    List generated contracts.
    """
    generator = get_contract_generator()
    return generator.list_generated_contracts(lead_id=lead_id)


@router.post("/contracts/generate")
async def generate_contract(
    request: ContractRequest,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Generate a contract for a lead.
    """
    from services.contract_generator import (
        SellerInfo, BuyerInfo, PropertyInfo, DealTerms, AssignmentTerms
    )
    
    # Load lead
    lead = db.query(Lead).filter(Lead.id == request.lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    
    parcel = lead.parcel
    owner = lead.owner
    party = owner.party if owner else None
    
    if not parcel:
        raise HTTPException(status_code=400, detail="Lead has no associated parcel")
    
    # Build seller info
    seller = SellerInfo(
        name=party.display_name if party else "Unknown Seller",
        address=party.raw_mailing_address or parcel.situs_address or "",
        city=parcel.city or "",
        state=parcel.state or lead.market_code,
        zip_code=party.normalized_zip or parcel.postal_code or "",
        phone=owner.phone_primary if owner else None,
        email=owner.email if owner else None,
    )
    
    # Build buyer info (wholesaler)
    buyer = BuyerInfo(
        name=SETTINGS.default_parish + " Land Investments, LLC",  # Placeholder
        address="",
        city="",
        state="LA",
        zip_code="",
        entity_type="llc",
    )
    
    # Build property info
    property_info = PropertyInfo(
        address=parcel.situs_address or "",
        city=parcel.city or "",
        state=parcel.state or lead.market_code,
        zip_code=parcel.postal_code or "",
        parish_county=parcel.parish,
        parcel_number=parcel.canonical_parcel_id,
        lot_size_acres=float(parcel.lot_size_acres or 1.0),
        zoning=parcel.zoning_code,
    )
    
    generator = get_contract_generator()
    
    if request.contract_type == "purchase_agreement":
        # Build deal terms
        terms = DealTerms(
            purchase_price=request.offer_amount,
            earnest_money=request.earnest_money,
            closing_date=utcnow() + timedelta(days=request.closing_days),
        )
        
        contract = generator.generate_purchase_agreement(
            lead_id=lead.id,
            seller=seller,
            buyer=buyer,
            property_info=property_info,
            terms=terms,
        )
    
    elif request.contract_type == "assignment":
        if not request.buyer_id or not request.assignment_fee:
            raise HTTPException(
                status_code=400,
                detail="buyer_id and assignment_fee required for assignment contract"
            )
        
        # Load end buyer
        end_buyer = db.query(Buyer).filter(Buyer.id == request.buyer_id).first()
        if not end_buyer:
            raise HTTPException(status_code=404, detail="End buyer not found")
        
        assignee = BuyerInfo(
            name=end_buyer.name,
            address="",
            city="",
            state="",
            zip_code="",
            phone=end_buyer.phone,
            email=end_buyer.email,
        )
        
        assignment_terms = AssignmentTerms(
            original_purchase_price=request.offer_amount,
            assignment_fee=request.assignment_fee,
            total_price=request.offer_amount + request.assignment_fee,
            assignment_date=utcnow() + timedelta(days=request.closing_days),
        )
        
        contract = generator.generate_assignment_contract(
            lead_id=lead.id,
            original_seller=seller,
            assignor=buyer,
            assignee=assignee,
            property_info=property_info,
            assignment_terms=assignment_terms,
            original_contract_date=utcnow(),
        )
    
    else:
        raise HTTPException(status_code=400, detail="Invalid contract type")
    
    return contract.to_dict()


__all__ = ["router"]

