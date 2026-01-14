"""Scheduled job definitions for the LA Land Wholesale platform."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from pathlib import Path

from core.config import get_settings
from core.db import get_session
from core.logging_config import get_logger
from domain.ingestion import IngestionService
from domain.scoring import ScoringService
from domain.outreach import OutreachService

LOGGER = get_logger(__name__)
SETTINGS = get_settings()


def run_enrichment_job(
    limit: int = 100,
    market_code: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Run enrichment on leads that need it.
    
    Args:
        limit: Maximum leads to enrich.
        market_code: Optional filter by market.
    
    Returns:
        Enrichment result summary.
    """
    job_id = f"enrichment_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    LOGGER.info("[%s] Starting enrichment job", job_id)
    
    try:
        from services.enrichment_pipeline import get_enrichment_pipeline
        
        enriched = 0
        failed = 0
        
        with get_session() as session:
            pipeline = get_enrichment_pipeline(session)
            
            # Get leads needing enrichment
            from core.models import Lead
            query = session.query(Lead).filter(Lead.status == "new")
            if market_code:
                query = query.filter(Lead.market_code == market_code.upper())
            leads = query.limit(limit).all()
            
            for lead in leads:
                try:
                    result = pipeline.enrich_lead(lead.id)
                    if result.success:
                        enriched += 1
                    else:
                        failed += 1
                except Exception as e:
                    LOGGER.warning("[%s] Enrichment failed for lead %s: %s", job_id, lead.id, e)
                    failed += 1
        
        LOGGER.info("[%s] Enrichment complete: enriched=%d, failed=%d", job_id, enriched, failed)
        
        return {
            "job_id": job_id,
            "job_type": "enrichment",
            "success": True,
            "result": {
                "enriched": enriched,
                "failed": failed,
            },
        }
    except Exception as e:
        LOGGER.exception("[%s] Enrichment job failed: %s", job_id, e)
        return {
            "job_id": job_id,
            "job_type": "enrichment",
            "success": False,
            "error": str(e),
        }


