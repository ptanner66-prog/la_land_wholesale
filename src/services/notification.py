"""Notification service for hot lead alerts with deduplication."""
from __future__ import annotations

from datetime import timedelta
from typing import Optional

import httpx
from sqlalchemy.orm import Session

from core.config import get_settings
from core.logging_config import get_logger
from core.models import AlertConfig, Lead
from core.utils import utcnow, CircuitBreaker, RateLimiter

LOGGER = get_logger(__name__)
SETTINGS = get_settings()


# Circuit breakers for external services
_twilio_circuit = CircuitBreaker(name="twilio_alerts", failure_threshold=3, recovery_timeout=300)
_slack_circuit = CircuitBreaker(name="slack_alerts", failure_threshold=3, recovery_timeout=300)

# Rate limiter for alerts (max 10 per minute)
_alert_rate_limiter = RateLimiter(max_calls=10, period_seconds=60)


class NotificationService:
    """
    Service for sending alerts and notifications.
    
    FIXED: Implements alert deduplication to prevent duplicate alerts.
    """

    # Default deduplication window (hours)
    DEFAULT_DEDUP_HOURS = 24

    def __init__(self, session: Session):
        """Initialize the notification service."""
        self.session = session
        self.twilio_circuit = _twilio_circuit
        self.slack_circuit = _slack_circuit
        self.rate_limiter = _alert_rate_limiter

    def get_alert_config(self, market_code: str) -> Optional[AlertConfig]:
        """Get alert configuration for a market."""
        return self.session.query(AlertConfig).filter(
            AlertConfig.market_code == market_code
        ).first()

    def _should_alert(self, lead: Lead, config: AlertConfig) -> bool:
        """
        Check if we should send an alert for this lead.
        
        FIXED: Implements deduplication based on last_alerted_at.
        
        Args:
            lead: The lead to check.
            config: Alert configuration.
            
        Returns:
            True if alert should be sent, False if it should be skipped.
        """
        if not config.enabled:
            return False
        
        # Check deduplication window
        dedup_hours = config.dedup_hours or self.DEFAULT_DEDUP_HOURS
        
        if lead.last_alerted_at:
            time_since_alert = utcnow() - lead.last_alerted_at
            if time_since_alert < timedelta(hours=dedup_hours):
                LOGGER.debug(
                    f"Alert skipped for lead {lead.id}: "
                    f"last alerted {time_since_alert.total_seconds() / 3600:.1f} hours ago"
                )
                return False
        
        # Check rate limit
        if not self.rate_limiter.can_proceed():
            LOGGER.warning("Alert rate limit reached")
            return False
        
        return True

    def _mark_alerted(self, lead: Lead) -> None:
        """Mark a lead as having been alerted."""
        lead.last_alerted_at = utcnow()
        self.session.flush()

    def send_sms_alert(
        self,
        phone: str,
        message: str,
        dry_run: bool = False,
    ) -> bool:
        """
        Send an SMS alert via Twilio.
        
        Args:
            phone: Phone number to send to.
            message: Message content.
            dry_run: If True, don't actually send.
            
        Returns:
            True if sent successfully.
        """
        if dry_run or SETTINGS.dry_run:
            LOGGER.info(f"[DRY RUN] SMS alert to {phone}: {message[:50]}...")
            return True
        
        if not SETTINGS.is_twilio_enabled():
            LOGGER.warning("Twilio not configured, cannot send SMS alert")
            return False
        
        if not self.twilio_circuit.can_execute():
            LOGGER.warning("Twilio circuit breaker is open")
            return False
        
        try:
            from outreach import get_twilio_client
            client = get_twilio_client()
            client.send_sms(to=phone, body=message)
            
            self.twilio_circuit.record_success()
            self.rate_limiter.record_call()
            
            LOGGER.info(f"Sent SMS alert to {phone}")
            return True
        except Exception as e:
            self.twilio_circuit.record_failure()
            LOGGER.error(f"Failed to send SMS alert: {e}")
            return False

    def send_slack_alert(
        self,
        webhook_url: str,
        message: str,
        dry_run: bool = False,
    ) -> bool:
        """
        Send a Slack alert via webhook.
        
        Args:
            webhook_url: Slack webhook URL.
            message: Message content.
            dry_run: If True, don't actually send.
            
        Returns:
            True if sent successfully.
        """
        if dry_run or SETTINGS.dry_run:
            LOGGER.info(f"[DRY RUN] Slack alert: {message[:50]}...")
            return True
        
        if not self.slack_circuit.can_execute():
            LOGGER.warning("Slack circuit breaker is open")
            return False
        
        try:
            response = httpx.post(
                webhook_url,
                json={"text": message},
                timeout=10,
            )
            response.raise_for_status()
            
            self.slack_circuit.record_success()
            self.rate_limiter.record_call()
            
            LOGGER.info("Sent Slack alert")
            return True
        except Exception as e:
            self.slack_circuit.record_failure()
            LOGGER.error(f"Failed to send Slack alert: {e}")
            return False

    def alert_hot_lead(self, lead: Lead, reason: str) -> bool:
        """
        Send alert for a hot lead.
        
        FIXED: Implements deduplication.
        
        Args:
            lead: The hot lead.
            reason: Why the lead is hot.
            
        Returns:
            True if any alert was sent successfully.
        """
        config = self.get_alert_config(lead.market_code)
        if not config:
            LOGGER.debug(f"No alert config for market {lead.market_code}")
            return False
        
        # Check if we should alert (deduplication)
        if not self._should_alert(lead, config):
            return False
        
        # Build alert message
        owner_name = lead.owner.party.display_name if lead.owner and lead.owner.party else "Unknown"
        address = lead.parcel.situs_address if lead.parcel else "Unknown"
        
        message = (
            f"🔥 HOT LEAD ALERT ({lead.market_code})\n\n"
            f"Owner: {owner_name}\n"
            f"Property: {address}\n"
            f"Score: {lead.motivation_score}\n"
            f"Reason: {reason}\n\n"
            f"Lead ID: {lead.id}"
        )
        
        sent = False
        
        # Try SMS
        if config.alert_phone:
            if self.send_sms_alert(config.alert_phone, message):
                sent = True
        
        # Try Slack
        if config.slack_webhook_url:
            if self.send_slack_alert(config.slack_webhook_url, message):
                sent = True
        
        # Mark as alerted if anything was sent
        if sent:
            self._mark_alerted(lead)
        
        return sent

    def alert_interested_reply(
        self,
        lead: Lead,
        classification: str,
        reply_text: str,
    ) -> bool:
        """
        Send alert for an interested reply.
        
        FIXED: Implements deduplication.
        
        Args:
            lead: The lead that replied.
            classification: The reply classification.
            reply_text: The reply text.
            
        Returns:
            True if any alert was sent successfully.
        """
        config = self.get_alert_config(lead.market_code)
        if not config:
            return False
        
        # Check if we should alert (deduplication)
        if not self._should_alert(lead, config):
            return False
        
        owner_name = lead.owner.party.display_name if lead.owner and lead.owner.party else "Unknown"
        
        message = (
            f"📬 {classification} REPLY ({lead.market_code})\n\n"
            f"Owner: {owner_name}\n"
            f"Score: {lead.motivation_score}\n"
            f"Reply: {reply_text[:200]}\n\n"
            f"Lead ID: {lead.id}"
        )
        
        sent = False
        
        if config.alert_phone:
            if self.send_sms_alert(config.alert_phone, message):
                sent = True
        
        if config.slack_webhook_url:
            if self.send_slack_alert(config.slack_webhook_url, message):
                sent = True
        
        if sent:
            self._mark_alerted(lead)
        
        return sent

    def send_test_alert(self, market_code: str) -> dict:
        """
        Send a test alert for a market.
        
        Args:
            market_code: Market to send test alert for.
            
        Returns:
            Dict with results.
        """
        config = self.get_alert_config(market_code)
        if not config:
            return {"success": False, "error": "No alert config found"}
        
        message = f"🧪 Test alert from LA Land Wholesale ({market_code})"
        
        results = {"sms": None, "slack": None}
        
        if config.alert_phone:
            results["sms"] = self.send_sms_alert(config.alert_phone, message)
        
        if config.slack_webhook_url:
            results["slack"] = self.send_slack_alert(config.slack_webhook_url, message)
        
        return {
            "success": any(v for v in results.values() if v is not None),
            "results": results,
        }

    def update_alert_config(
        self,
        market_code: str,
        enabled: Optional[bool] = None,
        hot_score_threshold: Optional[int] = None,
        alert_phone: Optional[str] = None,
        slack_webhook_url: Optional[str] = None,
        dedup_hours: Optional[int] = None,
    ) -> AlertConfig:
        """
        Update alert configuration for a market.
        
        Args:
            market_code: Market code to update.
            enabled: Whether alerts are enabled.
            hot_score_threshold: Score threshold for hot leads.
            alert_phone: Phone number for SMS alerts.
            slack_webhook_url: Slack webhook URL.
            dedup_hours: Deduplication window in hours.
            
        Returns:
            Updated AlertConfig.
        """
        config = self.get_alert_config(market_code)
        if not config:
            config = AlertConfig(market_code=market_code)
            self.session.add(config)
        
        if enabled is not None:
            config.enabled = enabled
        if hot_score_threshold is not None:
            config.hot_score_threshold = hot_score_threshold
        if alert_phone is not None:
            config.alert_phone = alert_phone
        if slack_webhook_url is not None:
            config.slack_webhook_url = slack_webhook_url
        if dedup_hours is not None:
            config.dedup_hours = dedup_hours
        
        self.session.flush()
        return config


def get_notification_service(session: Session) -> NotificationService:
    """Get a NotificationService instance."""
    return NotificationService(session)


__all__ = [
    "NotificationService",
    "get_notification_service",
]
