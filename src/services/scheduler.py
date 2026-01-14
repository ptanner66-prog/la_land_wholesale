"""Nightly scheduler service with distributed locking and task tracking."""
from __future__ import annotations

from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from core.config import get_settings
from core.logging_config import get_logger
from core.models import Lead, PipelineStage
from core.utils import utcnow
from services.market import MarketService
from services.timeline import TimelineService
from services.followup import FollowupService
from services.notification import NotificationService
from services.locking import get_scheduler_lock_service
from services.task_tracker import get_task_tracker
from services.outreach_validator import get_outreach_validator

LOGGER = get_logger(__name__)
SETTINGS = get_settings()


class SchedulerService:
    """
    Service for running the nightly pipeline.
    
    FIXED:
    - Uses distributed locking to prevent concurrent runs
    - Actually sends initial outreach messages
    - Tracks task execution for visibility
    """

    LOCK_NAME = "nightly_pipeline"
    LOCK_DURATION = 3600  # 1 hour

    def __init__(self, session: Session):
        """Initialize the scheduler service."""
        self.session = session
        self.timeline = TimelineService(session)
        self.followup = FollowupService(session)
        self.notification = NotificationService(session)
        self.lock_service = get_scheduler_lock_service(session)
        self.task_tracker = get_task_tracker(session)
        self.validator = get_outreach_validator(session)

    def run_nightly_pipeline(
        self,
        markets: Optional[List[str]] = None,
        dry_run: bool = False,
    ) -> Dict:
        """
        Run the full nightly pipeline with distributed locking.
        
        Steps:
        1. Acquire lock (prevent concurrent runs)
        2. Ingest new leads
        3. Enrich leads
        4. Score and update score_details
        5. Send initial outreach for high-priority new leads
        6. Process follow-ups
        7. Classify recent replies
        8. Move pipeline stages as appropriate
        9. Send alerts for HOT or INTERESTED leads
        
        Args:
            markets: List of market codes to process. None = all markets.
            dry_run: If True, don't make actual changes.
            
        Returns:
            Dict with results summary.
        """
        if markets is None:
            markets = MarketService.get_market_codes()
        
        # Try to acquire distributed lock
        with self.lock_service.scheduler_lock(self.LOCK_NAME, self.LOCK_DURATION) as acquired:
            if not acquired:
                LOGGER.warning("Could not acquire scheduler lock - another instance is running")
                return {
                    "error": "lock_not_acquired",
                    "message": "Another pipeline instance is currently running",
                }
            
            # Track task execution
            with self.task_tracker.track_task(
                "nightly_pipeline",
                params={"markets": markets, "dry_run": dry_run},
            ) as task:
                results = {
                    "started_at": utcnow().isoformat(),
                    "markets_processed": markets,
                    "dry_run": dry_run,
                    "steps": {},
                }
                
                LOGGER.info(f"Starting nightly pipeline for markets: {markets}")
                
                for market in markets:
                    market_results = self._process_market(market, dry_run)
                    results["steps"][market] = market_results
                
                results["completed_at"] = utcnow().isoformat()
                task.result = results
                
                LOGGER.info(f"Nightly pipeline complete: {results}")
                
                return results

    def _process_market(self, market_code: str, dry_run: bool) -> Dict:
        """Process pipeline for a single market."""
        LOGGER.info(f"Processing market: {market_code}")
        
        results = {
            "ingestion": None,
            "enrichment": None,
            "scoring": None,
            "outreach": None,
            "followups": None,
            "replies": None,
            "alerts": None,
        }
        
        try:
            # Step 1: Ingest new leads
            results["ingestion"] = self._run_ingestion(market_code, dry_run)
            
            # Step 2: Enrich leads
            results["enrichment"] = self._run_enrichment(market_code, dry_run)
            
            # Step 3: Score leads
            results["scoring"] = self._run_scoring(market_code, dry_run)
            
            # Step 4: Send initial outreach
            results["outreach"] = self._run_initial_outreach(market_code, dry_run)
            
            # Step 5: Process follow-ups
            results["followups"] = self._run_followups(market_code, dry_run)
            
            # Step 6: Classify replies (placeholder - handled by webhook)
            results["replies"] = {"processed": 0, "note": "Handled by webhook"}
            
            # Step 7: Send alerts for hot leads
            results["alerts"] = self._send_hot_lead_alerts(market_code, dry_run)
            
            self.session.commit()
            
        except Exception as e:
            LOGGER.error(f"Error processing market {market_code}: {e}")
            self.session.rollback()
            results["error"] = str(e)
        
        return results

    def _run_ingestion(self, market_code: str, dry_run: bool) -> Dict:
        """Run ingestion for a market."""
        if dry_run:
            return {"status": "skipped", "dry_run": True}
        
        try:
            from ingestion.service import get_ingestion_service
            service = get_ingestion_service(self.session)
            
            result = service.run_full_pipeline(market_code=market_code)
            return result.model_dump() if hasattr(result, 'model_dump') else {"status": "completed"}
        except ImportError:
            LOGGER.warning("Ingestion service not available")
            return {"status": "skipped", "reason": "service_not_available"}
        except Exception as e:
            LOGGER.error(f"Ingestion failed: {e}")
            return {"status": "error", "error": str(e)}

    def _run_enrichment(self, market_code: str, dry_run: bool) -> Dict:
        """Run enrichment for a market."""
        if dry_run:
            return {"status": "skipped", "dry_run": True}
        
        try:
            from enrichment.service import get_enrichment_service
            service = get_enrichment_service(self.session)
            
            leads = self.session.query(Lead).filter(
                Lead.market_code == market_code,
                Lead.pipeline_stage == PipelineStage.NEW.value,
            ).limit(100).all()
            
            enriched = 0
            for lead in leads:
                try:
                    service.enrich_lead(lead.id)
                    enriched += 1
                except Exception as e:
                    LOGGER.warning(f"Failed to enrich lead {lead.id}: {e}")
            
            return {"status": "completed", "enriched": enriched}
        except ImportError:
            return {"status": "skipped", "reason": "service_not_available"}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def _run_scoring(self, market_code: str, dry_run: bool) -> Dict:
        """Run scoring for a market."""
        if dry_run:
            return {"status": "skipped", "dry_run": True}
        
        try:
            from domain.scoring import ScoringService
            service = ScoringService(self.session)
            
            result = service.score_all(market_code=market_code)
            return {"status": "completed", "scored": result.updated}
        except ImportError:
            return {"status": "skipped", "reason": "service_not_available"}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def _run_initial_outreach(self, market_code: str, dry_run: bool) -> Dict:
        """
        Send initial outreach to high-priority new leads.
        
        FIXED: Actually sends messages via OutreachService.
        """
        if dry_run:
            return {"status": "skipped", "dry_run": True}
        
        try:
            config = MarketService.get_market(market_code)
            if not config:
                return {"status": "skipped", "reason": "invalid_market"}
            
            # Find high-priority new leads that haven't been contacted
            leads = self.session.query(Lead).filter(
                Lead.market_code == market_code,
                Lead.pipeline_stage == PipelineStage.NEW.value,
                Lead.motivation_score >= config.min_motivation_score,
                Lead.followup_count == 0,
            ).order_by(Lead.motivation_score.desc()).limit(50).all()
            
            sent = 0
            blocked = 0
            failed = 0
            
            for lead in leads:
                # Validate before sending
                validation = self.validator.validate_can_send(lead)
                if not validation.can_send:
                    blocked += 1
                    continue
                
                try:
                    # Actually send the message
                    from domain.outreach import OutreachService
                    outreach = OutreachService(self.session)
                    result = outreach.send_first_touch(lead.id, context="intro")
                    
                    if result.success:
                        # Schedule followup and update stage
                        self.followup.schedule_initial_followup(lead)
                        lead.pipeline_stage = PipelineStage.CONTACTED.value
                        
                        # Log to timeline
                        self.timeline.log_message_sent(lead.id, "sms", "intro")
                        
                        sent += 1
                    else:
                        failed += 1
                        LOGGER.warning(f"Outreach failed for lead {lead.id}: {result.error}")
                        
                except Exception as e:
                    failed += 1
                    LOGGER.error(f"Failed outreach for lead {lead.id}: {e}")
            
            self.session.flush()
            
            return {
                "status": "completed",
                "sent": sent,
                "blocked": blocked,
                "failed": failed,
                "total_candidates": len(leads),
            }
            
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def _run_followups(self, market_code: str, dry_run: bool) -> Dict:
        """Process follow-ups for a market."""
        def send_message(lead, context):
            """Send message function for followup service."""
            try:
                from domain.outreach import OutreachService
                outreach = OutreachService(self.session)
                result = outreach.send_first_touch(lead.id, context=context)
                
                if result.success:
                    self.timeline.log_message_sent(lead.id, "sms", context)
                    return result.attempt
                return None
            except Exception as e:
                LOGGER.error(f"Failed to send followup: {e}")
                return None
        
        return self.followup.run_followups(
            market_code=market_code,
            send_message_func=send_message if not dry_run else None,
            dry_run=dry_run,
        )

    def _send_hot_lead_alerts(self, market_code: str, dry_run: bool) -> Dict:
        """Send alerts for hot leads."""
        if dry_run:
            return {"status": "skipped", "dry_run": True}
        
        try:
            config = MarketService.get_market(market_code)
            if not config:
                return {"status": "skipped", "reason": "invalid_market"}
            
            # Find hot leads that haven't been alerted recently
            hot_leads = self.session.query(Lead).filter(
                Lead.market_code == market_code,
                Lead.pipeline_stage == PipelineStage.HOT.value,
                Lead.motivation_score >= config.hot_score_threshold,
            ).limit(10).all()
            
            alerts_sent = 0
            alerts_skipped = 0
            
            for lead in hot_leads:
                if self.notification.alert_hot_lead(lead, "High motivation score"):
                    alerts_sent += 1
                    self.timeline.log_alert_sent(lead.id, "hot_lead", "sms/slack")
                else:
                    alerts_skipped += 1
            
            return {
                "status": "completed",
                "alerts_sent": alerts_sent,
                "alerts_skipped": alerts_skipped,
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}


def get_scheduler_service(session: Session) -> SchedulerService:
    """Get a SchedulerService instance."""
    return SchedulerService(session)


__all__ = [
    "SchedulerService",
    "get_scheduler_service",
]
