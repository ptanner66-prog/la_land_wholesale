"""Idempotency service for outreach operations.

Prevents duplicate message sends by tracking idempotency keys.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from core.logging_config import get_logger
from core.models import OutreachAttempt
from core.utils import generate_idempotency_key, utcnow

LOGGER = get_logger(__name__)


class IdempotencyService:
    """
    Service for managing idempotency of outreach operations.
    
    Usage:
        key = idempotency.generate_key(lead_id, "followup", date)
        if idempotency.is_duplicate(key):
            # Already sent, skip
        else:
            # Create attempt with key, then send
    """

    def __init__(self, session: Session):
        """Initialize idempotency service."""
        self.session = session

    def generate_key(
        self,
        lead_id: int,
        context: str,
        date_key: Optional[str] = None,
    ) -> str:
        """
        Generate an idempotency key for an outreach operation.
        
        Args:
            lead_id: The lead ID.
            context: Message context (intro, followup, final).
            date_key: Optional date component (e.g., "2024-01-15").
                      If None, uses today's date.
        
        Returns:
            A 64-character hex string.
        """
        if date_key is None:
            date_key = utcnow().strftime("%Y-%m-%d")
        
        return generate_idempotency_key(lead_id, context, date_key)

    def is_duplicate(self, idempotency_key: str) -> bool:
        """
        Check if an idempotency key has already been used.
        
        Args:
            idempotency_key: The key to check.
        
        Returns:
            True if key exists (duplicate), False otherwise.
        """
        exists = self.session.query(OutreachAttempt).filter(
            OutreachAttempt.idempotency_key == idempotency_key
        ).first() is not None
        
        if exists:
            LOGGER.debug(f"Duplicate idempotency key detected: {idempotency_key}")
        
        return exists

    def get_existing_attempt(self, idempotency_key: str) -> Optional[OutreachAttempt]:
        """
        Get an existing outreach attempt by idempotency key.
        
        Args:
            idempotency_key: The key to look up.
        
        Returns:
            OutreachAttempt if found, None otherwise.
        """
        return self.session.query(OutreachAttempt).filter(
            OutreachAttempt.idempotency_key == idempotency_key
        ).first()

    def create_attempt_with_key(
        self,
        lead_id: int,
        idempotency_key: str,
        channel: str = "sms",
        context: str = "intro",
        message_body: Optional[str] = None,
    ) -> Optional[OutreachAttempt]:
        """
        Create an outreach attempt with idempotency protection.
        
        This method ensures that only one attempt can exist per key.
        
        Args:
            lead_id: The lead ID.
            idempotency_key: The idempotency key.
            channel: Communication channel.
            context: Message context.
            message_body: The message content.
        
        Returns:
            The created OutreachAttempt, or None if key already exists.
        """
        attempt = OutreachAttempt(
            lead_id=lead_id,
            idempotency_key=idempotency_key,
            channel=channel,
            message_context=context,
            message_body=message_body,
            status="pending",
            created_at=utcnow(),
        )
        
        try:
            self.session.add(attempt)
            self.session.flush()
            LOGGER.debug(f"Created outreach attempt with key {idempotency_key}")
            return attempt
        except IntegrityError:
            self.session.rollback()
            LOGGER.warning(f"Idempotency key collision: {idempotency_key}")
            return None

    def reserve_and_execute(
        self,
        lead_id: int,
        context: str,
        execute_fn,
        date_key: Optional[str] = None,
    ) -> Optional[OutreachAttempt]:
        """
        Reserve an idempotency slot and execute the send operation.
        
        This is the safest way to send messages:
        1. Generate key
        2. Create attempt (reserves the slot)
        3. Execute send
        4. Update attempt with result
        
        Args:
            lead_id: The lead ID.
            context: Message context.
            execute_fn: Function to execute, receives (attempt) and returns (success, external_id, error).
            date_key: Optional date component for key.
        
        Returns:
            The OutreachAttempt (successful or failed), or None if duplicate.
        """
        key = self.generate_key(lead_id, context, date_key)
        
        # Check for existing
        existing = self.get_existing_attempt(key)
        if existing:
            LOGGER.info(f"Duplicate send prevented for lead {lead_id}, context {context}")
            return existing
        
        # Create attempt first (reserves the slot)
        attempt = self.create_attempt_with_key(
            lead_id=lead_id,
            idempotency_key=key,
            context=context,
        )
        
        if not attempt:
            # Race condition - another process created it
            return self.get_existing_attempt(key)
        
        # Execute the send
        try:
            success, external_id, error = execute_fn(attempt)
            
            attempt.status = "sent" if success else "failed"
            attempt.external_id = external_id
            attempt.error_message = error
            attempt.sent_at = utcnow() if success else None
            
            self.session.flush()
            return attempt
            
        except Exception as e:
            attempt.status = "failed"
            attempt.error_message = str(e)
            self.session.flush()
            LOGGER.error(f"Send execution failed: {e}")
            return attempt


def get_idempotency_service(session: Session) -> IdempotencyService:
    """Get an IdempotencyService instance."""
    return IdempotencyService(session)


__all__ = [
    "IdempotencyService",
    "get_idempotency_service",
]

