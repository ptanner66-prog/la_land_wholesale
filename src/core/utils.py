"""Core utility functions."""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from functools import wraps
from typing import Any, Callable, Optional, TypeVar

from core.logging_config import get_logger

LOGGER = get_logger(__name__)

T = TypeVar("T")


def utcnow() -> datetime:
    """Get current UTC datetime with timezone info. Always use this instead of datetime.now()."""
    return datetime.now(timezone.utc)


def ensure_aware(dt: Optional[datetime]) -> Optional[datetime]:
    """
    Ensure a datetime is timezone-aware (UTC).
    
    SQLite stores datetimes without timezone info, so we need to make them
    aware before comparing with utcnow().
    
    Args:
        dt: A datetime that may or may not be timezone-aware.
        
    Returns:
        Timezone-aware datetime in UTC, or None if input was None.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        # Assume naive datetimes are UTC
        return dt.replace(tzinfo=timezone.utc)
    return dt


def generate_idempotency_key(*args: Any) -> str:
    """
    Generate a deterministic idempotency key from arguments.
    
    Args:
        *args: Values to include in the key (lead_id, context, timestamp, etc.)
    
    Returns:
        A 64-character hex string.
    """
    key_string = "|".join(str(arg) for arg in args)
    return hashlib.sha256(key_string.encode()).hexdigest()


def generate_unique_key() -> str:
    """Generate a unique random key."""
    return uuid.uuid4().hex


class CircuitBreaker:
    """
    Simple circuit breaker for external service calls.
    
    States:
    - CLOSED: Normal operation, calls pass through
    - OPEN: Service is down, calls fail fast
    - HALF_OPEN: Testing if service is back
    """
    
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"
    
    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        half_open_max_calls: int = 3,
    ):
        """
        Initialize circuit breaker.
        
        Args:
            name: Service name for logging.
            failure_threshold: Number of failures before opening circuit.
            recovery_timeout: Seconds to wait before trying again.
            half_open_max_calls: Max test calls in half-open state.
        """
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        
        self.state = self.CLOSED
        self.failure_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.half_open_calls = 0
    
    def can_execute(self) -> bool:
        """Check if a call can be made."""
        if self.state == self.CLOSED:
            return True
        
        if self.state == self.OPEN:
            if self.last_failure_time:
                elapsed = (utcnow() - self.last_failure_time).total_seconds()
                if elapsed >= self.recovery_timeout:
                    self.state = self.HALF_OPEN
                    self.half_open_calls = 0
                    LOGGER.info(f"Circuit breaker {self.name}: OPEN -> HALF_OPEN")
                    return True
            return False
        
        if self.state == self.HALF_OPEN:
            return self.half_open_calls < self.half_open_max_calls
        
        return False
    
    def record_success(self) -> None:
        """Record a successful call."""
        if self.state == self.HALF_OPEN:
            self.half_open_calls += 1
            if self.half_open_calls >= self.half_open_max_calls:
                self.state = self.CLOSED
                self.failure_count = 0
                LOGGER.info(f"Circuit breaker {self.name}: HALF_OPEN -> CLOSED")
        elif self.state == self.CLOSED:
            self.failure_count = 0
    
    def record_failure(self) -> None:
        """Record a failed call."""
        self.failure_count += 1
        self.last_failure_time = utcnow()
        
        if self.state == self.HALF_OPEN:
            self.state = self.OPEN
            LOGGER.warning(f"Circuit breaker {self.name}: HALF_OPEN -> OPEN (failure in test)")
        elif self.failure_count >= self.failure_threshold:
            self.state = self.OPEN
            LOGGER.warning(f"Circuit breaker {self.name}: CLOSED -> OPEN (threshold reached)")


class RateLimiter:
    """Simple in-memory rate limiter."""
    
    def __init__(self, max_calls: int, period_seconds: int):
        """
        Initialize rate limiter.
        
        Args:
            max_calls: Maximum calls allowed in period.
            period_seconds: Time period in seconds.
        """
        self.max_calls = max_calls
        self.period_seconds = period_seconds
        self.calls: list[datetime] = []
    
    def can_proceed(self) -> bool:
        """Check if a call can proceed within rate limit."""
        now = utcnow()
        cutoff = now.timestamp() - self.period_seconds
        
        # Remove old calls
        self.calls = [c for c in self.calls if c.timestamp() > cutoff]
        
        return len(self.calls) < self.max_calls
    
    def record_call(self) -> None:
        """Record a call."""
        self.calls.append(utcnow())
    
    def wait_time(self) -> float:
        """Get seconds to wait before next call is allowed."""
        if self.can_proceed():
            return 0
        
        oldest = min(self.calls)
        return self.period_seconds - (utcnow().timestamp() - oldest.timestamp())


def with_timeout(timeout_seconds: float, default: T = None) -> Callable:
    """
    Decorator to add timeout to a function.
    
    Args:
        timeout_seconds: Maximum execution time.
        default: Value to return on timeout.
    
    Returns:
        Decorated function.
    """
    import signal
    import platform
    
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        if platform.system() == "Windows":
            # Windows doesn't support SIGALRM, return function as-is
            return func
        
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            def handler(signum, frame):
                raise TimeoutError(f"Function {func.__name__} timed out after {timeout_seconds}s")
            
            old_handler = signal.signal(signal.SIGALRM, handler)
            signal.setitimer(signal.ITIMER_REAL, timeout_seconds)
            
            try:
                result = func(*args, **kwargs)
            finally:
                signal.setitimer(signal.ITIMER_REAL, 0)
                signal.signal(signal.SIGALRM, old_handler)
            
            return result
        
        return wrapper
    
    return decorator


__all__ = [
    "utcnow",
    "ensure_aware",
    "generate_idempotency_key",
    "generate_unique_key",
    "CircuitBreaker",
    "RateLimiter",
    "with_timeout",
]

