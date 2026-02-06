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


class ReplyRequest(BaseModel):
    """Request body for sending an inbox reply."""

    lead_id: int = Field(..., description="Lead ID to reply to")
    message: str = Field(..., min_length=1, max_length=1600, description="Reply message text")


@router.post("/reply")
async def send_reply(
    body: ReplyRequest,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Send an SMS reply from the inbox.

    Validates TCPA compliance (DNC/opt-out) before sending.
    Logs the attempt in outreach_attempt with direction context.
    """
    from core.models import Lead, OutreachAttempt, Owner
    from services.timeline import TimelineService
    from core.config import get_settings
    import uuid

    settings = get_settings()

    lead = db.query(Lead).filter(Lead.id == body.lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    owner = lead.owner
    if not owner:
        raise HTTPException(status_code=400, detail="Lead has no owner record")

    phone = owner.phone_primary
    if not phone:
        raise HTTPException(status_code=400, detail="Owner has no phone number")

    # TCPA compliance checks
    if owner.opt_out:
        raise HTTPException(status_code=403, detail="Owner has opted out of messages")
    if owner.is_dnr:
        raise HTTPException(status_code=403, detail="Owner is on Do Not Contact list")

    # Create outreach attempt record
    attempt = OutreachAttempt(
        lead_id=lead.id,
        idempotency_key=f"reply-{uuid.uuid4().hex[:16]}",
        channel="sms",
        message_body=body.message,
        message_context="reply",
        status="pending",
    )
    db.add(attempt)
    db.flush()

    # Send via Twilio (or dry-run)
    if settings.dry_run:
        attempt.status = "sent"
        attempt.result = "dry_run"
        LOGGER.info(f"DRY RUN reply to lead {lead.id}: {body.message[:50]}...")
    elif settings.is_twilio_enabled():
        try:
            from twilio.rest import Client as TwilioClient

            client = TwilioClient(settings.twilio_account_sid, settings.twilio_auth_token)
            from_number = settings.twilio_from_number or settings.twilio_messaging_service_sid

            msg_kwargs = {"body": body.message, "to": phone}
            if settings.twilio_messaging_service_sid:
                msg_kwargs["messaging_service_sid"] = settings.twilio_messaging_service_sid
            else:
                msg_kwargs["from_"] = from_number

            twilio_msg = client.messages.create(**msg_kwargs)
            attempt.status = "sent"
            attempt.result = "sent"
            attempt.external_id = twilio_msg.sid
            from core.utils import utcnow
            attempt.sent_at = utcnow()
            LOGGER.info(f"Reply sent to lead {lead.id}, SID: {twilio_msg.sid}")
        except Exception as e:
            attempt.status = "failed"
            attempt.result = "failed"
            attempt.error_message = str(e)
            LOGGER.error(f"Twilio send failed for reply to lead {lead.id}: {e}")
            raise HTTPException(status_code=502, detail=f"SMS send failed: {e}")
    else:
        attempt.status = "failed"
        attempt.result = "no_provider"
        attempt.error_message = "Twilio not configured"
        raise HTTPException(status_code=503, detail="SMS provider not configured")

    # Log to timeline
    try:
        timeline = TimelineService(db)
        timeline.log_message_sent(lead.id, "sms", "reply", body.message)
    except Exception:
        pass  # Don't fail the reply if timeline logging fails

    db.commit()

    return {
        "success": True,
        "attempt_id": attempt.id,
        "status": attempt.status,
        "result": attempt.result,
        "message": body.message,
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
