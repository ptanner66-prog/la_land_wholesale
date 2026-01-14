"""Custom exceptions for la_land_wholesale application."""
from __future__ import annotations


class LALandWholesaleError(Exception):
    """Base exception for all application errors."""

    pass


# =============================================================================
# Configuration Errors
# =============================================================================


class ConfigurationError(LALandWholesaleError):
    """Raised when required configuration is missing or invalid."""

    pass


class MissingCredentialsError(ConfigurationError):
    """Raised when required API credentials are not configured."""

    pass


# =============================================================================
# Database Errors
# =============================================================================


class DatabaseError(LALandWholesaleError):
    """Base exception for database-related errors."""

    pass


class ConnectionError(DatabaseError):
    """Raised when database connection fails."""

    pass


class MigrationError(DatabaseError):
    """Raised when database migration fails."""

    pass


# =============================================================================
# LLM Errors
# =============================================================================


class LLMError(LALandWholesaleError):
    """Base exception for LLM-related errors."""

    pass


class LLMAPIError(LLMError):
    """Raised when the LLM API returns an error."""

    pass


class LLMRateLimitError(LLMAPIError):
    """Raised when the LLM API rate limit is exceeded."""

    pass


class LLMTimeoutError(LLMAPIError):
    """Raised when the LLM API request times out."""

    pass


# =============================================================================
# Outreach Errors
# =============================================================================


class OutreachError(LALandWholesaleError):
    """Base exception for outreach-related errors."""

    pass


class TwilioError(OutreachError):
    """Raised when Twilio API fails."""

    pass


class TCPAError(OutreachError):
    """Raised when an action violates TCPA guardrails."""

    pass


# Aliases for backward compatibility
TCPAViolationError = TCPAError


class InvalidPhoneNumberError(OutreachError):
    """Raised when a phone number is invalid or cannot be normalized."""

    pass


# =============================================================================
# Ingestion Errors
# =============================================================================


class IngestionError(LALandWholesaleError):
    """Base exception for ingestion-related errors."""

    pass


class ValidationError(IngestionError):
    """Raised when data validation fails."""

    pass


# =============================================================================
# Scoring Errors
# =============================================================================


class ScoringError(LALandWholesaleError):
    """Base exception for scoring-related errors."""

    pass


# =============================================================================
# External Data Service Errors (Phase 1 & 2)
# =============================================================================


class ExternalServiceError(LALandWholesaleError):
    """Base exception for all external service errors."""

    pass


class AddressError(ExternalServiceError):
    """Raised when address parsing or normalization fails."""

    pass


class GeocodeError(ExternalServiceError):
    """Raised when geocoding fails (Google Maps)."""

    pass


class USPSVerificationError(ExternalServiceError):
    """Raised when USPS address verification fails."""

    pass


class CompsError(ExternalServiceError):
    """Raised when comp data retrieval fails (Zillow/Redfin)."""

    pass


class ScraperError(ExternalServiceError):
    """Raised when web scraping fails (county records, etc.)."""

    pass


class RateLimitError(ExternalServiceError):
    """Raised when an external API rate limit is hit."""

    pass


class ServiceUnavailableError(ExternalServiceError):
    """Raised when an external service is temporarily unavailable."""

    pass


__all__ = [
    # Base
    "LALandWholesaleError",
    # Configuration
    "ConfigurationError",
    "MissingCredentialsError",
    # Database
    "DatabaseError",
    "ConnectionError",
    "MigrationError",
    # LLM
    "LLMError",
    "LLMAPIError",
    "LLMRateLimitError",
    "LLMTimeoutError",
    # Outreach
    "OutreachError",
    "TwilioError",
    "TCPAError",
    "TCPAViolationError",
    "InvalidPhoneNumberError",
    # Ingestion
    "IngestionError",
    "ValidationError",
    # Scoring
    "ScoringError",
    # External Services
    "ExternalServiceError",
    "AddressError",
    "GeocodeError",
    "USPSVerificationError",
    "CompsError",
    "ScraperError",
    "RateLimitError",
    "ServiceUnavailableError",
]
