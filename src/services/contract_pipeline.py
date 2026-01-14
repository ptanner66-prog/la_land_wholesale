"""
Contract Pipeline Service - Manages leads from enrichment to contract.

Pipeline stages:
    INGESTED → ENRICHING → PRE_SCORE → NEW → CONTACTED → REVIEW → OFFER → CONTRACT
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, or_, func, desc
from sqlalchemy.orm import Session

from core.models import Lead, Parcel, Owner, Party, PipelineStage
from core.logging_config import get_logger
from scoring.deterministic_engine import (
    compute_deterministic_score,
    get_parish_median_values,
    CONTACT_THRESHOLD,
    HOT_THRESHOLD,
)

LOGGER = get_logger(__name__)


def is_enriched(parcel: Parcel) -> bool:
    """Check if a parcel has required enrichment data."""
    return (
        parcel.lot_size_acres is not None and parcel.lot_size_acres > 0
        and parcel.land_assessed_value is not None and parcel.land_assessed_value > 0
    )


def score_enriched_leads(
    session: Session,
    parish: Optional[str] = None,
    limit: int = 100,
) -> Dict[str, Any]:
    """
    Score ONLY leads that have been enriched.
    
    This does NOT score all 472k leads - only those with:
    - lot_size_acres > 0
    - land_assessed_value > 0
    
    Args:
        session: Database session.
        parish: Filter by parish.
        limit: Max leads to score.
    
    Returns:
        Scoring summary.
    """
    # Pre-compute parish medians
    parish_medians = get_parish_median_values(session)
    
    # Find enriched leads that need scoring
    query = (
        session.query(Lead)
        .join(Lead.parcel)
        .join(Lead.owner)
        .filter(
            Lead.deleted_at.is_(None),
            Parcel.lot_size_acres > 0,
            Parcel.land_assessed_value > 0,
        )
    )
    
    if parish:
        query = query.filter(func.lower(Parcel.parish) == parish.lower())
    
    leads = query.limit(limit).all()
    
    results = {
        'processed': 0,
        'hot': 0,
        'contact': 0,
        'low': 0,
        'disqualified': 0,
    }
    
    for lead in leads:
        parish_key = (lead.parcel.parish or '').lower().strip()
        parish_median = parish_medians.get(parish_key)
        
        score_result = compute_deterministic_score(lead, parish_median)
        
        # Update lead
        lead.motivation_score = score_result.motivation_score
        lead.score_details = score_result.to_dict()
        lead.updated_at = datetime.now(timezone.utc)
        
        # Update pipeline stage based on score
        # Only update stage if lead hasn't been manually advanced (CONTACTED, OFFER, CONTRACT)
        manual_stages = {PipelineStage.CONTACTED.value, PipelineStage.REVIEW.value, 
                        PipelineStage.OFFER.value, PipelineStage.CONTRACT.value}
        
        if score_result.disqualified:
            results['disqualified'] += 1
            # Don't change stage for disqualified - keep existing or set to INGESTED
            if lead.pipeline_stage not in manual_stages:
                lead.pipeline_stage = PipelineStage.INGESTED.value
        elif score_result.motivation_score >= HOT_THRESHOLD:
            results['hot'] += 1
            if lead.pipeline_stage not in manual_stages:
                lead.pipeline_stage = PipelineStage.HOT.value
        elif score_result.motivation_score >= CONTACT_THRESHOLD:
            results['contact'] += 1
            if lead.pipeline_stage not in manual_stages:
                lead.pipeline_stage = PipelineStage.NEW.value
        else:
            results['low'] += 1
            if lead.pipeline_stage not in manual_stages:
                lead.pipeline_stage = PipelineStage.PRE_SCORE.value
        
        results['processed'] += 1
    
    session.commit()
    
    LOGGER.info(
        "Scored %d enriched leads: %d hot, %d contact, %d low, %d disqualified",
        results['processed'], results['hot'], results['contact'], 
        results['low'], results['disqualified']
    )
    
    return results


def get_contract_candidates(
    session: Session,
    parish: Optional[str] = None,
    min_score: int = CONTACT_THRESHOLD,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """
    Get leads ready for contract offers.
    
    Criteria:
    - Score >= min_score (default 45)
    - Has phone OR has mailing address
    - Enriched (has acreage and land value)
    - Not already under contract
    
    Args:
        session: Database session.
        parish: Filter by parish.
        min_score: Minimum motivation score.
        limit: Max leads to return.
    
    Returns:
        List of contract candidate dicts.
    """
    query = (
        session.query(Lead)
        .join(Lead.parcel)
        .join(Lead.owner)
        .join(Owner.party)
        .filter(
            Lead.deleted_at.is_(None),
            Lead.motivation_score >= min_score,
            # Enriched
            Parcel.lot_size_acres > 0,
            # Has contact method
            or_(
                Owner.phone_primary.isnot(None),
                Party.raw_mailing_address.isnot(None),
            ),
            # Not already in contract stage
            Lead.pipeline_stage != PipelineStage.CONTRACT.value,
        )
        .order_by(desc(Lead.motivation_score))
    )
    
    if parish:
        query = query.filter(func.lower(Parcel.parish) == parish.lower())
    
    leads = query.limit(limit).all()
    
    candidates = []
    for lead in leads:
        # Calculate simple offer price (70% of assessed value)
        land_val = float(lead.parcel.land_assessed_value or 0)
        offer_price = round(land_val * 0.70, -2)  # Round to nearest $100
        
        candidates.append({
            'lead_id': lead.id,
            'score': lead.motivation_score,
            'canonical_parcel_id': lead.parcel.canonical_parcel_id,
            'parish': lead.parcel.parish,
            'situs_address': lead.parcel.situs_address,
            'acreage': float(lead.parcel.lot_size_acres) if lead.parcel.lot_size_acres else 0,
            'land_assessed_value': land_val,
            'offer_price': offer_price,
            'owner_name': lead.owner.party.display_name,
            'mailing_address': lead.owner.party.raw_mailing_address,
            'phone': lead.owner.phone_primary,
            'is_adjudicated': lead.parcel.is_adjudicated,
            'years_delinquent': lead.parcel.years_tax_delinquent or 0,
            'pipeline_stage': lead.pipeline_stage,
            'score_factors': lead.score_details.get('factors', []) if lead.score_details else [],
        })
    
    return candidates


def mark_offer_sent(session: Session, lead_id: int, offer_amount: float = None) -> bool:
    """Mark a lead as having received an offer."""
    lead = session.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        return False
    
    lead.pipeline_stage = PipelineStage.OFFER.value
    lead.updated_at = datetime.now(timezone.utc)
    
    # Store offer in tags
    if offer_amount:
        tags = lead.tags or []
        tags.append(f"offer:{offer_amount}")
        lead.tags = tags
    
    session.commit()
    return True


def mark_under_contract(session: Session, lead_id: int, contract_price: float = None) -> bool:
    """Mark a lead as under contract."""
    lead = session.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        return False
    
    lead.pipeline_stage = PipelineStage.CONTRACT.value
    lead.updated_at = datetime.now(timezone.utc)
    
    if contract_price:
        tags = lead.tags or []
        tags.append(f"contract:{contract_price}")
        lead.tags = tags
    
    session.commit()
    return True


def export_contract_candidates_csv(
    session: Session,
    parish: Optional[str] = None,
    min_score: int = CONTACT_THRESHOLD,
    limit: int = 20,
) -> str:
    """
    Export contract candidates as CSV for manual outreach.
    
    Returns:
        CSV string.
    """
    candidates = get_contract_candidates(session, parish=parish, min_score=min_score, limit=limit)
    
    if not candidates:
        return "No contract candidates found"
    
    lines = [
        "lead_id,score,canonical_parcel_id,parish,acreage,land_value,offer_price,owner_name,phone,mailing_address,adjudicated,years_delinquent"
    ]
    
    for c in candidates:
        lines.append(
            f'{c["lead_id"]},{c["score"]},"{c["canonical_parcel_id"]}","{c["parish"]}",{c["acreage"]:.2f},{c["land_assessed_value"]:.0f},{c["offer_price"]:.0f},"{c["owner_name"]}","{c["phone"] or ""}","{(c["mailing_address"] or "").replace(chr(34), "")}",{c["is_adjudicated"]},{c["years_delinquent"]}'
        )
    
    return "\n".join(lines)


__all__ = [
    'is_enriched',
    'score_enriched_leads',
    'get_contract_candidates',
    'mark_offer_sent',
    'mark_under_contract',
    'export_contract_candidates_csv',
]

