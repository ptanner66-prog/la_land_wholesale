"""Timeline service for tracking lead activity."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from core.models import TimelineEvent, Lead
from core.logging_config import get_logger
from core.utils import utcnow

LOGGER = get_logger(__name__)


class TimelineEventType:
    """Constants for timeline event types."""
    LEAD_CREATED = "lead_created"
    ENRICHMENT_DONE = "enrichment_done"
    SCORE_UPDATED = "score_updated"
    STAGE_CHANGED = "stage_changed"
    MESSAGE_SENT = "message_sent"
    REPLY_RECEIVED = "reply_received"
    REPLY_CLASSIFIED = "reply_classified"
    OFFER_CALCULATED = "offer_calculated"
    COMPS_FETCHED = "comps_fetched"
    ALERT_SENT = "alert_sent"
    OPT_OUT = "opt_out"
    FOLLOWUP_SCHEDULED = "followup_scheduled"


class TimelineService:
    """Service for managing lead timeline events."""

    def __init__(self, session: Session):
        """Initialize the timeline service."""
        self.session = session

    def add_event(
        self,
        lead_id: int,
        event_type: str,
        title: str,
        description: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> TimelineEvent:
        """
        Add a timeline event for a lead.
        
        Args:
            lead_id: ID of the lead.
            event_type: Type of event (use TimelineEventType constants).
            title: Short title for the event.
            description: Optional longer description.
            metadata: Optional JSON metadata.
            
        Returns:
            The created TimelineEvent.
        """
        event = TimelineEvent(
            lead_id=lead_id,
            event_type=event_type,
            title=title,
            description=description,
            event_metadata=metadata or {},
            created_at=utcnow(),
        )
        self.session.add(event)
        self.session.flush()
        
        LOGGER.debug(f"Added timeline event: {event_type} for lead {lead_id}")
        return event

    def get_lead_timeline(
        self,
        lead_id: int,
        limit: int = 50,
        event_type: Optional[str] = None,
    ) -> List[TimelineEvent]:
        """
        Get timeline events for a lead.
        
        Args:
            lead_id: ID of the lead.
            limit: Maximum number of events to return.
            event_type: Optional filter by event type.
            
        Returns:
            List of TimelineEvent objects, newest first.
        """
        query = self.session.query(TimelineEvent).filter(
            TimelineEvent.lead_id == lead_id
        )
        
        if event_type:
            query = query.filter(TimelineEvent.event_type == event_type)
        
        return query.order_by(TimelineEvent.created_at.desc()).limit(limit).all()

    def log_lead_created(self, lead: Lead) -> TimelineEvent:
        """Log lead creation event."""
        return self.add_event(
            lead_id=lead.id,
            event_type=TimelineEventType.LEAD_CREATED,
            title="Lead created",
            description=f"Lead created in {lead.market_code} market",
            metadata={
                "market_code": lead.market_code,
                "owner_id": lead.owner_id,
                "parcel_id": lead.parcel_id,
            },
        )

    def log_enrichment(self, lead_id: int, services_used: List[str]) -> TimelineEvent:
        """Log enrichment completion event."""
        return self.add_event(
            lead_id=lead_id,
            event_type=TimelineEventType.ENRICHMENT_DONE,
            title="Data enriched",
            description=f"Enriched with: {', '.join(services_used)}",
            metadata={"services": services_used},
        )

    def log_score_update(
        self,
        lead_id: int,
        old_score: int,
        new_score: int,
        score_details: Optional[Dict] = None,
    ) -> TimelineEvent:
        """Log score update event."""
        return self.add_event(
            lead_id=lead_id,
            event_type=TimelineEventType.SCORE_UPDATED,
            title=f"Score updated: {old_score} → {new_score}",
            description=f"Motivation score changed from {old_score} to {new_score}",
            metadata={
                "old_score": old_score,
                "new_score": new_score,
                "details": score_details,
            },
        )

    def log_stage_change(
        self,
        lead_id: int,
        old_stage: str,
        new_stage: str,
        reason: Optional[str] = None,
    ) -> TimelineEvent:
        """Log pipeline stage change event."""
        return self.add_event(
            lead_id=lead_id,
            event_type=TimelineEventType.STAGE_CHANGED,
            title=f"Stage: {old_stage} → {new_stage}",
            description=reason or f"Pipeline stage changed from {old_stage} to {new_stage}",
            metadata={
                "old_stage": old_stage,
                "new_stage": new_stage,
                "reason": reason,
            },
        )

    def log_message_sent(
        self,
        lead_id: int,
        channel: str,
        context: str,
        message_preview: Optional[str] = None,
    ) -> TimelineEvent:
        """Log outreach message sent event."""
        return self.add_event(
            lead_id=lead_id,
            event_type=TimelineEventType.MESSAGE_SENT,
            title=f"{context.title()} message sent via {channel.upper()}",
            description=message_preview[:100] if message_preview else None,
            metadata={
                "channel": channel,
                "context": context,
            },
        )

    def log_reply_received(
        self,
        lead_id: int,
        reply_text: str,
        classification: Optional[str] = None,
    ) -> TimelineEvent:
        """Log reply received event."""
        return self.add_event(
            lead_id=lead_id,
            event_type=TimelineEventType.REPLY_RECEIVED,
            title=f"Reply received" + (f" ({classification})" if classification else ""),
            description=reply_text[:200] if reply_text else None,
            metadata={
                "classification": classification,
                "reply_length": len(reply_text) if reply_text else 0,
            },
        )

    def log_offer_calculated(
        self,
        lead_id: int,
        recommended_offer: float,
        low_offer: float,
        high_offer: float,
    ) -> TimelineEvent:
        """Log offer calculation event."""
        return self.add_event(
            lead_id=lead_id,
            event_type=TimelineEventType.OFFER_CALCULATED,
            title=f"Offer calculated: ${recommended_offer:,.0f}",
            description=f"Range: ${low_offer:,.0f} - ${high_offer:,.0f}",
            metadata={
                "recommended": recommended_offer,
                "low": low_offer,
                "high": high_offer,
            },
        )

    def log_comps_fetched(
        self,
        lead_id: int,
        comp_count: int,
        avg_price_per_acre: Optional[float] = None,
    ) -> TimelineEvent:
        """Log comps fetch event."""
        return self.add_event(
            lead_id=lead_id,
            event_type=TimelineEventType.COMPS_FETCHED,
            title=f"Fetched {comp_count} comps",
            description=f"Avg price/acre: ${avg_price_per_acre:,.0f}" if avg_price_per_acre else None,
            metadata={
                "comp_count": comp_count,
                "avg_price_per_acre": avg_price_per_acre,
            },
        )

    def log_alert_sent(
        self,
        lead_id: int,
        alert_type: str,
        channel: str,
    ) -> TimelineEvent:
        """Log alert sent event."""
        return self.add_event(
            lead_id=lead_id,
            event_type=TimelineEventType.ALERT_SENT,
            title=f"Alert sent: {alert_type}",
            description=f"Alert sent via {channel}",
            metadata={
                "alert_type": alert_type,
                "channel": channel,
            },
        )

    def log_opt_out(
        self,
        lead_id: int,
        reason: str,
        reply_text: Optional[str] = None,
    ) -> TimelineEvent:
        """Log opt-out event."""
        return self.add_event(
            lead_id=lead_id,
            event_type=TimelineEventType.OPT_OUT,
            title="Owner opted out",
            description=reason,
            metadata={
                "reason": reason,
                "reply_preview": reply_text[:100] if reply_text else None,
            },
        )

    def log_followup_scheduled(
        self,
        lead_id: int,
        followup_date: str,
        followup_number: int,
    ) -> TimelineEvent:
        """Log followup scheduling event."""
        return self.add_event(
            lead_id=lead_id,
            event_type=TimelineEventType.FOLLOWUP_SCHEDULED,
            title=f"Followup #{followup_number} scheduled",
            description=f"Scheduled for {followup_date}",
            metadata={
                "followup_date": followup_date,
                "followup_number": followup_number,
            },
        )


def get_timeline_service(session: Session) -> TimelineService:
    """Get a TimelineService instance."""
    return TimelineService(session)


__all__ = [
    "TimelineService",
    "TimelineEventType",
    "get_timeline_service",
]
