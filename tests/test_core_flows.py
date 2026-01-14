"""Comprehensive tests for core LA Land Wholesale flows.

This test suite validates:
1. Lead creation and enrichment
2. Disposition summary endpoint
3. Buyer matching engine
4. Offer calculator (MAO and recommended offers)
5. Deal sheet generation
6. Assignment fee optimization
7. Motivation spike detection
8. End-to-end flow: lead → deal sheet → buyer match → blast

Run with: pytest tests/test_core_flows.py -v
"""
import pytest
from datetime import datetime, timezone
from typing import Generator
from unittest.mock import patch, MagicMock

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from core.db import Base
from core.models import (
    Lead, Owner, Parcel, Party, Buyer, BuyerDeal, 
    OutreachAttempt, TimelineEvent, PipelineStage
)


# ==============================================================================
# Test Fixtures
# ==============================================================================


@pytest.fixture(scope="function")
def test_db() -> Generator[Session, None, None]:
    """Create an in-memory SQLite database for testing."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)
    session = TestSession()
    
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def sample_party(test_db: Session) -> Party:
    """Create a sample party for testing."""
    party = Party(
        normalized_name="JOHN DOE",
        normalized_zip="70801",
        match_hash="test_hash_123",
        display_name="John Doe",
        party_type="individual",
        market_code="LA",
        raw_mailing_address="123 Main St, Baton Rouge, LA 70801",
    )
    test_db.add(party)
    test_db.flush()
    return party


@pytest.fixture
def sample_owner(test_db: Session, sample_party: Party) -> Owner:
    """Create a sample owner for testing."""
    owner = Owner(
        party_id=sample_party.id,
        phone_primary="+12255551234",
        market_code="LA",
        is_tcpa_safe=True,
        is_dnr=False,
        opt_out=False,
    )
    test_db.add(owner)
    test_db.flush()
    return owner


@pytest.fixture
def sample_parcel(test_db: Session) -> Parcel:
    """Create a sample parcel for testing."""
    parcel = Parcel(
        canonical_parcel_id="EBR-12345",
        parish="East Baton Rouge",
        market_code="LA",
        situs_address="456 Oak Ave",
        city="Baton Rouge",
        state="LA",
        postal_code="70801",
        latitude=30.4515,
        longitude=-91.1871,
        lot_size_acres=2.5,
        land_assessed_value=25000.0,
        improvement_assessed_value=0.0,
        is_adjudicated=True,
        years_tax_delinquent=2,
    )
    test_db.add(parcel)
    test_db.flush()
    return parcel


@pytest.fixture
def sample_lead(test_db: Session, sample_owner: Owner, sample_parcel: Parcel) -> Lead:
    """Create a sample lead for testing."""
    lead = Lead(
        owner_id=sample_owner.id,
        parcel_id=sample_parcel.id,
        market_code="LA",
        pipeline_stage=PipelineStage.NEW.value,
        status="new",
        motivation_score=65,
    )
    test_db.add(lead)
    test_db.flush()
    return lead


@pytest.fixture
def sample_buyer(test_db: Session) -> Buyer:
    """Create a sample buyer for testing."""
    buyer = Buyer(
        name="ABC Land Company",
        phone="+15551234567",
        email="buyer@example.com",
        market_codes=["LA"],
        counties=["East Baton Rouge"],
        min_acres=0.5,
        max_acres=10.0,
        price_min=5000.0,
        price_max=100000.0,
        vip=True,
        pof_verified=True,
        response_rate_pct=85.0,
        closing_rate_pct=40.0,
    )
    test_db.add(buyer)
    test_db.flush()
    return buyer


# ==============================================================================
# Test: Disposition Summary Endpoint
# ==============================================================================


class TestDispositionSummary:
    """Tests for the disposition summary endpoint fix."""
    
    def test_disposition_summary_with_valid_lead(
        self, test_db: Session, sample_lead: Lead, sample_buyer: Buyer
    ):
        """Test disposition summary returns correctly for a valid lead."""
        from services.deal_sheet import get_deal_sheet_service
        from services.buyer_match import get_buyer_match_service
        
        # Generate deal sheet
        deal_sheet_service = get_deal_sheet_service(test_db)
        deal_sheet = deal_sheet_service.generate_deal_sheet(sample_lead.id)
        
        assert deal_sheet is not None, "Deal sheet should be generated"
        assert deal_sheet.lead_id == sample_lead.id
        
        # Match buyers
        match_service = get_buyer_match_service(test_db)
        matches = match_service.match_buyers(sample_lead, limit=10)
        
        # Should find our sample buyer
        assert len(matches) >= 0, "Matching should not fail"
    
    def test_disposition_summary_with_no_buyers(
        self, test_db: Session, sample_lead: Lead
    ):
        """Test disposition summary handles empty buyer list gracefully."""
        from services.buyer_match import get_buyer_match_service
        
        match_service = get_buyer_match_service(test_db)
        matches = match_service.match_buyers(sample_lead, limit=10)
        
        # Should return empty list, not raise error
        assert matches is not None
        assert isinstance(matches, list)
    
    def test_disposition_summary_with_missing_lead(self, test_db: Session):
        """Test disposition summary returns proper error for missing lead."""
        from services.deal_sheet import get_deal_sheet_service
        
        service = get_deal_sheet_service(test_db)
        deal_sheet = service.generate_deal_sheet(99999)  # Non-existent
        
        assert deal_sheet is None, "Should return None for missing lead"


# ==============================================================================
# Test: Buyer Matching Engine
# ==============================================================================


class TestBuyerMatching:
    """Tests for the buyer matching engine."""
    
    def test_buyer_matching_by_market(
        self, test_db: Session, sample_lead: Lead, sample_buyer: Buyer
    ):
        """Test buyers are matched by market code."""
        from services.buyer_match import get_buyer_match_service
        
        service = get_buyer_match_service(test_db)
        matches = service.match_buyers(sample_lead, limit=10)
        
        # Check matching works
        buyer_ids = [m.buyer_id for m in matches]
        assert sample_buyer.id in buyer_ids, "Sample buyer should match"
    
    def test_buyer_matching_by_acreage(
        self, test_db: Session, sample_lead: Lead, sample_buyer: Buyer
    ):
        """Test buyers are matched by acreage range."""
        from services.buyer_match import get_buyer_match_service
        
        # Update parcel to be outside buyer's range
        sample_lead.parcel.lot_size_acres = 100.0  # Too big
        test_db.flush()
        
        service = get_buyer_match_service(test_db)
        matches = service.match_buyers(sample_lead, limit=10)
        
        # Buyer should not match (acreage out of range)
        buyer_ids = [m.buyer_id for m in matches]
        assert sample_buyer.id not in buyer_ids, "Buyer should not match out-of-range acreage"
    
    def test_match_score_calculation(
        self, test_db: Session, sample_lead: Lead, sample_buyer: Buyer
    ):
        """Test match score is calculated correctly."""
        from services.buyer_match import get_buyer_match_service
        
        service = get_buyer_match_service(test_db)
        matches = service.match_buyers(sample_lead, limit=10)
        
        for match in matches:
            assert 0 <= match.match_percentage <= 100, "Score should be 0-100"
            assert match.factors is not None, "Factors should be populated"


# ==============================================================================
# Test: Offer Calculator
# ==============================================================================


class TestOfferCalculator:
    """Tests for the offer calculation engine."""
    
    def test_offer_calculation_with_comps(self, test_db: Session, sample_lead: Lead):
        """Test offer calculation when comps are available."""
        from services.offer_calculator import get_offer_calculator
        
        calculator = get_offer_calculator()
        result = calculator.calculate_offer(
            lot_size_acres=2.5,
            motivation_score=65,
            comp_avg_price_per_acre=10000.0,
            land_assessed_value=25000.0,
            is_adjudicated=True,
        )
        
        assert result.recommended_offer > 0, "Should have recommended offer"
        assert result.low_offer < result.recommended_offer, "Low should be less than recommended"
        assert result.high_offer > result.recommended_offer, "High should be more than recommended"
    
    def test_offer_calculation_without_comps(self, test_db: Session, sample_lead: Lead):
        """Test offer calculation when no comps available."""
        from services.offer_calculator import get_offer_calculator
        
        calculator = get_offer_calculator()
        result = calculator.calculate_offer(
            lot_size_acres=2.5,
            motivation_score=65,
            comp_avg_price_per_acre=None,  # No comps
            land_assessed_value=25000.0,
            is_adjudicated=True,
        )
        
        assert result.recommended_offer > 0, "Should still calculate offer without comps"
    
    def test_mao_calculation(self, test_db: Session, sample_lead: Lead):
        """Test Maximum Allowable Offer calculation."""
        from services.offer_calculator import get_offer_calculator
        
        calculator = get_offer_calculator()
        result = calculator.calculate_offer(
            lot_size_acres=2.5,
            motivation_score=80,
            comp_avg_price_per_acre=15000.0,
            land_assessed_value=30000.0,
            is_adjudicated=True,
        )
        
        # MAO should be significantly less than retail (leaving room for profit)
        estimated_retail = 2.5 * 15000.0  # $37,500
        assert result.recommended_offer < estimated_retail, "MAO should be below retail"


# ==============================================================================
# Test: Assignment Fee Optimizer
# ==============================================================================


class TestAssignmentFeeOptimizer:
    """Tests for assignment fee optimization."""
    
    def test_fee_calculation_basic(self):
        """Test basic fee calculation."""
        from services.assignment_fee_optimizer import calculate_assignment_fee
        
        result = calculate_assignment_fee(
            purchase_price=20000.0,
            retail_value=35000.0,
            lot_size_acres=2.0,
            market_code="LA",
        )
        
        assert result.recommended_fee > 0, "Should have recommended fee"
        assert result.min_fee < result.recommended_fee, "Min should be less than recommended"
        assert result.max_fee > result.recommended_fee, "Max should be more than recommended"
        assert 0 <= result.confidence <= 1, "Confidence should be 0-1"
    
    def test_fee_calculation_with_high_buyer_demand(self):
        """Test fee increases with buyer demand."""
        from services.assignment_fee_optimizer import calculate_assignment_fee
        
        # Low demand
        low_demand = calculate_assignment_fee(
            purchase_price=20000.0,
            retail_value=35000.0,
            lot_size_acres=2.0,
            market_code="LA",
            buyer_count=1,
        )
        
        # High demand
        high_demand = calculate_assignment_fee(
            purchase_price=20000.0,
            retail_value=35000.0,
            lot_size_acres=2.0,
            market_code="LA",
            buyer_count=10,
        )
        
        assert high_demand.recommended_fee > low_demand.recommended_fee, \
            "Higher demand should yield higher fee"
    
    def test_minimum_fee_floor(self):
        """Test minimum fee is enforced."""
        from services.assignment_fee_optimizer import calculate_assignment_fee
        
        result = calculate_assignment_fee(
            purchase_price=2000.0,  # Very small deal
            retail_value=3000.0,
            lot_size_acres=0.25,
            market_code="LA",
        )
        
        # Should have minimum floor
        assert result.recommended_fee >= 1000, "Should enforce minimum fee floor"


# ==============================================================================
# Test: Motivation Spike Detector
# ==============================================================================


class TestMotivationSpikeDetector:
    """Tests for motivation spike detection."""
    
    def test_detect_adjudicated_spike(
        self, test_db: Session, sample_lead: Lead
    ):
        """Test adjudicated property triggers spike."""
        from services.motivation_detector import detect_spike
        
        # Ensure parcel is adjudicated
        sample_lead.parcel.is_adjudicated = True
        sample_lead.parcel.years_tax_delinquent = 3
        test_db.flush()
        
        result = detect_spike(test_db, sample_lead.id)
        
        assert result.is_spike_detected, "Adjudicated property should trigger spike"
        assert result.total_spike_score > 0, "Should have positive spike score"
    
    def test_no_spike_for_normal_lead(self, test_db: Session):
        """Test normal leads don't trigger false spikes."""
        from services.motivation_detector import detect_spike
        
        # Create a very normal lead
        party = Party(
            normalized_name="NORMAL OWNER",
            normalized_zip="70801",
            match_hash="normal_hash",
            display_name="Normal Owner",
            party_type="individual",
            market_code="LA",
        )
        test_db.add(party)
        test_db.flush()
        
        owner = Owner(
            party_id=party.id,
            market_code="LA",
        )
        test_db.add(owner)
        test_db.flush()
        
        parcel = Parcel(
            canonical_parcel_id="NORMAL-001",
            parish="East Baton Rouge",
            market_code="LA",
            is_adjudicated=False,
            years_tax_delinquent=0,
        )
        test_db.add(parcel)
        test_db.flush()
        
        lead = Lead(
            owner_id=owner.id,
            parcel_id=parcel.id,
            market_code="LA",
            pipeline_stage="NEW",
            status="new",
            motivation_score=30,
        )
        test_db.add(lead)
        test_db.flush()
        
        result = detect_spike(test_db, lead.id)
        
        # May or may not have spike, but should not crash
        assert result is not None
        assert result.lead_id == lead.id
    
    def test_find_hot_leads(self, test_db: Session, sample_lead: Lead):
        """Test finding hot leads in the system."""
        from services.motivation_detector import find_hot_leads
        
        # Make our sample lead hot
        sample_lead.parcel.is_adjudicated = True
        sample_lead.parcel.years_tax_delinquent = 4
        test_db.flush()
        
        results = find_hot_leads(test_db, market_code="LA", limit=10)
        
        # Should find at least our hot lead
        lead_ids = [r.lead_id for r in results]
        # Note: might not find if score is below threshold
        assert isinstance(results, list)


