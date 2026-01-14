"""
Conversations API - Inbox Thread Management

Derives conversation threads from outreach_attempt table.
Every lead with outreach history = one conversation thread.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, and_, or_, desc
from sqlalchemy.orm import Session, selectinload

from api.deps import get_db, get_readonly_db
from core.logging_config import get_logger
from core.models import Lead, Owner, Parcel, Party, OutreachAttempt, PipelineStage
from core.address_utils import compute_display_location

router = APIRouter()
LOGGER = get_logger(__name__)


class ConversationMessage(BaseModel):
    """A single message in a conversation."""
    id: int
    direction: str  # 'inbound' or 'outbound'
    body: str
    sent_at: Optional[str]
    status: str
    classification: Optional[str] = None


class ConversationThread(BaseModel):
    """A conversation thread (one per lead with outreach)."""
    id: int  # lead_id
    lead_id: int
    owner_name: str
    owner_phone: Optional[str]
    parcel_id: str
    parish: str
    property_address: str
    motivation_score: int
    pipeline_stage: str
    classification: Optional[str]  # YES, NO, MAYBE, PENDING
    last_message: str
    last_message_direction: str
    last_message_at: Optional[str]
    unread: bool
    message_count: int
    has_reply: bool


class ConversationDetail(ConversationThread):
    """Full conversation with messages."""
    messages: List[ConversationMessage]


class ClassifyRequest(BaseModel):
    """Request to classify a conversation."""
    classification: str = Field(..., pattern="^(YES|NO|MAYBE|OTHER)$")


@router.get("/threads")
async def get_conversation_threads(
    market: Optional[str] = Query(None, description="Filter by market code"),
    filter: str = Query("all", description="Filter: all, unread, yes, maybe, pending"),
    search: Optional[str] = Query(None, description="Search by owner name or phone"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_readonly_db),
) -> Dict[str, Any]:
    """
    Get conversation threads derived from outreach history.
    
    Each lead with at least one outreach attempt = one thread.
    """
    # Base query: leads with outreach attempts
    query = (
        db.query(Lead)
        .join(Lead.owner)
        .join(Owner.party)
        .join(Lead.parcel)
        .join(Lead.outreach_attempts)
        .options(
            selectinload(Lead.owner).selectinload(Owner.party),
            selectinload(Lead.parcel),
            selectinload(Lead.outreach_attempts),
        )
        .filter(Lead.deleted_at.is_(None))
    )
    
    # Market filter
    if market:
        query = query.filter(Lead.market_code == market.upper())
    
    # Classification/status filter
    if filter == "unread":
        # Has inbound message without classification
        query = query.filter(
            Lead.outreach_attempts.any(
                and_(
                    OutreachAttempt.response_received_at.isnot(None),
                    OutreachAttempt.reply_classification.is_(None),
                )
            )
        )
    elif filter == "yes":
        query = query.filter(
            Lead.outreach_attempts.any(OutreachAttempt.reply_classification == "YES")
        )
    elif filter == "maybe":
        query = query.filter(
            Lead.outreach_attempts.any(OutreachAttempt.reply_classification == "MAYBE")
        )
    elif filter == "pending":
        # Has outreach but no reply yet
        query = query.filter(
            ~Lead.outreach_attempts.any(OutreachAttempt.response_received_at.isnot(None))
        )
    
    # Search
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            or_(
                Party.display_name.ilike(search_term),
                Owner.phone_primary.ilike(search_term),
                Parcel.canonical_parcel_id.ilike(search_term),
            )
        )
    
    # Get distinct leads with outreach
    query = query.distinct(Lead.id)
    
    # Count total
    total = query.count()
    
    # Order by most recent activity
    query = query.order_by(desc(Lead.updated_at))
    
    # Paginate
    leads = query.offset(offset).limit(limit).all()
    
    # Build thread list
    threads = []
    for lead in leads:
        # Get latest outreach attempt
        attempts = sorted(lead.outreach_attempts, key=lambda a: a.created_at or datetime.min, reverse=True)
        latest = attempts[0] if attempts else None
        
        # Determine if unread (has reply without classification)
        has_unclassified_reply = any(
            a.response_received_at and not a.reply_classification 
            for a in attempts
        )
        
        # Get latest classification
        latest_classification = None
        for a in attempts:
            if a.reply_classification:
                latest_classification = a.reply_classification
                break
        
        # Has any reply?
        has_reply = any(a.response_received_at for a in attempts)
        
        # Get property location
        location = compute_display_location(lead)
        
        # Build thread
        thread = ConversationThread(
            id=lead.id,
            lead_id=lead.id,
            owner_name=lead.owner.party.display_name if lead.owner and lead.owner.party else "Unknown",
            owner_phone=lead.owner.phone_primary if lead.owner else None,
            parcel_id=lead.parcel.canonical_parcel_id if lead.parcel else "Unknown",
            parish=lead.parcel.parish if lead.parcel else "Unknown",
            property_address=location.short_address,
            motivation_score=lead.motivation_score or 0,
            pipeline_stage=lead.pipeline_stage or "NEW",
            classification=latest_classification,
            last_message=latest.message_body[:100] if latest and latest.message_body else "",
            last_message_direction="inbound" if latest and latest.response_received_at else "outbound",
            last_message_at=latest.sent_at.isoformat() if latest and latest.sent_at else None,
            unread=has_unclassified_reply,
            message_count=len(attempts),
            has_reply=has_reply,
        )
        threads.append(thread)
    
    return {
        "threads": [t.model_dump() for t in threads],
        "total": total,
        "limit": limit,
        "offset": offset,
        "filters": {
            "market": market,
            "filter": filter,
            "search": search,
        },
    }


@router.get("/threads/{lead_id}")
async def get_conversation_detail(
    lead_id: int,
    db: Session = Depends(get_readonly_db),
) -> Dict[str, Any]:
    """
    Get full conversation detail for a lead.
    
    Includes all messages (outbound + inbound replies).
    """
    lead = (
        db.query(Lead)
        .options(
            selectinload(Lead.owner).selectinload(Owner.party),
            selectinload(Lead.parcel),
            selectinload(Lead.outreach_attempts),
        )
        .filter(Lead.id == lead_id, Lead.deleted_at.is_(None))
        .first()
    )
    
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    
    # Build messages list
    messages = []
    for attempt in sorted(lead.outreach_attempts, key=lambda a: a.created_at or datetime.min):
        # Outbound message
        if attempt.message_body:
            messages.append(ConversationMessage(
                id=attempt.id,
                direction="outbound",
                body=attempt.message_body,
                sent_at=attempt.sent_at.isoformat() if attempt.sent_at else None,
                status=attempt.status or "sent",
                classification=None,
            ))
        
        # Inbound reply (if any)
        if attempt.response_body:
            messages.append(ConversationMessage(
                id=attempt.id * 1000,  # Unique ID for reply
                direction="inbound",
                body=attempt.response_body,
                sent_at=attempt.response_received_at.isoformat() if attempt.response_received_at else None,
                status="received",
                classification=attempt.reply_classification,
            ))
    
    # Get location
    location = compute_display_location(lead)
    
    # Determine latest classification
    latest_classification = None
    for attempt in sorted(lead.outreach_attempts, key=lambda a: a.created_at or datetime.min, reverse=True):
        if attempt.reply_classification:
            latest_classification = attempt.reply_classification
            break
    
    # Has unclassified reply?
    has_unclassified_reply = any(
        a.response_received_at and not a.reply_classification 
        for a in lead.outreach_attempts
    )
    
    return {
        "id": lead.id,
        "lead_id": lead.id,
        "owner_name": lead.owner.party.display_name if lead.owner and lead.owner.party else "Unknown",
        "owner_phone": lead.owner.phone_primary if lead.owner else None,
        "parcel_id": lead.parcel.canonical_parcel_id if lead.parcel else "Unknown",
        "parish": lead.parcel.parish if lead.parcel else "Unknown",
        "property_address": location.short_address,
        "motivation_score": lead.motivation_score or 0,
        "pipeline_stage": lead.pipeline_stage or "NEW",
        "classification": latest_classification,
        "last_message": messages[-1].body[:100] if messages else "",
        "last_message_direction": messages[-1].direction if messages else "outbound",
        "last_message_at": messages[-1].sent_at if messages else None,
        "unread": has_unclassified_reply,
        "message_count": len(messages),
        "has_reply": any(m.direction == "inbound" for m in messages),
        "messages": [m.model_dump() for m in messages],
    }


@router.post("/threads/{lead_id}/classify")
async def classify_conversation(
    lead_id: int,
    body: ClassifyRequest,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Classify a conversation (YES/NO/MAYBE/OTHER).
    
    Updates the reply_classification on the most recent outreach attempt with a reply.
    """
    lead = (
        db.query(Lead)
        .options(selectinload(Lead.outreach_attempts))
        .filter(Lead.id == lead_id, Lead.deleted_at.is_(None))
        .first()
    )
    
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    
    # Find the most recent attempt with a reply
    attempts_with_reply = [
        a for a in lead.outreach_attempts 
        if a.response_received_at
    ]
    
    if not attempts_with_reply:
        raise HTTPException(status_code=400, detail="No reply to classify")
    
    latest_reply = max(attempts_with_reply, key=lambda a: a.response_received_at)
    latest_reply.reply_classification = body.classification
    
    # Update lead pipeline stage if YES
    if body.classification == "YES":
        lead.pipeline_stage = PipelineStage.HOT.value
    
    db.commit()
    
    LOGGER.info(f"Classified conversation for lead {lead_id} as {body.classification}")
    
    return {
        "success": True,
        "lead_id": lead_id,
        "classification": body.classification,
        "pipeline_stage": lead.pipeline_stage,
    }


