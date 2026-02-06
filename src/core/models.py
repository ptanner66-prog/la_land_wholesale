"""SQLAlchemy ORM models for la_land_wholesale."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum as SQLEnum,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from core.db import Base


# =============================================================================
# Enums
# =============================================================================


class MarketCode(str, enum.Enum):
    """Supported market codes."""
    LA = "LA"  # Louisiana
    TX = "TX"  # Texas
    MS = "MS"  # Mississippi
    AR = "AR"  # Arkansas
    AL = "AL"  # Alabama


class PipelineStage(str, enum.Enum):
    """Lead pipeline stages."""
    INGESTED = "INGESTED"      # Raw data, not enriched
    ENRICHING = "ENRICHING"    # In enrichment queue
    PRE_SCORE = "PRE_SCORE"    # Enriched, awaiting scoring
    NEW = "NEW"                # Scored, ready for outreach
    CONTACTED = "CONTACTED"    # First outreach sent
    REVIEW = "REVIEW"          # Needs manual review
    OFFER = "OFFER"            # Offer sent
    CONTRACT = "CONTRACT"      # Under contract
    HOT = "HOT"                # High priority (legacy)


class ReplyClassification(str, enum.Enum):
    """AI-classified reply types."""
    INTERESTED = "INTERESTED"
    NOT_INTERESTED = "NOT_INTERESTED"
    SEND_OFFER = "SEND_OFFER"
    CONFUSED = "CONFUSED"
    DEAD = "DEAD"


class TaskStatus(str, enum.Enum):
    """Background task statuses."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class BuyerDealStage(str, enum.Enum):
    """Buyer deal pipeline stages."""
    NEW = "NEW"
    DEAL_SENT = "DEAL_SENT"
    VIEWED = "VIEWED"
    INTERESTED = "INTERESTED"
    NEGOTIATING = "NEGOTIATING"
    OFFERED = "OFFERED"
    CLOSED = "CLOSED"
    PASSED = "PASSED"


class PropertyType(str, enum.Enum):
    """Land property types."""
    INFILL = "infill"
    RURAL = "rural"
    WOODED = "wooded"
    LOT = "lot"
    AGRICULTURAL = "agricultural"
    RECREATIONAL = "recreational"
    WATERFRONT = "waterfront"


# =============================================================================
# Party Model
# =============================================================================


class Party(Base):
    """
    A normalized identity representing an owner across parcels.
    
    Multiple Owner records may link to the same Party based on
    name + mailing ZIP matching.
    """
    __tablename__ = "party"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    # Identity matching fields
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    normalized_zip: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    match_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    
    # Display fields
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    raw_mailing_address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    party_type: Mapped[str] = mapped_column(String(50), default="individual")
    
    # Market
    market_code: Mapped[str] = mapped_column(
        String(2), 
        default=MarketCode.LA.value,
        index=True
    )
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    owners: Mapped[list["Owner"]] = relationship("Owner", back_populates="party")

    __table_args__ = (
        Index("ix_party_match", "normalized_name", "normalized_zip"),
    )


# =============================================================================
# Owner Model
# =============================================================================


class Owner(Base):
    """
    Contact and preference information for a property owner.
    
    Links to Party for identity and can be associated with multiple Leads.
    """
    __tablename__ = "owner"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    party_id: Mapped[int] = mapped_column(ForeignKey("party.id"), nullable=False, index=True)

    # Contact info
    phone_primary: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, index=True)
    phone_secondary: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    # Market
    market_code: Mapped[str] = mapped_column(
        String(2), 
        default=MarketCode.LA.value,
        index=True
    )

    # Compliance flags
    is_tcpa_safe: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_dnr: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    opt_out: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    opt_out_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    party: Mapped["Party"] = relationship("Party", back_populates="owners")
    leads: Mapped[list["Lead"]] = relationship("Lead", back_populates="owner")

    __table_args__ = (
        Index("ix_owner_market_tcpa", "market_code", "is_tcpa_safe"),
    )


# =============================================================================
# Parcel Model
# =============================================================================


class Parcel(Base):
    """
    A property parcel with assessment and location data.
    """
    __tablename__ = "parcel"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    # Parcel identification
    canonical_parcel_id: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, index=True
    )
    parish: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    
    # Market
    market_code: Mapped[str] = mapped_column(
        String(2), 
        default=MarketCode.LA.value,
        index=True
    )

    # Location
    situs_address: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    state: Mapped[Optional[str]] = mapped_column(String(2), nullable=True)
    postal_code: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    
    # Coordinates (from Google Maps enrichment)
    latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # GIS / Zoning
    zoning_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    geom: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # WKT or GeoJSON
    inside_city_limits: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)

    # Assessment values
    land_assessed_value: Mapped[Optional[float]] = mapped_column(Numeric(14, 2), nullable=True)
    improvement_assessed_value: Mapped[Optional[float]] = mapped_column(Numeric(14, 2), nullable=True)
    lot_size_acres: Mapped[Optional[float]] = mapped_column(Numeric(10, 4), nullable=True)

    # Distress indicators
    is_adjudicated: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    years_tax_delinquent: Mapped[int] = mapped_column(Integer, default=0)

    # Raw data storage
    raw_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    leads: Mapped[list["Lead"]] = relationship("Lead", back_populates="parcel")

    __table_args__ = (
        Index("ix_parcel_market_adjudicated", "market_code", "is_adjudicated"),
    )


