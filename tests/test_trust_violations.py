"""
Trust Violation Regression Tests - PRODUCTION SAFETY

These tests ensure that:
1. Mailing address is NEVER used as property location
2. Maps NEVER render without verified geometry or situs
3. Offer math NEVER runs with missing acreage for per-acre calculations
4. Confidence indicators NEVER show HIGH with incomplete inputs

If any of these tests fail, the system has a CRITICAL trust violation
that could cause an operator to:
- Misidentify a property
- Quote the wrong land
- Trust the wrong map
- Believe data is authoritative when it is not
"""
import pytest
from unittest.mock import MagicMock, patch
from decimal import Decimal

# Import the modules we're testing
from core.address_utils import (
    compute_display_location,
    compute_mailing_address,
    DisplayLocation,
    MailingAddress,
    DataTrust,
    DataWarning,
    assert_property_location_not_mailing,
    assert_map_not_from_mailing,
)
from services.offer_helper import (
    compute_offer_range,
    OfferRange,
    OfferConfidence,
    DataWarning as OfferDataWarning,
    assert_offer_not_from_incomplete_data,
    assert_per_acre_not_from_missing_acreage,
)


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def mock_lead_with_situs():
    """Lead with full parcel data including situs address."""
    lead = MagicMock()
    lead.market_code = "LA"
    lead.id = 1
    
    parcel = MagicMock()
    parcel.situs_address = "123 Main St"
    parcel.city = "Baton Rouge"
    parcel.state = "LA"
    parcel.postal_code = "70801"
    parcel.parish = "East Baton Rouge"
    parcel.canonical_parcel_id = "0001234567"
    parcel.latitude = 30.4515
    parcel.longitude = -91.1871
    parcel.geom = None
    parcel.lot_size_acres = Decimal("1.5")
    parcel.land_assessed_value = Decimal("50000")
    parcel.is_adjudicated = False
    parcel.years_tax_delinquent = 0
    
    lead.parcel = parcel
    
    owner = MagicMock()
    party = MagicMock()
    party.raw_mailing_address = "456 Oak Ave, Baton Rouge, LA 70802"
    party.display_name = "John Smith"
    owner.party = party
    owner.phone_primary = "555-123-4567"
    owner.email = "john@example.com"
    owner.is_tcpa_safe = True
    
    lead.owner = owner
    
    return lead


@pytest.fixture
def mock_lead_no_situs():
    """Lead with parcel but NO situs address."""
    lead = MagicMock()
    lead.market_code = "LA"
    lead.id = 2
    
    parcel = MagicMock()
    parcel.situs_address = None  # NO SITUS
    parcel.city = None
    parcel.state = "LA"
    parcel.postal_code = None
    parcel.parish = "East Baton Rouge"
    parcel.canonical_parcel_id = "0009876543"
    parcel.latitude = None  # NO COORDINATES
    parcel.longitude = None
    parcel.geom = None
    parcel.lot_size_acres = Decimal("2.0")
    parcel.land_assessed_value = Decimal("30000")
    parcel.is_adjudicated = False
    parcel.years_tax_delinquent = 0
    
    lead.parcel = parcel
    
    owner = MagicMock()
    party = MagicMock()
    party.raw_mailing_address = "12430 Windermere Oaks Ct, Baton Rouge, LA 70810"
    party.display_name = "Jane Doe"
    owner.party = party
    owner.phone_primary = "555-987-6543"
    owner.email = None
    owner.is_tcpa_safe = True
    
    lead.owner = owner
    
    return lead


@pytest.fixture
def mock_lead_no_land_value():
    """Lead with NO assessed land value."""
    lead = MagicMock()
    lead.market_code = "LA"
    lead.id = 3
    
    parcel = MagicMock()
    parcel.situs_address = "789 Pine St"
    parcel.city = "Baton Rouge"
    parcel.state = "LA"
    parcel.postal_code = "70803"
    parcel.parish = "East Baton Rouge"
    parcel.canonical_parcel_id = "0005555555"
    parcel.latitude = 30.45
    parcel.longitude = -91.19
    parcel.geom = None
    parcel.lot_size_acres = Decimal("1.0")
    parcel.land_assessed_value = None  # NO VALUE
    parcel.is_adjudicated = False
    parcel.years_tax_delinquent = 0
    
    lead.parcel = parcel
    
    owner = MagicMock()
    party = MagicMock()
    party.raw_mailing_address = "789 Pine St, Baton Rouge, LA 70803"
    party.display_name = "Bob Wilson"
    owner.party = party
    owner.phone_primary = "555-555-5555"
    owner.email = None
    owner.is_tcpa_safe = True
    
    lead.owner = owner
    
    return lead


