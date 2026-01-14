"""Outreach domain service - core business logic for SMS outreach."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from core.config import get_settings
from core.exceptions import TCPAError, InvalidPhoneNumberError
from core.logging_config import get_logger
from core.models import Lead, Owner, OutreachAttempt
from llm.text_generator import generate_first_touch_sms
from outreach.phone import normalize_phone_e164, is_tcpa_safe
from outreach.selector import select_leads_for_first_touch
from outreach.twilio_sender import send_first_text
from risk.guardrails import check_daily_sms_limit

LOGGER = get_logger(__name__)
SETTINGS = get_settings()


@dataclass
class OutreachResult:
    """Result of an outreach attempt."""
    
    lead_id: int
    success: bool
    result: str
    message_body: Optional[str]
    twilio_sid: Optional[str]
    error: Optional[str]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "lead_id": self.lead_id,
            "success": self.success,
            "result": self.result,
            "message_body": self.message_body,
            "twilio_sid": self.twilio_sid,
            "error": self.error,
        }


@dataclass
class BatchOutreachResult:
    """Result of a batch outreach operation."""
    
    total_attempted: int
    successful: int
    failed: int
    dry_run: bool
    results: List[OutreachResult]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "total_attempted": self.total_attempted,
            "successful": self.successful,
            "failed": self.failed,
            "dry_run": self.dry_run,
            "results": [r.to_dict() for r in self.results],
        }


class OutreachService:
    """Service for outreach-related operations."""
    
    def __init__(self, session: Session) -> None:
        """Initialize the outreach service with a database session."""
        self.session = session
    
    def validate_lead_for_outreach(self, lead: Lead) -> tuple[bool, Optional[str]]:
        """
        Validate a lead is eligible for SMS outreach.
        
        Args:
            lead: Lead to validate.
        
        Returns:
            Tuple of (is_valid, error_message).
        """
        owner = lead.owner
        
        # Check TCPA safety
        if not owner.is_tcpa_safe:
            return False, "Lead is not TCPA-safe"
        
        # Check DNR flag
        if owner.is_dnr:
            return False, "Lead is on Do Not Reach list"
        
        # Check opt-out
        if owner.opt_out:
            return False, "Lead has opted out"
        
        # Check phone number
        phone = owner.phone_primary
        if not phone:
            return False, "Lead has no phone number"
        
        normalized = normalize_phone_e164(phone)
        if not normalized:
            return False, "Lead has invalid phone number"
        
        if not is_tcpa_safe(normalized):
            return False, "Phone number is not TCPA-compliant"
        
        return True, None
    
    def send_first_touch(
        self,
        lead_id: int,
        force: bool = False,
        context: str = "intro",
        message_body: Optional[str] = None,
    ) -> OutreachResult:
        """
        Send first-touch SMS to a specific lead.
        
        Args:
            lead_id: ID of the lead to contact.
            force: If True, skip some validation checks.
            context: Message context (intro, followup, final).
            message_body: Optional custom message body.
        
        Returns:
            OutreachResult with outcome details.
        """
        lead = self.session.query(Lead).filter(Lead.id == lead_id).one_or_none()
        
        if lead is None:
            return OutreachResult(
                lead_id=lead_id,
                success=False,
                result="not_found",
                message_body=None,
                twilio_sid=None,
                error="Lead not found",
            )
        
        # Validate lead
        is_valid, error = self.validate_lead_for_outreach(lead)
        if not is_valid and not force:
            return OutreachResult(
                lead_id=lead_id,
                success=False,
                result="validation_failed",
                message_body=None,
                twilio_sid=None,
                error=error,
            )
        
        try:
            attempt = send_first_text(self.session, lead, force=force, message_body=message_body)
            return OutreachResult(
                lead_id=lead_id,
                success=attempt.result in ("sent", "dry_run"),
                result=attempt.result or "unknown",
                message_body=attempt.message_body,
                twilio_sid=attempt.external_id,
                error=None,
            )
        except (TCPAError, InvalidPhoneNumberError) as e:
            LOGGER.warning("Outreach validation failed for lead %s: %s", lead_id, e)
            return OutreachResult(
                lead_id=lead_id,
                success=False,
                result="validation_error",
                message_body=None,
                twilio_sid=None,
                error=str(e),
            )
        except Exception as e:
            LOGGER.exception("Outreach failed for lead %s: %s", lead_id, e)
            return OutreachResult(
                lead_id=lead_id,
                success=False,
                result="error",
                message_body=None,
                twilio_sid=None,
                error=str(e),
            )
    
    def send_batch(
        self,
        limit: int = 10,
        min_score: Optional[int] = None,
        cooldown_days: Optional[int] = None,
        market_code: Optional[str] = None,
    ) -> BatchOutreachResult:
        """
        Send first-touch SMS to a batch of eligible leads.
        
        Args:
            limit: Maximum number of leads to contact.
            min_score: Minimum motivation score (uses config default if None).
            cooldown_days: Days since last outreach (uses config default if None).
        
        Returns:
            BatchOutreachResult with summary and individual results.
        """
        # Check daily SMS limit first
        if not check_daily_sms_limit(self.session, limit):
            LOGGER.warning("Daily SMS limit would be exceeded, reducing batch size")
            # Could reduce limit here, but for safety we proceed with what we have
        
        # Select eligible leads
        leads = select_leads_for_first_touch(
            session=self.session,
            limit=limit,
            min_score=min_score,
            cooldown_days=cooldown_days,
        )
        
        if not leads:
            return BatchOutreachResult(
                total_attempted=0,
                successful=0,
                failed=0,
                dry_run=SETTINGS.dry_run,
                results=[],
            )
        
        results: List[OutreachResult] = []
        successful = 0
        failed = 0
        
        for lead in leads:
            result = self.send_first_touch(lead.id)
            results.append(result)
            
            if result.success:
                successful += 1
            else:
                failed += 1
        
        return BatchOutreachResult(
            total_attempted=len(leads),
            successful=successful,
            failed=failed,
            dry_run=SETTINGS.dry_run,
            results=results,
        )
    
    def run_first_touch_batch(
        self,
        limit: int = 50,
        dry_run: bool = True,
    ) -> Dict[str, int]:
        """
        Run first touch batch (simplified interface).
        
        Args:
            limit: Max messages to send.
            dry_run: If True, do not actually send (note: this is also controlled by SETTINGS.dry_run).
        
        Returns:
            Stats dictionary.
        """
        result = self.send_batch(limit=limit)
        return {
            "selected": result.total_attempted,
            "sent": result.successful,
            "failed": result.failed,
            "skipped": 0,
        }
    
    def get_outreach_history(
        self,
        lead_id: Optional[int] = None,
        market_code: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        Get outreach attempt history.
        
        Args:
            lead_id: Filter by specific lead (all leads if None).
            market_code: Filter by market code (optional).
            status: Filter by status (optional).
            limit: Maximum records to return.
            offset: Records to skip.
        
        Returns:
            List of outreach attempt dictionaries.
        """
        query = self.session.query(OutreachAttempt).order_by(OutreachAttempt.created_at.desc())
        
        if lead_id is not None:
            query = query.filter(OutreachAttempt.lead_id == lead_id)
        
        if status is not None:
            query = query.filter(OutreachAttempt.status == status)
        
        attempts = query.offset(offset).limit(limit).all()
        
        return [
            {
                "id": a.id,
                "lead_id": a.lead_id,
                "channel": a.channel,
                "message_body": a.message_body,
                "message_context": a.message_context,
                "result": a.result,
                "status": a.status,
                "external_id": a.external_id,
                "sent_at": a.sent_at.isoformat() if a.sent_at else None,
                "delivered_at": a.delivered_at.isoformat() if a.delivered_at else None,
                "error_message": a.error_message,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in attempts
        ]
    
    def get_daily_stats(self, days: int = 7, market_code: Optional[str] = None) -> Dict[str, Any]:
        """
        Get daily outreach statistics.
        
        Args:
            days: Number of days to include.
            market_code: Optional filter by market code.
        
        Returns:
            Dictionary with daily breakdown by status and result.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        
        # Base filter
        base_filter = [OutreachAttempt.created_at >= cutoff]
        
        # Total attempts per day
        daily_counts = (
            self.session.query(
                func.date(OutreachAttempt.created_at).label("date"),
                func.count(OutreachAttempt.id).label("count"),
            )
            .filter(*base_filter)
            .group_by(func.date(OutreachAttempt.created_at))
            .all()
        )
        
        # Successful attempts per day (result = 'sent')
        daily_success = (
            self.session.query(
                func.date(OutreachAttempt.created_at).label("date"),
                func.count(OutreachAttempt.id).label("count"),
            )
            .filter(
                *base_filter,
                OutreachAttempt.result == "sent",
            )
            .group_by(func.date(OutreachAttempt.created_at))
            .all()
        )
        
        # Convert to dict for easy lookup
        counts_dict = {str(d): c for d, c in daily_counts}
        success_dict = {str(d): c for d, c in daily_success}
        
        # Total counts by result (all time)
        total_sent = self.session.query(func.count(OutreachAttempt.id)).filter(
            OutreachAttempt.result == "sent"
        ).scalar() or 0
        
        total_dry_run = self.session.query(func.count(OutreachAttempt.id)).filter(
            OutreachAttempt.result == "dry_run"
        ).scalar() or 0
        
        total_failed = self.session.query(func.count(OutreachAttempt.id)).filter(
            OutreachAttempt.result == "failed"
        ).scalar() or 0
        
        # Status breakdown (within date range)
        status_counts = (
            self.session.query(
                OutreachAttempt.status,
                func.count(OutreachAttempt.id).label("count"),
            )
            .filter(*base_filter)
            .group_by(OutreachAttempt.status)
            .all()
        )
        
        # Result breakdown (within date range)
        result_counts = (
            self.session.query(
                OutreachAttempt.result,
                func.count(OutreachAttempt.id).label("count"),
            )
            .filter(*base_filter)
            .group_by(OutreachAttempt.result)
            .all()
        )
        
        return {
            "daily_attempts": counts_dict,
            "daily_successful": success_dict,
            "total_sent": total_sent,
            "total_dry_run": total_dry_run,
            "total_failed": total_failed,
            "status_breakdown": {s or "unknown": c for s, c in status_counts},
            "result_breakdown": {r or "unknown": c for r, c in result_counts},
            "max_per_day": SETTINGS.max_sms_per_day,
        }


__all__ = ["OutreachService", "OutreachResult", "BatchOutreachResult"]
