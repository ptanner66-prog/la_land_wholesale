"""Pytest configuration and fixtures."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

# Add src to path for imports
src_path = Path(__file__).parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

# Set test environment
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("DRY_RUN", "true")
os.environ.setdefault("ENVIRONMENT", "test")

from core.db import Base
from core.models import Lead, Parcel, Owner, Party, OutreachAttempt


# Use in-memory SQLite for testing
# Note: We disable PostGIS-specific features for tests
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"


@pytest.fixture(scope="session")
def engine():
    """Create a test database engine."""
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    
    # Enable foreign key support for SQLite
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
    
    return engine


@pytest.fixture(scope="session")
def tables(engine):
    """Create all tables for testing."""
    # Create tables - SQLite doesn't support PostGIS so geometry columns will be text
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db_session(engine, tables) -> Session:
    """
    Returns a SQLAlchemy session for testing.
    
    Each test gets a fresh transaction that is rolled back after the test.
    """
    connection = engine.connect()
    transaction = connection.begin()
    
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=connection)
    session = SessionLocal()

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def sample_party(db_session) -> Party:
    """Create a sample Party for testing."""
    party = Party(
        normalized_name="JOHN DOE",
        normalized_zip="70808",
        match_hash="abc123hash",
        display_name="John Doe",
        raw_mailing_address="123 Main St, Baton Rouge, LA 70808",
        party_type="individual",
    )
    db_session.add(party)
    db_session.flush()
    return party


@pytest.fixture
def sample_owner(db_session, sample_party) -> Owner:
    """Create a sample Owner for testing."""
    owner = Owner(
        party_id=sample_party.id,
        phone_primary="+12255550100",
        email="john@example.com",
        is_tcpa_safe=True,
        is_dnr=False,
        opt_out=False,
    )
    db_session.add(owner)
    db_session.flush()
    return owner


@pytest.fixture
def sample_parcel(db_session) -> Parcel:
    """Create a sample Parcel for testing."""
    parcel = Parcel(
        canonical_parcel_id="123456789012",
        parish="East Baton Rouge",
        situs_address="456 Oak St",
        city="Baton Rouge",
        state="LA",
        postal_code="70808",
        land_assessed_value=10000.00,
        improvement_assessed_value=5000.00,
        lot_size_acres=1.5,
        is_adjudicated=False,
        years_tax_delinquent=0,
    )
    db_session.add(parcel)
    db_session.flush()
    return parcel


@pytest.fixture
def sample_lead(db_session, sample_owner, sample_parcel) -> Lead:
    """Create a sample Lead for testing."""
    lead = Lead(
        owner_id=sample_owner.id,
        parcel_id=sample_parcel.id,
        motivation_score=75,
        status="new",
    )
    db_session.add(lead)
    db_session.flush()
    return lead


@pytest.fixture
def high_priority_lead(db_session) -> Lead:
    """Create a high-priority lead with adjudicated, delinquent property."""
    party = Party(
        normalized_name="JANE SMITH",
        normalized_zip="75001",
        match_hash="xyz789hash",
        display_name="Jane Smith",
        raw_mailing_address="999 Texas Ave, Dallas, TX 75001",
        party_type="individual",
    )
    db_session.add(party)
    db_session.flush()
    
    owner = Owner(
        party_id=party.id,
        phone_primary="+12145550200",
        is_tcpa_safe=True,
        is_dnr=False,
        opt_out=False,
    )
    db_session.add(owner)
    db_session.flush()
    
    parcel = Parcel(
        canonical_parcel_id="987654321098",
        parish="East Baton Rouge",
        situs_address="789 Vacant Lot Rd",
        city="Baton Rouge",
        state="LA",
        postal_code="70801",
        land_assessed_value=15000.00,
        improvement_assessed_value=0.00,  # Vacant
        lot_size_acres=2.0,
        is_adjudicated=True,
        years_tax_delinquent=3,
    )
    db_session.add(parcel)
    db_session.flush()
    
    lead = Lead(
        owner_id=owner.id,
        parcel_id=parcel.id,
        motivation_score=0,  # Will be calculated
        status="new",
    )
    db_session.add(lead)
    db_session.flush()
    
    return lead
