"""Database connection and session management."""
from __future__ import annotations

import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, List

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings, PROJECT_ROOT, DATABASE_FILE

SETTINGS = get_settings()

# Required tables that MUST exist for the system to function
REQUIRED_TABLES = ["lead", "owner", "parcel", "party", "outreach_attempt", "timeline_event"]

# Check if using SQLite (doesn't support connection pooling)
_is_sqlite = SETTINGS.database_url.startswith("sqlite")


def _validate_database_path() -> None:
    """
    Validate that we're connecting to the correct database file.
    Prevents accidental creation of blank databases in wrong directories.
    """
    if not _is_sqlite:
        return  # Only validate SQLite
    
    # Extract path from URL: sqlite:///path/to/db.db
    db_url = SETTINGS.database_url
    if db_url.startswith("sqlite:///"):
        db_path_str = db_url.replace("sqlite:///", "")
        db_path = Path(db_path_str)
        
        # Check if it's the expected production database
        expected_db = DATABASE_FILE
        
        # If the database doesn't exist at all, that's a problem
        if not db_path.exists():
            print(f"[DB ERROR] Database file not found: {db_path}", file=sys.stderr)
            print(f"[DB ERROR] Expected database at: {expected_db}", file=sys.stderr)
            print(f"[DB ERROR] Current working directory: {Path.cwd()}", file=sys.stderr)
            print(f"[DB ERROR] Project root: {PROJECT_ROOT}", file=sys.stderr)
            
            # If we're pointing to the wrong file, abort
            if db_path.resolve() != expected_db.resolve():
                raise RuntimeError(
                    f"Database path mismatch! Expected {expected_db}, got {db_path}. "
                    f"Check DATABASE_URL in .env or ensure you're running from project root."
                )
            else:
                # The expected file doesn't exist - this is a fresh install
                print(f"[DB WARNING] Production database not found. Will create on first init_db() call.", file=sys.stderr)
        else:
            # Database exists - verify it's not empty/corrupt
            import sqlite3
            try:
                conn = sqlite3.connect(str(db_path))
                tables = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                ).fetchall()
                conn.close()
                
                table_names = [t[0] for t in tables]
                if len(table_names) == 0:
                    print(f"[DB WARNING] Database exists but has no tables: {db_path}", file=sys.stderr)
                else:
                    print(f"[DB OK] Found {len(table_names)} tables in {db_path.name}", file=sys.stderr)
            except Exception as e:
                print(f"[DB WARNING] Could not verify database: {e}", file=sys.stderr)


def _check_required_tables(engine) -> List[str]:
    """
    Check which required tables are missing.
    
    Returns:
        List of missing table names.
    """
    try:
        inspector = inspect(engine)
        existing_tables = inspector.get_table_names()
        missing = [t for t in REQUIRED_TABLES if t not in existing_tables]
        return missing
    except Exception as e:
        print(f"[DB WARNING] Could not inspect tables: {e}", file=sys.stderr)
        return []


# Validate database path on module load
_validate_database_path()

# Create engine with appropriate settings
if _is_sqlite:
    # SQLite with NullPool - no connection pooling to avoid exhaustion issues
    from sqlalchemy.pool import NullPool
    from sqlalchemy import event
    
    engine = create_engine(
        SETTINGS.database_url,
        connect_args={"check_same_thread": False},  # Allow multi-threaded access
        poolclass=NullPool,  # Disable connection pooling for SQLite
    )
    
    # Enable WAL mode for better concurrency
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=30000")  # 30 second timeout
        cursor.close()
else:
    # PostgreSQL/MySQL with connection pooling
    engine = create_engine(
        SETTINGS.database_url,
        pool_size=SETTINGS.db_pool_size,
        max_overflow=SETTINGS.db_max_overflow,
        pool_timeout=SETTINGS.db_pool_timeout,
        pool_pre_ping=True,  # Verify connection before usage
    )

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""
    pass


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """
    Context manager for database sessions.
    
    Yields:
        SQLAlchemy Session object.
    """
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@contextmanager
def get_readonly_session() -> Generator[Session, None, None]:
    """
    Context manager for read-only database sessions.
    
    Yields:
        SQLAlchemy Session object.
    """
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def init_db(create_missing_only: bool = True) -> dict:
    """
    Initialize database tables.
    
    Args:
        create_missing_only: If True, only creates missing tables (safe).
                            If False, creates all tables (use for fresh install).
    
    Returns:
        Dict with initialization results.
    """
    # Import models to ensure they are registered with Base
    from . import models  # noqa: F401
    
    result = {
        "status": "success",
        "tables_created": [],
        "tables_existing": [],
        "warnings": [],
    }
    
    try:
        inspector = inspect(engine)
        existing_tables = set(inspector.get_table_names())
        
        if create_missing_only and existing_tables:
            # Only create tables that don't exist
            all_tables = set(Base.metadata.tables.keys())
            missing_tables = all_tables - existing_tables
            
            if missing_tables:
                # Create only missing tables
                tables_to_create = [
                    Base.metadata.tables[name] 
                    for name in missing_tables
                ]
                Base.metadata.create_all(bind=engine, tables=tables_to_create)
                result["tables_created"] = list(missing_tables)
                print(f"[DB] Created missing tables: {missing_tables}", file=sys.stderr)
            
            result["tables_existing"] = list(existing_tables)
        else:
            # Fresh install - create all tables
            Base.metadata.create_all(bind=engine)
            
            # Re-inspect to see what was created
            new_tables = set(inspect(engine).get_table_names())
            result["tables_created"] = list(new_tables - existing_tables)
            result["tables_existing"] = list(existing_tables)
        
        # Verify required tables exist
        final_tables = set(inspect(engine).get_table_names())
        missing_required = [t for t in REQUIRED_TABLES if t not in final_tables]
        if missing_required:
            result["warnings"].append(f"Missing required tables: {missing_required}")
            result["status"] = "warning"
        
    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
        print(f"[DB ERROR] init_db failed: {e}", file=sys.stderr)
    
    return result


def validate_database() -> dict:
    """
    Validate database connection and required tables.
    
    Call this at application startup to ensure the database is ready.
    
    Returns:
        Dict with validation results.
    """
    result = {
        "status": "ok",
        "database_url": SETTINGS.database_url,
        "tables_found": [],
        "tables_missing": [],
        "errors": [],
    }
    
    try:
        # Test connection
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        
        # Check tables
        inspector = inspect(engine)
        existing_tables = inspector.get_table_names()
        result["tables_found"] = existing_tables
        
        # Check required tables
        missing = [t for t in REQUIRED_TABLES if t not in existing_tables]
        result["tables_missing"] = missing
        
        if missing:
            result["status"] = "missing_tables"
            result["errors"].append(f"Missing required tables: {missing}")
        
    except Exception as e:
        result["status"] = "error"
        result["errors"].append(str(e))
    
    return result


class SessionContextManager:
    """Context manager wrapper for database sessions in background tasks."""
    
    def __init__(self):
        self.session = None
    
    def __enter__(self):
        self.session = SessionLocal()
        return self.session
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            if exc_type is None:
                try:
                    self.session.commit()
                except Exception:
                    self.session.rollback()
                    raise
            else:
                self.session.rollback()
            self.session.close()
        return False


def get_session_factory():
    """
    Return a session factory for background tasks.
    
    This is used by background tasks that need to create their own sessions
    outside of the FastAPI request lifecycle.
    
    Returns:
        A callable that returns a context manager for database sessions.
    
    Usage:
        session_factory = get_session_factory()
        with session_factory() as session:
            # do work
            session.commit()  # auto-committed on success
    """
    return SessionContextManager