def run_followup_job(
    limit: int = 50,
    market_code: Optional[str] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Run follow-up messages for leads due.
    
    Args:
        limit: Maximum followups to process.
        market_code: Optional filter by market.
        dry_run: If True, don't actually send.
    
    Returns:
        Followup result summary.
    """
    job_id = f"followup_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    LOGGER.info("[%s] Starting followup job (dry_run=%s)", job_id, dry_run)
    
    try:
        from services.followup import get_followup_service
        from outreach.twilio_sender import send_first_text
        
        with get_session() as session:
            service = get_followup_service(session)
            
            def send_func(lead, context):
                return send_first_text(session, lead, force=False)
            
            result = service.run_followups(
                market_code=market_code,
                send_message_func=send_func if not dry_run else None,
                dry_run=dry_run or SETTINGS.dry_run,
                limit=limit,
            )
        
        LOGGER.info(
            "[%s] Followup complete: due=%d, sent=%d, skipped=%d",
            job_id, result["total_due"], result["sent"], result["skipped"]
        )
        
        return {
            "job_id": job_id,
            "job_type": "followup",
            "success": True,
            "result": result,
        }
    except Exception as e:
        LOGGER.exception("[%s] Followup job failed: %s", job_id, e)
        return {
            "job_id": job_id,
            "job_type": "followup",
            "success": False,
            "error": str(e),
        }


def run_alerts_job(market_code: Optional[str] = None) -> Dict[str, Any]:
    """
    Run hot lead alerts for configured markets.
    
    Args:
        market_code: Optional filter by market.
    
    Returns:
        Alert result summary.
    """
    job_id = f"alerts_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    LOGGER.info("[%s] Starting alerts job", job_id)
    
    try:
        from services.alerts import process_hot_lead_alerts
        
        with get_session() as session:
            result = process_hot_lead_alerts(session, market_code=market_code)
        
        LOGGER.info(
            "[%s] Alerts complete: sent=%d, skipped=%d",
            job_id, result.get("alerts_sent", 0), result.get("alerts_skipped", 0)
        )
        
        return {
            "job_id": job_id,
            "job_type": "alerts",
            "success": True,
            "result": result,
        }
    except Exception as e:
        LOGGER.exception("[%s] Alerts job failed: %s", job_id, e)
        return {
            "job_id": job_id,
            "job_type": "alerts",
            "success": False,
            "error": str(e),
        }


def run_ingestion_job(
    tax_roll_path: Optional[Path] = None,
    adjudicated_path: Optional[Path] = None,
    gis_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Run the daily ingestion pipeline.
    
    Args:
        tax_roll_path: Optional override for tax roll file.
        adjudicated_path: Optional override for adjudicated file.
        gis_path: Optional override for GIS file.
    
    Returns:
        Ingestion result summary.
    """
    job_id = f"ingestion_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    LOGGER.info("[%s] Starting ingestion job", job_id)
    
    try:
        service = IngestionService()
        result = service.run_full_pipeline(
            tax_roll_path=tax_roll_path,
            adjudicated_path=adjudicated_path,
            gis_path=gis_path,
        )
        
        LOGGER.info(
            "[%s] Ingestion complete: success=%s, stages=%d, duration=%.2fs",
            job_id,
            result.success,
            len(result.stages),
            result.total_duration_seconds,
        )
        
        return {
            "job_id": job_id,
            "job_type": "ingestion",
            "success": result.success,
            "result": result.to_dict(),
        }
    except Exception as e:
        LOGGER.exception("[%s] Ingestion job failed: %s", job_id, e)
        return {
            "job_id": job_id,
            "job_type": "ingestion",
            "success": False,
            "error": str(e),
        }


def run_scoring_job(min_score: Optional[int] = None) -> Dict[str, Any]:
    """
    Run the daily scoring job.
    
    Args:
        min_score: Optional minimum score filter.
    
    Returns:
        Scoring result summary.
    """
    job_id = f"scoring_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    LOGGER.info("[%s] Starting scoring job", job_id)
    
    try:
        with get_session() as session:
            service = ScoringService(session)
            result = service.score_all(min_score=min_score)
        
        LOGGER.info(
            "[%s] Scoring complete: updated=%d, avg_score=%.1f, duration=%.2fs",
            job_id,
            result.updated,
            result.average_score,
            result.duration_seconds,
        )
        
        return {
            "job_id": job_id,
            "job_type": "scoring",
            "success": True,
            "result": result.to_dict(),
        }
    except Exception as e:
        LOGGER.exception("[%s] Scoring job failed: %s", job_id, e)
        return {
            "job_id": job_id,
            "job_type": "scoring",
            "success": False,
            "error": str(e),
        }


def run_outreach_job(
    limit: Optional[int] = None,
    min_score: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Run the daily outreach job.
    
    Args:
        limit: Override for batch size (uses SMS_BATCH_SIZE if None).
        min_score: Override for minimum score threshold.
    
    Returns:
        Outreach result summary.
    """
    job_id = f"outreach_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    LOGGER.info("[%s] Starting outreach job", job_id)
    
    if limit is None:
        limit = SETTINGS.sms_batch_size
    
    try:
        with get_session() as session:
            service = OutreachService(session)
            result = service.send_batch(
                limit=limit,
                min_score=min_score,
            )
        
        LOGGER.info(
            "[%s] Outreach complete: attempted=%d, successful=%d, failed=%d, dry_run=%s",
            job_id,
            result.total_attempted,
            result.successful,
            result.failed,
            result.dry_run,
        )
        
        return {
            "job_id": job_id,
            "job_type": "outreach",
            "success": True,
            "result": result.to_dict(),
        }
    except Exception as e:
        LOGGER.exception("[%s] Outreach job failed: %s", job_id, e)
        return {
            "job_id": job_id,
            "job_type": "outreach",
            "success": False,
            "error": str(e),
        }


def run_daily_pipeline(
    run_ingestion: bool = True,
    run_enrichment: bool = True,
    run_scoring: bool = True,
    run_outreach: bool = True,
    run_followups: bool = True,
    run_alerts: bool = True,
    outreach_limit: Optional[int] = None,
    market_code: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Run the complete daily pipeline:
    ingestion → enrichment → scoring → outreach → followups → alerts.
    
    Args:
        run_ingestion: Whether to run ingestion stage.
        run_enrichment: Whether to run enrichment stage.
        run_scoring: Whether to run scoring stage.
        run_outreach: Whether to run outreach stage.
        run_followups: Whether to run followup stage.
        run_alerts: Whether to run alerts stage.
        outreach_limit: Override for outreach batch size.
        market_code: Optional filter by market.
    
    Returns:
        Combined results from all stages.
    """
    pipeline_id = f"daily_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    total_stages = sum([run_ingestion, run_enrichment, run_scoring, run_outreach, run_followups, run_alerts])
    LOGGER.info("[%s] Starting daily pipeline (%d stages)", pipeline_id, total_stages)
    
    started_at = datetime.now(timezone.utc)
    results: Dict[str, Any] = {
        "pipeline_id": pipeline_id,
        "started_at": started_at.isoformat(),
        "stages": {},
        "success": True,
        "dry_run": SETTINGS.dry_run,
    }
    
    stage_num = 0
    
    # Stage 1: Ingestion
    if run_ingestion:
        stage_num += 1
        LOGGER.info("[%s] Stage %d/%d: Ingestion", pipeline_id, stage_num, total_stages)
        ingestion_result = run_ingestion_job()
        results["stages"]["ingestion"] = ingestion_result
        if not ingestion_result.get("success"):
            results["success"] = False
            LOGGER.warning("[%s] Ingestion failed, continuing with other stages", pipeline_id)
    
    # Stage 2: Enrichment
    if run_enrichment:
        stage_num += 1
        LOGGER.info("[%s] Stage %d/%d: Enrichment", pipeline_id, stage_num, total_stages)
        enrichment_result = run_enrichment_job(market_code=market_code)
        results["stages"]["enrichment"] = enrichment_result
        if not enrichment_result.get("success"):
            LOGGER.warning("[%s] Enrichment failed, continuing with other stages", pipeline_id)
    
    # Stage 3: Scoring
    if run_scoring:
        stage_num += 1
        LOGGER.info("[%s] Stage %d/%d: Scoring", pipeline_id, stage_num, total_stages)
        scoring_result = run_scoring_job()
        results["stages"]["scoring"] = scoring_result
        if not scoring_result.get("success"):
            results["success"] = False
            LOGGER.warning("[%s] Scoring failed, continuing with other stages", pipeline_id)
    
    # Stage 4: Outreach
    if run_outreach:
        stage_num += 1
        LOGGER.info("[%s] Stage %d/%d: Outreach", pipeline_id, stage_num, total_stages)
        outreach_result = run_outreach_job(limit=outreach_limit)
        results["stages"]["outreach"] = outreach_result
        if not outreach_result.get("success"):
            results["success"] = False
    
    # Stage 5: Followups
    if run_followups:
        stage_num += 1
        LOGGER.info("[%s] Stage %d/%d: Followups", pipeline_id, stage_num, total_stages)
        followup_result = run_followup_job(market_code=market_code)
        results["stages"]["followups"] = followup_result
        if not followup_result.get("success"):
            LOGGER.warning("[%s] Followups failed, continuing with other stages", pipeline_id)
    
    # Stage 6: Alerts
    if run_alerts:
        stage_num += 1
        LOGGER.info("[%s] Stage %d/%d: Alerts", pipeline_id, stage_num, total_stages)
        alerts_result = run_alerts_job(market_code=market_code)
        results["stages"]["alerts"] = alerts_result
        if not alerts_result.get("success"):
            LOGGER.warning("[%s] Alerts failed", pipeline_id)
    
    completed_at = datetime.now(timezone.utc)
    results["completed_at"] = completed_at.isoformat()
    results["duration_seconds"] = (completed_at - started_at).total_seconds()
    
    LOGGER.info(
        "[%s] Daily pipeline complete: success=%s, duration=%.2fs",
        pipeline_id,
        results["success"],
        results["duration_seconds"],
    )
    
    return results


def run_nightly_pipeline(
    markets: Optional[List[str]] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Run the complete nightly pipeline for specified markets.
    
    This is the main entry point for scheduled nightly automation.
    
    Args:
        markets: List of market codes to process. If None, processes all configured markets.
        dry_run: If True, don't send real messages.
    
    Returns:
        Complete pipeline results by market.
    """
    pipeline_id = f"nightly_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    LOGGER.info("[%s] Starting nightly pipeline", pipeline_id)
    
    started_at = datetime.now(timezone.utc)
    
    # Default to all configured markets
    if markets is None:
        markets = ["LA"]  # Default to Louisiana
    
    results: Dict[str, Any] = {
        "pipeline_id": pipeline_id,
        "started_at": started_at.isoformat(),
        "markets_processed": markets,
        "dry_run": dry_run or SETTINGS.dry_run,
        "steps": {},
        "success": True,
    }
    
    for market in markets:
        LOGGER.info("[%s] Processing market: %s", pipeline_id, market)
        
        market_result: Dict[str, Any] = {}
        
        try:
            # Run scoring for market
            with get_session() as session:
                service = ScoringService(session)
                scoring = service.score_all(market_code=market)
                market_result["scoring"] = {
                    "status": "success",
                    "scored": scoring.updated,
                }
            
            # Run outreach for market
            with get_session() as session:
                service = OutreachService(session)
                outreach = service.send_batch(
                    limit=SETTINGS.sms_batch_size,
                    market_code=market,
                )
                market_result["outreach"] = {
                    "status": "success",
                    "sent": outreach.successful,
                    "blocked": outreach.failed,
                    "failed": 0,
                }
            
            # Run followups
            followup_result = run_followup_job(market_code=market, dry_run=dry_run or SETTINGS.dry_run)
            market_result["followups"] = followup_result.get("result", {})
            
            # Run alerts
            alerts_result = run_alerts_job(market_code=market)
            market_result["alerts"] = alerts_result.get("result", {})
            
        except Exception as e:
            LOGGER.exception("[%s] Market %s failed: %s", pipeline_id, market, e)
            market_result["error"] = str(e)
            results["success"] = False
        
        results["steps"][market] = market_result
    
    completed_at = datetime.now(timezone.utc)
    results["completed_at"] = completed_at.isoformat()
    
    LOGGER.info("[%s] Nightly pipeline complete", pipeline_id)
    
    return results


__all__ = [
    "run_ingestion_job",
    "run_enrichment_job",
    "run_scoring_job",
    "run_outreach_job",
    "run_followup_job",
    "run_alerts_job",
    "run_daily_pipeline",
    "run_nightly_pipeline",
]
