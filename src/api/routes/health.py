"""Health check routes with external service verification."""
from __future__ import annotations

from typing import Dict, Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text

from api.deps import get_readonly_db
from core.config import get_settings
from core.logging_config import get_logger
from core.utils import utcnow

router = APIRouter()
LOGGER = get_logger(__name__)
SETTINGS = get_settings()


@router.get("/")
async def health_check() -> Dict[str, Any]:
    """Basic health check - always returns OK."""
    try:
        return {
            "status": "healthy",
            "timestamp": utcnow().isoformat(),
            "dry_run": SETTINGS.dry_run,
            "environment": SETTINGS.environment,
        }
    except Exception as e:
        LOGGER.error(f"Health check error: {e}")
        return {
            "status": "healthy",
            "timestamp": utcnow().isoformat(),
            "error": str(e),
        }


@router.get("/detailed")
async def detailed_health_check(
    db: Session = Depends(get_readonly_db),
) -> Dict[str, Any]:
    """Detailed health check including database and external services."""
    status = "healthy"
    checks = {}
    
    # Database check
    try:
        db.execute(text("SELECT 1"))
        checks["database"] = {"status": "healthy", "connected": True}
    except Exception as e:
        LOGGER.error(f"Database health check failed: {e}")
        status = "unhealthy"
        checks["database"] = {"status": "unhealthy", "error": str(e)}
    
    # Twilio check
    checks["twilio"] = {
        "configured": SETTINGS.is_twilio_enabled(),
        "account_sid": bool(SETTINGS.twilio_account_sid),
        "auth_token": bool(SETTINGS.twilio_auth_token),
        "from_number": bool(SETTINGS.twilio_from_number),
    }
    
    # OpenAI/LLM check
    checks["openai"] = {
        "configured": bool(getattr(SETTINGS, 'openai_api_key', None)),
    }
    
    # Google Maps check
    checks["google_maps"] = {
        "configured": bool(getattr(SETTINGS, 'google_maps_api_key', None)),
    }
    
    # USPS check
    checks["usps"] = {
        "configured": bool(getattr(SETTINGS, 'usps_user_id', None)),
    }
    
    return {
        "status": status,
        "timestamp": utcnow().isoformat(),
        "checks": checks,
    }


@router.get("/external")
async def external_services_health(
    db: Session = Depends(get_readonly_db),
) -> Dict[str, Any]:
    """
    Check connectivity to external services.
    
    This endpoint actually attempts to connect to external services
    to verify they are accessible and properly configured.
    """
    results = {
        "timestamp": utcnow().isoformat(),
        "services": {},
    }
    
    overall_status = "healthy"
    
    # Twilio connectivity check
    twilio_result = {"configured": False, "connected": False, "error": None}
    if SETTINGS.is_twilio_enabled():
        twilio_result["configured"] = True
        try:
            from twilio.rest import Client
            client = Client(SETTINGS.twilio_account_sid, SETTINGS.twilio_auth_token)
            # Fetch account to verify credentials
            account = client.api.accounts(SETTINGS.twilio_account_sid).fetch()
            twilio_result["connected"] = True
            twilio_result["account_status"] = account.status
        except Exception as e:
            twilio_result["error"] = str(e)
            overall_status = "degraded"
    results["services"]["twilio"] = twilio_result
    
    # OpenAI connectivity check
    openai_result = {"configured": False, "connected": False, "error": None}
    openai_key = getattr(SETTINGS, 'openai_api_key', None)
    if openai_key:
        openai_result["configured"] = True
        try:
            import httpx
            response = httpx.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {openai_key}"},
                timeout=10,
            )
            if response.status_code == 200:
                openai_result["connected"] = True
            else:
                openai_result["error"] = f"Status {response.status_code}"
                overall_status = "degraded"
        except Exception as e:
            openai_result["error"] = str(e)
            overall_status = "degraded"
    results["services"]["openai"] = openai_result
    
    # Google Maps connectivity check
    gmaps_result = {"configured": False, "connected": False, "error": None}
    gmaps_key = getattr(SETTINGS, 'google_maps_api_key', None)
    if gmaps_key:
        gmaps_result["configured"] = True
        try:
            import httpx
            response = httpx.get(
                f"https://maps.googleapis.com/maps/api/geocode/json?address=test&key={gmaps_key}",
                timeout=10,
            )
            if response.status_code == 200:
                data = response.json()
                if data.get("status") != "REQUEST_DENIED":
                    gmaps_result["connected"] = True
                else:
                    gmaps_result["error"] = data.get("error_message", "Request denied")
                    overall_status = "degraded"
            else:
                gmaps_result["error"] = f"Status {response.status_code}"
                overall_status = "degraded"
        except Exception as e:
            gmaps_result["error"] = str(e)
            overall_status = "degraded"
    results["services"]["google_maps"] = gmaps_result
    
    results["overall_status"] = overall_status
    
    return results


@router.get("/tasks")
async def get_task_status(
    task_type: str = None,
    limit: int = 20,
    db: Session = Depends(get_readonly_db),
) -> Dict[str, Any]:
    """Get recent background task status."""
    from core.models import BackgroundTask
    
    query = db.query(BackgroundTask)
    
    if task_type:
        query = query.filter(BackgroundTask.task_type == task_type)
    
    tasks = query.order_by(BackgroundTask.created_at.desc()).limit(limit).all()
    
    return {
        "total": len(tasks),
        "tasks": [
            {
                "task_id": t.task_id,
                "task_type": t.task_type,
                "status": t.status,
                "market_code": t.market_code,
                "started_at": t.started_at.isoformat() if t.started_at else None,
                "completed_at": t.completed_at.isoformat() if t.completed_at else None,
                "error_message": t.error_message,
            }
            for t in tasks
        ],
    }


@router.get("/sms-mode")
async def get_sms_mode() -> Dict[str, Any]:
    """
    Get current SMS mode configuration.
    
    Returns whether DRY_RUN is enabled and Twilio configuration status.
    """
    return {
        "dry_run": SETTINGS.dry_run,
        "twilio_configured": SETTINGS.is_twilio_enabled(),
        "from_number": SETTINGS.twilio_from_number if SETTINGS.is_twilio_enabled() else None,
        "mode": "SIMULATED" if SETTINGS.dry_run else "LIVE",
        "warning": None if SETTINGS.dry_run else "LIVE MODE: Real SMS will be sent to real phone numbers!",
    }
