# Switch Back to DRY_RUN Mode

## Current Status
✅ **LIVE MODE CONFIRMED** - Real SMS messages are being sent!

**Evidence:**
- 3 real SMS messages sent successfully:
  - `SM80737675f83046095e27db5aded4c080` (Test #1 via script)
  - `SM8a9051de98512de747c7d4e32ae081d3` (Test #2 via script)
  - `SMec9763cc4ccea8c3396f8206d49f3ec0` (Test via API)
- All sent to Porter Tanner: `+12253178727`
- Twilio returned HTTP 201 with valid SIDs
- Status: `queued` → messages accepted by Twilio

## ⚠️ To Return to Safe Mode

### Step 1: Update `.env`
```bash
# Change this line:
DRY_RUN=false

# To this:
DRY_RUN=true
```

### Step 2: Restart Backend
```bash
taskkill /F /IM python.exe
python -m uvicorn src.api.app:app --host 0.0.0.0 --port 8001 --reload
```

### Step 3: Verify DRY_RUN Mode
Check startup logs for:
```
DRY_RUN mode enabled - No real SMS will be sent
```

Instead of:
```
!!! LIVE MODE !!! DRY_RUN=false - Real SMS will be sent!
```

### Step 4: Test DRY_RUN
```bash
python tests/debug_twilio_send.py
```

Should show:
```
Status: dry_run
Result: dry_run
External ID (SID): dry_run
```

## Optional: Disable Debug Logging

If you want to reduce log verbosity:

### Update `.env`
```bash
TWILIO_DEBUG=false
```

### Restart Backend
Same as Step 2 above.

## When to Use Each Mode

### DRY_RUN=true (Safe Mode) ✅ Recommended for:
- Development
- Testing
- Demos
- Debugging code changes
- Staging environments

### DRY_RUN=false (Live Mode) ⚠️ Only for:
- Production outreach
- Real customer contact
- Final testing before launch
- When you INTEND to send real SMS

## Quick Commands

### Check Current Mode
```bash
# PowerShell
Get-Content .env | Select-String "DRY_RUN"

# Bash
grep "DRY_RUN" .env
```

### Switch to DRY_RUN
```bash
# PowerShell
(Get-Content .env) -replace 'DRY_RUN=false', 'DRY_RUN=true' | Set-Content .env

# Bash
sed -i 's/DRY_RUN=false/DRY_RUN=true/' .env
```

### Switch to LIVE
```bash
# PowerShell
(Get-Content .env) -replace 'DRY_RUN=true', 'DRY_RUN=false' | Set-Content .env

# Bash
sed -i 's/DRY_RUN=true/DRY_RUN=false/' .env
```

## Safety Checklist

Before going LIVE in production:
- [ ] Verify Twilio account is upgraded (not trial)
- [ ] Verify sufficient Twilio balance
- [ ] Confirm all recipients are TCPA compliant
- [ ] Set up DNC scrubbing
- [ ] Set up litigator list checking
- [ ] Test with your own phone first
- [ ] Monitor initial sends closely
- [ ] Set up Twilio webhooks for delivery status
- [ ] Have rollback plan ready