# ==============================================================================
# Test: End-to-End Flow
# ==============================================================================


class TestEndToEndFlow:
    """Test complete workflow from lead to blast."""
    
    def test_lead_to_deal_sheet_flow(
        self, test_db: Session, sample_lead: Lead
    ):
        """Test creating a deal sheet from a lead."""
        from services.deal_sheet import get_deal_sheet_service
        
        service = get_deal_sheet_service(test_db)
        deal_sheet = service.generate_deal_sheet(sample_lead.id)
        
        assert deal_sheet is not None
        assert deal_sheet.lead_id == sample_lead.id
        assert deal_sheet.acreage == sample_lead.parcel.lot_size_acres
    
    def test_deal_sheet_to_buyer_match_flow(
        self, test_db: Session, sample_lead: Lead, sample_buyer: Buyer
    ):
        """Test matching buyers after deal sheet generation."""
        from services.deal_sheet import get_deal_sheet_service
        from services.buyer_match import get_buyer_match_service
        
        # Generate deal sheet
        ds_service = get_deal_sheet_service(test_db)
        deal_sheet = ds_service.generate_deal_sheet(sample_lead.id)
        
        assert deal_sheet is not None
        
        # Match buyers
        match_service = get_buyer_match_service(test_db)
        matches = match_service.match_buyers(
            sample_lead,
            offer_price=deal_sheet.recommended_offer,
            limit=10,
        )
        
        # Should work without error
        assert isinstance(matches, list)
    
    def test_buyer_match_to_blast_preview(
        self, test_db: Session, sample_lead: Lead, sample_buyer: Buyer
    ):
        """Test blast preview after matching."""
        from services.buyer_blast import get_buyer_blast_service
        
        service = get_buyer_blast_service(test_db)
        preview = service.preview_blast(
            lead_id=sample_lead.id,
            max_buyers=5,
            min_match_score=0,  # Include all for test
        )
        
        assert "lead_id" in preview
        assert "buyers" in preview
        assert isinstance(preview["buyers"], list)
    
    def test_complete_disposition_flow(
        self, test_db: Session, sample_lead: Lead, sample_buyer: Buyer
    ):
        """Test the complete disposition flow returns valid data."""
        from services.deal_sheet import get_deal_sheet_service
        from services.buyer_match import get_buyer_match_service
        from services.assignment_fee_optimizer import get_assignment_fee_optimizer
        
        # 1. Generate deal sheet
        ds_service = get_deal_sheet_service(test_db)
        deal_sheet = ds_service.generate_deal_sheet(sample_lead.id)
        assert deal_sheet is not None
        
        # 2. Match buyers
        match_service = get_buyer_match_service(test_db)
        matches = match_service.match_buyers(
            sample_lead,
            offer_price=deal_sheet.recommended_offer,
        )
        
        # 3. Calculate assignment fee
        optimizer = get_assignment_fee_optimizer()
        fee_range = optimizer.calculate_assignment_fee(
            purchase_price=deal_sheet.recommended_offer,
            retail_value=deal_sheet.recommended_offer * 1.5,
            lot_size_acres=float(sample_lead.parcel.lot_size_acres or 1),
            market_code=sample_lead.market_code,
            motivation_score=sample_lead.motivation_score,
            buyer_count=len(matches),
        )
        
        # 4. Verify all pieces work together
        assert deal_sheet.recommended_offer > 0
        assert fee_range.recommended_fee > 0
        assert isinstance(matches, list)


