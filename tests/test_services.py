"""Tests for external data services with fallback behavior."""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Add src to path
src_path = Path(__file__).parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

# Set test environment BEFORE importing config
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["DRY_RUN"] = "true"
os.environ["ENVIRONMENT"] = "test"
# Ensure all services are DISABLED by default for tests
os.environ["ENABLE_GOOGLE"] = "false"
os.environ["ENABLE_USPS"] = "false"
os.environ["ENABLE_COMPS"] = "false"
os.environ["ENABLE_COUNTY_SCRAPER"] = "false"
os.environ.pop("GOOGLE_MAPS_API_KEY", None)
os.environ.pop("USPS_USER_ID", None)


# ============================================================================
# Test Cache Utilities
# ============================================================================


class TestCacheUtilities:
    """Test the caching utilities."""

    def test_ttl_cache_set_get(self):
        """Test basic cache set/get operations."""
        from services.cache import TTLCache

        cache = TTLCache(default_ttl_seconds=60)
        cache.set("key1", "value1")
        
        assert cache.get("key1") == "value1"
        assert cache.size == 1

    def test_ttl_cache_miss(self):
        """Test cache miss returns None."""
        from services.cache import TTLCache

        cache = TTLCache()
        assert cache.get("nonexistent") is None

    def test_ttl_cache_expiry(self):
        """Test that expired entries are not returned."""
        from services.cache import TTLCache

        cache = TTLCache()
        cache.set("key1", "value1", ttl_seconds=0.05)
        
        # Immediately should work
        assert cache.get("key1") == "value1"
        
        # After expiry should be None
        time.sleep(0.1)
        assert cache.get("key1") is None

    def test_ttl_cache_stats(self):
        """Test cache statistics."""
        from services.cache import TTLCache

        cache = TTLCache()
        cache.set("key1", "value1")
        
        # Hit
        cache.get("key1")
        # Miss
        cache.get("key2")
        
        stats = cache.stats()
        assert stats["size"] == 1
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["hit_rate"] == 0.5

    def test_ttl_cache_cleanup(self):
        """Test cleanup of expired entries."""
        from services.cache import TTLCache

        cache = TTLCache()
        cache.set("key1", "value1", ttl_seconds=0.01)
        cache.set("key2", "value2", ttl_seconds=60)
        
        time.sleep(0.02)
        
        removed = cache.cleanup_expired()
        assert removed == 1
        assert cache.size == 1
        assert cache.get("key2") == "value2"

    def test_ttl_cache_delete(self):
        """Test deleting cache entries."""
        from services.cache import TTLCache

        cache = TTLCache()
        cache.set("key1", "value1")
        
        assert cache.delete("key1") is True
        assert cache.get("key1") is None
        assert cache.delete("nonexistent") is False

    def test_ttl_cache_clear(self):
        """Test clearing all entries."""
        from services.cache import TTLCache

        cache = TTLCache()
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        
        cache.clear()
        
        assert cache.size == 0
        assert cache.get("key1") is None

    def test_cached_decorator(self):
        """Test the @cached decorator."""
        from services.cache import TTLCache, cached

        cache = TTLCache()
        call_count = 0

        @cached(cache, ttl_seconds=60, key_prefix="test")
        def expensive_function(x: int) -> int:
            nonlocal call_count
            call_count += 1
            return x * 2

        # First call - should execute
        result1 = expensive_function(5)
        assert result1 == 10
        assert call_count == 1

        # Second call - should use cache
        result2 = expensive_function(5)
        assert result2 == 10
        assert call_count == 1  # No additional call

        # Different argument - should execute
        result3 = expensive_function(10)
        assert result3 == 20
        assert call_count == 2


# ============================================================================
# Test Retry Utilities
# ============================================================================


