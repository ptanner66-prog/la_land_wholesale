"""Quick Twilio diagnostic."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from twilio.rest import Client
from core.config import get_settings

SETTINGS = get_settings()

client = Client(SETTINGS.twilio_account_sid, SETTINGS.twilio_auth_token)

# Check account
account = client.api.accounts(SETTINGS.twilio_account_sid).fetch()
print(f"Account Status: {account.status}")
print(f"Account Type: {account.type}")

# Check from number
try:
    from_num = client.incoming_phone_numbers.list(phone_number=SETTINGS.twilio_from_number)
    if from_num:
        print(f"From Number: {SETTINGS.twilio_from_number}")
        print(f"SMS Capable: {from_num[0].capabilities.get('sms', False)}")
        print(f"Voice Capable: {from_num[0].capabilities.get('voice', False)}")
    else:
        print(f"ERROR: From number {SETTINGS.twilio_from_number} not found in account")
except Exception as e:
    print(f"ERROR checking from number: {e}")

# Check last message
try:
    msg = client.messages("SMec9763cc4ccea8c3396f8206d49f3ec0").fetch()
    print(f"\nLast Message (SMec9763...):")
    print(f"  Status: {msg.status}")
    print(f"  To: {msg.to}")
    print(f"  From: {msg.from_}")
    print(f"  Error Code: {msg.error_code}")
    print(f"  Error Message: {msg.error_message}")
    print(f"  Date Created: {msg.date_created}")
    print(f"  Date Sent: {msg.date_sent}")
    print(f"  Date Updated: {msg.date_updated}")
except Exception as e:
    print(f"ERROR fetching message: {e}")

