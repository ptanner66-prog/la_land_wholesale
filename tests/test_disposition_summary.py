"""Tests for the disposition summary endpoint.

This test validates the fix for the 500 error on GET /dispo/lead/{lead_id}/disposition-summary.
The root cause was a datetime comparison issue between offset-naive (SQLite) and 
offset-aware (utcnow()) datetime objects.
"""
import pytest
from sqlalchemy.orm import Session
from httpx import AsyncClient

from core.db import get_db_session
from core.models import Lead, Party, Parcel, Owner


@pytest.fixture
def test_lead(test_db_session: Session) -> Lead:
    """Create a test lead for disposition summary testing."""
    # Create party
    party = Party(
        normalized_name="TEST OWNER",
        normalized_zip="70801",
        match_hash="test_dispo_hash",
        display_name="Test Owner",
        party_type="individual",
        market_code="LA",
    )
    test_db_session.add(party)
    test_db_session.flush()
    
    # Create owner
    owner = Owner(
        party_id=party.id,
        phone_primary="+12255551234",
        market_code="LA",
        is_tcpa_safe=True,
    )
    test_db_session.add(owner)
    test_db_session.flush()
    
    # Create parcel
    parcel = Parcel(
        canonical_parcel_id="TEST-DISPO-001",
        parish="East Baton Rouge",
        market_code="LA",
        situs_address="123 Test Dispo St",
        city="Baton Rouge",
        state="LA",
        lot_size_acres=1.5,
        land_assessed_value=10000,
    )
    test_db_session.add(parcel)
    test_db_session.flush()
    
    # Create lead
    lead = Lead(
        owner_id=owner.id,
        parcel_id=parcel.id,
        market_code="LA",
        motivation_score=65,
        pipeline_stage="NEW",
        status="active",
    )
    test_db_session.add(lead)
    test_db_session.commit()
    
    return lead


class TestDispositionSummary:
    """Test suite for GET /dispo/lead/{lead_id}/disposition-summary."""
    
    def test_disposition_summary_returns_200(
        self, client, test_lead: Lead
    ):
        """
        Test that the disposition summary endpoint returns 200.
        
        This was the original bug - it returned 500 due to datetime comparison issues.
        """
        response = client.get(f"/dispo/lead/{test_lead.id}/disposition-summary")
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify required fields exist
        assert "lead_id" in data
        assert data["lead_id"] == test_lead.id
        assert "deal_sheet" in data  # Can be None
        assert "matched_buyers_count" in data
        assert "top_matches" in data
        assert "active_deals" in data
        assert "can_blast" in data
    
    def test_disposition_summary_handles_empty_buyers(
        self, client, test_lead: Lead
    ):
        """Test that empty buyer list is handled gracefully."""
        response = client.get(f"/dispo/lead/{test_lead.id}/disposition-summary")
        
        assert response.status_code == 200
        data = response.json()
        
        # With no buyers in database, these should be empty/0
        assert isinstance(data["top_matches"], list)
        assert isinstance(data["active_deals"], list)
        assert isinstance(data["matched_buyers_count"], int)
    
    def test_disposition_summary_nonexistent_lead(self, client):
        """Test 404 for non-existent lead."""
        response = client.get("/dispo/lead/999999/disposition-summary")
        
        assert response.status_code == 404
    
    def test_deal_sheet_endpoint_works(self, client, test_lead: Lead):
        """Verify deal sheet endpoint still works after fixes."""
        response = client.get(f"/dispo/dealsheet/{test_lead.id}")
        
        assert response.status_code == 200
        data = response.json()
        assert "recommended_offer" in data
        assert "retail_estimate" in data
    
    def test_call_script_endpoint_works(self, client, test_lead: Lead):
        """Verify call script endpoint still works after fixes."""
        response = client.get(f"/dispo/callscript/{test_lead.id}")
        
        assert response.status_code == 200
        data = response.json()
        assert "opening_line" in data
        assert "discovery_questions" in data

