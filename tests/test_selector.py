"""Test lead selector."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Add src to path
src_path = Path(__file__).parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from core.models import Lead, Parcel, Owner, Party, OutreachAttempt
from outreach.selector import select_leads_for_first_touch


def test_select_leads_for_first_touch(db_session, sample_lead):
    """Test selecting leads for first touch."""
    # Sample lead is TCPA safe, has phone, status=new, score=75
    leads = select_leads_for_first_touch(db_session, min_score=50)
    
    assert len(leads) == 1
    assert leads[0].id == sample_lead.id


def test_select_leads_min_score_filter(db_session, sample_lead):
    """Test that min_score filter works."""
    # Sample lead has score=75
    leads_high = select_leads_for_first_touch(db_session, min_score=80)
    leads_low = select_leads_for_first_touch(db_session, min_score=50)
    
    assert len(leads_high) == 0  # 75 < 80
    assert len(leads_low) == 1   # 75 >= 50


def test_select_leads_tcpa_filter(db_session):
    """Test that non-TCPA-safe leads are filtered out."""
    # Create a non-TCPA-safe lead
    party = Party(
        normalized_name="NON TCPA",
        match_hash="nontcpa123",
        raw_mailing_address="123 Test St",
    )
    db_session.add(party)
    db_session.flush()
    
    owner = Owner(
        party_id=party.id,
        phone_primary="+12225550100",
        is_tcpa_safe=False,  # Not TCPA safe
        is_dnr=False,
        opt_out=False,
    )
    db_session.add(owner)
    db_session.flush()
    
    parcel = Parcel(
        canonical_parcel_id="NONTCPA001",
        parish="EBR",
    )
    db_session.add(parcel)
    db_session.flush()
    
    lead = Lead(
        owner_id=owner.id,
        parcel_id=parcel.id,
        motivation_score=90,
        status="new",
    )
    db_session.add(lead)
    db_session.commit()
    
    # Should not select non-TCPA-safe lead
    leads = select_leads_for_first_touch(db_session, min_score=50)
    
    assert all(l.owner.is_tcpa_safe for l in leads)
    assert lead not in leads


def test_select_leads_no_phone_filter(db_session):
    """Test that leads without phone are filtered out."""
    party = Party(
        normalized_name="NO PHONE",
        match_hash="nophone123",
        raw_mailing_address="123 Test St",
    )
    db_session.add(party)
    db_session.flush()
    
    owner = Owner(
        party_id=party.id,
        phone_primary=None,  # No phone
        is_tcpa_safe=True,
        is_dnr=False,
        opt_out=False,
    )
    db_session.add(owner)
    db_session.flush()
    
    parcel = Parcel(
        canonical_parcel_id="NOPHONE001",
        parish="EBR",
    )
    db_session.add(parcel)
    db_session.flush()
    
    lead = Lead(
        owner_id=owner.id,
        parcel_id=parcel.id,
        motivation_score=90,
        status="new",
    )
    db_session.add(lead)
    db_session.commit()
    
    leads = select_leads_for_first_touch(db_session, min_score=50)
    
    assert lead not in leads


def test_select_leads_opt_out_filter(db_session):
    """Test that opted-out leads are filtered out."""
    party = Party(
        normalized_name="OPT OUT",
        match_hash="optout123",
        raw_mailing_address="123 Test St",
    )
    db_session.add(party)
    db_session.flush()
    
    owner = Owner(
        party_id=party.id,
        phone_primary="+12225550101",
        is_tcpa_safe=True,
        is_dnr=False,
        opt_out=True,  # Opted out
    )
    db_session.add(owner)
    db_session.flush()
    
    parcel = Parcel(
        canonical_parcel_id="OPTOUT001",
        parish="EBR",
    )
    db_session.add(parcel)
    db_session.flush()
    
    lead = Lead(
        owner_id=owner.id,
        parcel_id=parcel.id,
        motivation_score=90,
        status="new",
    )
    db_session.add(lead)
    db_session.commit()
    
    leads = select_leads_for_first_touch(db_session, min_score=50)
    
    assert lead not in leads


def test_select_leads_status_filter(db_session):
    """Test that non-new leads are filtered out."""
    party = Party(
        normalized_name="CONTACTED",
        match_hash="contacted123",
        raw_mailing_address="123 Test St",
    )
    db_session.add(party)
    db_session.flush()
    
    owner = Owner(
        party_id=party.id,
        phone_primary="+12225550102",
        is_tcpa_safe=True,
        is_dnr=False,
        opt_out=False,
    )
    db_session.add(owner)
    db_session.flush()
    
    parcel = Parcel(
        canonical_parcel_id="CONTACTED001",
        parish="EBR",
    )
    db_session.add(parcel)
    db_session.flush()
    
    lead = Lead(
        owner_id=owner.id,
        parcel_id=parcel.id,
        motivation_score=90,
        status="contacted",  # Already contacted
    )
    db_session.add(lead)
    db_session.commit()
    
    leads = select_leads_for_first_touch(db_session, min_score=50)
    
    assert lead not in leads


def test_select_leads_ordered_by_score(db_session):
    """Test that leads are ordered by motivation score descending."""
    # Create multiple leads with different scores
    for i, score in enumerate([60, 90, 75]):
        party = Party(
            normalized_name=f"MULTI {i}",
            match_hash=f"multi{i}",
            raw_mailing_address="123 Test St",
        )
        db_session.add(party)
        db_session.flush()
        
        owner = Owner(
            party_id=party.id,
            phone_primary=f"+1222555010{i}",
            is_tcpa_safe=True,
            is_dnr=False,
            opt_out=False,
        )
        db_session.add(owner)
        db_session.flush()
        
        parcel = Parcel(
            canonical_parcel_id=f"MULTI00{i}",
            parish="EBR",
        )
        db_session.add(parcel)
        db_session.flush()
        
        lead = Lead(
            owner_id=owner.id,
            parcel_id=parcel.id,
            motivation_score=score,
            status="new",
        )
        db_session.add(lead)
    
    db_session.commit()
    
    leads = select_leads_for_first_touch(db_session, min_score=50)
    
    # Should be ordered by score descending
    scores = [l.motivation_score for l in leads]
    assert scores == sorted(scores, reverse=True)


def test_select_leads_limit(db_session):
    """Test that limit parameter works."""
    # Create multiple qualifying leads
    for i in range(5):
        party = Party(
            normalized_name=f"LIMIT {i}",
            match_hash=f"limit{i}",
            raw_mailing_address="123 Test St",
        )
        db_session.add(party)
        db_session.flush()
        
        owner = Owner(
            party_id=party.id,
            phone_primary=f"+1333555010{i}",
            is_tcpa_safe=True,
            is_dnr=False,
            opt_out=False,
        )
        db_session.add(owner)
        db_session.flush()
        
        parcel = Parcel(
            canonical_parcel_id=f"LIMIT00{i}",
            parish="EBR",
        )
        db_session.add(parcel)
        db_session.flush()
        
        lead = Lead(
            owner_id=owner.id,
            parcel_id=parcel.id,
            motivation_score=80,
            status="new",
        )
        db_session.add(lead)
    
    db_session.commit()
    
    leads = select_leads_for_first_touch(db_session, min_score=50, limit=3)
    
    assert len(leads) == 3
