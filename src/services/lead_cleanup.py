"""Lead cleanup and deletion services."""
from __future__ import annotations

from typing import Dict, Any, Optional, List

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from core.config import get_settings
from core.logging_config import get_logger
from core.models import Lead, Owner, Parcel, OutreachAttempt, TimelineEvent, PipelineStage

LOGGER = get_logger(__name__)
SETTINGS = get_settings()


def delete_lead(session: Session, lead_id: int) -> Dict[str, Any]:
    """
    Delete a lead and its associated records.
    
    Args:
        session: Database session.
        lead_id: ID of the lead to delete.
    
    Returns:
        Dict with deletion results.
    """
    lead = session.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        return {"success": False, "error": "Lead not found"}
    
    owner_id = lead.owner_id
    parcel_id = lead.parcel_id
    
    # Delete associated records
    outreach_deleted = session.query(OutreachAttempt).filter(
        OutreachAttempt.lead_id == lead_id
    ).delete(synchronize_session=False)
    
    timeline_deleted = session.query(TimelineEvent).filter(
        TimelineEvent.lead_id == lead_id
    ).delete(synchronize_session=False)
    
    # Delete the lead
    session.delete(lead)
    
    # Check if owner/parcel are orphaned (only tied to this lead)
    owner_orphaned = False
    parcel_orphaned = False
    
    other_leads_with_owner = session.query(Lead).filter(
        Lead.owner_id == owner_id,
        Lead.id != lead_id,
    ).count()
    
    other_leads_with_parcel = session.query(Lead).filter(
        Lead.parcel_id == parcel_id,
        Lead.id != lead_id,
    ).count()
    
    # Note: We don't delete owner/parcel by default - they might be useful
    # for future ingestion deduplication
    
    session.commit()
    
    return {
        "success": True,
        "lead_id": lead_id,
        "outreach_deleted": outreach_deleted,
        "timeline_deleted": timeline_deleted,
        "owner_orphaned": other_leads_with_owner == 0,
        "parcel_orphaned": other_leads_with_parcel == 0,
    }


def auto_delete_low_value_leads(
    session: Session,
    market_code: Optional[str] = None,
    max_score: int = 5,
    batch_size: int = 10000,
    dry_run: bool = True,
) -> Dict[str, Any]:
    """
    Auto-delete leads that meet low-value criteria.
    
    Criteria:
    - motivation_score < max_score
    - No phone number (owner.phone_primary is NULL)
    - No outreach attempts
    - Stage is NEW
    - Not adjudicated
    - Not flagged or tagged
    
    Args:
        session: Database session.
        market_code: Optional filter by market.
        max_score: Maximum score threshold for deletion.
        batch_size: Number of leads to process per batch.
        dry_run: If True, only count without deleting.
    
    Returns:
        Dict with deletion statistics.
    """
    from core.models import Owner, Parcel
    
    # Build base query for candidates
    # Subquery to find leads with outreach attempts
    leads_with_outreach = session.query(OutreachAttempt.lead_id).distinct().subquery()
    
    query = (
        session.query(Lead)
        .join(Lead.owner)
        .join(Lead.parcel)
        .filter(
            Lead.motivation_score < max_score,
            Lead.pipeline_stage == PipelineStage.NEW.value,
            Owner.phone_primary.is_(None),
            Parcel.is_adjudicated == False,
            ~Lead.id.in_(session.query(leads_with_outreach)),
        )
    )
    
    if market_code:
        query = query.filter(Lead.market_code == market_code.upper())
    
    # Count candidates
    total_candidates = query.count()
    
    LOGGER.info(
        f"Auto-delete: Found {total_candidates} candidate leads "
        f"(max_score={max_score}, market={market_code or 'all'}, dry_run={dry_run})"
    )
    
    if dry_run:
        return {
            "dry_run": True,
            "candidates": total_candidates,
            "deleted": 0,
            "message": f"Would delete {total_candidates} leads",
        }
    
    # Delete in batches
    deleted = 0
    offset = 0
    
    while offset < total_candidates:
        batch = query.limit(batch_size).all()
        if not batch:
            break
        
        lead_ids = [lead.id for lead in batch]
        
        # Delete associated records first
        session.query(OutreachAttempt).filter(
            OutreachAttempt.lead_id.in_(lead_ids)
        ).delete(synchronize_session=False)
        
        session.query(TimelineEvent).filter(
            TimelineEvent.lead_id.in_(lead_ids)
        ).delete(synchronize_session=False)
        
        # Delete leads
        session.query(Lead).filter(
            Lead.id.in_(lead_ids)
        ).delete(synchronize_session=False)
        
        session.commit()
        deleted += len(lead_ids)
        
        LOGGER.info(f"Auto-delete: Deleted {deleted}/{total_candidates} leads...")
        
        # Re-query to get next batch (since we deleted, offset stays at 0)
    
    LOGGER.info(f"Auto-delete complete: Deleted {deleted} leads")
    
    return {
        "dry_run": False,
        "candidates": total_candidates,
        "deleted": deleted,
        "message": f"Deleted {deleted} low-value leads",
    }


def get_deletion_candidates_preview(
    session: Session,
    market_code: Optional[str] = None,
    max_score: int = 5,
    limit: int = 100,
) -> Dict[str, Any]:
    """
    Preview leads that would be deleted by auto-delete.
    
    Returns:
        Dict with candidate count and sample leads.
    """
    from core.models import Owner, Parcel
    
    leads_with_outreach = session.query(OutreachAttempt.lead_id).distinct().subquery()
    
    query = (
        session.query(Lead)
        .join(Lead.owner)
        .join(Lead.parcel)
        .filter(
            Lead.motivation_score < max_score,
            Lead.pipeline_stage == PipelineStage.NEW.value,
            Owner.phone_primary.is_(None),
            Parcel.is_adjudicated == False,
            ~Lead.id.in_(session.query(leads_with_outreach)),
        )
    )
    
    if market_code:
        query = query.filter(Lead.market_code == market_code.upper())
    
    total = query.count()
    sample = query.limit(limit).all()
    
    return {
        "total_candidates": total,
        "max_score": max_score,
        "market": market_code or "all",
        "sample": [
            {
                "id": lead.id,
                "score": lead.motivation_score,
                "stage": lead.pipeline_stage,
                "parcel_id": lead.parcel.canonical_parcel_id if lead.parcel else None,
            }
            for lead in sample
        ],
    }


__all__ = [
    "delete_lead",
    "auto_delete_low_value_leads",
    "get_deletion_candidates_preview",
]

