"""Centralized outreach validation service.

This service provides a global guard for ALL outbound message operations.
It must be used before any SMS/email send to ensure compliance.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from core.logging_config import get_logger
from core.models import Lead, Owner, ReplyClassification
from core.utils import utcnow

LOGGER = get_logger(__name__)


@dataclass
class ValidationResult:
    """Result of send validation check."""
    
    can_send: bool
    reason: Optional[str] = None
    error_code: Optional[str] = None
    
    def to_dict(self) -> dict:
        return {
            "can_send": self.can_send,
            "reason": self.reason,
            "error_code": self.error_code,
        }


class OutreachValidationError(Exception):
    """Exception raised when outreach validation fails."""
    
    def __init__(self, message: str, error_code: str):
        super().__init__(message)
        self.message = message
        self.error_code = error_code


class OutreachValidator:
    """
    Centralized validator for all outbound message operations.
    
    CRITICAL: This validator must be called before ANY message send operation.
    It enforces TCPA compliance and opt-out rules.
    """

    # Classification values that block further outreach
    BLOCKED_CLASSIFICATIONS = [
        ReplyClassification.DEAD.value,
        ReplyClassification.NOT_INTERESTED.value,
    ]

    def __init__(self, session: Session):
        """Initialize validator with database session."""
        self.session = session

    def validate_can_send(self, lead: Lead, force: bool = False) -> ValidationResult:
        """
        Validate whether a message can be sent to a lead.
        
        This is the main entry point for all outreach validation.
        
        Args:
            lead: The lead to validate.
            force: If True, bypass some checks (NOT opt-out or DNC).
            
        Returns:
            ValidationResult indicating whether send is allowed.
        """
        owner = lead.owner
        
        # CRITICAL: Never bypass opt-out check
        if owner.opt_out:
            LOGGER.warning(f"Send blocked: Owner {owner.id} has opted out")
            return ValidationResult(
                can_send=False,
                reason="Owner has opted out of communications",
                error_code="OPT_OUT",
            )
        
        # CRITICAL: Never bypass DNC check
        if owner.is_dnr:
            LOGGER.warning(f"Send blocked: Owner {owner.id} is on Do Not Reach list")
            return ValidationResult(
                can_send=False,
                reason="Owner is on Do Not Reach list",
                error_code="DNC",
            )
        
        # Check for DEAD/NOT_INTERESTED classification
        if lead.last_reply_classification in self.BLOCKED_CLASSIFICATIONS:
            if not force:
                LOGGER.warning(
                    f"Send blocked: Lead {lead.id} has classification {lead.last_reply_classification}"
                )
                return ValidationResult(
                    can_send=False,
                    reason=f"Lead classified as {lead.last_reply_classification}",
                    error_code="BLOCKED_CLASSIFICATION",
                )
            LOGGER.info(f"Force bypass for blocked classification on lead {lead.id}")
        
        # Check for valid phone number
        if not owner.phone_primary:
            return ValidationResult(
                can_send=False,
                reason="Owner has no phone number",
                error_code="NO_PHONE",
            )
        
        # All checks passed
        return ValidationResult(can_send=True)

    def validate_can_send_by_id(self, lead_id: int, force: bool = False) -> Tuple[ValidationResult, Optional[Lead]]:
        """
        Validate by lead ID and return the lead if valid.
        
        Args:
            lead_id: The lead ID to validate.
            force: If True, bypass some checks.
            
        Returns:
            Tuple of (ValidationResult, Lead or None).
        """
        lead = self.session.query(Lead).filter(Lead.id == lead_id).first()
        
        if not lead:
            return ValidationResult(
                can_send=False,
                reason="Lead not found",
                error_code="NOT_FOUND",
            ), None
        
        result = self.validate_can_send(lead, force=force)
        return result, lead if result.can_send else None

    def validate_and_raise(self, lead: Lead, force: bool = False) -> None:
        """
        Validate and raise exception if send is not allowed.
        
        Args:
            lead: The lead to validate.
            force: If True, bypass some checks.
            
        Raises:
            OutreachValidationError: If send is not allowed.
        """
        result = self.validate_can_send(lead, force=force)
        if not result.can_send:
            raise OutreachValidationError(result.reason, result.error_code)

    def mark_opted_out(self, owner: Owner, reason: str = "User requested") -> None:
        """
        Mark an owner as opted out.
        
        Args:
            owner: The owner to mark.
            reason: Reason for opt-out.
        """
        owner.opt_out = True
        owner.opt_out_at = utcnow()
        self.session.flush()
        LOGGER.info(f"Owner {owner.id} marked as opted out: {reason}")

    def mark_dnc(self, owner: Owner, reason: str = "Added to DNC list") -> None:
        """
        Mark an owner as Do Not Contact.
        
        Args:
            owner: The owner to mark.
            reason: Reason for DNC.
        """
        owner.is_dnr = True
        self.session.flush()
        LOGGER.info(f"Owner {owner.id} marked as DNC: {reason}")


def get_outreach_validator(session: Session) -> OutreachValidator:
    """Get an OutreachValidator instance."""
    return OutreachValidator(session)


__all__ = [
    "OutreachValidator",
    "OutreachValidationError",
    "ValidationResult",
    "get_outreach_validator",
]

