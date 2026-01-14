"""Background job management service with status tracking."""
from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Callable
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from core.config import get_settings
from core.logging_config import get_logger
from core.models import BackgroundTask, TaskStatus

LOGGER = get_logger(__name__)
SETTINGS = get_settings()


@dataclass
class JobProgress:
    """Track progress of a background job."""
    job_id: str
    job_type: str
    status: str = "pending"
    total: int = 0
    processed: int = 0
    remaining: int = 0
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    result: Dict[str, Any] = field(default_factory=dict)


# In-memory job progress tracking (for real-time updates)
_job_progress: Dict[str, JobProgress] = {}
_job_lock = threading.Lock()


def create_job(job_type: str, params: Optional[Dict[str, Any]] = None) -> str:
    """
    Create a new background job and return its ID.
    
    Args:
        job_type: Type of job (e.g., 'scoring', 'ingestion', 'outreach').
        params: Optional parameters for the job.
    
    Returns:
        Job ID string.
    """
    job_id = f"{job_type}_{uuid.uuid4().hex[:12]}"
    
    with _job_lock:
        _job_progress[job_id] = JobProgress(
            job_id=job_id,
            job_type=job_type,
            status="pending",
        )
    
    return job_id


def start_job(job_id: str, total: int = 0) -> None:
    """Mark a job as started."""
    with _job_lock:
        if job_id in _job_progress:
            _job_progress[job_id].status = "running"
            _job_progress[job_id].total = total
            _job_progress[job_id].remaining = total
            _job_progress[job_id].started_at = datetime.now(timezone.utc)


def update_job_progress(job_id: str, processed: int, remaining: int) -> None:
    """Update job progress."""
    with _job_lock:
        if job_id in _job_progress:
            _job_progress[job_id].processed = processed
            _job_progress[job_id].remaining = remaining


def complete_job(job_id: str, result: Dict[str, Any]) -> None:
    """Mark a job as completed."""
    with _job_lock:
        if job_id in _job_progress:
            _job_progress[job_id].status = "completed"
            _job_progress[job_id].completed_at = datetime.now(timezone.utc)
            _job_progress[job_id].result = result
            _job_progress[job_id].remaining = 0


def fail_job(job_id: str, error: str) -> None:
    """Mark a job as failed."""
    with _job_lock:
        if job_id in _job_progress:
            _job_progress[job_id].status = "failed"
            _job_progress[job_id].completed_at = datetime.now(timezone.utc)
            _job_progress[job_id].error = error


def get_job_status(job_id: str) -> Optional[Dict[str, Any]]:
    """
    Get the current status of a job.
    
    Returns:
        Job status dict or None if not found.
    """
    with _job_lock:
        progress = _job_progress.get(job_id)
        if not progress:
            return None
        
        return {
            "job_id": progress.job_id,
            "job_type": progress.job_type,
            "status": progress.status,
            "total": progress.total,
            "processed": progress.processed,
            "remaining": progress.remaining,
            "started_at": progress.started_at.isoformat() if progress.started_at else None,
            "completed_at": progress.completed_at.isoformat() if progress.completed_at else None,
            "error": progress.error,
            "result": progress.result,
            "progress_percent": round(progress.processed / progress.total * 100, 1) if progress.total > 0 else 0,
        }


def cleanup_old_jobs(max_age_hours: int = 24) -> int:
    """Remove old completed jobs from memory."""
    now = datetime.now(timezone.utc)
    removed = 0
    
    with _job_lock:
        to_remove = []
        for job_id, progress in _job_progress.items():
            if progress.completed_at:
                age = (now - progress.completed_at).total_seconds() / 3600
                if age > max_age_hours:
                    to_remove.append(job_id)
        
        for job_id in to_remove:
            del _job_progress[job_id]
            removed += 1
    
    return removed


def persist_job_to_db(session: Session, job_id: str) -> None:
    """Persist job status to database for long-term tracking."""
    with _job_lock:
        progress = _job_progress.get(job_id)
        if not progress:
            return
        
        # Check if already exists
        existing = session.query(BackgroundTask).filter(
            BackgroundTask.task_id == job_id
        ).first()
        
        if existing:
            existing.status = progress.status
            existing.result = progress.result
            existing.error_message = progress.error
            existing.completed_at = progress.completed_at
        else:
            task = BackgroundTask(
                task_id=job_id,
                task_type=progress.job_type,
                status=progress.status,
                params={"total": progress.total},
                result=progress.result,
                error_message=progress.error,
                started_at=progress.started_at,
                completed_at=progress.completed_at,
            )
            session.add(task)
        
        session.commit()


__all__ = [
    "create_job",
    "start_job", 
    "update_job_progress",
    "complete_job",
    "fail_job",
    "get_job_status",
    "cleanup_old_jobs",
    "persist_job_to_db",
]