@pytest.fixture
def mock_lead_no_acreage():
    """Lead with land value but NO acreage."""
    lead = MagicMock()
    lead.market_code = "LA"
    lead.id = 4
    
    parcel = MagicMock()
    parcel.situs_address = "321 Elm St"
    parcel.city = "Baton Rouge"
    parcel.state = "LA"
    parcel.postal_code = "70804"
    parcel.parish = "East Baton Rouge"
    parcel.canonical_parcel_id = "0006666666"
    parcel.latitude = 30.46
    parcel.longitude = -91.20
    parcel.geom = None
    parcel.lot_size_acres = None  # NO ACREAGE
    parcel.land_assessed_value = Decimal("40000")
    parcel.is_adjudicated = False
    parcel.years_tax_delinquent = 0
    
    lead.parcel = parcel
    
    owner = MagicMock()
    party = MagicMock()
    party.raw_mailing_address = "321 Elm St, Baton Rouge, LA 70804"
    party.display_name = "Alice Brown"
    owner.party = party
    owner.phone_primary = "555-666-7777"
    owner.email = None
    owner.is_tcpa_safe = True
    
    lead.owner = owner
    
    return lead


# =============================================================================
# TEST: MAILING ADDRESS NEVER USED AS PROPERTY LOCATION
# =============================================================================

class TestMailingAddressNeverPropertyLocation:
    """
    CRITICAL: Mailing address must NEVER be promoted as property location.
    """
    
    def test_property_location_uses_situs_not_mailing(self, mock_lead_with_situs):
        """Property location should come from parcel situs, not mailing."""
        location = compute_display_location(mock_lead_with_situs)
        mailing = compute_mailing_address(mock_lead_with_situs)
        
        # Property location should have situs address
        assert location.has_situs_address is True
        assert location.address_line1 == "123 Main St"
        
        # Mailing should be different
        assert mailing.raw_address != location.address_line1
        
        # Regression guard should pass
        assert_property_location_not_mailing(location, mailing)
    
    def test_no_situs_shows_parcel_id_not_mailing(self, mock_lead_no_situs):
        """When no situs, show parcel ID - NEVER mailing address."""
        location = compute_display_location(mock_lead_no_situs)
        mailing = compute_mailing_address(mock_lead_no_situs)
        
        # Property location should NOT have situs
        assert location.has_situs_address is False
        assert location.address_line1 is None
        
        # Full address should show parcel, not mailing
        assert "Parcel" in location.full_address
        assert location.parcel_id in location.full_address
        
        # CRITICAL: Mailing address should NOT appear in property location
        assert "Windermere" not in location.full_address
        assert "12430" not in location.full_address
        
        # Regression guard should pass
        assert_property_location_not_mailing(location, mailing)
    
    def test_no_situs_warning_is_explicit(self, mock_lead_no_situs):
        """Missing situs should have explicit warning."""
        location = compute_display_location(mock_lead_no_situs)
        
        assert DataWarning.NO_SITUS_ADDRESS in location.warnings
        assert location.missing_data_message is not None
        assert "situs" in location.missing_data_message.lower()


# =============================================================================
# TEST: MAP NEVER RENDERS WITHOUT VERIFIED GEOMETRY
# =============================================================================

