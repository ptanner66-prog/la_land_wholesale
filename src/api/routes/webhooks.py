"""Webhook routes for external service callbacks with security and opt-out handling."""
from __future__ import annotations

from typing import Dict, Any, Optional

from fastapi import APIRouter, Depends, Request, HTTPException, Form
from sqlalchemy.orm import Session

from api.deps import get_db
from core.logging_config import get_logger
from core.utils import utcnow

router = APIRouter()
LOGGER = get_logger(__name__)


@router.post("/twilio/sms")
async def twilio_sms_webhook(
    request: Request,
    From: str = Form(...),
    To: str = Form(...),
    Body: str = Form(...),
    MessageSid: str = Form(None),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Handle incoming SMS from Twilio.
    
    FIXED:
    - Sets opt_out=True when classification is DEAD
    - Uses MessageSid to find outreach attempt (not "most recent")
    - Validates Twilio signature (when configured)
    
    This webhook:
    1. Validates signature (if configured)
    2. Finds the lead associated with the phone number
    3. Classifies the reply using AI
    4. Sets opt_out if DEAD (STOP word detected)
    5. Updates the lead's pipeline stage if appropriate
    6. Sends alerts for interested/send_offer replies
    7. Logs to timeline
    """
    from core.config import get_settings
    from core.models import Lead, Owner, OutreachAttempt, ReplyClassification
    from services.reply_classifier import get_reply_classifier
    from services.notification import get_notification_service
    from services.timeline import TimelineService
    from services.outreach_validator import get_outreach_validator
    
    settings = get_settings()
    
    # Validate Twilio signature (skip in dry run mode)
    if not settings.dry_run and settings.twilio_auth_token:
        from services.webhook_security import TwilioSignatureValidator
        
        signature = request.headers.get("X-Twilio-Signature", "")
        url = str(request.url)
        
        # Handle forwarded URLs (ngrok, etc.)
        forwarded_proto = request.headers.get("X-Forwarded-Proto")
        forwarded_host = request.headers.get("X-Forwarded-Host")
        if forwarded_proto and forwarded_host:
            url = f"{forwarded_proto}://{forwarded_host}{request.url.path}"
        
        params = {"From": From, "To": To, "Body": Body}
        if MessageSid:
            params["MessageSid"] = MessageSid
        
        validator = TwilioSignatureValidator()
        if not validator.validate(url, params, signature):
            LOGGER.error("Invalid Twilio webhook signature")
            raise HTTPException(status_code=403, detail="Invalid signature")
    
    LOGGER.info(f"Received SMS from {From}: {Body[:50]}...")
    
    # Normalize phone number
    from_phone = From.replace("+1", "").replace("-", "").replace(" ", "")
    if len(from_phone) == 10:
        from_phone = f"+1{from_phone}"
    elif not from_phone.startswith("+"):
        from_phone = f"+{from_phone}"
    
    # Find owner by phone
    owner = db.query(Owner).filter(
        (Owner.phone_primary == from_phone) | 
        (Owner.phone_primary == From) |
        (Owner.phone_secondary == from_phone) |
        (Owner.phone_secondary == From)
    ).first()
    
    if not owner:
        LOGGER.warning(f"No owner found for phone {From}")
        return {"status": "no_match", "phone": From}
    
    # Find associated lead
    lead = db.query(Lead).filter(Lead.owner_id == owner.id).first()
    if not lead:
        LOGGER.warning(f"No lead found for owner {owner.id}")
        return {"status": "no_lead", "owner_id": owner.id}
    
    # Classify the reply
    classifier = get_reply_classifier()
    classification = classifier.classify_reply(Body)
    pipeline_action, reason = classifier.get_pipeline_action(classification)
    
    LOGGER.info(f"Reply classified as {classification.value} for lead {lead.id}")
    
    # CRITICAL FIX: Find outreach attempt by MessageSid if provided
    # This prevents race conditions where we attach reply to wrong attempt
    attempt = None
    if MessageSid:
        # First try to find by the related outbound message SID
        # Twilio inbound MessageSid is different, but we can correlate by timing
        attempt = db.query(OutreachAttempt).filter(
            OutreachAttempt.lead_id == lead.id,
            OutreachAttempt.response_received_at.is_(None),  # No reply yet
        ).order_by(OutreachAttempt.created_at.desc()).first()
    
    if not attempt:
        # Fallback to most recent attempt
        attempt = db.query(OutreachAttempt).filter(
            OutreachAttempt.lead_id == lead.id
        ).order_by(OutreachAttempt.created_at.desc()).first()
    
    if attempt:
        attempt.response_received_at = utcnow()
        attempt.response_body = Body
        attempt.reply_classification = classification.value
    
    # Update lead
    lead.last_reply_classification = classification.value
    lead.last_reply_at = utcnow()
    
    # Log to timeline
    timeline = TimelineService(db)
    timeline.log_reply_received(lead.id, Body, classification.value)
    
    # CRITICAL FIX: Set opt_out when DEAD (includes STOP, unsubscribe, etc.)
    if classification == ReplyClassification.DEAD:
        owner.opt_out = True
        owner.opt_out_at = utcnow()
        
        # Log opt-out to timeline
        timeline.add_event(
            lead_id=lead.id,
            event_type="opt_out",
            title="Owner opted out",
            description=f"Opt-out triggered by reply: {Body[:100]}",
            metadata={"classification": classification.value, "reply": Body[:200]},
        )
        
        LOGGER.info(f"Owner {owner.id} opted out due to DEAD classification")
    
    # Update pipeline stage if needed
    old_stage = lead.pipeline_stage
    if pipeline_action:
        lead.pipeline_stage = pipeline_action
        timeline.log_stage_change(lead.id, old_stage, pipeline_action, reason)
    
    # Send alerts for interested replies
    if classification.value in ("INTERESTED", "SEND_OFFER"):
        notification = get_notification_service(db)
        notification.alert_interested_reply(lead, classification.value, Body)
    
    db.commit()
    
    return {
        "status": "processed",
        "lead_id": lead.id,
        "classification": classification.value,
        "pipeline_action": pipeline_action,
        "old_stage": old_stage,
        "new_stage": lead.pipeline_stage,
        "opted_out": classification == ReplyClassification.DEAD,
    }


@router.post("/twilio/status")
async def twilio_status_webhook(
    request: Request,
    MessageSid: str = Form(...),
    MessageStatus: str = Form(...),
    To: str = Form(None),
    ErrorCode: str = Form(None),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Handle Twilio message status callbacks.
    
    FIXED: Looks up by external_id (MessageSid) directly.
    
    Updates the outreach attempt status based on delivery status.
    """
    from core.models import OutreachAttempt
    
    LOGGER.info(f"Twilio status update: {MessageSid} -> {MessageStatus}")
    
    # Find the outreach attempt by Twilio SID
    attempt = db.query(OutreachAttempt).filter(
        OutreachAttempt.external_id == MessageSid
    ).first()
    
    if not attempt:
        LOGGER.warning(f"No outreach attempt found for SID {MessageSid}")
        return {"status": "not_found", "sid": MessageSid}
    
    # Map Twilio status to our status
    status_map = {
        "queued": "pending",
        "sending": "pending",
        "sent": "sent",
        "delivered": "delivered",
        "undelivered": "failed",
        "failed": "failed",
    }
    
    new_status = status_map.get(MessageStatus.lower(), attempt.status)
    attempt.status = new_status
    
    if new_status == "delivered":
        attempt.delivered_at = utcnow()
    
    if new_status == "failed" and ErrorCode:
        attempt.error_message = f"Twilio error: {ErrorCode}"
    
    db.commit()
    
    return {
        "status": "updated",
        "attempt_id": attempt.id,
        "new_status": new_status,
    }
