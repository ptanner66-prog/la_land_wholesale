"""Tests for authentication system: registration, login, tokens, and protected routes."""
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
from core.auth import hash_password, verify_password, create_access_token, decode_access_token
from core.models import User, RefreshToken
from api.app import app
from api.deps import get_db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Unit Tests: Password Hashing
# ---------------------------------------------------------------------------

class TestPasswordHashing:
    def test_hash_and_verify(self):
        pwd = "my-secret-pass"
        hashed = hash_password(pwd)
        assert hashed != pwd
        assert verify_password(pwd, hashed)

    def test_wrong_password_fails(self):
        hashed = hash_password("correct")
        assert not verify_password("wrong", hashed)


# ---------------------------------------------------------------------------
# Unit Tests: JWT Tokens
# ---------------------------------------------------------------------------

class TestJWTTokens:
    def test_create_and_decode_access_token(self):
        token = create_access_token(user_id=1, email="test@test.com", role="admin")
        payload = decode_access_token(token)
        assert payload is not None
        assert payload["sub"] == "1"
        assert payload["email"] == "test@test.com"
        assert payload["role"] == "admin"
        assert payload["type"] == "access"

    def test_invalid_token_returns_none(self):
        assert decode_access_token("garbage.token.here") is None

    def test_empty_token_returns_none(self):
        assert decode_access_token("") is None


# ---------------------------------------------------------------------------
# Integration Tests: Auth Endpoints
# ---------------------------------------------------------------------------

class TestRegister:
    def test_register_success(self, client):
        resp = client.post("/auth/register", json={
            "email": "newuser@example.com",
            "password": "securepass123",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

    def test_register_duplicate_email(self, client):
        client.post("/auth/register", json={
            "email": "dupe@example.com",
            "password": "securepass123",
        })
        resp = client.post("/auth/register", json={
            "email": "dupe@example.com",
            "password": "otherpass456",
        })
        assert resp.status_code == 409

    def test_register_short_password(self, client):
        resp = client.post("/auth/register", json={
            "email": "short@example.com",
            "password": "short",
        })
        assert resp.status_code == 422


class TestLogin:
    def test_login_success(self, client):
        # Register first
        client.post("/auth/register", json={
            "email": "login@example.com",
            "password": "securepass123",
        })
        resp = client.post("/auth/login", json={
            "email": "login@example.com",
            "password": "securepass123",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data

    def test_login_wrong_password(self, client):
        client.post("/auth/register", json={
            "email": "wrongpwd@example.com",
            "password": "securepass123",
        })
        resp = client.post("/auth/login", json={
            "email": "wrongpwd@example.com",
            "password": "wrongpassword",
        })
        assert resp.status_code == 401

    def test_login_nonexistent_user(self, client):
        resp = client.post("/auth/login", json={
            "email": "nobody@example.com",
            "password": "securepass123",
        })
        assert resp.status_code == 401


class TestTokenRefresh:
    def test_refresh_token_success(self, client):
        reg_resp = client.post("/auth/register", json={
            "email": "refresh@example.com",
            "password": "securepass123",
        })
        refresh_token = reg_resp.json()["refresh_token"]

        resp = client.post("/auth/refresh", json={
            "refresh_token": refresh_token,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        # New refresh token should be different
        assert data["refresh_token"] != refresh_token

    def test_refresh_invalid_token(self, client):
        resp = client.post("/auth/refresh", json={
            "refresh_token": "invalid-token",
        })
        assert resp.status_code == 401


class TestProtectedRoutes:
    def test_unauthenticated_access_blocked(self, client):
        resp = client.get("/leads")
        assert resp.status_code == 401

    def test_authenticated_access_allowed(self, client):
        reg_resp = client.post("/auth/register", json={
            "email": "authuser@example.com",
            "password": "securepass123",
        })
        token = reg_resp.json()["access_token"]

        resp = client.get("/leads", headers={
            "Authorization": f"Bearer {token}",
        })
        # Should not be 401 — it may be 200 or another code depending on data
        assert resp.status_code != 401

    def test_invalid_token_rejected(self, client):
        resp = client.get("/leads", headers={
            "Authorization": "Bearer invalid.jwt.token",
        })
        assert resp.status_code == 401


class TestGetMe:
    def test_get_me_success(self, client):
        reg_resp = client.post("/auth/register", json={
            "email": "me@example.com",
            "password": "securepass123",
        })
        token = reg_resp.json()["access_token"]

        resp = client.get("/auth/me", headers={
            "Authorization": f"Bearer {token}",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == "me@example.com"
        assert "id" in data
        assert "role" in data


class TestLogout:
    def test_logout_revokes_refresh(self, client):
        reg_resp = client.post("/auth/register", json={
            "email": "logout@example.com",
            "password": "securepass123",
        })
        refresh_token = reg_resp.json()["refresh_token"]

        # Logout
        resp = client.post("/auth/logout", json={
            "refresh_token": refresh_token,
        })
        assert resp.status_code == 200

        # Refresh should now fail
        resp = client.post("/auth/refresh", json={
            "refresh_token": refresh_token,
        })
        assert resp.status_code == 401


class TestHealthEndpointPublic:
    def test_health_no_auth_required(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] in ("ok", "healthy")
