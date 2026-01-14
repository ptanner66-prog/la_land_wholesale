"""Twilio webhook handlers."""
from typing import Dict, Any

from fastapi import APIRouter, Form, Request
from sqlalchemy.orm import Session

from api.deps import get_db
from core.logging_config import get_logger
from core.models import OutreachAttempt
from fastapi import Depends

router = APIRouter()
LOGGER = get_logger(__name__)


@router.post("/status-callback")
async def twilio_status_callback(
    request: Request,
    MessageSid: str = Form(...),
    MessageStatus: str = Form(...),
    ErrorCode: str = Form(None),
    ErrorMessage: str = Form(None),
    To: str = Form(None),
    From: str = Form(None),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Handle Twilio delivery status callbacks.
    
    Status progression: queued → sending → sent → delivered | undelivered | failed
    """
    LOGGER.info(
        "Twilio callback: SID=%s, Status=%s, ErrorCode=%s, To=%s",
        MessageSid, MessageStatus, ErrorCode, To
    )
    
    # Find outreach attempt by external_id (SID)
    attempt = db.query(OutreachAttempt).filter(
        OutreachAttempt.external_id == MessageSid
    ).first()
    
    if not attempt:
        LOGGER.warning("No OutreachAttempt found for SID: %s", MessageSid)
        return {"status": "ok", "warning": "attempt_not_found"}
    
    # Update status
    old_status = attempt.status
    
    if MessageStatus == "delivered":
        attempt.status = "delivered"
        attempt.result = "delivered"
    elif MessageStatus in ["undelivered", "failed"]:
        attempt.status = "failed"
        attempt.result = MessageStatus
        attempt.error_message = f"Error {ErrorCode}: {ErrorMessage}" if ErrorCode else MessageStatus
    elif MessageStatus in ["sent", "sending"]:
        attempt.status = "sent"
        attempt.result = "sent"
    
    db.commit()
    
    LOGGER.info(
        "Updated OutreachAttempt %s: %s → %s (SID: %s)",
        attempt.id, old_status, attempt.status, MessageSid
    )
    
    return {"status": "ok", "updated": True}

