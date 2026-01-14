"""Metrics endpoints (Prometheus format)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Any

from fastapi import APIRouter, Depends, Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from api.deps import get_readonly_db
from core.config import get_settings
from core.models import Lead, Owner, Parcel, OutreachAttempt

router = APIRouter()
SETTINGS = get_settings()


def _format_prometheus_metric(name: str, value: float, help_text: str, metric_type: str = "gauge") -> str:
    """Format a single metric in Prometheus format."""
    return f"# HELP {name} {help_text}\n# TYPE {name} {metric_type}\n{name} {value}\n"


@router.get("")
async def get_metrics(
    db: Session = Depends(get_readonly_db),
) -> Response:
    """
    Get metrics in Prometheus format.
    
    Returns:
        Prometheus-formatted metrics text.
    """
    metrics = []
    
    # Lead metrics
    total_leads = db.query(func.count(Lead.id)).scalar() or 0
    metrics.append(_format_prometheus_metric(
        "la_land_leads_total",
        total_leads,
        "Total number of leads in the system"
    ))
    
    tcpa_safe_leads = db.query(func.count(Lead.id)).join(Lead.owner).filter(
        Owner.is_tcpa_safe.is_(True)
    ).scalar() or 0
    metrics.append(_format_prometheus_metric(
        "la_land_leads_tcpa_safe",
        tcpa_safe_leads,
        "Number of TCPA-safe leads"
    ))
    
    high_score_leads = db.query(func.count(Lead.id)).filter(
        Lead.motivation_score >= SETTINGS.min_motivation_score
    ).scalar() or 0
    metrics.append(_format_prometheus_metric(
        "la_land_leads_high_score",
        high_score_leads,
        "Number of leads above minimum score threshold"
    ))
    
    avg_score = db.query(func.avg(Lead.motivation_score)).scalar() or 0
    metrics.append(_format_prometheus_metric(
        "la_land_leads_avg_score",
        float(avg_score),
        "Average motivation score across all leads"
    ))
    
    # Owner metrics
    total_owners = db.query(func.count(Owner.id)).scalar() or 0
    metrics.append(_format_prometheus_metric(
        "la_land_owners_total",
        total_owners,
        "Total number of owners"
    ))
    
    owners_with_phone = db.query(func.count(Owner.id)).filter(
        Owner.phone_primary.isnot(None),
        Owner.phone_primary != "",
    ).scalar() or 0
    metrics.append(_format_prometheus_metric(
        "la_land_owners_with_phone",
        owners_with_phone,
        "Number of owners with phone numbers"
    ))
    
    # Parcel metrics
    total_parcels = db.query(func.count(Parcel.id)).scalar() or 0
    metrics.append(_format_prometheus_metric(
        "la_land_parcels_total",
        total_parcels,
        "Total number of parcels"
    ))
    
    adjudicated_parcels = db.query(func.count(Parcel.id)).filter(
        Parcel.is_adjudicated.is_(True)
    ).scalar() or 0
    metrics.append(_format_prometheus_metric(
        "la_land_parcels_adjudicated",
        adjudicated_parcels,
        "Number of adjudicated parcels"
    ))
    
    # Outreach metrics
    total_outreach = db.query(func.count(OutreachAttempt.id)).scalar() or 0
    metrics.append(_format_prometheus_metric(
        "la_land_outreach_total",
        total_outreach,
        "Total number of outreach attempts",
        "counter"
    ))
    
    successful_outreach = db.query(func.count(OutreachAttempt.id)).filter(
        OutreachAttempt.result == "sent"
    ).scalar() or 0
    metrics.append(_format_prometheus_metric(
        "la_land_outreach_sent",
        successful_outreach,
        "Number of successful SMS sends",
        "counter"
    ))
    
    dry_run_outreach = db.query(func.count(OutreachAttempt.id)).filter(
        OutreachAttempt.result == "dry_run"
    ).scalar() or 0
    metrics.append(_format_prometheus_metric(
        "la_land_outreach_dry_run",
        dry_run_outreach,
        "Number of dry-run outreach attempts",
        "counter"
    ))
    
    # Config metrics
    metrics.append(_format_prometheus_metric(
        "la_land_config_dry_run",
        1 if SETTINGS.dry_run else 0,
        "Whether the system is in dry-run mode"
    ))
    
    metrics.append(_format_prometheus_metric(
        "la_land_config_max_sms_per_day",
        SETTINGS.max_sms_per_day,
        "Maximum SMS messages allowed per day"
    ))
    
    metrics.append(_format_prometheus_metric(
        "la_land_config_min_score",
        SETTINGS.min_motivation_score,
        "Minimum motivation score threshold"
    ))
    
    return Response(
        content="\n".join(metrics),
        media_type="text/plain; charset=utf-8",
    )


@router.get("/json")
async def get_metrics_json(
    db: Session = Depends(get_readonly_db),
) -> Dict[str, Any]:
    """
    Get metrics in JSON format.
    
    Returns:
        Metrics as JSON object.
    """
    # Lead metrics
    total_leads = db.query(func.count(Lead.id)).scalar() or 0
    tcpa_safe_leads = db.query(func.count(Lead.id)).join(Lead.owner).filter(
        Owner.is_tcpa_safe.is_(True)
    ).scalar() or 0
    high_score_leads = db.query(func.count(Lead.id)).filter(
        Lead.motivation_score >= SETTINGS.min_motivation_score
    ).scalar() or 0
    avg_score = db.query(func.avg(Lead.motivation_score)).scalar() or 0
    
    # Status breakdown
    status_counts = db.query(Lead.status, func.count(Lead.id)).group_by(Lead.status).all()
    
    # Owner metrics
    total_owners = db.query(func.count(Owner.id)).scalar() or 0
    owners_with_phone = db.query(func.count(Owner.id)).filter(
        Owner.phone_primary.isnot(None),
        Owner.phone_primary != "",
    ).scalar() or 0
    
    # Parcel metrics
    total_parcels = db.query(func.count(Parcel.id)).scalar() or 0
    adjudicated_parcels = db.query(func.count(Parcel.id)).filter(
        Parcel.is_adjudicated.is_(True)
    ).scalar() or 0
    
    # Outreach metrics
    total_outreach = db.query(func.count(OutreachAttempt.id)).scalar() or 0
    successful_outreach = db.query(func.count(OutreachAttempt.id)).filter(
        OutreachAttempt.result == "sent"
    ).scalar() or 0
    
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "leads": {
            "total": total_leads,
            "tcpa_safe": tcpa_safe_leads,
            "high_score": high_score_leads,
            "average_score": round(float(avg_score), 1),
            "by_status": {status: count for status, count in status_counts},
        },
        "owners": {
            "total": total_owners,
            "with_phone": owners_with_phone,
        },
        "parcels": {
            "total": total_parcels,
            "adjudicated": adjudicated_parcels,
        },
        "outreach": {
            "total_attempts": total_outreach,
            "successful": successful_outreach,
        },
        "config": {
            "dry_run": SETTINGS.dry_run,
            "max_sms_per_day": SETTINGS.max_sms_per_day,
            "min_motivation_score": SETTINGS.min_motivation_score,
            "environment": SETTINGS.environment,
        },
    }
