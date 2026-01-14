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

from fastapi.testclient import TestClient
from api.app import app

client = TestClient(app)


def test_health_check():
    """Test health endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_get_leads_empty():
    """Test getting leads when database is empty."""
    response = client.get("/leads")
    assert response.status_code == 200
    # Should return empty list, not error
    assert isinstance(response.json(), list)


def test_get_lead_not_found():
    """Test getting non-existent lead."""
    response = client.get("/leads/99999")
    assert response.status_code == 404


def test_scoring_config():
    """Test getting scoring configuration."""
    response = client.get("/scoring/config")
    assert response.status_code == 200
    
    data = response.json()
    assert "weights" in data
    assert "thresholds" in data
    assert "adjudicated" in data["weights"]
    assert "min_motivation_score" in data["thresholds"]


def test_score_distribution_empty():
    """Test score distribution when database is empty."""
    response = client.get("/scoring/distribution")
    assert response.status_code == 200
    
    data = response.json()
    assert "total_leads" in data
    assert "distribution" in data
    assert data["total_leads"] == 0


def test_metrics_json():
    """Test metrics JSON endpoint."""
    response = client.get("/metrics/json")
    assert response.status_code == 200
    
    data = response.json()
    assert "timestamp" in data
    assert "leads" in data
    assert "owners" in data
    assert "parcels" in data
    assert "config" in data


def test_metrics_prometheus():
    """Test Prometheus metrics endpoint."""
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    
    # Should contain metric definitions
    content = response.text
    assert "la_land_leads_total" in content


def test_outreach_stats():
    """Test outreach statistics endpoint."""
    response = client.get("/outreach/stats")
    assert response.status_code == 200
    
    data = response.json()
    assert "total_sent" in data
    assert "max_per_day" in data


def test_outreach_history_empty():
    """Test outreach history when empty."""
    response = client.get("/outreach/history")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_owners_list_empty():
    """Test owner listing when empty."""
    response = client.get("/owners")
    assert response.status_code == 200
    
    data = response.json()
    assert "owners" in data
    assert "count" in data


def test_owners_statistics():
    """Test owner statistics endpoint."""
    response = client.get("/owners/statistics")
    assert response.status_code == 200
    
    data = response.json()
    assert "total_owners" in data
    assert "tcpa_safe" in data


def test_ingestion_statistics():
    """Test ingestion statistics endpoint."""
    response = client.get("/ingest/statistics")
    assert response.status_code == 200
    
    data = response.json()
    assert "parcels" in data
    assert "owners" in data
    assert "leads" in data
