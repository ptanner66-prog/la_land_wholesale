"""Application bootstrap and environment validation.

This module ensures all required configuration is present before the application
starts, failing fast with clear error messages if anything is missing.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from typing import List, Optional

from sqlalchemy import text

from .config import get_settings
from .db import engine, init_db
from .logging_config import setup_logging, get_logger

LOGGER = get_logger(__name__)
SETTINGS = get_settings()


@dataclass
class ValidationResult:
    """Result of environment validation."""
    
    is_valid: bool = True
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    
    def add_error(self, message: str) -> None:
        """Add an error and mark validation as failed."""
        self.errors.append(message)
        self.is_valid = False
    
    def add_warning(self, message: str) -> None:
        """Add a warning (does not fail validation)."""
        self.warnings.append(message)


def validate_environment(require_twilio: bool = False, require_openai: bool = False) -> ValidationResult:
    """
    Validate all required environment variables are set.
    
    Args:
        require_twilio: If True, Twilio credentials are required.
        require_openai: If True, OpenAI API key is required.
    
    Returns:
        ValidationResult with errors and warnings.
    """
    result = ValidationResult()
    
    # -------------------------------------------------------------------------
    # Required: Database Configuration
    # -------------------------------------------------------------------------
    if not SETTINGS.database_url:
        result.add_error("DATABASE_URL is not set.")
    
    # -------------------------------------------------------------------------
    # Optional: Twilio (Required for production or if explicitly requested)
    # -------------------------------------------------------------------------
    check_twilio = require_twilio or (SETTINGS.environment == "production" and not SETTINGS.dry_run)
    
    if check_twilio:
        if not SETTINGS.twilio_account_sid:
            result.add_error("TWILIO_ACCOUNT_SID is missing (required for production/outreach).")
        if not SETTINGS.twilio_auth_token:
            result.add_error("TWILIO_AUTH_TOKEN is missing (required for production/outreach).")
        if not SETTINGS.twilio_from_number:
            result.add_error("TWILIO_FROM_NUMBER is missing (required for production/outreach).")
    elif not SETTINGS.twilio_account_sid:
        result.add_warning("Twilio is not configured. SMS outreach will fail if attempted.")

    # -------------------------------------------------------------------------
    # Optional: OpenAI (Required for production or if explicitly requested)
    # -------------------------------------------------------------------------
    check_openai = require_openai or (SETTINGS.environment == "production")
    
    if check_openai:
        if not SETTINGS.openai_api_key:
            result.add_error("OPENAI_API_KEY is missing (required for production/LLM).")
    elif not SETTINGS.openai_api_key:
        result.add_warning("OpenAI is not configured. LLM features will be disabled.")

    return result


def check_database_connection() -> bool:
    """
    Verify database connectivity.
    
    Returns:
        True if connection successful, False otherwise.
    """
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        LOGGER.error("Database connection check failed: %s", exc)
        return False


def ensure_postgis_extension() -> None:
    """Ensure PostGIS extension is enabled in the database."""
    try:
        with engine.connect() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis;"))
            conn.commit()
            LOGGER.info("PostGIS extension verified/enabled.")
    except Exception as exc:
        LOGGER.error("Failed to enable PostGIS extension: %s", exc)
        # Don't raise here, might be a permissions issue but DB could still work if already enabled
        # However, for a fresh install this is critical.
        if "permission denied" in str(exc).lower():
             LOGGER.warning("Could not enable PostGIS (permission denied). Assuming it is already installed.")
        else:
             raise


def run_migrations() -> None:
    """Run Alembic migrations to update database schema."""
    try:
        from alembic import command
        from alembic.config import Config
        
        # Assuming alembic.ini is in the project root
        alembic_cfg = Config("alembic.ini")
        
        # Check if alembic.ini exists
        if not os.path.exists("alembic.ini"):
             LOGGER.warning("alembic.ini not found. Skipping migrations via Alembic.")
             # Fallback to init_db() for development/testing if no migrations exist
             init_db()
             return

        LOGGER.info("Running database migrations...")
        command.upgrade(alembic_cfg, "head")
        LOGGER.info("Database migrations complete.")
    except Exception as exc:
        LOGGER.error("Database migration failed: %s", exc)
        raise


def bootstrap_application() -> None:
    """
    Perform full application bootstrap.
    
    1. Validate environment
    2. Check DB connection
    3. Enable PostGIS
    4. Run migrations
    """
    # 1. Validate Environment
    validation = validate_environment()
    for warning in validation.warnings:
        LOGGER.warning("Config Warning: %s", warning)
    
    if not validation.is_valid:
        for error in validation.errors:
            LOGGER.error("Config Error: %s", error)
        raise ValueError("Environment validation failed. See logs for details.")

    # 2. Check DB Connection
    if not check_database_connection():
        raise ConnectionError("Could not connect to the database.")

    # 3. Enable PostGIS
    ensure_postgis_extension()

    # 4. Run Migrations
    run_migrations()

    LOGGER.info("Application bootstrap completed successfully.")


def validate_or_exit(require_twilio: bool = False, require_openai: bool = False) -> None:
    """
    Validate environment and exit process if invalid.
    
    Args:
        require_twilio: If True, require Twilio config.
        require_openai: If True, require OpenAI config.
    """
    validation = validate_environment(require_twilio, require_openai)
    
    for warning in validation.warnings:
        LOGGER.warning(warning)
        
    if not validation.is_valid:
        for error in validation.errors:
            LOGGER.critical(error)
        sys.exit(1)
