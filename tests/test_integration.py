"""Integration tests."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# Add src to path
src_path = Path(__file__).parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

# Set test environment before importing app
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("DRY_RUN", "true")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-for-ci")
os.environ.setdefault("ALLOWED_ORIGINS", "http://localhost:3000")

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from core.db import Base
from core.models import User
from api.app import app
from api.deps import get_db

# ---------------------------------------------------------------------------
# Test DB setup — override get_db so integration tests use in-memory SQLite
# ---------------------------------------------------------------------------
_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

@event.listens_for(_engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

Base.metadata.create_all(bind=_engine)
_SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)


def _override_get_db():
    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


app.dependency_overrides[get_db] = _override_get_db
client = TestClient(app)


def _get_auth_headers() -> dict:
    """Register a test user and return auth headers."""
    resp = client.post("/auth/register", json={
        "email": "integration@test.com",
        "password": "testpassword123",
    })
    if resp.status_code == 409:
        # Already registered, login instead
        resp = client.post("/auth/login", json={
            "email": "integration@test.com",
            "password": "testpassword123",
        })
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# Get auth headers once for all tests
_auth_headers = None

def auth_headers():
    global _auth_headers
    if _auth_headers is None:
        _auth_headers = _get_auth_headers()
    return _auth_headers


def test_health_check():
    """Test health endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] in ("ok", "healthy")


def test_get_leads_empty():
    """Test getting leads when database is empty."""
    response = client.get("/leads", headers=auth_headers())
    assert response.status_code == 200
    data = response.json()
    # May return a list or paginated dict
    if isinstance(data, dict):
        assert "items" in data
        assert data["total"] == 0
    else:
        assert isinstance(data, list)


def test_get_lead_not_found():
    """Test getting non-existent lead."""
    response = client.get("/leads/99999", headers=auth_headers())
    assert response.status_code == 404


def test_scoring_config():
    """Test getting scoring configuration."""
    response = client.get("/scoring/config", headers=auth_headers())
    assert response.status_code == 200

    data = response.json()
    assert "thresholds" in data
    assert "min_motivation_score" in data["thresholds"]


def test_score_distribution_empty():
    """Test score distribution when database is empty."""
    response = client.get("/scoring/distribution", headers=auth_headers())
    assert response.status_code == 200

    data = response.json()
    assert "total_leads" in data
    assert "distribution" in data
    assert data["total_leads"] == 0


def test_metrics_json():
    """Test metrics JSON endpoint."""
    response = client.get("/metrics/json", headers=auth_headers())
    assert response.status_code == 200

    data = response.json()
    assert "timestamp" in data
    assert "leads" in data
    assert "owners" in data
    assert "parcels" in data
    assert "config" in data


def test_metrics_prometheus():
    """Test Prometheus metrics endpoint."""
    response = client.get("/metrics", headers=auth_headers())
    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]

    # Should contain metric definitions
    content = response.text
    assert "la_land_leads_total" in content


def test_outreach_stats():
    """Test outreach statistics endpoint."""
    response = client.get("/outreach/stats", headers=auth_headers())
    assert response.status_code == 200

    data = response.json()
    assert "total_sent" in data
    assert "max_per_day" in data


def test_outreach_history_empty():
    """Test outreach history when empty."""
    response = client.get("/outreach/history", headers=auth_headers())
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_owners_list_empty():
    """Test owner listing when empty."""
    response = client.get("/owners", headers=auth_headers())
    assert response.status_code == 200

    data = response.json()
    # May return a list or dict with owners key
    if isinstance(data, dict):
        assert "owners" in data or "items" in data
    else:
        assert isinstance(data, list)


def test_owners_statistics():
    """Test owner statistics endpoint."""
    response = client.get("/owners/statistics", headers=auth_headers())
    assert response.status_code == 200

    data = response.json()
    assert "total_owners" in data
    assert "tcpa_safe" in data


def test_ingestion_statistics():
    """Test ingestion statistics endpoint."""
    response = client.get("/ingest/statistics", headers=auth_headers())
    assert response.status_code == 200

    data = response.json()
    # Validate it has some kind of statistics structure
    assert isinstance(data, dict)
    assert len(data) > 0
