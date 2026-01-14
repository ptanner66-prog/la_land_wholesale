"""Outreach tools for selecting leads and sending SMS."""
from .phone import normalize_phone_e164, is_tcpa_safe, validate_phone_for_sms
from .selector import select_leads_for_first_touch
from .twilio_sender import send_first_text
from .twilio_client import TwilioClient, SMSResult, get_twilio_client

__all__ = [
    "normalize_phone_e164",
    "is_tcpa_safe",
    "validate_phone_for_sms",
    "select_leads_for_first_touch",
    "send_first_text",
    "TwilioClient",
    "SMSResult",
    "get_twilio_client",
]
