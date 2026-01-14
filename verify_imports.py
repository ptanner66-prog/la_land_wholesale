#!/usr/bin/env python
"""Verify all imports work correctly."""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Set environment
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["DRY_RUN"] = "true"
os.environ["ENVIRONMENT"] = "local"

# Add src to path
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

def main() -> int:
    """Run import verification."""
    print("=" * 60)
    print("LA Land Wholesale - Import Verification")
    print("=" * 60)
    
    errors = []
    
    # Test core imports
    print("\n[1/6] Testing core imports...")
    try:
        from core.config import get_settings, reload_settings
        from core.db import get_engine, get_session
        from core.logging_config import setup_logging, get_logger
        from core.exceptions import (
            LALandWholesaleError,
            ExternalServiceError,
            GeocodeError,
            USPSVerificationError,
            CompsError,
            ScraperError,
            RateLimitError,
            ServiceUnavailableError,
        )
        from core.models import Party, Owner, Parcel, Lead, OutreachAttempt
        print("  ✓ core module OK")
    except Exception as e:
        errors.append(f"core: {e}")
        print(f"  ✗ core module FAILED: {e}")

    # Test services imports
    print("\n[2/6] Testing services imports...")
    try:
        from services.cache import TTLCache, cached, get_geocode_cache
        from services.retry import with_retry, RetryContext
        from services.google_maps import GoogleMapsService, geocode
        from services.usps import USPSService, verify_address
        from services.comps import CompsService, get_comps
        from services.county_scraper import CountyScraperService, scrape_recent_sales
        from services.external_data import ExternalDataService, EnrichedLeadData, EnrichmentSummary
        print("  ✓ services module OK")
    except Exception as e:
        errors.append(f"services: {e}")
        print(f"  ✗ services module FAILED: {e}")

    # Test domain imports
    print("\n[3/6] Testing domain imports...")
    try:
        from domain.leads import LeadService, LeadDetail, LeadSummary
        from domain.outreach import OutreachService
        from domain.ingestion import IngestionService
        from domain.scoring import ScoringService
        print("  ✓ domain module OK")
    except Exception as e:
        errors.append(f"domain: {e}")
        print(f"  ✗ domain module FAILED: {e}")

    # Test API imports
    print("\n[4/6] Testing API imports...")
    try:
        from api.app import create_app, app
        from api.routes import health, leads, outreach, ingestion, scoring, config
        print("  ✓ api module OK")
    except Exception as e:
        errors.append(f"api: {e}")
        print(f"  ✗ api module FAILED: {e}")

    # Test config feature flags
    print("\n[5/6] Testing config feature flags...")
    try:
        settings = reload_settings()
        assert settings.enable_google is False, "ENABLE_GOOGLE should default to False"
        assert settings.enable_usps is False, "ENABLE_USPS should default to False"
        assert settings.enable_comps is False, "ENABLE_COMPS should default to False"
        assert settings.enable_county_scraper is False, "ENABLE_COUNTY_SCRAPER should default to False"
        assert settings.is_google_enabled() is False, "is_google_enabled() should be False"
        assert settings.is_usps_enabled() is False, "is_usps_enabled() should be False"
        print("  ✓ feature flags OK")
    except AssertionError as e:
        errors.append(f"feature flags: {e}")
        print(f"  ✗ feature flags FAILED: {e}")
    except Exception as e:
        errors.append(f"feature flags: {e}")
        print(f"  ✗ feature flags FAILED: {e}")

    # Test external data service fallbacks
    print("\n[6/6] Testing external data service fallbacks...")
    try:
        service = ExternalDataService()
        result = service.enrich_address(
            address="123 Test St",
            city="Baton Rouge",
            state="LA",
            zip_code="70808",
        )
        assert result is not None, "Result should not be None"
        assert result.original_address == "123 Test St", "Original address should be preserved"
        assert result.summary is not None, "Summary should be present"
        # All services should be skipped (not failed)
        assert len(result.summary.services_failed) == 0, "No services should have failed"
        print("  ✓ external data fallbacks OK")
    except AssertionError as e:
        errors.append(f"external data fallbacks: {e}")
        print(f"  ✗ external data fallbacks FAILED: {e}")
    except Exception as e:
        errors.append(f"external data fallbacks: {e}")
        print(f"  ✗ external data fallbacks FAILED: {e}")

    # Summary
    print("\n" + "=" * 60)
    if errors:
        print(f"VERIFICATION FAILED - {len(errors)} error(s):")
        for error in errors:
            print(f"  - {error}")
        return 1
    else:
        print("ALL IMPORTS VERIFIED SUCCESSFULLY")
        print("\nYou can now run:")
        print("  cd src && python cli.py --help")
        print("  cd src && python cli.py server")
        print("  cd src && streamlit run dashboard/streamlit_app.py")
        print("  pytest -v")
        return 0


if __name__ == "__main__":
    sys.exit(main())

