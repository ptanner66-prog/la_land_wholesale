"""Automated follow-up service with idempotency and proper NULL handling."""
from __future__ import annotations

from datetime import timedelta
from typing import List, Optional, Callable, Any

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from core.config import get_settings
from core.logging_config import get_logger
from core.models import Lead, OutreachAttempt, PipelineStage, ReplyClassification
from core.utils import utcnow
from src.services.market import MarketService
from src.services.timeline import TimelineService
from src.services.idempotency import get_idempotency_service
from src.services.locking import get_send_lock_service
from src.services.outreach_validator import get_outreach_validator

LOGGER = get_logger(__name__)
SETTINGS = get_settings()


class FollowupService:
    """Service for managing automated follow-ups with proper safeguards."""

    def __init__(self, session: Session):
        """Initialize the followup service."""
        self.session = session
        self.timeline = TimelineService(session)
        self.idempotency = get_idempotency_service(session)
        self.lock_service = get_send_lock_service(session)
        self.validator = get_outreach_validator(session)

    def get_leads_due_for_followup(
        self,
        market_code: Optional[str] = None,
        limit: int = 100,
    ) -> List[Lead]:
        """
        Get leads that are due for a follow-up message.
        
        FIXED: Proper NULL handling for last_reply_classification.
        
        Args:
            market_code: Optional filter by market.
            limit: Maximum number of leads to return.
            
        Returns:
            List of leads due for followup.
        """
        now = utcnow()
        
        # FIXED: Proper handling of NULL values in last_reply_classification
        # NULL means no reply yet, which is valid for followup
        blocked_classifications = [
            ReplyClassification.NOT_INTERESTED.value,
            ReplyClassification.DEAD.value,
        ]
        
        classification_filter = or_(
            Lead.last_reply_classification.is_(None),
            ~Lead.last_reply_classification.in_(blocked_classifications),
        )
        
        query = self.session.query(Lead).filter(
            and_(
                Lead.next_followup_at <= now,
                Lead.next_followup_at.isnot(None),
                Lead.pipeline_stage != PipelineStage.HOT.value,
                classification_filter,
            )
        )
        
        if market_code:
            query = query.filter(Lead.market_code == market_code.upper())
        
        return query.order_by(Lead.next_followup_at.asc()).limit(limit).all()

    def schedule_initial_followup(self, lead: Lead) -> None:
        """
        Schedule the first followup for a newly contacted lead.
        
        Args:
            lead: The lead to schedule followup for.
        """
        market_config = MarketService.get_market(lead.market_code)
        if not market_config:
            market_config = MarketService.get_default_market()
        
        # Schedule first followup
        lead.next_followup_at = utcnow() + timedelta(days=market_config.followup_day_1)
        lead.followup_count = 0
        
        LOGGER.info(
            f"Scheduled initial followup for lead {lead.id} "
            f"on {lead.next_followup_at}"
        )

    def process_followup(
        self,
        lead: Lead,
        send_message_func: Callable[[Lead, str], Optional[OutreachAttempt]],
    ) -> Optional[OutreachAttempt]:
        """
        Process a followup for a lead with idempotency and locking.
        
        FIXED: Uses idempotency keys and send locks to prevent double-sends.
        Updates state BEFORE sending to prevent duplicates on retry.
        
        Args:
            lead: The lead to follow up with.
            send_message_func: Function to send the message.
            
        Returns:
            The OutreachAttempt if message was sent, None otherwise.
        """
        # Validate can send
        validation = self.validator.validate_can_send(lead)
        if not validation.can_send:
            LOGGER.info(f"Followup blocked for lead {lead.id}: {validation.reason}")
            return None
        
        market_config = MarketService.get_market(lead.market_code)
        if not market_config:
            market_config = MarketService.get_default_market()
        
        # Check if we've exceeded max followups
        if lead.followup_count >= market_config.max_followups:
            LOGGER.info(f"Lead {lead.id} has reached max followups ({market_config.max_followups})")
            lead.next_followup_at = None
            return None
        
        # Determine followup context
        followup_num = lead.followup_count + 1
        context = "final" if followup_num > 1 else "followup"
        
        # Generate idempotency key for today's followup
        date_key = utcnow().strftime("%Y-%m-%d")
        idem_key = self.idempotency.generate_key(lead.id, context, date_key)
        
        # Check for duplicate
        if self.idempotency.is_duplicate(idem_key):
            LOGGER.info(f"Duplicate followup prevented for lead {lead.id}")
            return self.idempotency.get_existing_attempt(idem_key)
        
        # Acquire send lock
        with self.lock_service.send_lock(lead) as acquired:
            if not acquired:
                LOGGER.warning(f"Could not acquire send lock for lead {lead.id}")
                return None
            
            # UPDATE STATE FIRST (before sending) to prevent double-sends on retry
            lead.followup_count = followup_num
            lead.last_followup_at = utcnow()
            
            # Schedule next followup if applicable
            if followup_num < market_config.max_followups:
                days_until_next = market_config.followup_day_2 - market_config.followup_day_1
                lead.next_followup_at = utcnow() + timedelta(days=days_until_next)
            else:
                lead.next_followup_at = None
            
            # Flush state update before external call
            self.session.flush()
            
            # Send the message
            try:
                attempt = send_message_func(lead, context)
                
                if attempt:
                    # Update idempotency key on the attempt
                    attempt.idempotency_key = idem_key
                    self.session.flush()
                    
                    LOGGER.info(f"Sent followup #{followup_num} for lead {lead.id}")
                    return attempt
                else:
                    LOGGER.warning(f"Send function returned None for lead {lead.id}")
                    return None
                    
            except Exception as e:
                LOGGER.error(f"Failed to send followup for lead {lead.id}: {e}")
                # State is already updated, which is intentional to prevent retry loops
                return None

    def run_followups(
        self,
        market_code: Optional[str] = None,
        send_message_func: Optional[Callable] = None,
        dry_run: bool = False,
        limit: int = 50,
    ) -> dict:
        """
        Run followups for all due leads.
        
        Args:
            market_code: Optional filter by market.
            send_message_func: Function to send messages.
            dry_run: If True, don't actually send messages.
            limit: Maximum number of followups to process.
            
        Returns:
            Dict with results summary.
        """
        leads = self.get_leads_due_for_followup(market_code=market_code, limit=limit)
        
        results = {
            "total_due": len(leads),
            "sent": 0,
            "skipped": 0,
            "failed": 0,
            "blocked": 0,
            "dry_run": dry_run,
        }
        
        for lead in leads:
            # Validate before processing
            validation = self.validator.validate_can_send(lead)
            if not validation.can_send:
                results["blocked"] += 1
                LOGGER.debug(f"Lead {lead.id} blocked: {validation.reason}")
                continue
            
            if dry_run:
                LOGGER.info(f"[DRY RUN] Would send followup to lead {lead.id}")
                results["skipped"] += 1
                continue
            
            if send_message_func:
                attempt = self.process_followup(lead, send_message_func)
                if attempt and attempt.status == "sent":
                    results["sent"] += 1
                elif attempt:
                    results["failed"] += 1
                else:
                    results["skipped"] += 1
            else:
                results["skipped"] += 1
        
        LOGGER.info(f"Followup run complete: {results}")
        return results


def get_followup_service(session: Session) -> FollowupService:
    """Get a FollowupService instance."""
    return FollowupService(session)


__all__ = [
    "FollowupService",
    "get_followup_service",
]
