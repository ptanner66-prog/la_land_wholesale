"""Database session dependency for FastAPI routes."""
from __future__ import annotations

from typing import Generator

from fastapi import Depends
from sqlalchemy.orm import Session

from core.db import SessionLocal


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency that provides a database session.
    
    Yields:
        SQLAlchemy Session instance.
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_readonly_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency that provides a read-only database session.
    
    Yields:
        SQLAlchemy Session instance (read-only mode).
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.rollback()
        db.close()


__all__ = ["get_db", "get_readonly_db"]
