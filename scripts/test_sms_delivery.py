"""Test SMS delivery with status polling."""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from twilio.rest import Client
from core.config import get_settings
from core.db import get_session
from core.models import Lead
from outreach.twilio_sender import send_first_text

SETTINGS = get_settings()

def poll_message_status(sid: str, max_attempts: int = 24) -> None:
    """Poll Twilio for message status every 5 seconds for up to 2 minutes."""
    client = Client(SETTINGS.twilio_account_sid, SETTINGS.twilio_auth_token)
    
    print(f"\nPolling status for SID: {sid}")
    print("=" * 60)
    
    for i in range(max_attempts):
        try:
            msg = client.messages(sid).fetch()
            print(f"[{i*5}s] Status: {msg.status}", end="")
            
            if msg.error_code:
                print(f" | ERROR {msg.error_code}: {msg.error_message}")
            else:
                print()
            
            # Terminal states
            if msg.status in ["delivered", "undelivered", "failed"]:
                print("\n" + "=" * 60)
                print(f"FINAL STATUS: {msg.status}")
                if msg.error_code:
                    print(f"ERROR CODE: {msg.error_code}")
                    print(f"ERROR MESSAGE: {msg.error_message}")
                    print("\nCommon Error Codes:")
                    print("  30034 = US A2P 10DLC unregistered")
                    print("  30007 = Message blocked (spam filter)")
                    print("  30008 = Unknown destination carrier")
                    print("  21610 = Blacklisted/unsubscribed")
                else:
                    print("✓ Message delivered successfully!")
                return
            
            time.sleep(5)
        except Exception as e:
            print(f"\nError fetching status: {e}")
            return
    
    print("\n⚠ Timeout: Message still pending after 2 minutes")


def main():
    """Send test SMS and poll for delivery."""
    print("Sending test SMS to Porter Tanner...")
    
    with get_session() as session:
        lead = session.query(Lead).filter(Lead.id == 472159).first()
        if not lead:
            print("Lead 472159 not found")
            sys.exit(1)
        
        attempt = send_first_text(
            session=session,
            lead=lead,
            force=False,
            message_body="[DELIVERY TEST] Testing message delivery tracking. Reply STOP to opt out.",
        )
        
        print(f"SMS sent: {attempt.result}")
        print(f"SID: {attempt.external_id}")
        
        if attempt.external_id and attempt.external_id != "dry_run":
            poll_message_status(attempt.external_id)
        else:
            print("\nDRY_RUN mode - no polling needed")


if __name__ == "__main__":
    main()