class TestMapNeverFromMailing:
    """
    CRITICAL: Map queries must NEVER be derived from mailing address.
    """
    
    def test_map_query_uses_coordinates_when_available(self, mock_lead_with_situs):
        """Map should use coordinates when available."""
        location = compute_display_location(mock_lead_with_situs)
        
        assert location.has_coordinates is True
        assert location.can_show_map is True
        assert "30.4515" in location.map_query
    
    def test_map_query_uses_situs_when_no_coordinates(self, mock_lead_no_situs):
        """When no coordinates, map query should be None (not mailing)."""
        # Modify to have situs but no coordinates
        mock_lead_no_situs.parcel.situs_address = "555 Test St"
        mock_lead_no_situs.parcel.latitude = None
        mock_lead_no_situs.parcel.longitude = None
        
        location = compute_display_location(mock_lead_no_situs)
        
        # Should use situs for map query
        assert location.has_situs_address is True
        assert "555 Test St" in location.map_query
        
        # CRITICAL: Mailing address should NOT be in map query
        mailing = compute_mailing_address(mock_lead_no_situs)
        assert_map_not_from_mailing(location, mailing)
    
    def test_map_query_is_none_when_no_verified_data(self, mock_lead_no_situs):
        """When no coordinates or situs, map_query should be None."""
        location = compute_display_location(mock_lead_no_situs)
        
        # No coordinates, no situs
        assert location.has_coordinates is False
        assert location.has_situs_address is False
        
        # Map query should be None - NO GUESSING
        assert location.map_query is None
        assert location.can_show_map is False
    
    def test_map_never_uses_mailing_address(self, mock_lead_no_situs):
        """Map query should NEVER contain mailing address."""
        location = compute_display_location(mock_lead_no_situs)
        mailing = compute_mailing_address(mock_lead_no_situs)
        
        # Even if map_query exists, it should never contain mailing data
        if location.map_query:
            assert "Windermere" not in location.map_query
            assert "12430" not in location.map_query
        
        # Regression guard
        assert_map_not_from_mailing(location, mailing)


# =============================================================================
# TEST: OFFER MATH NEVER WITH MISSING DATA
# =============================================================================

class TestOfferNeverWithMissingData:
    """
    CRITICAL: Offer calculations must handle missing data explicitly.
    """
    
    def test_offer_with_complete_data_is_high_confidence(self, mock_lead_with_situs):
        """Complete data should give high confidence offer."""
        offer = compute_offer_range(mock_lead_with_situs)
        
        assert offer.can_make_offer is True
        assert offer.confidence == OfferConfidence.HIGH
        assert offer.low_offer > 0
        assert offer.high_offer > offer.low_offer
        
        # Regression guard
        assert_offer_not_from_incomplete_data(offer)
    
    def test_offer_with_no_land_value_cannot_compute(self, mock_lead_no_land_value):
        """Missing land value should prevent offer computation."""
        offer = compute_offer_range(mock_lead_no_land_value)
        
        assert offer.can_make_offer is False
        assert offer.confidence == OfferConfidence.CANNOT_COMPUTE
        assert offer.low_offer == 0
        assert offer.high_offer == 0
        assert OfferDataWarning.MISSING_LAND_VALUE in offer.warnings
        assert offer.cannot_offer_reason is not None
    
    def test_offer_with_no_acreage_is_medium_confidence(self, mock_lead_no_acreage):
        """Missing acreage should reduce confidence."""
        offer = compute_offer_range(mock_lead_no_acreage)
        
        assert offer.can_make_offer is True
        assert offer.confidence in [OfferConfidence.MEDIUM, OfferConfidence.LOW]
        assert OfferDataWarning.MISSING_ACREAGE in offer.warnings
        assert offer.missing_data_summary is not None
        assert "acreage" in offer.missing_data_summary.lower()
    
    def test_per_acre_price_is_none_when_no_acreage(self, mock_lead_no_acreage):
        """Per-acre price should be None when acreage is missing."""
        offer = compute_offer_range(mock_lead_no_acreage)
        
        assert offer.price_per_acre_low is None
        assert offer.price_per_acre_high is None
        
        # Regression guard
        assert_per_acre_not_from_missing_acreage(offer)
    
    def test_per_acre_display_explains_missing_acreage(self, mock_lead_no_acreage):
        """Per-acre display should explain why it's unavailable."""
        offer = compute_offer_range(mock_lead_no_acreage)
        
        # Should have explanatory text, not just None
        assert offer.per_acre_display is not None
        assert "unavailable" in offer.per_acre_display.lower() or "missing" in offer.per_acre_display.lower()


# =============================================================================
# TEST: CONFIDENCE NEVER HIGH WITH INCOMPLETE DATA
# =============================================================================

