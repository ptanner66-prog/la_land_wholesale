"""
Caller Sheet API Routes.

These endpoints support the sales-call-first workflow:
1. Generate caller work queue
2. Log call outcomes
3. Update pipeline based on outcomes
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from api.deps import get_db, get_readonly_db
from core.active_market import require_active_market
from core.logging_config import get_logger
from core.models import Lead, PipelineStage, TimelineEvent
from services.caller_sheet import get_caller_sheet_service

router = APIRouter()
LOGGER = get_logger(__name__)


class CallOutcome(str, Enum):
    """Possible call outcomes."""
    NOT_INTERESTED = "not_interested"
    CALL_BACK = "call_back"
    INTERESTED = "interested"
    NO_ANSWER = "no_answer"
    WRONG_NUMBER = "wrong_number"
    VOICEMAIL = "voicemail"


class LogCallOutcomeRequest(BaseModel):
    """Request to log a call outcome."""
    outcome: CallOutcome
    notes: Optional[str] = Field(None, max_length=1000)
    callback_date: Optional[str] = Field(None, description="ISO date for callback if outcome is call_back")


@router.get("/sheet")
async def get_caller_sheet(
    limit: int = 50,
    db: Session = Depends(get_readonly_db),
) -> Dict[str, Any]:
    """
    Generate the caller work queue.
    
    Requirements:
    - Active Market must be set
    - Returns HOT leads first, then CONTACT leads
    - All leads have TCPA-safe phone numbers
    
    If no leads are available, returns explanation of why.
    """
    service = get_caller_sheet_service(db)
    sheet = service.generate(limit=limit)
    return sheet.to_dict()


@router.post("/{lead_id}/outcome")
async def log_call_outcome(
    lead_id: int,
    request: LogCallOutcomeRequest,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Log the outcome of a sales call.
    
    Outcomes and pipeline updates:
    - NOT_INTERESTED: Mark lead as REJECTED, no further contact
    - CALL_BACK: Schedule callback, keep in queue
    - INTERESTED: Move to OFFER stage
    - NO_ANSWER/VOICEMAIL: Keep in queue, increment attempt count
    - WRONG_NUMBER: Mark phone as invalid
    """
    # Require active market
    active_market = require_active_market()
    
    # Get lead
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    
    # Verify lead is in active market
    if lead.market_code != active_market.market_code:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "cross_market_action",
                "message": f"Lead {lead_id} is in {lead.market_code}, but active market is {active_market.market_code}",
                "action": "Switch to the correct market or select a lead from the current market.",
            }
        )
    
    # Process outcome
    outcome = request.outcome
    now = datetime.now(timezone.utc)
    
    # Create timeline event
    event = TimelineEvent(
        lead_id=lead_id,
        event_type="call_outcome",
        title=f"Call: {outcome.value.replace('_', ' ').title()}",
        description=request.notes,
        event_metadata={
            "outcome": outcome.value,
            "callback_date": request.callback_date,
        },
        created_at=now,
    )
    db.add(event)
    
    # Update lead based on outcome
    pipeline_update = None
    message = ""
    
    if outcome == CallOutcome.NOT_INTERESTED:
        lead.status = "rejected"
        lead.pipeline_stage = PipelineStage.REVIEW.value  # Move to review for potential re-contact later
        pipeline_update = "REVIEW"
        message = "Lead marked as not interested. Moved to Review for potential future contact."
        
    elif outcome == CallOutcome.CALL_BACK:
        lead.status = "callback"
        if request.callback_date:
            try:
                lead.next_followup_at = datetime.fromisoformat(request.callback_date.replace("Z", "+00:00"))
            except ValueError:
                pass
        message = f"Callback scheduled{' for ' + request.callback_date if request.callback_date else ''}."
        
    elif outcome == CallOutcome.INTERESTED:
        lead.pipeline_stage = PipelineStage.OFFER.value
        lead.status = "interested"
        pipeline_update = "OFFER"
        message = "Lead is interested! Moved to Offer stage."
        
    elif outcome == CallOutcome.NO_ANSWER:
        lead.followup_count = (lead.followup_count or 0) + 1
        message = f"No answer. Attempt #{lead.followup_count}."
        
    elif outcome == CallOutcome.VOICEMAIL:
        lead.followup_count = (lead.followup_count or 0) + 1
        message = f"Left voicemail. Attempt #{lead.followup_count}."
        
    elif outcome == CallOutcome.WRONG_NUMBER:
        if lead.owner:
            lead.owner.phone_primary = None
            lead.owner.is_tcpa_safe = False
        message = "Phone marked as wrong number. Lead removed from caller queue."
    
    lead.updated_at = now
    db.commit()
    
    return {
        "success": True,
        "lead_id": lead_id,
        "outcome": outcome.value,
        "pipeline_update": pipeline_update,
        "message": message,
    }


@router.get("/{lead_id}")
async def get_lead_for_call(
    lead_id: int,
    db: Session = Depends(get_readonly_db),
) -> Dict[str, Any]:
    """
    Get lead details for a sales call.
    
    Returns:
    - Owner name and phone
    - Parcel summary
    - Score (read-only)
    - Previous call notes
    """
    # Require active market
    active_market = require_active_market()
    
    lead = (
        db.query(Lead)
        .filter(Lead.id == lead_id)
        .first()
    )
    
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    
    # Verify lead is in active market
    if lead.market_code != active_market.market_code:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "cross_market_action",
                "message": f"Lead {lead_id} is in {lead.market_code}, but active market is {active_market.market_code}",
            }
        )
    
    # Get previous call outcomes
    previous_calls = (
        db.query(TimelineEvent)
        .filter(
            TimelineEvent.lead_id == lead_id,
            TimelineEvent.event_type == "call_outcome",
        )
        .order_by(TimelineEvent.created_at.desc())
        .limit(10)
        .all()
    )
    
    parcel = lead.parcel
    owner = lead.owner
    party = owner.party if owner else None
    
    return {
        "id": lead.id,
        "owner_name": party.display_name if party else "Unknown",
        "phone": owner.phone_primary if owner else None,
        "motivation_score": lead.motivation_score,
        "pipeline_stage": lead.pipeline_stage,
        "parcel": {
            "parcel_id": parcel.canonical_parcel_id if parcel else None,
            "parish": parcel.parish if parcel else None,
            "acreage": float(parcel.lot_size_acres) if parcel and parcel.lot_size_acres else None,
            "land_value": float(parcel.land_assessed_value) if parcel and parcel.land_assessed_value else None,
            "is_adjudicated": parcel.is_adjudicated if parcel else False,
            "years_delinquent": parcel.years_tax_delinquent if parcel else 0,
            "property_address": parcel.situs_address if parcel else None,
        },
        "mailing_address": party.raw_mailing_address if party else None,
        "previous_calls": [
            {
                "date": e.created_at.isoformat() if e.created_at else None,
                "outcome": e.event_metadata.get("outcome") if e.event_metadata else None,
                "notes": e.description,
            }
            for e in previous_calls
        ],
    }


__all__ = ["router"]

