"""Risk guardrails for outreach volume and quality."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import List, Sequence, Optional

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from core.config import get_settings
from core.logging_config import get_logger
from core.models import Lead, OutreachAttempt

SETTINGS = get_settings()
LOGGER = get_logger(__name__)


def filter_by_min_score(leads: Sequence[Lead], min_score: Optional[int] = None) -> List[Lead]:
    """
    Filter leads by minimum motivation score.

    Args:
        leads: Sequence of Lead objects to filter.
        min_score: Minimum score threshold (uses config default if None).

    Returns:
        List of leads meeting the minimum score threshold.
    """
    min_threshold = min_score if min_score is not None else SETTINGS.min_motivation_score
    filtered = [lead for lead in leads if lead.motivation_score >= min_threshold]
    LOGGER.debug(
        "Score filter: %d/%d leads passed (min_score=%d)",
        len(filtered),
        len(leads),
        min_threshold,
    )
    return filtered


def check_daily_sms_limit(session: Session, count_to_send: int) -> bool:
    """
    Check if sending 'count_to_send' messages would exceed daily limit.
    
    Args:
        session: Database session.
        count_to_send: Number of messages intended to send.
        
    Returns:
        True if safe to send, False if limit exceeded.
    """
    limit = SETTINGS.max_sms_per_day
    
    # Count messages sent today
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    stmt = select(func.count(OutreachAttempt.id)).where(
        OutreachAttempt.created_at >= today_start,
        OutreachAttempt.channel == "sms",
        OutreachAttempt.result == "sent" # Only count actual sends
    )
    
    sent_today = session.scalar(stmt) or 0
    
    if sent_today + count_to_send > limit:
        LOGGER.warning(
            "Daily SMS limit reached. Sent: %d, Limit: %d, Attempting: %d",
            sent_today, limit, count_to_send
        )
        return False
        
    return True