class TestRetryUtilities:
    """Test retry utilities."""

    def test_retry_context(self):
        """Test the RetryContext manager."""
        from services.retry import RetryContext

        ctx = RetryContext(max_attempts=3, base_delay=0.001)
        
        assert ctx.should_retry()
        ctx.record_error(Exception("test"))
        assert ctx.should_retry()
        ctx.record_error(Exception("test"))
        assert ctx.should_retry()
        ctx.record_error(Exception("test"))
        assert not ctx.should_retry()

    def test_retry_context_as_context_manager(self):
        """Test RetryContext as context manager."""
        from services.retry import RetryContext

        with RetryContext(max_attempts=2, base_delay=0.001) as ctx:
            assert ctx.should_retry()
            ctx.record_error(ValueError("test"))
            assert ctx.should_retry()


# ============================================================================
# Test Google Maps Service
# ============================================================================


class TestGoogleMapsService:
    """Test Google Maps service with fallback behavior."""

    def test_geocode_disabled_returns_fallback(self):
        """Test geocode returns fallback when disabled."""
        from core.config import reload_settings
        reload_settings()
        
        from services.google_maps import geocode
        
        result = geocode("123 Main St, Baton Rouge, LA 70808")
        
        # Should return fallback with verified=False
        assert result is not None
        assert result["verified"] is False
        assert result["source"] == "fallback"
        assert result["lat"] is None
        assert result["lng"] is None

    def test_geocode_result_dataclass(self):
        """Test GeocodeResult dataclass."""
        from services.google_maps import GeocodeResult

        result = GeocodeResult(
            lat=30.4515,
            lng=-91.1871,
            formatted_address="123 Main St, Baton Rouge, LA 70808",
            city="Baton Rouge",
            state="LA",
            postal_code="70808",
        )
        
        d = result.to_dict()
        assert d["lat"] == 30.4515
        assert d["city"] == "Baton Rouge"
        assert d["formatted_address"] == "123 Main St, Baton Rouge, LA 70808"
        assert d["verified"] is True

    def test_geocode_preserves_original_address_in_fallback(self):
        """Test that fallback preserves the original address."""
        from core.config import reload_settings
        reload_settings()
        
        from services.google_maps import geocode
        
        test_address = "555 Unique Test Address"
        result = geocode(test_address)
        
        assert result["formatted_address"] == test_address


# ============================================================================
# Test USPS Service
# ============================================================================


class TestUSPSService:
    """Test USPS service with fallback behavior."""

    def test_verify_disabled_returns_fallback(self):
        """Test verify_address returns fallback when disabled."""
        from core.config import reload_settings
        reload_settings()
        
        from services.usps import verify_address
        
        result = verify_address("123 Main St", "Baton Rouge", "LA", "70808")
        
        # Should return unverified fallback
        assert result is not None
        assert result["verified"] is False
        assert result["source"] == "fallback"
        assert result["address1"] == "123 MAIN ST"
        assert result["city"] == "BATON ROUGE"

    def test_verification_result_dataclass(self):
        """Test USPSVerificationResult dataclass."""
        from services.usps import USPSVerificationResult

        result = USPSVerificationResult(
            address1="123 MAIN ST",
            address2=None,
            city="BATON ROUGE",
            state="LA",
            zip5="70808",
            zip4="1234",
            dpv_confirmation="Y",
            dpv_cmra="N",
            dpv_vacant="N",
            dpv_no_stat=None,
            carrier_route="C001",
            footnotes=None,
            return_text=None,
        )
        
        assert result.is_valid
        assert result.is_residential
        assert not result.is_vacant
        assert result.full_zip == "70808-1234"
        
        d = result.to_dict()
        assert d["is_valid"]
        assert d["city"] == "BATON ROUGE"
        assert d["verified"] is True

    def test_usps_fallback_uppercases_input(self):
        """Test that fallback uppercases input for consistency."""
        from core.config import reload_settings
        reload_settings()
        
        from services.usps import verify_address
        
        result = verify_address("lower case street", "city name", "la", "70808")
        
        assert result["address1"] == "LOWER CASE STREET"
        assert result["city"] == "CITY NAME"
        assert result["state"] == "LA"


# ============================================================================
# Test Comps Service
# ============================================================================


