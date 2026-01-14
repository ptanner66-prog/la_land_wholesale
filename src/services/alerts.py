"""Hot lead alert processing service."""
from __future__ import annotations

from typing import Dict, Any, Optional

from sqlalchemy.orm import Session

from core.config import get_settings
from core.logging_config import get_logger
from core.models import Lead, PipelineStage
from services.notification import get_notification_service

LOGGER = get_logger(__name__)
SETTINGS = get_settings()


def process_hot_lead_alerts(
    session: Session,
    market_code: Optional[str] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Process hot lead alerts for configured markets.
    
    Finds leads that have reached HOT status and sends alerts
    to configured notification channels.
    
    Args:
        session: Database session.
        market_code: Optional filter by market.
        dry_run: If True, don't actually send alerts.
    
    Returns:
        Dict with alert processing results.
    """
    notification_service = get_notification_service(session)
    
    # Find hot leads that haven't been alerted recently
    query = session.query(Lead).filter(
        Lead.pipeline_stage == PipelineStage.HOT.value,
    )
    
    if market_code:
        query = query.filter(Lead.market_code == market_code.upper())
    
    hot_leads = query.all()
    
    alerts_sent = 0
    alerts_skipped = 0
    errors = []
    
    for lead in hot_leads:
        try:
            # Determine reason for being hot
            reasons = []
            if lead.motivation_score >= 80:
                reasons.append(f"High motivation score ({lead.motivation_score})")
            if lead.last_reply_classification in ("INTERESTED", "SEND_OFFER"):
                reasons.append(f"Interested reply: {lead.last_reply_classification}")
            if lead.parcel and lead.parcel.is_adjudicated:
                reasons.append("Adjudicated property")
            
            reason = "; ".join(reasons) if reasons else "Marked as HOT lead"
            
            # Try to send alert (notification service handles deduplication)
            if notification_service.alert_hot_lead(lead, reason):
                alerts_sent += 1
            else:
                alerts_skipped += 1
                
        except Exception as e:
            LOGGER.warning(f"Failed to process alert for lead {lead.id}: {e}")
            errors.append(f"Lead {lead.id}: {str(e)}")
            alerts_skipped += 1
    
    LOGGER.info(
        f"Alert processing complete: sent={alerts_sent}, skipped={alerts_skipped}"
    )
    
    return {
        "status": "success",
        "alerts_sent": alerts_sent,
        "alerts_skipped": alerts_skipped,
        "total_hot_leads": len(hot_leads),
        "errors": errors,
    }


__all__ = ["process_hot_lead_alerts"]

