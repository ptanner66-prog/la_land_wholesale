"""Background task tracking service."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Dict, Generator, Optional

from sqlalchemy.orm import Session

from core.logging_config import get_logger
from core.models import BackgroundTask, TaskStatus
from core.utils import utcnow, generate_unique_key

LOGGER = get_logger(__name__)


class TaskTracker:
    """
    Service for tracking background task execution.
    
    Provides visibility into task status, errors, and history.
    """

    def __init__(self, session: Session):
        """Initialize task tracker."""
        self.session = session

    def create_task(
        self,
        task_type: str,
        market_code: Optional[str] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> BackgroundTask:
        """
        Create a new task record.
        
        Args:
            task_type: Type of task (e.g., "nightly_pipeline", "followup_batch").
            market_code: Optional market filter.
            params: Optional task parameters.
        
        Returns:
            The created BackgroundTask.
        """
        task = BackgroundTask(
            task_id=generate_unique_key(),
            task_type=task_type,
            status=TaskStatus.PENDING.value,
            market_code=market_code,
            params=params,
            created_at=utcnow(),
        )
        self.session.add(task)
        self.session.flush()
        
        LOGGER.info(f"Created task {task.task_id} of type {task_type}")
        return task

    def start_task(self, task: BackgroundTask) -> None:
        """Mark a task as started."""
        task.status = TaskStatus.RUNNING.value
        task.started_at = utcnow()
        self.session.flush()
        LOGGER.info(f"Task {task.task_id} started")

    def complete_task(
        self,
        task: BackgroundTask,
        result: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Mark a task as completed successfully."""
        task.status = TaskStatus.COMPLETED.value
        task.completed_at = utcnow()
        task.result = result
        self.session.flush()
        LOGGER.info(f"Task {task.task_id} completed")

    def fail_task(
        self,
        task: BackgroundTask,
        error_message: str,
        result: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Mark a task as failed."""
        task.status = TaskStatus.FAILED.value
        task.completed_at = utcnow()
        task.error_message = error_message
        task.result = result
        self.session.flush()
        LOGGER.error(f"Task {task.task_id} failed: {error_message}")

    def cancel_task(self, task: BackgroundTask, reason: str = "Cancelled") -> None:
        """Mark a task as cancelled."""
        task.status = TaskStatus.CANCELLED.value
        task.completed_at = utcnow()
        task.error_message = reason
        self.session.flush()
        LOGGER.info(f"Task {task.task_id} cancelled: {reason}")

    def get_task(self, task_id: str) -> Optional[BackgroundTask]:
        """Get a task by ID."""
        return self.session.query(BackgroundTask).filter(
            BackgroundTask.task_id == task_id
        ).first()

    def get_recent_tasks(
        self,
        task_type: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> list[BackgroundTask]:
        """Get recent tasks with optional filters."""
        query = self.session.query(BackgroundTask)
        
        if task_type:
            query = query.filter(BackgroundTask.task_type == task_type)
        if status:
            query = query.filter(BackgroundTask.status == status)
        
        return query.order_by(BackgroundTask.created_at.desc()).limit(limit).all()

    def get_failed_tasks(self, limit: int = 50) -> list[BackgroundTask]:
        """Get recent failed tasks."""
        return self.get_recent_tasks(status=TaskStatus.FAILED.value, limit=limit)

    @contextmanager
    def track_task(
        self,
        task_type: str,
        market_code: Optional[str] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Generator[BackgroundTask, None, None]:
        """
        Context manager for task tracking.
        
        Usage:
            with tracker.track_task("nightly_pipeline", "LA") as task:
                # do work
                task.result = {"processed": 100}
        
        Automatically handles start/complete/fail status.
        """
        task = self.create_task(task_type, market_code, params)
        self.start_task(task)
        
        try:
            yield task
            self.complete_task(task, task.result)
        except Exception as e:
            self.fail_task(task, str(e))
            raise

    def cleanup_old_tasks(self, days: int = 30) -> int:
        """
        Remove tasks older than specified days.
        
        Args:
            days: Delete tasks older than this many days.
        
        Returns:
            Number of tasks deleted.
        """
        from datetime import timedelta
        cutoff = utcnow() - timedelta(days=days)
        
        result = self.session.query(BackgroundTask).filter(
            BackgroundTask.created_at < cutoff
        ).delete()
        
        self.session.flush()
        LOGGER.info(f"Cleaned up {result} old tasks")
        return result


def get_task_tracker(session: Session) -> TaskTracker:
    """Get a TaskTracker instance."""
    return TaskTracker(session)


__all__ = [
    "TaskTracker",
    "get_task_tracker",
]

