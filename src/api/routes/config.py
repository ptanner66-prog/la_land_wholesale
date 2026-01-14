"""Configuration endpoints."""
from __future__ import annotations

from typing import Dict, Any

from fastapi import APIRouter

from core.config import get_settings

router = APIRouter()
SETTINGS = get_settings()


@router.get("")
async def get_config() -> Dict[str, Any]:
    """
    Get current application configuration.
    
    Returns:
        Configuration settings (non-sensitive).
    """
    return {
        "environment": SETTINGS.environment,
        "dry_run": SETTINGS.dry_run,
        "log_level": SETTINGS.log_level,
        "log_format": SETTINGS.log_format,
        "max_sms_per_day": SETTINGS.max_sms_per_day,
        "min_motivation_score": SETTINGS.min_motivation_score,
        "outreach_cooldown_days": SETTINGS.outreach_cooldown_days,
        "sms_batch_size": SETTINGS.sms_batch_size,
        "default_parish": SETTINGS.default_parish,
        "twilio_configured": SETTINGS.is_twilio_enabled(),
        "openai_configured": SETTINGS.is_openai_enabled(),
        "openai_model": SETTINGS.openai_model,
    }


@router.get("/external-services")
async def get_external_services_config() -> Dict[str, Any]:
    """
    Get external services configuration status.
    
    Returns:
        Status of all external service integrations.
    """
    return {
        "google_maps": {
            "flag_enabled": SETTINGS.enable_google,
            "fully_configured": SETTINGS.is_google_enabled(),
            "timeout_seconds": SETTINGS.google_geocode_timeout,
            "cache_ttl_hours": SETTINGS.geocode_cache_ttl_hours,
        },
        "usps": {
            "flag_enabled": SETTINGS.enable_usps,
            "fully_configured": SETTINGS.is_usps_enabled(),
            "timeout_seconds": SETTINGS.usps_timeout,
        },
        "comps": {
            "flag_enabled": SETTINGS.enable_comps,
            "fully_configured": SETTINGS.is_comps_enabled(),
            "cache_ttl_hours": SETTINGS.comps_cache_ttl_hours,
        },
        "county_scraper": {
            "flag_enabled": SETTINGS.enable_county_scraper,
            "fully_configured": SETTINGS.is_county_scraper_enabled(),
            "request_timeout": SETTINGS.scraper_request_timeout,
            "max_retries": SETTINGS.scraper_max_retries,
        },
        "enabled_services": SETTINGS.get_enabled_services(),
    }


@router.get("/scoring")
async def get_scoring_config() -> Dict[str, Any]:
    """
    Get scoring weight configuration.
    
    Returns:
        Scoring weights and thresholds.
    """
    return {
        "weights": {
            "adjudicated": SETTINGS.score_weight_adjudicated,
            "tax_delinquent_per_year": SETTINGS.score_weight_tax_delinquent_per_year,
            "tax_delinquent_max": SETTINGS.score_weight_tax_delinquent_max,
            "low_improvement": SETTINGS.score_weight_low_improvement,
            "absentee": SETTINGS.score_weight_absentee,
            "lot_size": SETTINGS.score_weight_lot_size,
        },
        "thresholds": {
            "min_motivation_score": SETTINGS.min_motivation_score,
        },
    }


@router.get("/limits")
async def get_limits() -> Dict[str, Any]:
    """
    Get rate limiting configuration.
    
    Returns:
        Rate limits and quotas.
    """
    return {
        "max_sms_per_day": SETTINGS.max_sms_per_day,
        "sms_batch_size": SETTINGS.sms_batch_size,
        "outreach_cooldown_days": SETTINGS.outreach_cooldown_days,
        "twilio_max_messages_per_second": SETTINGS.twilio_max_messages_per_second,
    }


__all__ = ["router"]
