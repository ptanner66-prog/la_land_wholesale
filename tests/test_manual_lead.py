"""Tests for manual lead creation with enrichment."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# Add src to path
src_path = Path(__file__).parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

# Set test environment
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["DRY_RUN"] = "true"
os.environ["ENVIRONMENT"] = "test"
os.environ["ENABLE_GOOGLE"] = "false"
os.environ["ENABLE_USPS"] = "false"
os.environ["ENABLE_COMPS"] = "false"
os.environ["ENABLE_COUNTY_SCRAPER"] = "false"


class TestManualLeadCreation:
    """Test manual lead creation through LeadService."""

    def test_create_manual_lead_basic(self, db_session):
        """Test basic manual lead creation without enrichment."""
        from domain.leads import LeadService
        
        service = LeadService(session=db_session)
        
        lead = service.create_manual_lead(
            owner_name="Test Owner",
            address="123 Test St",
            city="Baton Rouge",
            state="LA",
            postal_code="70808",
            parish="East Baton Rouge",
            phone="+12255551234",
            notes="Test lead",
            tcpa_safe=True,
            enrich=False,  # Disable enrichment
        )
        
        db_session.commit()
        
        assert lead is not None
        assert lead.id is not None
        assert lead.owner_name == "TEST OWNER"  # Normalized
        assert lead.motivation_score >= 0

    def test_create_manual_lead_with_enrichment_disabled(self, db_session):
        """Test manual lead creation with enrichment enabled but services disabled."""
        from core.config import reload_settings
        reload_settings()
        
        from domain.leads import LeadService
        
        service = LeadService(session=db_session)
        
        lead = service.create_manual_lead(
            owner_name="Enriched Owner",
            address="456 Enriched Ave",
            city="Baton Rouge",
            state="LA",
            postal_code="70808",
            parish="East Baton Rouge",
            enrich=True,  # Enable enrichment (services are disabled)
        )
        
        db_session.commit()
        
        assert lead is not None
        assert lead.id is not None
        # Enrichment data should be present but show services skipped
        if lead.enrichment_data:
            summary = lead.enrichment_data.get("summary", {})
            # All services should be skipped
            assert len(summary.get("services_failed", [])) == 0

    def test_create_manual_lead_requires_owner_and_address(self, db_session):
        """Test that owner_name and address are required."""
        from domain.leads import LeadService
        
        service = LeadService(session=db_session)
        
        with pytest.raises(ValueError, match="owner_name and address are required"):
            service.create_manual_lead(
                owner_name="",
                address="123 Test St",
                enrich=False,
            )
        
        with pytest.raises(ValueError, match="owner_name and address are required"):
            service.create_manual_lead(
                owner_name="Test Owner",
                address="",
                enrich=False,
            )

    def test_create_manual_lead_deduplication(self, db_session):
        """Test that creating same lead twice returns existing lead."""
        from domain.leads import LeadService
        
        service = LeadService(session=db_session)
        
        # Create first lead
        lead1 = service.create_manual_lead(
            owner_name="Dupe Test Owner",
            address="789 Dupe St",
            city="Baton Rouge",
            state="LA",
            postal_code="70808",
            enrich=False,
        )
        db_session.commit()
        
        # Create second lead with same info
        lead2 = service.create_manual_lead(
            owner_name="Dupe Test Owner",
            address="789 Dupe St",
            city="Baton Rouge",
            state="LA",
            postal_code="70808",
            enrich=False,
        )
        db_session.commit()
        
        # Should return same lead
        assert lead1.id == lead2.id

    def test_create_manual_lead_phone_normalization(self, db_session):
        """Test that phone numbers are normalized."""
        from domain.leads import LeadService
        
        service = LeadService(session=db_session)
        
        # Create lead with unformatted phone
        lead = service.create_manual_lead(
            owner_name="Phone Test Owner",
            address="101 Phone St",
            city="Baton Rouge",
            state="LA",
            phone="(225) 555-0199",
            enrich=False,
        )
        db_session.commit()
        
        assert lead is not None
        # Phone should be normalized to E.164 format
        assert lead.owner_phone == "+12255550199"


class TestLeadService:
    """Test LeadService methods."""

    def test_list_leads_empty(self, db_session):
        """Test listing leads when none exist."""
        from domain.leads import LeadService
        
        service = LeadService(session=db_session)
        leads = service.list_leads()
        
        assert leads == []

    def test_list_leads_with_filter(self, db_session, sample_lead):
        """Test listing leads with filters."""
        from domain.leads import LeadService
        
        service = LeadService(session=db_session)
        
        # Filter by minimum score
        leads = service.list_leads(min_score=50)
        assert len(leads) == 1  # sample_lead has score 75
        
        leads = service.list_leads(min_score=80)
        assert len(leads) == 0

    def test_get_lead(self, db_session, sample_lead):
        """Test getting a specific lead."""
        from domain.leads import LeadService
        
        service = LeadService(session=db_session)
        lead = service.get_lead(sample_lead.id)
        
        assert lead is not None
        assert lead.id == sample_lead.id

    def test_get_lead_not_found(self, db_session):
        """Test getting non-existent lead."""
        from domain.leads import LeadService
        
        service = LeadService(session=db_session)
        lead = service.get_lead(99999)
        
        assert lead is None

    def test_update_lead_status(self, db_session, sample_lead):
        """Test updating lead status."""
        from domain.leads import LeadService
        
        service = LeadService(session=db_session)
        
        # Update status
        updated = service.update_lead_status(sample_lead.id, "contacted")
        db_session.commit()
        
        assert updated is not None
        assert updated.status == "contacted"

    def test_get_statistics(self, db_session, sample_lead):
        """Test getting lead statistics."""
        from domain.leads import LeadService
        
        service = LeadService(session=db_session)
        stats = service.get_statistics()
        
        assert "total_leads" in stats
        assert stats["total_leads"] >= 1


class TestLeadDetail:
    """Test LeadDetail dataclass."""

    def test_lead_detail_to_dict(self):
        """Test LeadDetail serialization."""
        from datetime import datetime
        from domain.leads import LeadDetail
        
        detail = LeadDetail(
            id=1,
            owner_name="Test Owner",
            owner_phone="+12255550100",
            parcel_id="ABC123",
            parish="East Baton Rouge",
            city="Baton Rouge",
            acreage=1.5,
            motivation_score=75,
            status="new",
            is_tcpa_safe=True,
            is_adjudicated=False,
            outreach_count=0,
            created_at=datetime.now(),
            situs_address="123 Test St",
            land_value=10000.0,
            improvement_value=5000.0,
            years_tax_delinquent=0,
        )
        
        d = detail.to_dict()
        
        assert d["id"] == 1
        assert d["owner_name"] == "Test Owner"
        assert d["motivation_score"] == 75
        assert d["situs_address"] == "123 Test St"

    def test_lead_detail_with_enrichment(self):
        """Test LeadDetail with enrichment data."""
        from datetime import datetime
        from domain.leads import LeadDetail
        
        enrichment = {
            "usps": {"verified": True},
            "geocode": {"lat": 30.45, "lng": -91.18},
        }
        
        detail = LeadDetail(
            id=1,
            owner_name="Test Owner",
            owner_phone=None,
            parcel_id="ABC123",
            parish="East Baton Rouge",
            city="Baton Rouge",
            acreage=None,
            motivation_score=65,
            status="new",
            is_tcpa_safe=False,
            is_adjudicated=False,
            outreach_count=0,
            created_at=datetime.now(),
            enrichment_data=enrichment,
        )
        
        d = detail.to_dict()
        assert d["enrichment"] == enrichment
