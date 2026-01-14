"""Outreach routes with validation and message body support."""
from __future__ import annotations

from typing import Dict, Any, List, Optional

from fastapi import APIRouter, Depends, BackgroundTasks, Query, Body, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from api.deps import get_db, get_readonly_db
from core.logging_config import get_logger

router = APIRouter()
LOGGER = get_logger(__name__)


# =============================================================================
# Pydantic Models
# =============================================================================


class ClassifyReplyRequest(BaseModel):
    """Request body for reply classification."""
    
    text: str = Field(..., min_length=1, description="Reply text to classify")


class GenerateMessageRequest(BaseModel):
    """Request body for message generation."""
    
    lead_id: int = Field(..., description="Lead ID to generate message for")
    context: str = Field(..., description="Message context: intro, followup, or final")


class SendMessageRequest(BaseModel):
    """Request body for sending a message with custom content."""
    
    message_body: Optional[str] = Field(None, description="Custom message body to send")
    context: str = Field("intro", description="Message context: intro, followup, or final")
    force: bool = Field(False, description="Force send even if validation fails")


# =============================================================================
# Routes
# =============================================================================


@router.post("/run")
async def run_outreach(
    market: Optional[str] = Query(default=None, description="Filter by market code"),
    limit: int = Query(default=50, ge=1, le=500),
    min_score: Optional[int] = Query(default=None, ge=0, le=100),
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Trigger outreach batch."""
    from domain.outreach import OutreachService
    
    def _run() -> None:
        from core.db import SessionLocal
        session = SessionLocal()
        try:
            service = OutreachService(session)
            result = service.send_batch(limit=limit, min_score=min_score, market_code=market)
            session.commit()
            LOGGER.info(
                f"Outreach complete: {result.successful}/{result.total_attempted} successful"
            )
        except Exception as e:
            session.rollback()
            LOGGER.error(f"Background outreach failed: {e}")
        finally:
            session.close()

    if background_tasks:
        background_tasks.add_task(_run)
        return {"message": "Outreach batch started in background", "limit": limit, "market": market}
    else:
        service = OutreachService(db)
        result = service.send_batch(limit=limit, min_score=min_score, market_code=market)
        return result.to_dict()


@router.post("/send/{lead_id}")
async def send_to_lead(
    lead_id: int,
    body: SendMessageRequest = Body(default=SendMessageRequest()),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Send SMS to a specific lead.
    
    FIXED: Accepts optional message_body to send user-selected message variant.
    """
    from domain.outreach import OutreachService
    from services.timeline import TimelineService
    from services.outreach_validator import get_outreach_validator
    from core.models import Lead
    
    # Validate lead exists
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    
    # Validate can send
    validator = get_outreach_validator(db)
    validation = validator.validate_can_send(lead, force=body.force)
    
    if not validation.can_send and not body.force:
        return {
            "success": False,
            "error": validation.reason,
            "error_code": validation.error_code,
        }
    
    service = OutreachService(db)
    
    # Pass message_body if provided (user-selected variant)
    result = service.send_first_touch(
        lead_id,
        force=body.force,
        context=body.context,
        message_body=body.message_body,  # FIXED: Pass custom message
    )
    
    # Log to timeline
    if result.success:
        timeline = TimelineService(db)
        timeline.log_message_sent(lead_id, "sms", body.context, result.message_body)
    
    db.commit()
    
    return result.to_dict()


@router.get("/history")
async def get_outreach_history(
    market: Optional[str] = Query(default=None, description="Filter by market code"),
    lead_id: Optional[int] = Query(default=None),
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_readonly_db),
) -> List[Dict[str, Any]]:
    """Get outreach attempt history."""
    from domain.outreach import OutreachService
    
    service = OutreachService(db)
    return service.get_outreach_history(
        lead_id=lead_id,
        market_code=market,
        status=status,
        limit=limit,
        offset=offset,
    )


@router.get("/stats")
async def get_outreach_stats(
    market: Optional[str] = Query(default=None, description="Filter by market code"),
    days: int = Query(default=7, ge=1, le=30),
    db: Session = Depends(get_readonly_db),
) -> Dict[str, Any]:
    """Get daily outreach statistics."""
    from domain.outreach import OutreachService
    
    service = OutreachService(db)
    return service.get_daily_stats(days=days, market_code=market)


@router.post("/reply/{lead_id}")
async def send_reply_to_lead(
    lead_id: int,
    message: str = Body(..., embed=True),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Send manual reply to a lead from the inbox."""
    from domain.outreach import OutreachService
    from core.models import Lead

    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    service = OutreachService(db)
    result = service.send_first_touch(lead_id, force=True, context="reply", message_body=message)

    if result.success:
        return {
            "success": True,
            "message_sid": result.twilio_sid,
            "message": "Reply sent successfully"
        }
    else:
        raise HTTPException(status_code=400, detail=result.error or "Failed to send reply")


@router.post("/classify_reply")
async def classify_reply(
    body: ClassifyReplyRequest,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Classify a reply text using AI."""
    from services.reply_classifier import get_reply_classifier
    
    classifier = get_reply_classifier()
    classification = classifier.classify_reply(body.text)
    pipeline_action, reason = classifier.get_pipeline_action(classification)
    
    return {
        "classification": classification.value,
        "pipeline_action": pipeline_action,
        "reason": reason,
    }


@router.post("/generate_message")
async def generate_message(
    body: GenerateMessageRequest,
    db: Session = Depends(get_readonly_db),
) -> Dict[str, Any]:
    """Generate message templates for a lead."""
    from services.message_generator import get_message_generator
    from core.models import Lead
    
    lead = db.query(Lead).filter(Lead.id == body.lead_id).first()
    if not lead:
        return {"success": False, "error": "Lead not found"}
    
    valid_contexts = ["intro", "followup", "final"]
    if body.context not in valid_contexts:
        return {"success": False, "error": f"Invalid context. Must be one of: {valid_contexts}"}
    
    generator = get_message_generator()
    variants = generator.generate_messages(lead, body.context)
    
    return {
        "success": True,
        "lead_id": body.lead_id,
        "context": body.context,
        "variants": [v.to_dict() for v in variants],
    }


@router.get("/followup_due")
async def get_followups_due(
    market: Optional[str] = Query(default=None, description="Filter by market code"),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_readonly_db),
) -> Dict[str, Any]:
    """Get leads due for follow-up."""
    from services.followup import get_followup_service
    
    service = get_followup_service(db)
    leads = service.get_leads_due_for_followup(market_code=market, limit=limit)
    
    return {
        "total_due": len(leads),
        "leads": [
            {
                "id": lead.id,
                "market_code": lead.market_code,
                "pipeline_stage": lead.pipeline_stage,
                "followup_count": lead.followup_count,
                "next_followup_at": lead.next_followup_at.isoformat() if lead.next_followup_at else None,
            }
            for lead in leads
        ],
    }
