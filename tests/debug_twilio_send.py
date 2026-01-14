"""
Debug script to test Twilio SMS delivery with full diagnostics.

This script sends a test SMS to a specific lead (Porter Tanner) and prints
detailed Twilio diagnostics to help debug SMS delivery issues.

Usage:
    python tests/debug_twilio_send.py
"""
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from core.config import get_settings
from core.db import get_session
from core.logging_config import get_logger
from core.models import Lead
from outreach.twilio_sender import send_first_text
from outreach.phone import normalize_phone_e164, validate_phone_for_sms

LOGGER = get_logger(__name__)
SETTINGS = get_settings()


def print_config():
    """Print current Twilio configuration."""
    print("\n" + "="*80)
    print("TWILIO CONFIGURATION")
    print("="*80)
    print(f"Account SID: {SETTINGS.twilio_account_sid[:10]}..." if SETTINGS.twilio_account_sid else "NOT SET")
    print(f"Auth Token: {'*' * 20} (configured)" if SETTINGS.twilio_auth_token else "NOT SET")
    print(f"From Number: {SETTINGS.twilio_from_number}")
    print(f"DRY_RUN: {SETTINGS.dry_run}")
    print(f"TWILIO_DEBUG: {SETTINGS.twilio_debug}")
    print("="*80 + "\n")


def validate_phone(lead_id: int):
    """Validate and print phone number details."""
    print("\n" + "="*80)
    print("PHONE NUMBER VALIDATION")
    print("="*80)
    
    with get_session() as session:
        lead = session.query(Lead).filter(Lead.id == lead_id).first()
        if not lead or not lead.owner.phone_primary:
            print("ERROR: Lead has no phone number")
            print("="*80 + "\n")
            return None
        
        phone = lead.owner.phone_primary
        print(f"Original: {phone}")
        
        e164 = normalize_phone_e164(phone)
        print(f"E.164 Format: {e164}")
        
        if e164:
            validation = validate_phone_for_sms(phone)
            print(f"Valid: {validation.is_valid}")
            print(f"Mobile: {validation.is_mobile}")
            print(f"Business: {validation.is_business}")
            if validation.error:
                print(f"Error: {validation.error}")
        else:
            print("ERROR: Could not normalize to E.164 format")
        
        print("="*80 + "\n")
        return e164


def find_porter_lead():
    """Find Porter Tanner's lead."""
    print("\n" + "="*80)
    print("FINDING PORTER TANNER LEAD")
    print("="*80)
    
    with get_session() as session:
        # Try to find lead with ID 472159 (from earlier logs)
        from core.models import Owner, Party
        lead = (
            session.query(Lead)
            .join(Lead.owner)
            .join(Owner.party)
            .filter(Lead.id == 472159)
            .first()
        )
        
        if not lead:
            # Try to find by owner name
            lead = (
                session.query(Lead)
                .join(Lead.owner)
                .join(Owner.party)
                .filter(Party.display_name.ilike("%porter%"))
                .first()
            )
        
        if lead:
            # Access all attributes within the session before returning
            lead_id = lead.id
            owner_name = lead.owner.party.display_name
            phone = lead.owner.phone_primary
            tcpa_safe = lead.owner.is_tcpa_safe
            parish = lead.parcel.parish
            address = lead.parcel.situs_address
            
            print(f"✓ Found lead ID: {lead_id}")
            print(f"  Owner: {owner_name}")
            print(f"  Phone: {phone}")
            print(f"  TCPA Safe: {tcpa_safe}")
            print(f"  Parish: {parish}")
            print(f"  Address: {address}")
            
            print("="*80 + "\n")
            return lead_id  # Return just the ID, we'll re-query it later
        else:
            print("✗ Could not find Porter Tanner lead")
            print("\nSearching for any lead with a phone number...")
            lead = (
                session.query(Lead)
                .join(Lead.owner)
                .filter(Owner.phone_primary.isnot(None))
                .filter(Owner.is_tcpa_safe == True)
                .first()
            )
            if lead:
                lead_id = lead.id
                owner_name = lead.owner.party.display_name
                phone = lead.owner.phone_primary
                print(f"✓ Found alternative lead ID: {lead_id}")
                print(f"  Owner: {owner_name}")
                print(f"  Phone: {phone}")
                print("="*80 + "\n")
                return lead_id
        
        print("="*80 + "\n")
        return None