# =============================================================================
# Lead Model
# =============================================================================


class Lead(Base):
    """
    A lead combining an owner and parcel, tracked through the pipeline.
    """
    __tablename__ = "lead"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    # Foreign keys
    owner_id: Mapped[int] = mapped_column(ForeignKey("owner.id"), nullable=False, index=True)
    parcel_id: Mapped[int] = mapped_column(ForeignKey("parcel.id"), nullable=False, index=True)
    
    # Market
    market_code: Mapped[str] = mapped_column(
        String(2), 
        default=MarketCode.LA.value,
        index=True
    )

    # Scoring
    motivation_score: Mapped[int] = mapped_column(Integer, default=0, index=True)
    score_details: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    
    # Pipeline
    pipeline_stage: Mapped[str] = mapped_column(
        String(20),
        default=PipelineStage.NEW.value,
        index=True
    )
    status: Mapped[str] = mapped_column(String(50), default="new", index=True)

    # Reply classification
    last_reply_classification: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, index=True)
    last_reply_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Follow-up tracking
    followup_count: Mapped[int] = mapped_column(Integer, default=0)
    last_followup_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    next_followup_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    
    # Alert tracking (for deduplication)
    last_alerted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Send locking (prevent concurrent sends)
    send_locked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    send_locked_by: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    
    # Tags and metadata
    tags: Mapped[list] = mapped_column(JSON, default=list)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    
    # Soft delete
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    # Relationships
    owner: Mapped["Owner"] = relationship("Owner", back_populates="leads")
    parcel: Mapped["Parcel"] = relationship("Parcel", back_populates="leads")
    outreach_attempts: Mapped[list["OutreachAttempt"]] = relationship(
        "OutreachAttempt", back_populates="lead", order_by="desc(OutreachAttempt.created_at)"
    )
    timeline_events: Mapped[list["TimelineEvent"]] = relationship(
        "TimelineEvent", back_populates="lead", order_by="desc(TimelineEvent.created_at)"
    )
    buyer_deals: Mapped[list["BuyerDeal"]] = relationship(
        "BuyerDeal", back_populates="lead", order_by="desc(BuyerDeal.created_at)"
    )
    deal_sheet: Mapped[Optional["DealSheet"]] = relationship(
        "DealSheet", back_populates="lead", uselist=False
    )

    __table_args__ = (
        Index("ix_lead_market_score", "market_code", "motivation_score"),
        Index("ix_lead_market_stage", "market_code", "pipeline_stage"),
        Index("ix_lead_followup", "next_followup_at", "pipeline_stage"),
        Index("ix_lead_last_alerted", "last_alerted_at"),
    )


# =============================================================================
# OutreachAttempt Model
# =============================================================================


class OutreachAttempt(Base):
    """
    A record of an outreach attempt (SMS, email, etc.) to a lead.
    """
    __tablename__ = "outreach_attempt"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("lead.id"), nullable=False, index=True)

    # Idempotency
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, unique=True, index=True)

    # Channel and content
    channel: Mapped[str] = mapped_column(String(20), default="sms")
    message_body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    message_context: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # intro, followup, final
    
    # Status
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    result: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # sent, dry_run, failed, etc.
    external_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)  # Twilio SID

    # Timestamps
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Response
    response_received_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    response_body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reply_classification: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    
    # Errors
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    lead: Mapped["Lead"] = relationship("Lead", back_populates="outreach_attempts")

    __table_args__ = (
        Index("ix_outreach_lead_status", "lead_id", "status"),
        Index("ix_outreach_external_id", "external_id"),
        Index("ix_outreach_idempotency", "idempotency_key", unique=True),
    )


# =============================================================================
# TimelineEvent Model
# =============================================================================


class TimelineEvent(Base):
    """
    A timeline event for tracking lead activity history.
    """
    __tablename__ = "timeline_event"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("lead.id"), nullable=False, index=True)
    
    # Event data
    event_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    event_metadata: Mapped[Optional[dict]] = mapped_column("metadata", JSON, nullable=True)
    
    # Timestamp
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    lead: Mapped["Lead"] = relationship("Lead", back_populates="timeline_events")


# =============================================================================
# AlertConfig Model
# =============================================================================


class AlertConfig(Base):
    """
    Configuration for hot lead alerts.
    """
    __tablename__ = "alert_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    market_code: Mapped[str] = mapped_column(String(2), unique=True, nullable=False)
    
    # Alert settings
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    hot_score_threshold: Mapped[int] = mapped_column(Integer, default=75)
    alert_phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    slack_webhook_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    
    # Alert deduplication (hours)
    dedup_hours: Mapped[int] = mapped_column(Integer, default=24)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


# =============================================================================
# BackgroundTask Model
# =============================================================================