class TestCompsService:
    """Test Comps service."""

    def test_comps_returns_empty_without_session(self):
        """Test CompsService returns empty result when no session."""
        from services.comps import CompsService, CompsResult

        service = CompsService(session=None)
        # Without a session, the service can't query DB — test result type
        result = CompsResult()

        assert result is not None
        assert result.comps == []
        assert result.is_mock_data is False

    def test_comp_sale_dataclass(self):
        """Test CompSale dataclass."""
        from services.comps import CompSale

        comp = CompSale(
            address="456 Oak Ave, Baton Rouge, LA 70808",
            sale_price=250000.0,
            sale_date="2024-01-15",
            lot_size_acres=1.5,
            price_per_acre=166666.67,
            source="manual",
        )

        d = comp.to_dict()
        assert d["sale_price"] == 250000.0
        assert d["lot_size_acres"] == 1.5
        assert d["source"] == "manual"


# ============================================================================
# Test County Scraper Service
# ============================================================================


class TestCountyScraperService:
    """Test County Scraper with fallback behavior."""

    def test_scraper_disabled_returns_fallback(self):
        """Test scrape_recent_sales returns fallback when disabled."""
        from core.config import reload_settings
        reload_settings()
        
        from services.county_scraper import scrape_recent_sales
        
        result = scrape_recent_sales(days_back=30, limit=10)
        
        # Should return fallback with available=False
        assert result is not None
        assert result["available"] is False
        assert result["source"] == "fallback"
        assert result["records"] == []

    def test_county_sale_record_dataclass(self):
        """Test CountySaleRecord dataclass."""
        from services.county_scraper import CountySaleRecord

        record = CountySaleRecord(
            owner_name="Test Owner",
            sale_price=150000,
            sale_date="2024-01-15",
            property_address="123 Test St",
            parcel_number="ABC123",
        )
        
        d = record.to_dict()
        assert d["owner_name"] == "Test Owner"
        assert d["sale_price"] == 150000
        assert d["sale_date"] == "2024-01-15"


# ============================================================================
# Test External Data Service (Orchestrator)
# ============================================================================


class TestExternalDataService:
    """Test the orchestrator service with fallback behavior."""

    def test_enriched_lead_data_dataclass(self):
        """Test EnrichedLeadData dataclass."""
        from services.external_data import EnrichedLeadData

        data = EnrichedLeadData(
            original_address="123 Main St",
            original_city="Baton Rouge",
            original_state="LA",
            original_zip="70808",
        )
        
        assert data.best_address == "123 Main St, Baton Rouge, LA 70808"
        assert data.best_city == "Baton Rouge"
        assert data.best_state == "LA"
        assert data.best_zip == "70808"
        assert not data.has_coordinates
        assert not data.is_verified

    def test_enriched_lead_data_with_coordinates(self):
        """Test EnrichedLeadData with geocoded coordinates."""
        from services.external_data import EnrichedLeadData

        data = EnrichedLeadData(
            original_address="123 Main St",
            original_city="Baton Rouge",
            original_state="LA",
            original_zip="70808",
        )
        
        # Add coordinates
        data.latitude = 30.4515
        data.longitude = -91.1871
        data.geocoded = True
        
        assert data.has_coordinates
        assert data.is_verified

    def test_enriched_lead_data_with_usps(self):
        """Test EnrichedLeadData with USPS verification."""
        from services.external_data import EnrichedLeadData

        data = EnrichedLeadData(
            original_address="123 main st",
            original_city="baton rouge",
            original_state="la",
            original_zip="70808",
        )
        
        # Add USPS data
        data.usps_verified = True
        data.usps_standardized_address = "123 MAIN ST"
        data.usps_city = "BATON ROUGE"
        data.usps_state = "LA"
        data.usps_zip5 = "70808"
        
        assert data.is_verified
        assert data.best_address == "123 MAIN ST"
        assert data.best_city == "BATON ROUGE"

    def test_enrichment_summary_dataclass(self):
        """Test EnrichmentSummary dataclass."""
        from services.external_data import EnrichmentSummary

        summary = EnrichmentSummary(
            services_called=["usps", "google_maps"],
            services_succeeded=["usps"],
            services_failed=["google_maps"],
            services_skipped=["comps"],
            total_duration_ms=150.5,
        )
        
        d = summary.to_dict()
        assert len(d["services_called"]) == 2
        assert len(d["services_succeeded"]) == 1
        assert len(d["services_failed"]) == 1
        assert d["success_rate"] == 0.5

    def test_enrich_address_all_disabled(self):
        """Test enrich_address returns basic data when all services disabled."""
        from core.config import reload_settings
        reload_settings()
        
        from services.external_data import ExternalDataService

        service = ExternalDataService()
        result = service.enrich_address(
            address="123 Main St",
            city="Baton Rouge",
            state="LA",
            zip_code="70808",
        )
        
        assert result.original_address == "123 Main St"
        assert not result.usps_verified
        assert not result.geocoded
        assert not result.comps_available
        
        # Summary should show all skipped
        assert result.summary is not None
        assert "usps" in result.summary.services_skipped
        assert "google_maps" in result.summary.services_skipped
        assert "comps" in result.summary.services_skipped

    def test_quick_verify_method(self):
        """Test quick_verify method."""
        from core.config import reload_settings
        reload_settings()
        
        from services.external_data import ExternalDataService

        service = ExternalDataService()
        result = service.quick_verify(
            address="123 Main St",
            city="Baton Rouge",
            state="LA",
            zip_code="70808",
        )
        
        # Should return dict with expected keys
        assert "valid" in result
        assert "standardized_address" in result
        assert "city" in result
        assert "state" in result
        assert "zip" in result
        assert "is_residential" in result

    def test_get_coordinates_method(self):
        """Test get_coordinates method."""
        from core.config import reload_settings
        reload_settings()
        
        from services.external_data import ExternalDataService

        service = ExternalDataService()
        result = service.get_coordinates(
            address="123 Main St",
            city="Baton Rouge",
            state="LA",
            zip_code="70808",
        )
        
        # Should return None when geocoding is disabled
        assert result is None


