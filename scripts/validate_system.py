#!/usr/bin/env python3
"""
System Validation Script for LA Land Wholesale Platform.

Run this script to verify the system is operational:
    python scripts/validate_system.py

Options:
    --quick     Skip slow tests (outreach, scoring)
    --verbose   Show more details

Exit codes:
    0 = All checks passed
    1 = One or more checks failed
"""
from __future__ import annotations

import os
import sys
import argparse
from pathlib import Path
from typing import Dict, Any, List, Tuple

# Ensure src/ is in path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

# Track results
RESULTS: List[Tuple[str, bool, str]] = []
VERBOSE = False


def check(name: str, passed: bool, message: str = "") -> bool:
    """Record a check result."""
    status = "✅ PASS" if passed else "❌ FAIL"
    RESULTS.append((name, passed, message))
    print(f"{status}: {name}")
    if message:
        if not passed or VERBOSE:
            print(f"       {message}")
    return passed


def main() -> int:
    """Run all system validation checks."""
    global VERBOSE
    
    parser = argparse.ArgumentParser(description="LA Land Wholesale System Validation")
    parser.add_argument("--quick", action="store_true", help="Skip slow tests")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show more details")
    args = parser.parse_args()
    
    VERBOSE = args.verbose
    quick_mode = args.quick
    
    print("=" * 60)
    print("LA LAND WHOLESALE - SYSTEM VALIDATION")
    if quick_mode:
        print("(Quick mode - skipping slow tests)")
    print("=" * 60)
    print()

    all_passed = True

    # -------------------------------------------------------------------------
    # 1. Check imports
    # -------------------------------------------------------------------------
    print("--- IMPORT CHECKS ---")
    try:
        from core.config import get_settings, PROJECT_ROOT as PR, DATABASE_FILE
        check("Import core.config", True)
        print(f"       PROJECT_ROOT: {PR}")
        print(f"       DATABASE_FILE: {DATABASE_FILE}")
    except Exception as e:
        check("Import core.config", False, str(e))
        all_passed = False

    try:
        from core.db import get_session, validate_database, engine, REQUIRED_TABLES
        check("Import core.db", True)
    except Exception as e:
        check("Import core.db", False, str(e))
        all_passed = False

    try:
        from core.models import Lead, Owner, Parcel, Party, OutreachAttempt
        check("Import core.models", True)
    except Exception as e:
        check("Import core.models", False, str(e))
        all_passed = False

    try:
        from domain.outreach import OutreachService, OutreachResult
        check("Import domain.outreach", True)
    except Exception as e:
        check("Import domain.outreach", False, str(e))
        all_passed = False

    try:
        from services.alerts import process_hot_lead_alerts
        check("Import services.alerts", True)
    except Exception as e:
        check("Import services.alerts", False, str(e))
        all_passed = False

    try:
        from llm.client import LLMClient
        check("Import llm.client", True)
    except Exception as e:
        check("Import llm.client", False, str(e))
        all_passed = False

    print()

    # -------------------------------------------------------------------------
    # 2. Check database
    # -------------------------------------------------------------------------
    print("--- DATABASE CHECKS ---")
    try:
        from core.db import validate_database, engine
        from core.config import get_settings
        
        settings = get_settings()
        db_url = settings.database_url
        check("Database URL configured", bool(db_url), db_url[:50] + "..." if len(db_url) > 50 else db_url)
        
        # Validate database
        db_result = validate_database()
        check(
            "Database connection",
            db_result["status"] in ("ok", "missing_tables"),
            f"Status: {db_result['status']}"
        )
        
        if db_result["tables_found"]:
            print(f"       Tables found: {len(db_result['tables_found'])}")
            for t in db_result["tables_found"][:10]:
                print(f"         - {t}")
            if len(db_result["tables_found"]) > 10:
                print(f"         ... and {len(db_result['tables_found']) - 10} more")
        
        if db_result["tables_missing"]:
            check("Required tables present", False, f"Missing: {db_result['tables_missing']}")
            all_passed = False
        else:
            check("Required tables present", True)
            
    except Exception as e:
        check("Database validation", False, str(e))
        all_passed = False

    print()

    # -------------------------------------------------------------------------
    # 3. Check data counts
    # -------------------------------------------------------------------------
    print("--- DATA COUNTS ---")
    try:
        from core.db import get_session
        from core.models import Lead, Owner, Parcel, Party
        
        with get_session() as session:
            lead_count = session.query(Lead).count()
            owner_count = session.query(Owner).count()
            parcel_count = session.query(Parcel).count()
            party_count = session.query(Party).count()
            
            check("Leads exist", lead_count > 0, f"Count: {lead_count:,}")
            check("Owners exist", owner_count > 0, f"Count: {owner_count:,}")
            check("Parcels exist", parcel_count > 0, f"Count: {parcel_count:,}")
            check("Parties exist", party_count > 0, f"Count: {party_count:,}")
            
            if lead_count == 0:
                all_passed = False
                
    except Exception as e:
        check("Data counts", False, str(e))
        all_passed = False

    print()

    # -------------------------------------------------------------------------
    # 4. Check lead query
    # -------------------------------------------------------------------------
    print("--- LEAD QUERY TEST ---")
    try:
        from core.db import get_session
        from core.models import Lead
        
        with get_session() as session:
            # Simple query
            lead = session.query(Lead).first()
            if lead:
                check("Lead query", True, f"Lead ID: {lead.id}")
                print(f"       Owner ID: {lead.owner_id}")
                print(f"       Parcel ID: {lead.parcel_id}")
                print(f"       Score: {lead.motivation_score}")
                print(f"       Stage: {lead.pipeline_stage}")
            else:
                check("Lead query", False, "No leads found in database")
                all_passed = False
                
    except Exception as e:
        check("Lead query", False, str(e))
        all_passed = False

    print()

    # -------------------------------------------------------------------------
    # 5. Check alerts service
    # -------------------------------------------------------------------------
    print("--- ALERTS SERVICE TEST ---")
    try:
        from core.db import get_session
        from services.alerts import process_hot_lead_alerts
        
        with get_session() as session:
            result = process_hot_lead_alerts(session, dry_run=True)
            check(
                "Alerts service",
                result.get("status") == "success",
                f"Hot leads: {result.get('total_hot_leads', 0)}"
            )
            
    except Exception as e:
        check("Alerts service", False, str(e))
        all_passed = False

    print()

    # -------------------------------------------------------------------------
    # 6. Check LLM client
    # -------------------------------------------------------------------------
    print("--- LLM CLIENT TEST ---")
    try:
        from llm.client import LLMClient
        
        client = LLMClient()
        check("LLM client initialized", True, f"Provider: {client.provider}")
        check("LLM available", client.is_available(), f"Model: {client.model}")
        
        if not client.is_available():
            print("       WARNING: No LLM configured - AI features will use fallback templates")
            
    except Exception as e:
        check("LLM client", False, str(e))
        # LLM not being available is not a critical failure
        print("       WARNING: LLM initialization failed - AI features will use fallback templates")

    print()

    # -------------------------------------------------------------------------
    # 7. Check outreach service (dry-run)
    # -------------------------------------------------------------------------
    print("--- OUTREACH SERVICE TEST ---")
    try:
        from core.db import get_session
        from core.models import Lead
        from domain.outreach import OutreachService
        from core.config import get_settings
        
        settings = get_settings()
        check("DRY_RUN mode", settings.dry_run, f"DRY_RUN={settings.dry_run}")
        
        if not settings.dry_run:
            print("       ⚠️  WARNING: DRY_RUN=false - Real SMS will be sent!")
        
        with get_session() as session:
            service = OutreachService(session)
            check("OutreachService initialized", True)
            
    except Exception as e:
        check("Outreach service", False, str(e))
        all_passed = False

    print()

    # -------------------------------------------------------------------------
    # 8. Check external services config (informational - not critical)
    # -------------------------------------------------------------------------
    print("--- EXTERNAL SERVICES ---")
    try:
        from core.config import get_settings
        
        settings = get_settings()
        
        check("Twilio configured", settings.is_twilio_enabled(), 
              f"SID: {settings.twilio_account_sid[:10]}..." if settings.twilio_account_sid else "Not configured")
        
        check("OpenAI configured", settings.is_openai_enabled(),
              f"Key: {settings.openai_api_key[:10]}..." if settings.openai_api_key else "Not configured")
        
        # Google Maps is optional - just informational
        google_status = "Enabled" if settings.is_google_enabled() else "Not configured (optional)"
        print(f"ℹ️  INFO: Google Maps: {google_status}")
        
        # DRY_RUN status
        if settings.dry_run:
            print(f"ℹ️  INFO: DRY_RUN=true - SMS will NOT be sent")
        else:
            print(f"⚠️  WARNING: DRY_RUN=false - LIVE SMS MODE!")
              
    except Exception as e:
        check("External services config", False, str(e))

    print()

    # -------------------------------------------------------------------------
    # 9. Test API endpoints (if not quick mode)
    # -------------------------------------------------------------------------
    if not quick_mode:
        print("--- API ENDPOINT TESTS ---")
        try:
            import httpx
            
            base_url = "http://127.0.0.1:8001"
            
            # Health check
            try:
                resp = httpx.get(f"{base_url}/", timeout=5)
                check("API Health endpoint", resp.status_code == 200, f"Status: {resp.status_code}")
            except Exception as e:
                check("API Health endpoint", False, f"Server not running? {e}")
                print("       ⚠️  Start the backend with: python -m uvicorn src.api.app:app --port 8001")
            
            # Leads endpoint
            try:
                resp = httpx.get(f"{base_url}/leads?limit=5", timeout=10)
                check("API Leads endpoint", resp.status_code == 200, f"Status: {resp.status_code}")
            except Exception as e:
                check("API Leads endpoint", False, str(e))
            
            # Automation status endpoint
            try:
                resp = httpx.get(f"{base_url}/automation/alerts", timeout=10)
                check("API Alerts endpoint", resp.status_code == 200, f"Status: {resp.status_code}")
            except Exception as e:
                check("API Alerts endpoint", False, str(e))
                
        except ImportError:
            print("       ⚠️  httpx not installed - skipping API tests")
    else:
        print("--- API ENDPOINT TESTS (skipped in quick mode) ---")

    print()

    # -------------------------------------------------------------------------
    # Summary
    # -------------------------------------------------------------------------
    print("=" * 60)
    passed_count = sum(1 for _, passed, _ in RESULTS if passed)
    failed_count = sum(1 for _, passed, _ in RESULTS if not passed)
    
    print(f"SUMMARY: {passed_count} passed, {failed_count} failed")
    
    if all_passed and failed_count == 0:
        print("✅ SYSTEM VALIDATION PASSED")
        print("=" * 60)
        return 0
    else:
        print("❌ SYSTEM VALIDATION FAILED")
        print()
        print("Failed checks:")
        for name, passed, msg in RESULTS:
            if not passed:
                print(f"  - {name}: {msg}")
        print("=" * 60)
        return 1


if __name__ == "__main__":
    sys.exit(main())
