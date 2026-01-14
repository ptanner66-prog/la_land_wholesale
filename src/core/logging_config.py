"""Centralized logging configuration with JSON structured logging support."""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Optional


# Default format for text logs
TEXT_LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class JSONFormatter(logging.Formatter):
    """
    Custom JSON formatter for structured logging.
    
    Outputs logs in JSON format suitable for log aggregation systems
    like ELK, Datadog, or CloudWatch.
    """

    def format(self, record: logging.LogRecord) -> str:
        """Format a log record as JSON."""
        log_data: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add extra fields if present
        if hasattr(record, "extra_data"):
            log_data["extra"] = record.extra_data

        # Add common context fields
        if hasattr(record, "request_id"):
            log_data["request_id"] = record.request_id
        if hasattr(record, "user_id"):
            log_data["user_id"] = record.user_id
        if hasattr(record, "lead_id"):
            log_data["lead_id"] = record.lead_id

        return json.dumps(log_data, default=str)


class ContextLogger(logging.LoggerAdapter):
    """
    Logger adapter that allows adding context to log messages.
    
    Usage:
        logger = get_context_logger(__name__, request_id="abc123")
        logger.info("Processing request")  # Will include request_id in output
    """

    def process(self, msg: str, kwargs: Dict[str, Any]) -> tuple[str, Dict[str, Any]]:
        """Add context to log record."""
        extra = kwargs.get("extra", {})
        extra.update(self.extra)
        kwargs["extra"] = extra
        return msg, kwargs


def setup_logging(
    level: str = "INFO",
    log_file: Optional[str] = None,
    json_format: bool = False,
) -> None:
    """
    Configure logging for the application.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        log_file: Optional path to a log file.
        json_format: If True, use JSON structured logging.
    """
    handlers: list[logging.Handler] = []

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    if json_format:
        console_handler.setFormatter(JSONFormatter())
    else:
        console_handler.setFormatter(logging.Formatter(TEXT_LOG_FORMAT, DATE_FORMAT))
    handlers.append(console_handler)

    # File handler (optional)
    if log_file:
        file_handler = logging.FileHandler(log_file)
        if json_format:
            file_handler.setFormatter(JSONFormatter())
        else:
            file_handler.setFormatter(logging.Formatter(TEXT_LOG_FORMAT, DATE_FORMAT))
        handlers.append(file_handler)

    logging.basicConfig(
        level=level,
        handlers=handlers,
        force=True,  # Overwrite any existing configuration
    )

    # Set third-party loggers to WARNING to reduce noise
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.INFO)


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance with the specified name.

    Args:
        name: Name of the logger (usually __name__).

    Returns:
        Configured logger instance.
    """
    return logging.getLogger(name)


def get_context_logger(name: str, **context: Any) -> ContextLogger:
    """
    Get a logger with context that will be included in all log messages.

    Args:
        name: Name of the logger (usually __name__).
        **context: Context key-value pairs to include in logs.

    Returns:
        ContextLogger adapter.
    
    Example:
        logger = get_context_logger(__name__, request_id="abc123", lead_id=42)
        logger.info("Processing lead")  # Logs will include request_id and lead_id
    """
    base_logger = logging.getLogger(name)
    return ContextLogger(base_logger, context)


def log_external_call(
    logger: logging.Logger,
    service: str,
    operation: str,
    success: bool,
    duration_ms: float,
    **extra: Any,
) -> None:
    """
    Log an external service call with standard fields.

    Args:
        logger: Logger instance to use.
        service: Name of the external service (e.g., "google_maps", "usps").
        operation: Operation performed (e.g., "geocode", "verify_address").
        success: Whether the call succeeded.
        duration_ms: Duration of the call in milliseconds.
        **extra: Additional context to log.
    """
    log_data = {
        "service": service,
        "operation": operation,
        "success": success,
        "duration_ms": round(duration_ms, 2),
        **extra,
    }

    if success:
        logger.info(
            f"External call: {service}.{operation} completed in {duration_ms:.2f}ms",
            extra={"extra_data": log_data},
        )
    else:
        logger.warning(
            f"External call: {service}.{operation} failed after {duration_ms:.2f}ms",
            extra={"extra_data": log_data},
        )


__all__ = [
    "setup_logging",
    "get_logger",
    "get_context_logger",
    "log_external_call",
    "JSONFormatter",
    "ContextLogger",
]