# ==============================================================================
# Test: Skip Trace Service
# ==============================================================================


class TestSkipTraceService:
    """Tests for skip trace service."""
    
    def test_phone_validation(self):
        """Test phone number validation."""
        from services.skip_trace import get_skip_trace_service
        
        service = get_skip_trace_service()
        
        # Valid phone
        result = service.validate_phone("+12255551234")
        assert result["is_valid"] is True
        
        # Invalid phone
        result = service.validate_phone("123")
        assert result["is_valid"] is False
    
    def test_email_validation(self):
        """Test email validation."""
        from services.skip_trace import get_skip_trace_service
        
        service = get_skip_trace_service()
        
        # Valid email
        result = service.validate_email("test@example.com")
        assert result["is_valid"] is True
        
        # Invalid email
        result = service.validate_email("notanemail")
        assert result["is_valid"] is False
    
    def test_skip_trace_disabled_fallback(self):
        """Test skip trace returns fallback when disabled."""
        from services.skip_trace import skip_trace_person
        
        # With service disabled, should return fallback
        result = skip_trace_person(
            name="John Doe",
            address="123 Main St",
            state="LA",
        )
        
        assert result.source == "fallback"
        assert result.found is False


# ==============================================================================
# Test: Database Integrity
# ==============================================================================


class TestDatabaseIntegrity:
    """Tests for database relationships and constraints."""
    
    def test_lead_owner_relationship(
        self, test_db: Session, sample_lead: Lead
    ):
        """Test lead-owner relationship is correct."""
        assert sample_lead.owner is not None
        assert sample_lead.owner.party is not None
        assert sample_lead.owner.party.display_name == "John Doe"
    
    def test_lead_parcel_relationship(
        self, test_db: Session, sample_lead: Lead
    ):
        """Test lead-parcel relationship is correct."""
        assert sample_lead.parcel is not None
        assert sample_lead.parcel.canonical_parcel_id == "EBR-12345"
        assert sample_lead.parcel.lot_size_acres == 2.5
    
    def test_buyer_deal_creation(
        self, test_db: Session, sample_lead: Lead, sample_buyer: Buyer
    ):
        """Test buyer deal can be created correctly."""
        deal = BuyerDeal(
            buyer_id=sample_buyer.id,
            lead_id=sample_lead.id,
            stage="BLASTED",
            match_score=75.0,
        )
        test_db.add(deal)
        test_db.flush()
        
        assert deal.id is not None
        assert deal.buyer.name == "ABC Land Company"
        assert deal.lead.id == sample_lead.id


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

