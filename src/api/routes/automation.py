"""Automation routes for scheduler, followups, and alerts."""
from __future__ import annotations

import threading
from typing import Dict, Any, List, Optional

from fastapi import APIRouter, Depends, Query, Body, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from api.deps import get_db, get_readonly_db
from core.logging_config import get_logger
from src.services.background_jobs import (
    create_job, start_job, update_job_progress, 
    complete_job, fail_job, get_job_status
)

router = APIRouter()
LOGGER = get_logger(__name__)


# =============================================================================
# Pydantic Models
# =============================================================================


class RunFollowupsRequest(BaseModel):
    """Request body for running followups."""
    
    market: Optional[str] = Field(None, description="Filter by market code")
    dry_run: bool = Field(False, description="If true, don't actually send messages")
    limit: int = Field(50, ge=1, le=200, description="Max followups to process")


class AlertConfigUpdate(BaseModel):
    """Request body for updating alert configuration."""
    
    enabled: Optional[bool] = None
    hot_score_threshold: Optional[int] = Field(None, ge=0, le=100)
    alert_phone: Optional[str] = None
    slack_webhook_url: Optional[str] = None


class ScoringJobRequest(BaseModel):
    """Request body for scoring job."""
    
    market: Optional[str] = Field(None, description="Filter by market code")
    batch_size: int = Field(1000, ge=100, le=5000, description="Leads per batch")


class AutoDeleteRequest(BaseModel):
    """Request body for auto-delete job."""
    
    market: Optional[str] = Field(None, description="Filter by market code")
    max_score: int = Field(5, ge=0, le=20, description="Max score to delete")
    batch_size: int = Field(10000, ge=1000, le=50000, description="Leads per batch")
    dry_run: bool = Field(True, description="Preview without deleting")


# =============================================================================
# Job Status Routes
# =============================================================================


@router.get("/status/{job_id}")
async def get_automation_job_status(job_id: str) -> Dict[str, Any]:
    """
    Get the status of a background job.
    
    Returns progress, counts, and result when complete.
    """
    status = get_job_status(job_id)
    if not status:
        raise HTTPException(status_code=404, detail="Job not found")
    return status


# =============================================================================
# Scoring Routes
# =============================================================================


def _run_scoring_job(job_id: str, market: Optional[str], batch_size: int) -> None:
    """Background task to run chunked scoring."""
    from core.db import SessionLocal
    from sqlalchemy import func
    from core.models import Lead
    from domain.scoring import ScoringService
    
    session = SessionLocal()
    try:
        # Count total leads
        count_query = session.query(func.count(Lead.id)).join(Lead.parcel).join(Lead.owner)
        if market:
            count_query = count_query.filter(Lead.market_code == market.upper())
        total_count = count_query.scalar() or 0
        
        start_job(job_id, total_count)
        LOGGER.info(f"[{job_id}] Starting scoring job for {total_count} leads")
        
        service = ScoringService(session)
        result = service.score_all(market_code=market, batch_size=batch_size)
        
        complete_job(job_id, result.to_dict())
        LOGGER.info(f"[{job_id}] Scoring complete: {result.updated} leads scored")
        
    except Exception as e:
        LOGGER.exception(f"[{job_id}] Scoring job failed: {e}")
        fail_job(job_id, str(e))
    finally:
        session.close()


@router.post("/scoring/start")
async def start_scoring_job(
    body: ScoringJobRequest = Body(default=ScoringJobRequest()),
) -> Dict[str, Any]:
    """
    Start a background scoring job.
    
    Returns immediately with a job_id that can be polled for status.
    """
    job_id = create_job("scoring")
    
    # Start in background thread
    thread = threading.Thread(
        target=_run_scoring_job,
        args=(job_id, body.market, body.batch_size),
        daemon=True,
    )
    thread.start()
    
    return {
        "job_id": job_id,
        "status": "started",
        "message": f"Scoring job started for market: {body.market or 'all'}",
    }


# =============================================================================
# Auto-Delete Routes
# =============================================================================


def _run_auto_delete_job(
    job_id: str, 
    market: Optional[str], 
    max_score: int, 
    batch_size: int,
    dry_run: bool,
) -> None:
    """Background task to auto-delete low-value leads."""
    from core.db import SessionLocal
    from services.lead_cleanup import auto_delete_low_value_leads
    
    session = SessionLocal()
    try:
        start_job(job_id, 0)  # Total unknown until we query
        LOGGER.info(f"[{job_id}] Starting auto-delete job (dry_run={dry_run})")
        
        result = auto_delete_low_value_leads(
            session=session,
            market_code=market,
            max_score=max_score,
            batch_size=batch_size,
            dry_run=dry_run,
        )
        
        complete_job(job_id, result)
        LOGGER.info(f"[{job_id}] Auto-delete complete: {result.get('deleted', 0)} leads deleted")
        
    except Exception as e:
        LOGGER.exception(f"[{job_id}] Auto-delete job failed: {e}")
        fail_job(job_id, str(e))
    finally:
        session.close()


