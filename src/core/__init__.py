"""Core module exports."""
from __future__ import annotations

from core.config import Settings, get_settings, reload_settings
from core.db import get_session, SessionLocal, get_session_factory
from core.exceptions import (
    # Base
    LALandWholesaleError,
    # Configuration
    ConfigurationError,
    MissingCredentialsError,
    # Database
    DatabaseError,
    ConnectionError,
    MigrationError,
    # LLM
    LLMError,
    LLMAPIError,
    LLMRateLimitError,
    LLMTimeoutError,
    # Outreach
    OutreachError,
    TwilioError,
    TCPAError,
    TCPAViolationError,
    InvalidPhoneNumberError,
    # Ingestion
    IngestionError,
    ValidationError,
    # Scoring
    ScoringError,
    # External Services
    ExternalServiceError,
    AddressError,
    GeocodeError,
    USPSVerificationError,
    CompsError,
    ScraperError,
    RateLimitError,
    ServiceUnavailableError,
)
from core.logging_config import (
    setup_logging,
    get_logger,
    get_context_logger,
    log_external_call,
    JSONFormatter,
    ContextLogger,
)
from core.models import (
    Base,
    Party,
    Owner,
    Parcel,
    Lead,
    OutreachAttempt,
)

__all__ = [
    # Config
    "Settings",
    "get_settings",
    "reload_settings",
    # Database
    "get_session",
    "get_session_factory",
    "SessionLocal",
    "Base",
    # Models
    "Party",
    "Owner",
    "Parcel",
    "Lead",
    "OutreachAttempt",
    # Exceptions - Base
    "LALandWholesaleError",
    # Exceptions - Config
    "ConfigurationError",
    "MissingCredentialsError",
    # Exceptions - Database
    "DatabaseError",
    "ConnectionError",
    "MigrationError",
    # Exceptions - LLM
    "LLMError",
    "LLMAPIError",
    "LLMRateLimitError",
    "LLMTimeoutError",
    # Exceptions - Outreach
    "OutreachError",
    "TwilioError",
    "TCPAError",
    "TCPAViolationError",
    "InvalidPhoneNumberError",
    # Exceptions - Ingestion
    "IngestionError",
    "ValidationError",
    # Exceptions - Scoring
    "ScoringError",
    # Exceptions - External Services
    "ExternalServiceError",
    "AddressError",
    "GeocodeError",
    "USPSVerificationError",
    "CompsError",
    "ScraperError",
    "RateLimitError",
    "ServiceUnavailableError",
    # Logging
    "setup_logging",
    "get_logger",
    "get_context_logger",
    "log_external_call",
    "JSONFormatter",
    "ContextLogger",
]
