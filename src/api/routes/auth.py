"""Authentication routes: register, login, refresh, logout."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from api.deps import get_db
from api.auth_deps import check_login_rate_limit, get_current_user
from core.auth import (
    create_access_token,
    create_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from core.config import get_settings
from core.logging_config import get_logger
from core.models import RefreshToken, User

router = APIRouter()
LOGGER = get_logger(__name__)
SETTINGS = get_settings()


# =============================================================================
# Request/Response Models
# =============================================================================


class RegisterRequest(BaseModel):
    """Registration request body."""

    email: EmailStr = Field(..., description="User email address")
    password: str = Field(..., min_length=8, max_length=128, description="Password (min 8 chars)")


class LoginRequest(BaseModel):
    """Login request body."""

    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    """Token refresh request body."""

    refresh_token: str = Field(..., description="Refresh token from login")


class TokenResponse(BaseModel):
    """Token response with access and refresh tokens."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class UserResponse(BaseModel):
    """Public user information."""

    id: int
    email: str
    role: str
    created_at: str


# =============================================================================
# Routes
# =============================================================================


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterRequest,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Register a new user account.

    Returns JWT access token and refresh token on success.
    """
    existing = db.query(User).filter(User.email == body.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    user = User(
        email=body.email,
        hashed_password=hash_password(body.password),
        role="admin",  # First user gets admin; production should scope this
    )
    db.add(user)
    db.flush()

    access_token = create_access_token(user.id, user.email, user.role)
    raw_refresh, token_hash = create_refresh_token()

    refresh_record = RefreshToken(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=datetime.now(timezone.utc)
        + timedelta(days=SETTINGS.jwt_refresh_token_expire_days),
    )
    db.add(refresh_record)
    db.flush()

    LOGGER.info(f"User registered: {user.email}")

    return {
        "access_token": access_token,
        "refresh_token": raw_refresh,
        "token_type": "bearer",
        "expires_in": SETTINGS.jwt_access_token_expire_minutes * 60,
    }


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Authenticate user and return tokens.

    Rate limited to 5 attempts per minute per IP.
    """
    client_ip = request.client.host if request.client else "unknown"
    check_login_rate_limit(client_ip)

    user = db.query(User).filter(User.email == body.email).first()
    if not user or not verify_password(body.password, user.hashed_password):
        LOGGER.warning(f"Failed login attempt for: {body.email}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated",
        )

    access_token = create_access_token(user.id, user.email, user.role)
    raw_refresh, token_hash = create_refresh_token()

    refresh_record = RefreshToken(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=datetime.now(timezone.utc)
        + timedelta(days=SETTINGS.jwt_refresh_token_expire_days),
    )
    db.add(refresh_record)
    db.flush()

    LOGGER.info(f"User logged in: {user.email}")

    return {
        "access_token": access_token,
        "refresh_token": raw_refresh,
        "token_type": "bearer",
        "expires_in": SETTINGS.jwt_access_token_expire_minutes * 60,
    }


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    body: RefreshRequest,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Rotate refresh token and issue new access token.

    The old refresh token is revoked and a new one is issued.
    """
    token_hash = hash_refresh_token(body.refresh_token)

    stored = (
        db.query(RefreshToken)
        .filter(
            RefreshToken.token_hash == token_hash,
            RefreshToken.revoked.is_(False),
        )
        .first()
    )

    if not stored:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    if stored.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        stored.revoked = True
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token expired",
        )

    user = db.query(User).filter(User.id == stored.user_id, User.is_active.is_(True)).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    # Revoke old token
    stored.revoked = True
    db.flush()

    # Issue new tokens
    access_token = create_access_token(user.id, user.email, user.role)
    raw_refresh, new_hash = create_refresh_token()

    new_refresh = RefreshToken(
        user_id=user.id,
        token_hash=new_hash,
        expires_at=datetime.now(timezone.utc)
        + timedelta(days=SETTINGS.jwt_refresh_token_expire_days),
    )
    db.add(new_refresh)
    db.flush()

    return {
        "access_token": access_token,
        "refresh_token": raw_refresh,
        "token_type": "bearer",
        "expires_in": SETTINGS.jwt_access_token_expire_minutes * 60,
    }


@router.post("/logout")
async def logout(
    body: RefreshRequest,
    db: Session = Depends(get_db),
) -> Dict[str, str]:
    """Revoke refresh token to log out."""
    token_hash = hash_refresh_token(body.refresh_token)

    stored = db.query(RefreshToken).filter(RefreshToken.token_hash == token_hash).first()
    if stored:
        stored.revoked = True
        db.flush()

    return {"message": "Logged out successfully"}


@router.get("/me", response_model=UserResponse)
async def get_me(
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Get current authenticated user info."""
    return {
        "id": current_user.id,
        "email": current_user.email,
        "role": current_user.role,
        "created_at": current_user.created_at.isoformat() if current_user.created_at else "",
    }