def send_test_sms(lead_id: int):
    """Send a test SMS to the lead."""
    print("\n" + "="*80)
    print("SENDING TEST SMS")
    print("="*80)
    
    try:
        with get_session() as session:
            # Query lead in this session
            lead = session.query(Lead).filter(Lead.id == lead_id).first()
            
            if not lead:
                print(f"✗ ERROR: Lead {lead_id} not found")
                return None
            
            test_message = (
                f"[TEST] Hi {lead.owner.party.display_name}, "
                f"this is a test message from LA Land Wholesale. "
                f"Reply STOP to unsubscribe."
            )
            
            print(f"Test message: {test_message}")
            print(f"Length: {len(test_message)} characters")
            print("\nAttempting to send...\n")
            
            attempt = send_first_text(
                session=session,
                lead=lead,
                force=False,  # Respect TCPA checks
                message_body=test_message,
            )
            
            # Access all attributes within the session before returning
            attempt_result = attempt.result
            attempt_status = attempt.status
            attempt_sid = attempt.external_id
            attempt_error = attempt.error_message
            attempt_sent_at = attempt.sent_at
            
            print("\n" + "-"*80)
            print("SEND RESULT")
            print("-"*80)
            print(f"Status: {attempt_status}")
            print(f"Result: {attempt_result}")
            print(f"External ID (SID): {attempt_sid}")
            print(f"Error: {attempt_error or 'None'}")
            print(f"Sent At: {attempt_sent_at}")
            print("-"*80)
            
            if attempt_result == "sent":
                print("\n✓ SUCCESS: Message sent successfully!")
                print(f"  Twilio SID: {attempt_sid}")
                print(f"  Check Twilio console: https://console.twilio.com/us1/monitor/logs/sms")
            else:
                print(f"\n✗ FAILED: Message not sent")
                print(f"  Reason: {attempt_result}")
                if attempt_error:
                    print(f"  Error: {attempt_error}")
            
            # Return a dict instead of the detached object
            return {
                "result": attempt_result,
                "status": attempt_status,
                "external_id": attempt_sid,
                "error_message": attempt_error,
                "sent_at": attempt_sent_at,
            }
            
    except Exception as e:
        print("\n" + "-"*80)
        print("EXCEPTION OCCURRED")
        print("-"*80)
        print(f"Type: {type(e).__name__}")
        print(f"Message: {str(e)}")
        print("-"*80)
        import traceback
        traceback.print_exc()
        return None


def main():
    """Run the debug script."""
    print("\n" + "#"*80)
    print("# TWILIO SMS DEBUG SCRIPT")
    print("#"*80)
    
    # 1. Print configuration
    print_config()
    
    # 2. Find Porter's lead
    lead_id = find_porter_lead()
    
    if not lead_id:
        print("\n✗ ERROR: Could not find a suitable lead to test with")
        sys.exit(1)
    
    # 3. Validate phone number
    e164 = validate_phone(lead_id)
    if not e164:
        print("\n✗ ERROR: Phone number is invalid")
        sys.exit(1)
    
    # 4. Send test SMS
    attempt = send_test_sms(lead_id)
    
    # 5. Print summary
    print("\n" + "#"*80)
    print("# TEST COMPLETE")
    print("#"*80)
    
    if attempt and attempt.get("result") == "sent":
        print("\n✓ Test completed successfully!")
        print("\nNext steps:")
        print("1. Check your phone for the test message")
        print("2. Check Twilio console: https://console.twilio.com/us1/monitor/logs/sms")
        print(f"3. Search for SID: {attempt['external_id']}")
        sys.exit(0)
    else:
        print("\n✗ Test failed - see errors above")
        print("\nTroubleshooting:")
        print("1. Verify TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN in .env")
        print("2. Verify TWILIO_FROM_NUMBER is correct and SMS-enabled")
        print("3. If using trial account, verify recipient number in Twilio console")
        print("4. Check Twilio account balance and status")
        print("5. Enable TWILIO_DEBUG=true in .env for more details")
        sys.exit(1)


if __name__ == "__main__":
    main()

