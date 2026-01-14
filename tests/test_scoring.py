"""Test scoring engine."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Add src to path
src_path = Path(__file__).parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from core.models import Parcel, Owner, Lead, Party
from scoring.engine import compute_motivation_score


def test_compute_motivation_score_basic(db_session, sample_lead):
    """Test basic score computation."""
    lead = sample_lead
    parcel = lead.parcel
    owner = lead.owner
    
    # Sample lead has non-adjudicated parcel with no delinquency
    score = compute_motivation_score(parcel, owner, is_adjudicated=False)
    
    # Should get some points for lot size (1.5 acres is in range)
    # Should be relatively low as no delinquency, has improvement, local owner
    assert score >= 0
    assert score <= 100


def test_compute_motivation_score_high(db_session, high_priority_lead):
    """Test high score computation for motivated seller indicators."""
    lead = high_priority_lead
    parcel = lead.parcel
    owner = lead.owner
    
    score = compute_motivation_score(parcel, owner, is_adjudicated=True)
    
    # Should be high due to:
    # - Adjudicated status (+40)
    # - Tax delinquent 3 years (+15)
    # - Vacant land (improvement = 0, ratio < 0.1) (+20)
    # - Absentee owner (TX address, LA property) (+10)
    # - Lot size in range (2.0 acres) (+10)
    # Total potential: 95
    assert score > 50
    assert score <= 100


def test_compute_motivation_score_adjudicated():
    """Test that adjudicated properties get points."""
    # Create minimal test objects
    party = Party(
        normalized_name="TEST",
        match_hash="test123",
        raw_mailing_address="123 Local St, Baton Rouge, LA 70808",
    )
    owner = Owner(party=party)
    parcel = Parcel(
        canonical_parcel_id="TEST001",
        parish="EBR",
        state="LA",
        years_tax_delinquent=0,
        land_assessed_value=10000,
        improvement_assessed_value=50000,
        lot_size_acres=0.25,  # Too small for bonus
        is_adjudicated=True,
    )
    
    score_adjudicated = compute_motivation_score(parcel, owner, is_adjudicated=True)
    score_not_adjudicated = compute_motivation_score(parcel, owner, is_adjudicated=False)
    
    # Adjudicated should score higher
    assert score_adjudicated > score_not_adjudicated


def test_compute_motivation_score_delinquent():
    """Test that tax delinquent properties get points."""
    party = Party(
        normalized_name="TEST",
        match_hash="test456",
        raw_mailing_address="123 Local St, Baton Rouge, LA 70808",
    )
    owner = Owner(party=party)
    
    parcel_delinquent = Parcel(
        canonical_parcel_id="TEST002",
        parish="EBR",
        state="LA",
        years_tax_delinquent=5,
        land_assessed_value=10000,
        improvement_assessed_value=50000,
        lot_size_acres=0.25,
    )
    
    parcel_current = Parcel(
        canonical_parcel_id="TEST003",
        parish="EBR",
        state="LA",
        years_tax_delinquent=0,
        land_assessed_value=10000,
        improvement_assessed_value=50000,
        lot_size_acres=0.25,
    )
    
    score_delinquent = compute_motivation_score(parcel_delinquent, owner, is_adjudicated=False)
    score_current = compute_motivation_score(parcel_current, owner, is_adjudicated=False)
    
    assert score_delinquent > score_current


def test_compute_motivation_score_vacant_land():
    """Test that vacant land (low improvement value) gets points."""
    party = Party(
        normalized_name="TEST",
        match_hash="test789",
        raw_mailing_address="123 Local St, Baton Rouge, LA 70808",
    )
    owner = Owner(party=party)
    
    parcel_vacant = Parcel(
        canonical_parcel_id="TEST004",
        parish="EBR",
        state="LA",
        years_tax_delinquent=0,
        land_assessed_value=10000,
        improvement_assessed_value=0,  # Vacant
        lot_size_acres=0.25,
    )
    
    parcel_improved = Parcel(
        canonical_parcel_id="TEST005",
        parish="EBR",
        state="LA",
        years_tax_delinquent=0,
        land_assessed_value=10000,
        improvement_assessed_value=50000,  # Improved
        lot_size_acres=0.25,
    )
    
    score_vacant = compute_motivation_score(parcel_vacant, owner, is_adjudicated=False)
    score_improved = compute_motivation_score(parcel_improved, owner, is_adjudicated=False)
    
    assert score_vacant > score_improved


def test_compute_motivation_score_capped_at_100():
    """Test that score is capped at 100."""
    party = Party(
        normalized_name="TEST",
        match_hash="testmax",
        raw_mailing_address="123 Out of State St, Dallas, TX 75001",
    )
    owner = Owner(party=party)
    
    # Maximum everything
    parcel = Parcel(
        canonical_parcel_id="TESTMAX",
        parish="EBR",
        state="LA",
        years_tax_delinquent=10,
        land_assessed_value=10000,
        improvement_assessed_value=0,
        lot_size_acres=5.0,
        is_adjudicated=True,
    )
    
    score = compute_motivation_score(parcel, owner, is_adjudicated=True)
    
    assert score <= 100
    assert score >= 0