@router.get("/stats")
async def get_conversation_stats(
    market: Optional[str] = Query(None),
    db: Session = Depends(get_readonly_db),
) -> Dict[str, Any]:
    """Get conversation statistics for the inbox."""
    base_query = (
        db.query(Lead)
        .join(Lead.outreach_attempts)
        .filter(Lead.deleted_at.is_(None))
    )
    
    if market:
        base_query = base_query.filter(Lead.market_code == market.upper())
    
    # Total threads (leads with outreach)
    total_threads = base_query.distinct(Lead.id).count()
    
    # Unread (has reply without classification)
    unread_count = (
        base_query
        .filter(
            OutreachAttempt.response_received_at.isnot(None),
            OutreachAttempt.reply_classification.is_(None),
        )
        .distinct(Lead.id)
        .count()
    )
    
    # YES replies
    yes_count = (
        base_query
        .filter(OutreachAttempt.reply_classification == "YES")
        .distinct(Lead.id)
        .count()
    )
    
    # MAYBE replies
    maybe_count = (
        base_query
        .filter(OutreachAttempt.reply_classification == "MAYBE")
        .distinct(Lead.id)
        .count()
    )
    
    # Pending (no reply yet)
    pending_count = (
        db.query(Lead)
        .join(Lead.outreach_attempts)
        .filter(
            Lead.deleted_at.is_(None),
            ~Lead.outreach_attempts.any(OutreachAttempt.response_received_at.isnot(None)),
        )
        .distinct(Lead.id)
        .count()
    )
    
    return {
        "total_threads": total_threads,
        "unread": unread_count,
        "yes_queue": yes_count,
        "maybe_queue": maybe_count,
        "pending": pending_count,
    }


__all__ = ["router"]

