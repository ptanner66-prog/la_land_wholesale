"""Logic for selecting leads for outreach."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy import and_, func, not_, or_, select
from sqlalchemy.orm import Session

from core.config import get_settings
from core.logging_config import get_logger
from core.models import Lead, OutreachAttempt, Owner

LOGGER = get_logger(__name__)
SETTINGS = get_settings()


def select_leads_for_first_touch(
    session: Session,
    limit: int = 50,
    min_score: Optional[int] = None,
    cooldown_days: Optional[int] = None,
) -> List[Lead]:
    """
    Select high-priority leads for first contact.

    Criteria:
    - Status is 'new'
    - Motivation score >= min_score
    - Owner is TCPA safe
    - Owner has not opted out
    - No outreach attempts in last cooldown_days (for this lead)
    
    Args:
        session: Database session.
        limit: Max leads to return.
        min_score: Minimum motivation score (defaults to settings).
        cooldown_days: Minimum days since last contact (defaults to settings).

    Returns:
        List of eligible Lead objects.
    """
    score_threshold = min_score if min_score is not None else SETTINGS.min_motivation_score
    cooldown = cooldown_days if cooldown_days is not None else SETTINGS.outreach_cooldown_days
    
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=cooldown)

    # Subquery to find leads recently contacted
    recent_outreach = (
        select(OutreachAttempt.lead_id)
        .where(OutreachAttempt.created_at >= cutoff_date)
        .scalar_subquery()
    )

    stmt = (
        select(Lead)
        .join(Lead.owner)
        .where(
            and_(
                Lead.status == "new",
                Lead.motivation_score >= score_threshold,
                Owner.is_tcpa_safe.is_(True),
                Owner.opt_out.is_(False),
                Owner.is_dnr.is_(False),
                Owner.phone_primary.isnot(None),
                not_(Lead.id.in_(recent_outreach)),
            )
        )
        .order_by(Lead.motivation_score.desc(), Lead.created_at.asc())
        .limit(limit)
    )

    return session.scalars(stmt).all()
