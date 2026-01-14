"""Configuration management for the la_land_wholesale platform.

All configuration is loaded from environment variables and/or .env file.
Feature flags default to False (disabled) when not set.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Project root detection
PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = PROJECT_ROOT / ".env"

# Absolute path to the production database (never changes regardless of CWD)
DATABASE_FILE = PROJECT_ROOT / "la_land_wholesale.db"
ABSOLUTE_DATABASE_URL = f"sqlite:///{DATABASE_FILE.as_posix()}"


def _resolve_database_url(url: str) -> str:
    """
    Convert relative SQLite paths to absolute paths based on PROJECT_ROOT.
    
    This prevents issues when the app is started from different working directories.
    """
    if not url.startswith("sqlite:///"):
        return url  # Not SQLite, return as-is
    
    # Extract path from URL
    path_part = url.replace("sqlite:///", "")
    
    # Check if it's a relative path (starts with ./ or doesn't start with /)
    if path_part.startswith("./") or (not path_part.startswith("/") and ":" not in path_part):
        # Relative path - resolve against PROJECT_ROOT
        if path_part.startswith("./"):
            path_part = path_part[2:]  # Remove ./
        
        absolute_path = PROJECT_ROOT / path_part
        return f"sqlite:///{absolute_path.as_posix()}"
    
    return url  # Already absolute


# Load .env if it exists (pydantic-settings handles this via SettingsConfigDict)


class Settings(BaseSettings):
    """
    Runtime configuration powered by environment variables and .env overrides.
    
    All settings can be configured via:
    1. Environment variables (highest priority)
    2. .env file in project root (loaded automatically)
    3. Default values (lowest priority)
    
    Feature flags (ENABLE_*) default to False for safety.
    """

    model_config = SettingsConfigDict(
        env_file=ENV_FILE if ENV_FILE.exists() else None,
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,  # Allow case-insensitive env vars
    )

    # -------------------------------------------------------------------------
    # Database
    # -------------------------------------------------------------------------
    database_url: str = Field(
        default=ABSOLUTE_DATABASE_URL,
        alias="DATABASE_URL",
        description="SQLAlchemy connection string.",
    )
    db_pool_size: int = Field(default=5, alias="DB_POOL_SIZE", ge=1)
    db_max_overflow: int = Field(default=10, alias="DB_MAX_OVERFLOW", ge=0)
    db_pool_timeout: int = Field(default=30, alias="DB_POOL_TIMEOUT", ge=1)

    # -------------------------------------------------------------------------
    # Twilio
    # -------------------------------------------------------------------------
    twilio_account_sid: Optional[str] = Field(default=None, alias="TWILIO_ACCOUNT_SID")
    twilio_auth_token: Optional[str] = Field(default=None, alias="TWILIO_AUTH_TOKEN")
    twilio_from_number: Optional[str] = Field(default=None, alias="TWILIO_FROM_NUMBER")
    twilio_messaging_service_sid: Optional[str] = Field(
        default=None, alias="TWILIO_MESSAGING_SERVICE_SID"
    )
    twilio_max_messages_per_second: float = Field(
        default=1.0, alias="TWILIO_MAX_MESSAGES_PER_SECOND", gt=0
    )
    twilio_debug: bool = Field(
        default=False, alias="TWILIO_DEBUG", description="Enable detailed Twilio debug logging"
    )
    twilio_status_callback_url: Optional[str] = Field(
        default=None, alias="TWILIO_STATUS_CALLBACK_URL", description="Webhook URL for delivery status"
    )

    # -------------------------------------------------------------------------
    # Anthropic (Claude)
    # -------------------------------------------------------------------------
    anthropic_api_key: Optional[str] = Field(default=None, alias="ANTHROPIC_API_KEY")
    anthropic_model: str = Field(default="claude-sonnet-4-20250514", alias="ANTHROPIC_MODEL")
    anthropic_temperature: float = Field(default=0.3, alias="ANTHROPIC_TEMPERATURE", ge=0.0, le=1.0)
    anthropic_timeout_seconds: int = Field(default=30, alias="ANTHROPIC_TIMEOUT_SECONDS", ge=1)
    anthropic_max_retries: int = Field(default=3, alias="ANTHROPIC_MAX_RETRIES", ge=1)

    # -------------------------------------------------------------------------
    # OpenAI (legacy/fallback)
    # -------------------------------------------------------------------------
    openai_api_key: Optional[str] = Field(default=None, alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4o-mini", alias="OPENAI_MODEL")
    openai_temperature: float = Field(default=0.3, alias="OPENAI_TEMPERATURE", ge=0.0, le=1.0)
    openai_timeout_seconds: int = Field(default=30, alias="OPENAI_TIMEOUT_SECONDS", ge=1)
    openai_max_retries: int = Field(default=3, alias="OPENAI_MAX_RETRIES", ge=1)

    # -------------------------------------------------------------------------
    # Google Maps
    # -------------------------------------------------------------------------
    google_maps_api_key: Optional[str] = Field(default=None, alias="GOOGLE_MAPS_API_KEY")
    google_geocode_timeout: int = Field(default=10, alias="GOOGLE_GEOCODE_TIMEOUT", ge=1)

    # -------------------------------------------------------------------------
    # USPS
    # -------------------------------------------------------------------------
    usps_user_id: Optional[str] = Field(default=None, alias="USPS_USER_ID")
    usps_timeout: int = Field(default=10, alias="USPS_TIMEOUT", ge=1)

    # -------------------------------------------------------------------------
    # PropStream
    # -------------------------------------------------------------------------
    propstream_api_key: Optional[str] = Field(default=None, alias="PROPSTREAM_API_KEY")
    propstream_user_id: Optional[str] = Field(default=None, alias="PROPSTREAM_USER_ID")
    propstream_timeout: int = Field(default=30, alias="PROPSTREAM_TIMEOUT", ge=1)
    enable_propstream: bool = Field(
        default=False,
        alias="ENABLE_PROPSTREAM",
        description="Enable PropStream property data integration",
    )

    # -------------------------------------------------------------------------
    # Comps API (ATTOM, CoreLogic, etc.)
    # -------------------------------------------------------------------------
    comps_api_key: Optional[str] = Field(default=None, alias="COMPS_API_KEY")
    comps_api_provider: str = Field(default="attom", alias="COMPS_API_PROVIDER")
    comps_timeout: int = Field(default=30, alias="COMPS_TIMEOUT", ge=1)

    # -------------------------------------------------------------------------
    # Feature Flags (Default: DISABLED for safety)
    # Set these to "true" in .env to enable external services
    # -------------------------------------------------------------------------
    enable_google: bool = Field(
        default=False,
        alias="ENABLE_GOOGLE",
        description="Enable Google Maps geocoding integration",
    )
    enable_usps: bool = Field(
        default=False,
        alias="ENABLE_USPS",
        description="Enable USPS address verification",
    )
    enable_comps: bool = Field(
        default=False,
        alias="ENABLE_COMPS",
        description="Enable Zillow/Redfin comparable sales scraping",
    )
    enable_county_scraper: bool = Field(
        default=False,
        alias="ENABLE_COUNTY_SCRAPER",
        description="Enable EBR county records scraping",
    )

    # -------------------------------------------------------------------------
    # External Service Settings
    # -------------------------------------------------------------------------
    comps_cache_ttl_hours: int = Field(default=24, alias="COMPS_CACHE_TTL_HOURS", ge=1)
    geocode_cache_ttl_hours: int = Field(default=168, alias="GEOCODE_CACHE_TTL_HOURS", ge=1)
    scraper_request_timeout: int = Field(default=15, alias="SCRAPER_REQUEST_TIMEOUT", ge=1)
    scraper_max_retries: int = Field(default=3, alias="SCRAPER_MAX_RETRIES", ge=1)

    # -------------------------------------------------------------------------
    # Outreach & Scoring
    # -------------------------------------------------------------------------
    max_sms_per_day: int = Field(default=60, alias="MAX_SMS_PER_DAY", ge=0)
    min_motivation_score: int = Field(default=45, alias="MIN_MOTIVATION_SCORE", ge=0, le=100)
    hot_score_threshold: int = Field(default=65, alias="HOT_SCORE_THRESHOLD", ge=0, le=100)
    reject_score_threshold: int = Field(default=30, alias="REJECT_SCORE_THRESHOLD", ge=0, le=100)
    outreach_cooldown_days: int = Field(default=4, alias="OUTREACH_COOLDOWN_DAYS", ge=0)

    # Legacy scoring weights (kept for backward compatibility, not used by deterministic engine)
    score_weight_adjudicated: int = Field(default=40, alias="SCORE_WEIGHT_ADJUDICATED", ge=0, le=100)
    score_weight_tax_delinquent_per_year: int = Field(
        default=5, alias="SCORE_WEIGHT_TAX_DELINQUENT_PER_YEAR", ge=0, le=100
    )
    score_weight_tax_delinquent_max: int = Field(
        default=20, alias="SCORE_WEIGHT_TAX_DELINQUENT_MAX", ge=0, le=100
    )
    score_weight_low_improvement: int = Field(
        default=20, alias="SCORE_WEIGHT_LOW_IMPROVEMENT", ge=0, le=100
    )
    score_weight_absentee: int = Field(default=10, alias="SCORE_WEIGHT_ABSENTEE", ge=0, le=100)
    score_weight_lot_size: int = Field(default=10, alias="SCORE_WEIGHT_LOT_SIZE", ge=0, le=100)

    # -------------------------------------------------------------------------
    # Application
    # -------------------------------------------------------------------------
    dry_run: bool = Field(default=True, alias="DRY_RUN")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    log_format: str = Field(default="text", alias="LOG_FORMAT")  # "text" or "json"
    environment: str = Field(default="local", alias="ENVIRONMENT")
    sms_batch_size: int = Field(default=25, alias="SMS_BATCH_SIZE", ge=1)
    default_parish: str = Field(default="East Baton Rouge", alias="DEFAULT_PARISH")
    streamlit_port: int = Field(default=8501, alias="STREAMLIT_PORT", ge=1)

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Ensure log level is valid."""
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = v.upper()
        if upper not in valid_levels:
            raise ValueError(f"log_level must be one of {valid_levels}")
        return upper

    @field_validator("log_format")
    @classmethod
    def validate_log_format(cls, v: str) -> str:
        """Ensure log format is valid."""
        lower = v.lower()
        if lower not in {"text", "json"}:
            raise ValueError("log_format must be 'text' or 'json'")
        return lower

    @model_validator(mode="after")
    def validate_twilio_config(self) -> "Settings":
        """Validate Twilio configuration when not in dry-run mode."""
        if not self.dry_run and self.environment == "production":
            if not all([self.twilio_account_sid, self.twilio_auth_token, self.twilio_from_number]):
                raise ValueError("Twilio credentials required in production mode")
        return self

    @model_validator(mode="after")
    def resolve_database_url(self) -> "Settings":
        """Convert relative SQLite paths to absolute paths."""
        self.database_url = _resolve_database_url(self.database_url)
        return self

    # -------------------------------------------------------------------------
    # Helper Methods for Feature Detection
    # -------------------------------------------------------------------------

    def is_google_enabled(self) -> bool:
        """
        Check if Google Maps integration is enabled AND configured.
        
        Returns True only if:
        - ENABLE_GOOGLE=true in .env
        - GOOGLE_MAPS_API_KEY is set
        """
        return self.enable_google and bool(self.google_maps_api_key)

    def is_usps_enabled(self) -> bool:
        """
        Check if USPS integration is enabled AND configured.
        
        Returns True only if:
        - ENABLE_USPS=true in .env
        - USPS_USER_ID is set
        """
        return self.enable_usps and bool(self.usps_user_id)

    def is_comps_enabled(self) -> bool:
        """
        Check if comps scraping is enabled.
        
        Returns True only if ENABLE_COMPS=true in .env.
        No API key required (uses web scraping).
        """
        return self.enable_comps

    def is_propstream_enabled(self) -> bool:
        """
        Check if PropStream integration is enabled AND configured.
        
        Returns True only if:
        - ENABLE_PROPSTREAM=true in .env
        - PROPSTREAM_API_KEY is set
        """
        return self.enable_propstream and bool(self.propstream_api_key)

    def is_county_scraper_enabled(self) -> bool:
        """
        Check if county scraper is enabled.
        
        Returns True only if ENABLE_COUNTY_SCRAPER=true in .env.
        """
        return self.enable_county_scraper

    def is_twilio_enabled(self) -> bool:
        """Check if Twilio is configured."""
        return bool(self.twilio_account_sid and self.twilio_auth_token)

    def is_anthropic_enabled(self) -> bool:
        """Check if Anthropic/Claude is configured."""
        return bool(self.anthropic_api_key)

    def is_openai_enabled(self) -> bool:
        """Check if OpenAI is configured."""
        return bool(self.openai_api_key)

    def is_llm_enabled(self) -> bool:
        """Check if any LLM is configured (Anthropic or OpenAI)."""
        return self.is_anthropic_enabled() or self.is_openai_enabled()

    def get_enabled_services(self) -> list[str]:
        """Get list of enabled external services."""
        services = []
        if self.is_google_enabled():
            services.append("google_maps")
        if self.is_usps_enabled():
            services.append("usps")
        if self.is_propstream_enabled():
            services.append("propstream")
        if self.is_comps_enabled():
            services.append("comps")
        if self.is_county_scraper_enabled():
            services.append("county_scraper")
        if self.is_twilio_enabled():
            services.append("twilio")
        if self.is_anthropic_enabled():
            services.append("anthropic")
        if self.is_openai_enabled():
            services.append("openai")
        return services


@lru_cache
def get_settings() -> Settings:
    """
    Get cached settings instance.
    
    Settings are loaded once and cached. To reload settings,
    call `get_settings.cache_clear()` first.
    
    Returns:
        Settings object with all configuration.
    """
    return Settings()


def reload_settings() -> Settings:
    """
    Clear settings cache and reload from environment.
    
    Useful for testing or after modifying .env file.
    """
    get_settings.cache_clear()
    return get_settings()