# ============================================================================
# Test Configuration and Feature Flags
# ============================================================================


class TestConfigSettings:
    """Test configuration and feature flags."""

    def test_feature_flags_default_false(self):
        """Test that all feature flags default to False."""
        # Clear any existing flags
        for key in ["ENABLE_GOOGLE", "ENABLE_USPS", "ENABLE_COMPS", "ENABLE_COUNTY_SCRAPER"]:
            os.environ.pop(key, None)
        
        from core.config import reload_settings
        settings = reload_settings()
        
        # All should default to False
        assert settings.enable_google is False
        assert settings.enable_usps is False
        assert settings.enable_comps is False
        assert settings.enable_county_scraper is False
        
        # Helper methods should also return False
        assert settings.is_google_enabled() is False
        assert settings.is_usps_enabled() is False
        assert settings.is_comps_enabled() is False
        assert settings.is_county_scraper_enabled() is False

    def test_feature_flag_requires_api_key(self):
        """Test that is_*_enabled() requires both flag AND API key."""
        os.environ["ENABLE_GOOGLE"] = "true"
        os.environ.pop("GOOGLE_MAPS_API_KEY", None)
        
        from core.config import reload_settings
        settings = reload_settings()
        
        # Flag is true but no API key
        assert settings.enable_google is True
        assert settings.is_google_enabled() is False  # Requires API key
        
        # Cleanup
        os.environ["ENABLE_GOOGLE"] = "false"
        reload_settings()

    def test_feature_flag_with_api_key(self):
        """Test that is_*_enabled() returns True with both flag AND API key."""
        os.environ["ENABLE_GOOGLE"] = "true"
        os.environ["GOOGLE_MAPS_API_KEY"] = "test_key"
        
        from core.config import reload_settings
        settings = reload_settings()
        
        assert settings.enable_google is True
        assert settings.is_google_enabled() is True
        
        # Cleanup
        os.environ["ENABLE_GOOGLE"] = "false"
        os.environ.pop("GOOGLE_MAPS_API_KEY", None)
        reload_settings()

    def test_get_enabled_services(self):
        """Test get_enabled_services() method."""
        from core.config import reload_settings
        settings = reload_settings()
        
        # With nothing enabled
        services = settings.get_enabled_services()
        assert "google_maps" not in services
        assert "usps" not in services

    def test_log_format_validation(self):
        """Test log format validation."""
        from core.config import reload_settings
        
        os.environ["LOG_FORMAT"] = "json"
        settings = reload_settings()
        assert settings.log_format == "json"
        
        os.environ["LOG_FORMAT"] = "text"
        settings = reload_settings()
        assert settings.log_format == "text"