class BackgroundTask(Base):
    """
    Tracking for background/async tasks.
    """
    __tablename__ = "background_task"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    task_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), default=TaskStatus.PENDING.value, index=True)
    market_code: Mapped[Optional[str]] = mapped_column(String(2), nullable=True)
    
    # Task data
    params: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    result: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Timing
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# =============================================================================
# SchedulerLock Model
# =============================================================================


class SchedulerLock(Base):
    """
    Distributed locking for scheduler operations.
    """
    __tablename__ = "scheduler_lock"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lock_name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    locked_by: Mapped[str] = mapped_column(String(64), nullable=False)
    locked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


# =============================================================================
# Buyer Model
# =============================================================================


class Buyer(Base):
    """
    A land buyer with preferences and criteria for deals.
    """
    __tablename__ = "buyer"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    # Basic info
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    # Market preferences (stored as JSON array for SQLite compatibility)
    market_codes: Mapped[list] = mapped_column(JSON, default=list)  # ["LA", "TX"]
    counties: Mapped[list] = mapped_column(JSON, default=list)  # ["East Baton Rouge", "Harris"]
    
    # Property preferences
    min_acres: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_acres: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    property_types: Mapped[list] = mapped_column(JSON, default=list)  # ["infill", "rural"]
    
    # Budget
    price_min: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    price_max: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    target_spread: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # Desired assignment fee
    
    # Buyer profile
    closing_speed_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    vip: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Proof of Funds
    pof_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    pof_verified: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    pof_last_updated: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Performance metrics
    deals_count: Mapped[int] = mapped_column(Integer, default=0)
    response_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    last_deal_sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    deals: Mapped[list["BuyerDeal"]] = relationship("BuyerDeal", back_populates="buyer")


# =============================================================================
# BuyerDeal Model
# =============================================================================


class BuyerDeal(Base):
    """
    Tracks a deal between a buyer and a lead through the disposition pipeline.
    """
    __tablename__ = "buyer_deal"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    buyer_id: Mapped[int] = mapped_column(ForeignKey("buyer.id"), nullable=False, index=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("lead.id"), nullable=False, index=True)
    
    # Pipeline
    stage: Mapped[str] = mapped_column(
        String(20),
        default=BuyerDealStage.NEW.value,
        index=True
    )
    
    # Deal details
    match_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    offer_amount: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    assignment_fee: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Tracking timestamps
    blast_sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    viewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    responded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    buyer: Mapped["Buyer"] = relationship("Buyer", back_populates="deals")
    lead: Mapped["Lead"] = relationship("Lead", back_populates="buyer_deals")

    __table_args__ = (
        Index("ix_buyer_deal_buyer_lead", "buyer_id", "lead_id", unique=True),
    )


# =============================================================================
# DealSheet Model
# =============================================================================


class DealSheet(Base):
    """
    Cached deal sheet for a lead, used in buyer blasts.
    """
    __tablename__ = "deal_sheet"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("lead.id"), nullable=False, unique=True, index=True)
    
    # Content
    content: Mapped[dict] = mapped_column(JSON, nullable=False)
    ai_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Validity
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    lead: Mapped["Lead"] = relationship("Lead", back_populates="deal_sheet")


# =============================================================================
# User Model (Authentication)
# =============================================================================


class UserRole(str, enum.Enum):
    """User roles for authorization."""
    ADMIN = "admin"
    USER = "user"


class User(Base):
    """Application user for authentication and authorization."""
    __tablename__ = "user"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), default=UserRole.USER.value, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(
        "RefreshToken", back_populates="user", cascade="all, delete-orphan"
    )


class RefreshToken(Base):
    """Server-side refresh token storage for revocation support."""
    __tablename__ = "refresh_token"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped["User"] = relationship("User", back_populates="refresh_tokens")


# =============================================================================
# ManualComp Model
# =============================================================================


class ManualComp(Base):
    """Manually entered comparable sale for a parcel/market area."""
    __tablename__ = "manual_comp"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    parcel_id: Mapped[Optional[int]] = mapped_column(ForeignKey("parcel.id"), nullable=True, index=True)

    address: Mapped[str] = mapped_column(String(255), nullable=False)
    sale_date: Mapped[str] = mapped_column(String(20), nullable=False)
    sale_price: Mapped[float] = mapped_column(Float, nullable=False)
    lot_size_acres: Mapped[float] = mapped_column(Float, nullable=False)
    parish: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    market_code: Mapped[str] = mapped_column(String(2), default=MarketCode.LA.value, index=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


__all__ = [
    "Base",
    "MarketCode",
    "PipelineStage",
    "ReplyClassification",
    "TaskStatus",
    "BuyerDealStage",
    "PropertyType",
    "UserRole",
    "User",
    "RefreshToken",
    "Party",
    "Owner",
    "Parcel",
    "Lead",
    "OutreachAttempt",
    "TimelineEvent",
    "AlertConfig",
    "BackgroundTask",
    "SchedulerLock",
    "Buyer",
    "BuyerDeal",
    "DealSheet",
    "ManualComp",
]
