"""Job scheduler for automated daily workflows."""
from __future__ import annotations

import signal
import sys
import time
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from core.config import get_settings
from core.logging_config import get_logger, setup_logging
from scheduler.jobs import run_daily_pipeline, run_scoring_job, run_outreach_job

LOGGER = get_logger(__name__)
SETTINGS = get_settings()

# Global scheduler instance
_scheduler: Optional[BackgroundScheduler] = None


def run_daily_scoring() -> None:
    """Run daily lead scoring."""
    LOGGER.info("Starting scheduled scoring job...")
    try:
        result = run_scoring_job()
        LOGGER.info("Scheduled scoring job completed: %s", result.get("success"))
    except Exception as e:
        LOGGER.error(f"Scheduled scoring job failed: {e}")


def run_daily_outreach() -> None:
    """Run daily outreach batch."""
    LOGGER.info("Starting scheduled outreach job...")
    try:
        result = run_outreach_job()
        LOGGER.info("Scheduled outreach job completed: %s", result.get("success"))
    except Exception as e:
        LOGGER.error(f"Scheduled outreach job failed: {e}")


def run_full_daily_pipeline() -> None:
    """Run the complete daily pipeline: ingestion → scoring → outreach."""
    LOGGER.info("Starting scheduled daily pipeline...")
    try:
        result = run_daily_pipeline(
            run_ingestion=True,
            run_scoring=True,
            run_outreach=True,
        )
        LOGGER.info("Daily pipeline completed: %s", result.get("success"))
    except Exception as e:
        LOGGER.error(f"Daily pipeline failed: {e}")


def start_scheduler() -> BackgroundScheduler:
    """
    Start the background scheduler with configured jobs.
    
    Returns:
        The running BackgroundScheduler instance.
    """
    global _scheduler
    
    if _scheduler is not None and _scheduler.running:
        LOGGER.warning("Scheduler is already running")
        return _scheduler
    
    _scheduler = BackgroundScheduler()
    
    # Run full pipeline every day at 2 AM
    _scheduler.add_job(
        run_full_daily_pipeline,
        CronTrigger(hour=2, minute=0),
        id="daily_pipeline",
        replace_existing=True,
        name="Daily Pipeline (Ingest → Score → Outreach)",
    )
    
    # Run scoring every day at 6 AM (in case pipeline fails)
    _scheduler.add_job(
        run_daily_scoring,
        CronTrigger(hour=6, minute=0),
        id="daily_scoring",
        replace_existing=True,
        name="Daily Scoring Backup",
    )
    
    # Run outreach every day at 10 AM
    _scheduler.add_job(
        run_daily_outreach,
        CronTrigger(hour=10, minute=0),
        id="daily_outreach",
        replace_existing=True,
        name="Daily Outreach",
    )
    
    _scheduler.start()
    LOGGER.info("Scheduler started with %d jobs.", len(_scheduler.get_jobs()))
    
    return _scheduler


def stop_scheduler() -> None:
    """Stop the background scheduler gracefully."""
    global _scheduler
    
    if _scheduler is not None:
        LOGGER.info("Stopping scheduler...")
        _scheduler.shutdown(wait=True)
        _scheduler = None
        LOGGER.info("Scheduler stopped.")
    else:
        LOGGER.warning("Scheduler is not running")


def _signal_handler(signum: int, frame: object) -> None:
    """Handle shutdown signals."""
    LOGGER.info("Received signal %d, shutting down...", signum)
    stop_scheduler()
    sys.exit(0)


def run_scheduler_blocking() -> None:
    """
    Start the scheduler and block until interrupted.
    
    This is the main entry point for running the scheduler as a standalone process.
    """
    setup_logging(level=SETTINGS.log_level)
    
    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)
    
    LOGGER.info("Starting LA Land Wholesale Scheduler...")
    LOGGER.info("Environment: %s, Dry Run: %s", SETTINGS.environment, SETTINGS.dry_run)
    
    start_scheduler()
    
    try:
        # Keep main thread alive
        while True:
            time.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        stop_scheduler()
        LOGGER.info("Scheduler shutdown complete.")


if __name__ == "__main__":
    run_scheduler_blocking()