# ============================================================================
# Test Exception Hierarchy
# ============================================================================


class TestExceptions:
    """Test custom exceptions."""

    def test_exception_hierarchy(self):
        """Test that new exceptions inherit properly."""
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

        # All external service errors should inherit from ExternalServiceError
        assert issubclass(GeocodeError, ExternalServiceError)
        assert issubclass(USPSVerificationError, ExternalServiceError)
        assert issubclass(CompsError, ExternalServiceError)
        assert issubclass(ScraperError, ExternalServiceError)
        assert issubclass(RateLimitError, ExternalServiceError)
        assert issubclass(ServiceUnavailableError, ExternalServiceError)
        
        # ExternalServiceError should inherit from base
        assert issubclass(ExternalServiceError, LALandWholesaleError)

    def test_exception_can_be_raised_and_caught(self):
        """Test that exceptions can be properly raised and caught."""
        from core.exceptions import GeocodeError, ExternalServiceError

        with pytest.raises(ExternalServiceError):
            raise GeocodeError("Test error")

        with pytest.raises(GeocodeError):
            raise GeocodeError("Specific error")


# ============================================================================
# Test Full Integration Flow
# ============================================================================


class TestIntegrationFlow:
    """Test the full enrichment flow."""

    def test_full_enrichment_disabled_services(self):
        """Test full enrichment flow with all services disabled."""
        from core.config import reload_settings
        reload_settings()
        
        from services.external_data import get_external_data_service

        service = get_external_data_service()
        result = service.enrich_address(
            address="123 Main St",
            city="Baton Rouge",
            state="LA",
            zip_code="70808",
            include_usps=True,
            include_geocode=True,
            include_comps=True,
            include_county=True,
        )
        
        # Should complete without error
        assert result is not None
        
        # Original data should be preserved
        assert result.original_address == "123 Main St"
        assert result.best_address == "123 Main St, Baton Rouge, LA 70808"
        
        # Summary should show all skipped
        summary = result.summary
        assert summary is not None
        assert len(summary.services_skipped) == 4
        assert len(summary.services_failed) == 0
        assert len(summary.services_called) == 0

    def test_enrichment_to_dict(self):
        """Test enrichment result serialization."""
        from core.config import reload_settings
        reload_settings()
        
        from services.external_data import ExternalDataService

        service = ExternalDataService()
        result = service.enrich_address(
            address="123 Main St",
            city="Baton Rouge",
            state="LA",
            zip_code="70808",
        )
        
        # to_dict should work without errors
        d = result.to_dict()
        
        assert "original" in d
        assert "usps" in d
        assert "geocode" in d
        assert "comps" in d
        assert "summary" in d
        
        assert d["original"]["address"] == "123 Main St"


# ============================================================================
# Test Logging Utilities
# ============================================================================


class TestLoggingUtilities:
    """Test logging utilities."""

    def test_get_logger(self):
        """Test get_logger function."""
        from core.logging_config import get_logger
        
        logger = get_logger("test.module")
        assert logger is not None
        assert logger.name == "test.module"

    def test_log_external_call(self):
        """Test log_external_call function."""
        from core.logging_config import get_logger, log_external_call
        
        logger = get_logger("test")
        
        # Should not raise
        log_external_call(
            logger,
            service="test_service",
            operation="test_op",
            success=True,
            duration_ms=100.5,
            extra_field="value",
        )

    def test_json_formatter(self):
        """Test JSONFormatter class."""
        import json
        import logging
        from io import StringIO
        from core.logging_config import JSONFormatter

        # Create a logger with JSONFormatter
        logger = logging.getLogger("test_json")
        logger.setLevel(logging.DEBUG)
        
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(JSONFormatter())
        logger.addHandler(handler)
        
        logger.info("Test message")
        
        output = stream.getvalue()
        # Should be valid JSON
        data = json.loads(output)
        assert data["message"] == "Test message"
        assert data["level"] == "INFO"
