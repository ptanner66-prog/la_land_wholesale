"""Retry and timeout utilities using tenacity."""
from __future__ import annotations

import time
from functools import wraps
from typing import Any, Callable, Optional, Type, TypeVar, ParamSpec

from tenacity import (
    RetryError,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    stop_after_delay,
    wait_exponential,
    wait_random_exponential,
    before_sleep_log,
)

from core.config import get_settings
from core.logging_config import get_logger
from core.exceptions import (
    ExternalServiceError,
    RateLimitError,
    ServiceUnavailableError,
)

LOGGER = get_logger(__name__)
SETTINGS = get_settings()

P = ParamSpec("P")
T = TypeVar("T")


# Retry configurations for different scenarios
RETRY_NETWORK = retry(
    retry=retry_if_exception_type((ConnectionError, TimeoutError, OSError)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    before_sleep=before_sleep_log(LOGGER, log_level=20),  # INFO level
    reraise=True,
)

RETRY_RATE_LIMIT = retry(
    retry=retry_if_exception_type(RateLimitError),
    stop=stop_after_attempt(5),
    wait=wait_random_exponential(multiplier=2, min=2, max=60),
    before_sleep=before_sleep_log(LOGGER, log_level=30),  # WARNING level
    reraise=True,
)

RETRY_SERVICE = retry(
    retry=retry_if_exception_type((ServiceUnavailableError, ConnectionError, TimeoutError)),
    stop=stop_after_delay(30),  # Stop after 30 seconds total
    wait=wait_exponential(multiplier=1, min=1, max=10),
    before_sleep=before_sleep_log(LOGGER, log_level=20),
    reraise=True,
)


def with_retry(
    max_attempts: int = 3,
    max_delay_seconds: float = 30,
    retry_exceptions: tuple[Type[Exception], ...] = (
        ConnectionError,
        TimeoutError,
        OSError,
        ExternalServiceError,
    ),
    exponential_base: float = 2,
    min_wait: float = 1,
    max_wait: float = 10,
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """
    Decorator to add retry logic to a function.
    
    Args:
        max_attempts: Maximum number of retry attempts.
        max_delay_seconds: Maximum total time to spend retrying.
        retry_exceptions: Tuple of exception types to retry on.
        exponential_base: Base for exponential backoff.
        min_wait: Minimum wait time between retries.
        max_wait: Maximum wait time between retries.
        
    Returns:
        Decorated function with retry logic.
    
    Example:
        @with_retry(max_attempts=3, retry_exceptions=(ConnectionError, TimeoutError))
        def call_external_api():
            ...
    """

    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @retry(
            retry=retry_if_exception_type(retry_exceptions),
            stop=stop_after_attempt(max_attempts) | stop_after_delay(max_delay_seconds),
            wait=wait_exponential(multiplier=exponential_base, min=min_wait, max=max_wait),
            before_sleep=before_sleep_log(LOGGER, log_level=20),
            reraise=True,
        )
        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            return func(*args, **kwargs)

        return wrapper

    return decorator


def with_timeout(
    timeout_seconds: float,
    timeout_exception: Type[Exception] = TimeoutError,
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """
    Decorator to add a timeout to a function.
    
    Note: This is a simple implementation that only works with synchronous code.
    For async code, use asyncio.timeout().
    
    Args:
        timeout_seconds: Maximum time allowed for the function to complete.
        timeout_exception: Exception to raise on timeout.
        
    Returns:
        Decorated function with timeout.
    """
    import signal
    import sys

    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            # Signal-based timeout only works on Unix
            if sys.platform != "win32":

                def timeout_handler(signum: int, frame: Any) -> None:
                    raise timeout_exception(
                        f"{func.__name__} timed out after {timeout_seconds}s"
                    )

                old_handler = signal.signal(signal.SIGALRM, timeout_handler)
                signal.alarm(int(timeout_seconds))
                try:
                    return func(*args, **kwargs)
                finally:
                    signal.alarm(0)
                    signal.signal(signal.SIGALRM, old_handler)
            else:
                # On Windows, just run without timeout
                # For production, consider using concurrent.futures.ThreadPoolExecutor
                return func(*args, **kwargs)

        return wrapper

    return decorator


def timed_call(func: Callable[P, T]) -> Callable[P, tuple[T, float]]:
    """
    Decorator to measure function execution time.
    
    Args:
        func: Function to time.
        
    Returns:
        Tuple of (result, duration_ms).
    """

    @wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> tuple[T, float]:
        start = time.perf_counter()
        result = func(*args, **kwargs)
        duration_ms = (time.perf_counter() - start) * 1000
        return result, duration_ms

    return wrapper


class RetryContext:
    """
    Context manager for retry logic.
    
    Example:
        async with RetryContext(max_attempts=3) as ctx:
            while ctx.should_retry():
                try:
                    result = await api_call()
                    break
                except ConnectionError as e:
                    ctx.record_error(e)
    """

    def __init__(
        self,
        max_attempts: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 30.0,
    ):
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.attempts = 0
        self.last_error: Optional[Exception] = None

    def should_retry(self) -> bool:
        """Check if we should continue retrying."""
        return self.attempts < self.max_attempts

    def record_error(self, error: Exception) -> None:
        """Record an error and increment attempt counter."""
        self.last_error = error
        self.attempts += 1

        if self.should_retry():
            delay = min(self.base_delay * (2 ** (self.attempts - 1)), self.max_delay)
            LOGGER.warning(
                f"Attempt {self.attempts} failed with {type(error).__name__}: {error}. "
                f"Retrying in {delay:.1f}s..."
            )
            time.sleep(delay)

    def raise_if_exhausted(self) -> None:
        """Raise the last error if all retries are exhausted."""
        if self.last_error and not self.should_retry():
            raise self.last_error

    def __enter__(self) -> "RetryContext":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> bool:
        return False


__all__ = [
    "with_retry",
    "with_timeout",
    "timed_call",
    "RetryContext",
    "RETRY_NETWORK",
    "RETRY_RATE_LIMIT",
    "RETRY_SERVICE",
]

