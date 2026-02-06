"""Tests for ingestion path traversal prevention."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("DRY_RUN", "true")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-for-ci")
os.environ.setdefault("ALLOWED_ORIGINS", "http://localhost:3000")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.db import Base
from core.auth import create_access_token
from core.models import User
from api.app import app
from api.deps import get_db


@pytest.fixture(scope="module")
def test_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db_session(test_engine):
    connection = test_engine.connect()
    transaction = connection.begin()
    Session = sessionmaker(autocommit=False, autoflush=False, bind=connection)
    session = Session()
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def auth_token(db_session):
    """Create a test user and return a valid JWT token."""
    from core.auth import hash_password
    user = User(
        email="admin@test.com",
        hashed_password=hash_password("testpass123"),
        role="admin",
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    return create_access_token(user.id, user.email, user.role)


@pytest.fixture
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


class TestPathTraversalPrevention:
    """Test that path traversal attacks are blocked on all ingestion endpoints."""

    TRAVERSAL_PATHS = [
        "../../etc/passwd",
        "/etc/shadow",
        "../../../home/user/.ssh/id_rsa",
        "/tmp/../../etc/hosts",
    ]

    INGESTION_ENDPOINTS = [
        ("/ingest/tax-roll", "file_path"),
        ("/ingest/gis", "file_path"),
        ("/ingest/adjudicated", "file_path"),
        ("/ingest/auctions", "file_path"),
        ("/ingest/expired", "file_path"),
        ("/ingest/tax-delinquent", "file_path"),
        ("/ingest/absentee", "file_path"),
    ]

    @pytest.mark.parametrize("path", TRAVERSAL_PATHS)
    def test_tax_roll_traversal_blocked(self, client, auth_token, path):
        resp = client.post(
            "/ingest/tax-roll",
            params={"file_path": path},
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 403

    @pytest.mark.parametrize("path", TRAVERSAL_PATHS)
    def test_universal_traversal_blocked(self, client, auth_token, path):
        resp = client.post(
            "/ingest/universal",
            json={"file_path": path},
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 403

    @pytest.mark.parametrize("path", TRAVERSAL_PATHS)
    def test_enrich_traversal_blocked(self, client, auth_token, path):
        resp = client.post(
            "/ingest/enrich",
            json={"file_path": path},
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert resp.status_code == 403

    def test_unauthenticated_ingestion_blocked(self, client):
        """Ingestion endpoints require auth."""
        resp = client.post("/ingest/tax-roll", params={"file_path": "/tmp/test.csv"})
        assert resp.status_code == 401
