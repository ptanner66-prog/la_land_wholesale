"""Distributed locking services.

Provides:
- Lead-level send locks (prevent concurrent sends to same lead)
- Scheduler locks (prevent concurrent pipeline runs)
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import timedelta
from typing import Generator, Optional

from sqlalchemy import and_, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.logging_config import get_logger
from core.models import Lead, SchedulerLock
from core.utils import utcnow, generate_unique_key

LOGGER = get_logger(__name__)


class LockAcquisitionError(Exception):
    """Exception raised when a lock cannot be acquired."""
    pass


class SendLockService:
    """
    Service for lead-level send locking.
    
    Prevents concurrent message sends to the same lead.
    """
    
    # Lock timeout in seconds (how long a lock is valid)
    DEFAULT_LOCK_TIMEOUT = 60
    
    def __init__(self, session: Session):
        """Initialize the send lock service."""
        self.session = session
        self.instance_id = generate_unique_key()
    
    def acquire_send_lock(
        self,
        lead: Lead,
        timeout_seconds: int = DEFAULT_LOCK_TIMEOUT,
    ) -> bool:
        """
        Attempt to acquire a send lock for a lead.
        
        Args:
            lead: The lead to lock.
            timeout_seconds: How long the lock should be valid.
            
        Returns:
            True if lock was acquired, False if already locked.
        """
        now = utcnow()
        
        # Check if there's an existing valid lock
        if lead.send_locked_at and lead.send_locked_by:
            lock_expires = lead.send_locked_at + timedelta(seconds=timeout_seconds)
            if now < lock_expires:
                if lead.send_locked_by == self.instance_id:
                    # We already have the lock
                    return True
                LOGGER.debug(f"Lead {lead.id} is locked by {lead.send_locked_by}")
                return False
        
        # Try to acquire lock
        lead.send_locked_at = now
        lead.send_locked_by = self.instance_id
        
        try:
            self.session.flush()
            LOGGER.debug(f"Acquired send lock for lead {lead.id}")
            return True
        except IntegrityError:
            self.session.rollback()
            return False
    
    def release_send_lock(self, lead: Lead) -> None:
        """
        Release a send lock for a lead.
        
        Args:
            lead: The lead to unlock.
        """
        if lead.send_locked_by == self.instance_id:
            lead.send_locked_at = None
            lead.send_locked_by = None
            self.session.flush()
            LOGGER.debug(f"Released send lock for lead {lead.id}")
    
    @contextmanager
    def send_lock(
        self,
        lead: Lead,
        timeout_seconds: int = DEFAULT_LOCK_TIMEOUT,
    ) -> Generator[bool, None, None]:
        """
        Context manager for send locking.
        
        Usage:
            with lock_service.send_lock(lead) as acquired:
                if acquired:
                    # send message
        
        Args:
            lead: The lead to lock.
            timeout_seconds: Lock timeout.
            
        Yields:
            True if lock was acquired, False otherwise.
        """
        acquired = self.acquire_send_lock(lead, timeout_seconds)
        try:
            yield acquired
        finally:
            if acquired:
                self.release_send_lock(lead)


class SchedulerLockService:
    """
    Service for distributed scheduler locking.
    
    Prevents concurrent pipeline runs.
    """
    
    # Default lock duration in seconds
    DEFAULT_LOCK_DURATION = 3600  # 1 hour
    
    def __init__(self, session: Session):
        """Initialize the scheduler lock service."""
        self.session = session
        self.instance_id = generate_unique_key()
    
    def acquire_lock(
        self,
        lock_name: str,
        duration_seconds: int = DEFAULT_LOCK_DURATION,
    ) -> bool:
        """
        Attempt to acquire a scheduler lock.
        
        Args:
            lock_name: Name of the lock (e.g., "nightly_pipeline").
            duration_seconds: How long the lock should be valid.
            
        Returns:
            True if lock was acquired, False if already locked.
        """
        now = utcnow()
        expires_at = now + timedelta(seconds=duration_seconds)
        
        # Check for existing lock
        existing = self.session.query(SchedulerLock).filter(
            SchedulerLock.lock_name == lock_name
        ).first()
        
        if existing:
            if now < existing.expires_at:
                if existing.locked_by == self.instance_id:
                    # We already have the lock, extend it
                    existing.expires_at = expires_at
                    self.session.flush()
                    return True
                LOGGER.warning(f"Lock {lock_name} held by {existing.locked_by} until {existing.expires_at}")
                return False
            else:
                # Lock expired, take it over
                existing.locked_by = self.instance_id
                existing.locked_at = now
                existing.expires_at = expires_at
                self.session.flush()
                LOGGER.info(f"Acquired expired lock {lock_name}")
                return True
        
        # Create new lock
        try:
            lock = SchedulerLock(
                lock_name=lock_name,
                locked_by=self.instance_id,
                locked_at=now,
                expires_at=expires_at,
            )
            self.session.add(lock)
            self.session.flush()
            LOGGER.info(f"Acquired lock {lock_name}")
            return True
        except IntegrityError:
            self.session.rollback()
            return False
    
    def release_lock(self, lock_name: str) -> None:
        """
        Release a scheduler lock.
        
        Args:
            lock_name: Name of the lock to release.
        """
        lock = self.session.query(SchedulerLock).filter(
            and_(
                SchedulerLock.lock_name == lock_name,
                SchedulerLock.locked_by == self.instance_id,
            )
        ).first()
        
        if lock:
            self.session.delete(lock)
            self.session.flush()
            LOGGER.info(f"Released lock {lock_name}")
    
    @contextmanager
    def scheduler_lock(
        self,
        lock_name: str,
        duration_seconds: int = DEFAULT_LOCK_DURATION,
    ) -> Generator[bool, None, None]:
        """
        Context manager for scheduler locking.
        
        Usage:
            with lock_service.scheduler_lock("nightly_pipeline") as acquired:
                if acquired:
                    # run pipeline
        
        Args:
            lock_name: Name of the lock.
            duration_seconds: Lock duration.
            
        Yields:
            True if lock was acquired, False otherwise.
        """
        acquired = self.acquire_lock(lock_name, duration_seconds)
        try:
            yield acquired
        finally:
            if acquired:
                self.release_lock(lock_name)
    
    def cleanup_expired_locks(self) -> int:
        """
        Remove all expired locks.
        
        Returns:
            Number of locks removed.
        """
        now = utcnow()
        result = self.session.query(SchedulerLock).filter(
            SchedulerLock.expires_at < now
        ).delete()
        self.session.flush()
        return result


def get_send_lock_service(session: Session) -> SendLockService:
    """Get a SendLockService instance."""
    return SendLockService(session)


def get_scheduler_lock_service(session: Session) -> SchedulerLockService:
    """Get a SchedulerLockService instance."""
    return SchedulerLockService(session)


__all__ = [
    "SendLockService",
    "SchedulerLockService",
    "LockAcquisitionError",
    "get_send_lock_service",
    "get_scheduler_lock_service",
]

