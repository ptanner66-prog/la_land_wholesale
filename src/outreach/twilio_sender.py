"""Twilio SMS sender with rate limiting and error handling."""
from __future__ import annotations

import time
from typing import Optional

from sqlalchemy.orm import Session
from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client

from core.config import get_settings
from core.exceptions import TwilioError, TCPAError
from core.logging_config import get_logger
from core.models import Lead, OutreachAttempt
from llm.text_generator import generate_first_touch_sms
from .phone import is_tcpa_safe, normalize_phone_e164

LOGGER = get_logger(__name__)
SETTINGS = get_settings()


def _get_twilio_client() -> Client:
    """Get authenticated Twilio client."""
    if not SETTINGS.twilio_account_sid or not SETTINGS.twilio_auth_token:
        raise TwilioError("Twilio credentials not configured")
    return Client(SETTINGS.twilio_account_sid, SETTINGS.twilio_auth_token)


def send_first_text(
    session: Session,
    lead: Lead,
    force: bool = False,
    message_body: Optional[str] = None,
) -> OutreachAttempt:
    """
    Send the first outreach SMS to a lead.

    Args:
        session: Database session.
        lead: The lead to contact.
        force: If True, bypass some checks (use with caution).
        message_body: Optional pre-generated message body. If None, generates via AI.

    Returns:
        Created OutreachAttempt record.

    Raises:
        TCPAError: If lead is not safe to contact.
        TwilioError: If sending fails.
    """
    owner = lead.owner
    parcel = lead.parcel
    
    # 1. TCPA Checks
    if not owner.phone_primary:
        raise TCPAError(f"Lead {lead.id} has no phone number")
        
    if not force:
        if not owner.is_tcpa_safe:
            raise TCPAError(f"Lead {lead.id} is not marked TCPA safe")
        if owner.is_dnr or owner.opt_out:
            raise TCPAError(f"Lead {lead.id} has opted out or is DNR")
            
    # 2. Normalize Phone
    to_number = normalize_phone_e164(owner.phone_primary)
    if not to_number:
        raise TCPAError(f"Lead {lead.id} has invalid phone number: {owner.phone_primary}")
        
    # 3. Generate Content (use provided message_body or generate via AI)
    if message_body is None:
        message_body = generate_first_touch_sms(
            owner_name=owner.party.display_name or owner.party.normalized_name,
            parish=parcel.parish,
            lot_size_acres=float(parcel.lot_size_acres) if parcel.lot_size_acres else None,
        )
    else:
        LOGGER.info(f"Using pre-generated message for lead {lead.id}")
    
    # 4. Send SMS via Twilio
    sid = None
    status = "pending"
    result = None
    error_msg = None
    error_code = None
    
    if SETTINGS.dry_run:
        # DRY RUN MODE - Simulate send without hitting Twilio
        LOGGER.info("[DRY RUN] Would send SMS to %s: %s", to_number, message_body[:50] + "...")
        status = "dry_run"
        result = "dry_run"
        sid = "dry_run"
    else:
        # LIVE MODE - Actually send via Twilio
        LOGGER.warning(
            "!!! LIVE SMS !!! Sending to %s from %s",
            to_number, SETTINGS.twilio_from_number
        )
        
        if SETTINGS.twilio_debug:
            LOGGER.info(
                "[Twilio Debug - PRE-SEND]\n"
                "  To: %s\n"
                "  From: %s\n"
                "  Body: %s\n"
                "  Account SID: %s",
                to_number, SETTINGS.twilio_from_number, 
                message_body[:100], SETTINGS.twilio_account_sid[:10] + "..."
            )
        
        try:
            client = _get_twilio_client()
            
            # Build status callback URL if configured
            create_params = {
                "body": message_body,
                "from_": SETTINGS.twilio_from_number,
                "to": to_number,
            }
            
            if SETTINGS.twilio_status_callback_url:
                create_params["status_callback"] = SETTINGS.twilio_status_callback_url
            
            message = client.messages.create(**create_params)
            sid = message.sid
            
            # Check the message status from Twilio response
            message_status = message.status  # queued, sending, sent, failed, delivered, undelivered
            message_error_code = message.error_code
            message_error_message = message.error_message
            
            if SETTINGS.twilio_debug:
                LOGGER.info(
                    "[Twilio Debug - POST-SEND]\n"
                    "  SID: %s\n"
                    "  Status: %s\n"
                    "  Error Code: %s\n"
                    "  Error Message: %s\n"
                    "  To: %s\n"
                    "  From: %s\n"
                    "  Price: %s\n"
                    "  Direction: %s",
                    sid, message_status, message_error_code, 
                    message_error_message, message.to, message.from_,
                    message.price, message.direction
                )
            
            # Handle different Twilio statuses
            if message_error_code:
                # Message was accepted but has an error
                error_code = message_error_code
                error_msg = message_error_message or f"Twilio error code: {message_error_code}"
                status = "failed"
                result = "twilio_error"
                LOGGER.error(
                    "Twilio accepted message but reported error. SID: %s, Code: %s, Message: %s",
                    sid, message_error_code, message_error_message
                )
            elif message_status in ["failed", "undelivered"]:
                status = "failed"
                result = "delivery_failed"
                error_msg = f"Twilio status: {message_status}"
                LOGGER.error("Message failed with status %s (SID: %s)", message_status, sid)
            elif message_status in ["queued", "accepted", "sending", "sent"]:
                status = "sent"
                result = "sent"
                LOGGER.info("SMS sent successfully to %s (SID: %s, Status: %s)", to_number, sid, message_status)
            else:
                # Unknown status - log but mark as sent
                status = "sent"
                result = "sent"
                LOGGER.warning("SMS sent with unknown status %s (SID: %s)", message_status, sid)
            
        except TwilioRestException as exc:
            error_code = exc.code if hasattr(exc, 'code') else None
            error_msg = str(exc)
            
            if SETTINGS.twilio_debug:
                LOGGER.error(
                    "[Twilio Debug - ERROR]\n"
                    "  Error Code: %s\n"
                    "  Error Message: %s\n"
                    "  Status: %s\n"
                    "  To: %s\n"
                    "  From: %s",
                    error_code, error_msg, exc.status if hasattr(exc, 'status') else 'N/A',
                    to_number, SETTINGS.twilio_from_number
                )
            
            # Handle specific Twilio errors gracefully
            if error_code == 21211:  # Invalid phone number
                LOGGER.warning("Invalid phone number %s: %s", to_number, exc)
                status = "failed"
                result = "invalid_number"
            elif error_code == 21408:  # Permission denied / Geo permissions
                LOGGER.warning("Geo permissions issue for %s: %s", to_number, exc)
                status = "failed"
                result = "geo_restricted"
            elif error_code == 21610:  # Blacklisted / Unsubscribed
                LOGGER.warning("Number blacklisted/unsubscribed %s: %s", to_number, exc)
                status = "failed"
                result = "blacklisted"
            elif error_code == 21608:  # Unverified number (trial account)
                LOGGER.warning("Unverified recipient on trial account %s: %s", to_number, exc)
                status = "failed"
                result = "unverified_recipient"
                # For trial accounts, this is critical - raise it
                raise TwilioError(
                    f"Trial account cannot send to unverified number {to_number}. "
                    f"Verify this number in Twilio console or upgrade account."
                ) from exc
            elif error_code == 21614:  # Invalid 'To' number
                LOGGER.warning("Invalid 'To' number %s: %s", to_number, exc)
                status = "failed"
                result = "invalid_to_number"
            elif error_code == 20003:  # Auth error
                LOGGER.error("Twilio authentication failed: %s", exc)
                status = "failed"
                result = "auth_error"
                raise TwilioError(f"Twilio authentication failed: {exc}") from exc
            elif error_code == 20429 or error_code == 429:  # Rate limit
                LOGGER.warning("Twilio rate limit exceeded: %s", exc)
                status = "failed"
                result = "rate_limited"
                raise TwilioError(f"Twilio rate limit exceeded: {exc}") from exc
            else:
                LOGGER.error("Twilio error sending to %s: %s (code=%s)", to_number, exc, error_code)
                status = "failed"
                result = "twilio_error"
                # For unknown errors, raise them so they can be investigated
                raise TwilioError(f"Twilio error {error_code}: {error_msg}") from exc
                
        except Exception as exc:
            LOGGER.exception("Unexpected error sending SMS to %s: %s", to_number, exc)
            status = "failed"
            result = "error"
            error_msg = str(exc)
            raise TwilioError(f"Unexpected error sending SMS: {exc}") from exc
            
    # 5. Record Attempt
    from core.utils import utcnow
    
    attempt = OutreachAttempt(
        lead_id=lead.id,
        channel="sms",
        message_body=message_body,
        message_context="intro",
        status=status,
        result=result,
        external_id=sid,
        error_message=error_msg,
        sent_at=utcnow() if status == "sent" else None,
    )
    session.add(attempt)
    
    # Update lead status and pipeline stage
    if status == "sent":
        lead.status = "contacted"
        lead.pipeline_stage = "CONTACTED"
        
    session.commit()
    return attempt