@router.post("/auto-delete/start")
async def start_auto_delete_job(
    body: AutoDeleteRequest = Body(default=AutoDeleteRequest()),
) -> Dict[str, Any]:
    """
    Start a background job to auto-delete low-value leads.
    
    Criteria for deletion:
    - motivation_score < max_score
    - No phone number
    - No outreach attempts
    - Stage is NEW
    - Not adjudicated
    """
    job_id = create_job("auto_delete")
    
    thread = threading.Thread(
        target=_run_auto_delete_job,
        args=(job_id, body.market, body.max_score, body.batch_size, body.dry_run),
        daemon=True,
    )
    thread.start()
    
    return {
        "job_id": job_id,
        "status": "started",
        "dry_run": body.dry_run,
        "message": f"Auto-delete job started (max_score={body.max_score}, dry_run={body.dry_run})",
    }


# =============================================================================
# Followup Routes
# =============================================================================


@router.post("/run_followups")
async def run_followups(
    body: RunFollowupsRequest = Body(default=RunFollowupsRequest()),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Run followups for leads that are due."""
    from services.followup import get_followup_service
    from domain.outreach import OutreachService
    
    followup_service = get_followup_service(db)
    outreach_service = OutreachService(db)
    
    # Define message sending function
    def send_message(lead, context):
        result = outreach_service.send_first_touch(lead.id, context=context)
        return result if result.success else None
    
    results = followup_service.run_followups(
        market_code=body.market,
        send_message_func=send_message if not body.dry_run else None,
        dry_run=body.dry_run,
        limit=body.limit,
    )
    
    db.commit()
    
    return results


# =============================================================================
# Scheduler Routes
# =============================================================================


@router.post("/run_nightly")
async def run_nightly_pipeline(
    markets: Optional[List[str]] = Query(default=None, description="Markets to process"),
    dry_run: bool = Query(default=False, description="If true, don't make changes"),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Run the nightly automation pipeline."""
    from services.scheduler import get_scheduler_service
    
    scheduler = get_scheduler_service(db)
    results = scheduler.run_nightly_pipeline(markets=markets, dry_run=dry_run)
    
    db.commit()
    
    return results


# =============================================================================
# Alert Routes
# =============================================================================


@router.get("/alerts/config")
async def get_alert_configs(
    db: Session = Depends(get_readonly_db),
) -> List[Dict[str, Any]]:
    """Get alert configurations for all markets."""
    from core.models import AlertConfig
    
    configs = db.query(AlertConfig).all()
    
    return [
        {
            "market_code": c.market_code,
            "enabled": c.enabled,
            "hot_score_threshold": c.hot_score_threshold,
            "alert_phone": c.alert_phone,
            "slack_webhook_url": c.slack_webhook_url if c.slack_webhook_url else None,
        }
        for c in configs
    ]


@router.get("/alerts/config/{market_code}")
async def get_alert_config(
    market_code: str,
    db: Session = Depends(get_readonly_db),
) -> Dict[str, Any]:
    """Get alert configuration for a specific market."""
    from core.models import AlertConfig
    
    config = db.query(AlertConfig).filter(
        AlertConfig.market_code == market_code.upper()
    ).first()
    
    if not config:
        raise HTTPException(status_code=404, detail="Alert config not found")
    
    return {
        "market_code": config.market_code,
        "enabled": config.enabled,
        "hot_score_threshold": config.hot_score_threshold,
        "alert_phone": config.alert_phone,
        "slack_webhook_url": config.slack_webhook_url if config.slack_webhook_url else None,
    }


@router.put("/alerts/config/{market_code}")
async def update_alert_config(
    market_code: str,
    body: AlertConfigUpdate,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Update alert configuration for a market."""
    from services.notification import get_notification_service
    
    service = get_notification_service(db)
    config = service.update_alert_config(
        market_code=market_code.upper(),
        enabled=body.enabled,
        hot_score_threshold=body.hot_score_threshold,
        alert_phone=body.alert_phone,
        slack_webhook_url=body.slack_webhook_url,
    )
    
    db.commit()
    
    return {
        "market_code": config.market_code,
        "enabled": config.enabled,
        "hot_score_threshold": config.hot_score_threshold,
        "alert_phone": config.alert_phone,
        "slack_webhook_url": config.slack_webhook_url if config.slack_webhook_url else None,
        "success": True,
    }


@router.post("/alerts/test")
async def send_test_alert(
    market: str = Query(..., description="Market code to send test alert for"),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Send a test alert for a market."""
    from services.notification import get_notification_service
    
    service = get_notification_service(db)
    result = service.send_test_alert(market.upper())
    
    return result


@router.get("/alerts")
async def get_alerts(
    market: Optional[str] = Query(default=None, description="Filter by market code"),
    limit: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_readonly_db),
) -> Dict[str, Any]:
    """
    Get actionable alerts for the dashboard.
    
    Returns hot leads, high-score leads needing attention, and followups due.
    """
    from sqlalchemy import func, and_
    from core.models import Lead, Owner, Parcel, Party, PipelineStage
    from core.config import get_settings
    from core.utils import utcnow
    
    settings = get_settings()
    alerts = []
    
    from scoring.deterministic_engine import HOT_THRESHOLD, CONTACT_THRESHOLD
    
    # Query for hot leads (high priority) - use score-based classification
    hot_query = (
        db.query(Lead)
        .join(Lead.owner)
        .join(Owner.party)
        .join(Lead.parcel)
        .filter(
            Lead.deleted_at.is_(None),
            Lead.motivation_score >= HOT_THRESHOLD,
        )
    )
    if market:
        hot_query = hot_query.filter(Lead.market_code == market.upper())
    
    hot_leads = hot_query.order_by(Lead.motivation_score.desc()).limit(limit).all()
    
    for lead in hot_leads:
        alerts.append({
            "type": "hot_lead",
            "priority": "high",
            "lead_id": lead.id,
            "title": f"Hot Lead: {lead.owner.party.display_name if lead.owner and lead.owner.party else 'Unknown'}",
            "description": f"Score: {lead.motivation_score} | {lead.parcel.parish if lead.parcel else 'Unknown parish'}",
            "market_code": lead.market_code,
            "created_at": lead.updated_at.isoformat() if lead.updated_at else lead.created_at.isoformat(),
        })
    
    # Query for high-score leads not yet contacted (use score-based classification)
    high_score_query = (
        db.query(Lead)
        .join(Lead.owner)
        .join(Owner.party)
        .join(Lead.parcel)
        .filter(
            Lead.deleted_at.is_(None),
            Lead.motivation_score >= CONTACT_THRESHOLD,
            Lead.motivation_score < HOT_THRESHOLD,  # Contact-ready but not hot
            Lead.pipeline_stage.notin_([PipelineStage.CONTACTED.value, PipelineStage.OFFER.value, PipelineStage.CONTRACT.value]),
        )
    )
    if market:
        high_score_query = high_score_query.filter(Lead.market_code == market.upper())
    
    high_score_leads = high_score_query.order_by(Lead.motivation_score.desc()).limit(limit).all()
    
    for lead in high_score_leads:
        alerts.append({
            "type": "high_score",
            "priority": "medium",
            "lead_id": lead.id,
            "title": f"High Score Lead: {lead.owner.party.display_name if lead.owner and lead.owner.party else 'Unknown'}",
            "description": f"Score: {lead.motivation_score} - needs outreach",
            "market_code": lead.market_code,
            "created_at": lead.created_at.isoformat() if lead.created_at else None,
        })
    
    # Query for followups due
    now = utcnow()
    followup_query = (
        db.query(Lead)
        .join(Lead.owner)
        .join(Owner.party)
        .filter(
            Lead.next_followup_at.isnot(None),
            Lead.next_followup_at <= now,
        )
    )
    if market:
        followup_query = followup_query.filter(Lead.market_code == market.upper())
    
    followup_leads = followup_query.order_by(Lead.next_followup_at).limit(limit).all()
    
    for lead in followup_leads:
        alerts.append({
            "type": "followup_due",
            "priority": "medium",
            "lead_id": lead.id,
            "title": f"Followup Due: {lead.owner.party.display_name if lead.owner and lead.owner.party else 'Unknown'}",
            "description": f"Followup #{lead.followup_count + 1} overdue",
            "market_code": lead.market_code,
            "created_at": lead.next_followup_at.isoformat() if lead.next_followup_at else None,
        })
    
    # Sort by priority and limit
    priority_order = {"high": 0, "medium": 1, "low": 2}
    alerts.sort(key=lambda x: priority_order.get(x["priority"], 2))
    
    return {
        "total": len(alerts),
        "alerts": alerts[:limit],
        "counts": {
            "hot_leads": len(hot_leads),
            "high_score": len(high_score_leads),
            "followups_due": len(followup_leads),
        },
    }