class TestConfidenceAccurate:
    """
    CRITICAL: Confidence indicators must accurately reflect data quality.
    """
    
    def test_high_confidence_requires_all_data(self, mock_lead_with_situs):
        """HIGH confidence should only show when all data is present."""
        offer = compute_offer_range(mock_lead_with_situs)
        
        if offer.confidence == OfferConfidence.HIGH:
            # Must have all critical data
            assert offer.acreage is not None
            assert offer.land_value is not None
            assert offer.land_value > 0
            assert OfferDataWarning.ADJUDICATED_TITLE_RISK not in offer.warnings
    
    def test_adjudicated_property_not_high_confidence(self, mock_lead_with_situs):
        """Adjudicated properties should never be HIGH confidence."""
        mock_lead_with_situs.parcel.is_adjudicated = True
        
        offer = compute_offer_range(mock_lead_with_situs)
        
        assert offer.confidence != OfferConfidence.HIGH
        assert OfferDataWarning.ADJUDICATED_TITLE_RISK in offer.warnings
    
    def test_missing_acreage_not_high_confidence(self, mock_lead_no_acreage):
        """Missing acreage should never be HIGH confidence."""
        offer = compute_offer_range(mock_lead_no_acreage)
        
        assert offer.confidence != OfferConfidence.HIGH


# =============================================================================
# TEST: DATA TRUST LEVELS
# =============================================================================

class TestDataTrustLevels:
    """
    Data trust levels must be accurately reported.
    """
    
    def test_coordinates_are_verified_gis_trust(self, mock_lead_with_situs):
        """Leads with coordinates should have VERIFIED_GIS trust."""
        location = compute_display_location(mock_lead_with_situs)
        
        assert location.data_trust == DataTrust.VERIFIED_GIS
    
    def test_situs_only_is_parcel_record_trust(self, mock_lead_no_situs):
        """Leads with situs but no coordinates should have PARCEL_RECORD trust."""
        mock_lead_no_situs.parcel.situs_address = "Test Address"
        mock_lead_no_situs.parcel.latitude = None
        mock_lead_no_situs.parcel.longitude = None
        
        location = compute_display_location(mock_lead_no_situs)
        
        assert location.data_trust == DataTrust.PARCEL_RECORD
    
    def test_no_situs_no_coords_is_derived_trust(self, mock_lead_no_situs):
        """Leads with neither situs nor coordinates should have DERIVED trust."""
        location = compute_display_location(mock_lead_no_situs)
        
        assert location.data_trust == DataTrust.DERIVED
    
    def test_mailing_address_is_owner_provided_trust(self, mock_lead_with_situs):
        """Mailing address should always be OWNER_PROVIDED trust."""
        mailing = compute_mailing_address(mock_lead_with_situs)
        
        assert mailing.data_trust == DataTrust.OWNER_PROVIDED


# =============================================================================
# REGRESSION GUARD TESTS
# =============================================================================

class TestRegressionGuards:
    """
    Test that regression guards catch violations.
    """
    
    def test_guard_catches_property_from_mailing(self):
        """Regression guard should catch mailing address used as property."""
        # Create a location that looks like it came from mailing
        bad_location = DisplayLocation(
            address_line1="123 Mailing St",  # Same as mailing
            city="Baton Rouge",
            state="LA",
            postal_code="70801",
            parish="East Baton Rouge",
            parcel_id="0001234567",
            has_situs_address=False,  # But no situs flag!
        )
        
        mailing = MailingAddress(
            line1="123 Mailing St",
            city="Baton Rouge",
            state="LA",
            postal_code="70801",
        )
        
        # This should raise because address_line1 exists but has_situs_address is False
        with pytest.raises(AssertionError):
            assert_property_location_not_mailing(bad_location, mailing)
    
    def test_guard_catches_high_confidence_without_acreage(self):
        """Regression guard should catch HIGH confidence without acreage."""
        bad_offer = OfferRange(
            low_offer=10000,
            high_offer=20000,
            land_value=30000,
            acreage=None,  # Missing!
            discount_low=0.55,
            discount_high=0.70,
            confidence=OfferConfidence.HIGH,  # But claims HIGH!
            confidence_reason="Test",
        )
        
        with pytest.raises(AssertionError):
            assert_offer_not_from_incomplete_data(bad_offer)
    
    def test_guard_catches_per_acre_without_acreage(self):
        """Regression guard should catch per-acre price without acreage."""
        # Create a mock that would have per-acre prices
        bad_offer = MagicMock()
        bad_offer.acreage = None
        bad_offer.price_per_acre_low = 5000  # Should not exist!
        bad_offer.price_per_acre_high = 10000
        
        with pytest.raises(AssertionError):
            assert_per_acre_not_from_missing_acreage(bad_offer)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

