"""Lead domain service - core business logic for lead management."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from core.config import get_settings
from core.logging_config import get_logger
from core.models import Lead, Owner, Parcel, Party, OutreachAttempt, PipelineStage

LOGGER = get_logger(__name__)
SETTINGS = get_settings()


@dataclass
class LeadSummary:
    """Summary data for a lead."""
    
    # Required fields (non-optional)
    id: int
    owner_name: str
    parcel_id: str
    parish: str
    motivation_score: int
    status: str
    pipeline_stage: str
    market_code: str
    is_tcpa_safe: bool
    is_adjudicated: bool
    outreach_count: int
    created_at: datetime
    
    # Optional fields (have default None)
    owner_phone: Optional[str] = None
    city: Optional[str] = None
    situs_address: Optional[str] = None  # Property address (where land is)
    acreage: Optional[float] = None
    last_reply_classification: Optional[str] = None
    
    @property
    def display_address(self) -> str:
        """
        Deterministic address display:
        - If situs exists → show it
        - Else → show Parcel <parcel_id>, <Parish>
        """
        if self.situs_address and self.situs_address.strip():
            return self.situs_address
        return f"Parcel {self.parcel_id}"
    
    @property
    def display_location(self) -> str:
        """Secondary location context (city/parish)."""
        parts = []
        if self.city:
            parts.append(self.city)
        if self.parish:
            parts.append(self.parish)
        return ", ".join(parts) if parts else self.market_code
    
    @property
    def has_situs_address(self) -> bool:
        """Whether we have a real situs address."""
        return bool(self.situs_address and self.situs_address.strip())
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "id": self.id,
            "owner_name": self.owner_name,
            "owner_phone": self.owner_phone,
            "parcel_id": self.parcel_id,
            "parish": self.parish,
            "city": self.city,
            "situs_address": self.situs_address,
            "display_address": self.display_address,
            "display_location": self.display_location,
            "has_situs_address": self.has_situs_address,
            "acreage": float(self.acreage) if self.acreage else None,
            "motivation_score": self.motivation_score,
            "status": self.status,
            "pipeline_stage": self.pipeline_stage,
            "market_code": self.market_code,
            "is_tcpa_safe": self.is_tcpa_safe,
            "is_adjudicated": self.is_adjudicated,
            "outreach_count": self.outreach_count,
            "last_reply_classification": self.last_reply_classification,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


@dataclass
class LeadDetail(LeadSummary):
    """Detailed lead data including parcel and outreach history."""
    
    # Additional fields beyond LeadSummary
    owner_email: Optional[str] = None
    mailing_address: Optional[str] = None
    land_value: Optional[float] = None
    improvement_value: Optional[float] = None
    years_tax_delinquent: int = 0
    tags: List[str] = field(default_factory=list)
    geometry_wkt: Optional[str] = None
    recent_outreach: List[Dict[str, Any]] = field(default_factory=list)
    enrichment_data: Optional[Dict[str, Any]] = None
    score_details: Optional[Dict[str, Any]] = None
    followup_count: int = 0
    last_followup_at: Optional[datetime] = None
    next_followup_at: Optional[datetime] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        base = super().to_dict()
        base.update({
            "owner_email": self.owner_email,
            "mailing_address": self.mailing_address,
            "land_value": float(self.land_value) if self.land_value else None,
            "improvement_value": float(self.improvement_value) if self.improvement_value else None,
            "years_tax_delinquent": self.years_tax_delinquent,
            "tags": self.tags,
            "geometry_wkt": self.geometry_wkt,
            "recent_outreach": self.recent_outreach,
            "enrichment": self.enrichment_data,
            "score_details": self.score_details,
            "followup_count": self.followup_count,
            "last_followup_at": self.last_followup_at.isoformat() if self.last_followup_at else None,
            "next_followup_at": self.next_followup_at.isoformat() if self.next_followup_at else None,
            "latitude": self.latitude,
            "longitude": self.longitude,
        })
        return base


class LeadService:
    """Service for lead-related operations."""
    
    def __init__(self, session: Session) -> None:
        """Initialize the lead service with a database session."""
        self.session = session
    
    def _lead_to_summary(self, lead: Lead) -> LeadSummary:
        """Convert a Lead model to LeadSummary."""
        owner = lead.owner
        parcel = lead.parcel
        party = owner.party
        
        return LeadSummary(
            # Required fields
            id=lead.id,
            owner_name=party.display_name or party.normalized_name,
            parcel_id=parcel.canonical_parcel_id,
            parish=parcel.parish,
            motivation_score=lead.motivation_score,
            status=lead.status,
            pipeline_stage=lead.pipeline_stage or PipelineStage.NEW.value,
            market_code=lead.market_code,
            is_tcpa_safe=owner.is_tcpa_safe,
            is_adjudicated=parcel.is_adjudicated,
            outreach_count=len(lead.outreach_attempts) if lead.outreach_attempts else 0,
            created_at=lead.created_at,
            # Optional fields
            owner_phone=owner.phone_primary,
            city=parcel.city,
            situs_address=parcel.situs_address,
            acreage=parcel.lot_size_acres,
            last_reply_classification=lead.last_reply_classification,
        )
    
    def _lead_to_detail(self, lead: Lead) -> LeadDetail:
        """Convert a Lead model to LeadDetail."""
        owner = lead.owner
        parcel = lead.parcel
        party = owner.party
        
        # Get geometry as WKT if available
        geometry_wkt = None
        if parcel.geom is not None:
            try:
                # If stored as WKT string
                if isinstance(parcel.geom, str):
                    geometry_wkt = parcel.geom
                else:
                    from geoalchemy2.shape import to_shape
                    shape = to_shape(parcel.geom)
                    geometry_wkt = shape.wkt
            except Exception:
                pass
        
        # Format recent outreach
        recent_outreach = []
        for attempt in (lead.outreach_attempts or [])[:10]:
            recent_outreach.append({
                "id": attempt.id,
                "channel": attempt.channel,
                "status": attempt.status,
                "message_body": attempt.message_body,
                "message_context": attempt.message_context,
                "external_id": attempt.external_id,
                "reply_classification": attempt.reply_classification,
                "response_body": attempt.response_body,
                "sent_at": attempt.sent_at.isoformat() if attempt.sent_at else None,
                "created_at": attempt.created_at.isoformat() if attempt.created_at else None,
            })
        
        return LeadDetail(
            # Required fields from LeadSummary
            id=lead.id,
            owner_name=party.display_name or party.normalized_name,
            parcel_id=parcel.canonical_parcel_id,
            parish=parcel.parish,
            motivation_score=lead.motivation_score,
            status=lead.status,
            pipeline_stage=lead.pipeline_stage or PipelineStage.NEW.value,
            market_code=lead.market_code,
            is_tcpa_safe=owner.is_tcpa_safe,
            is_adjudicated=parcel.is_adjudicated,
            outreach_count=len(lead.outreach_attempts) if lead.outreach_attempts else 0,
            created_at=lead.created_at,
            # Optional fields from LeadSummary
            owner_phone=owner.phone_primary,
            city=parcel.city,
            situs_address=parcel.situs_address,
            acreage=parcel.lot_size_acres,
            last_reply_classification=lead.last_reply_classification,
            # LeadDetail-specific fields
            owner_email=owner.email,
            mailing_address=party.raw_mailing_address,
            land_value=parcel.land_assessed_value,
            improvement_value=parcel.improvement_assessed_value,
            years_tax_delinquent=parcel.years_tax_delinquent,
            tags=list(lead.tags) if lead.tags else [],
            geometry_wkt=geometry_wkt,
            recent_outreach=recent_outreach,
            score_details=lead.score_details,
            followup_count=lead.followup_count,
            last_followup_at=lead.last_followup_at,
            next_followup_at=lead.next_followup_at,
            latitude=parcel.latitude,
            longitude=parcel.longitude,
        )
    
    def list_leads(
        self,
        limit: int = 100,
        offset: int = 0,
        market_code: Optional[str] = None,
        pipeline_stage: Optional[str] = None,
        min_score: Optional[int] = None,
        status: Optional[str] = None,
        tcpa_safe_only: bool = False,
        order_by: str = "score_desc",
    ) -> List[LeadSummary]:
        """
        List leads with filtering and pagination.
        
        Args:
            limit: Maximum number of leads to return.
            offset: Number of leads to skip.
            market_code: Filter by market (LA, TX, MS, AR, AL).
            pipeline_stage: Filter by pipeline stage (NEW, CONTACTED, HOT).
            min_score: Minimum motivation score filter.
            status: Filter by status (e.g., 'new', 'contacted').
            tcpa_safe_only: If True, only return TCPA-safe leads.
            order_by: Sort order ('score_desc', 'score_asc', 'created_desc', 'created_asc').
        
        Returns:
            List of LeadSummary objects.
        """
        query = (
            self.session.query(Lead)
            .join(Lead.owner)
            .join(Lead.parcel)
            .options(
                selectinload(Lead.owner).selectinload(Owner.party),
                selectinload(Lead.parcel),
                selectinload(Lead.outreach_attempts),
            )
        )
        
        # Exclude soft-deleted leads
        query = query.filter(Lead.deleted_at.is_(None))
        
        # Apply filters
        if market_code:
            query = query.filter(Lead.market_code == market_code.upper())
        
        if pipeline_stage:
            query = query.filter(Lead.pipeline_stage == pipeline_stage.upper())
        
        if min_score is not None:
            query = query.filter(Lead.motivation_score >= min_score)
        
        if status:
            query = query.filter(Lead.status == status)
        
        if tcpa_safe_only:
            query = query.filter(Owner.is_tcpa_safe.is_(True))
        
        # Apply ordering
        if order_by == "score_desc":
            query = query.order_by(Lead.motivation_score.desc(), Lead.created_at.asc())
        elif order_by == "score_asc":
            query = query.order_by(Lead.motivation_score.asc(), Lead.created_at.asc())
        elif order_by == "created_desc":
            query = query.order_by(Lead.created_at.desc())
        elif order_by == "created_asc":
            query = query.order_by(Lead.created_at.asc())
        
        leads = query.offset(offset).limit(limit).all()
        return [self._lead_to_summary(lead) for lead in leads]
    
    def count_leads(
        self,
        market_code: Optional[str] = None,
        pipeline_stage: Optional[str] = None,
        min_score: Optional[int] = None,
        status: Optional[str] = None,
        tcpa_safe_only: bool = False,
    ) -> int:
        """
        Count leads matching the given filters.
        
        Args:
            market_code: Filter by market (LA, TX, MS, AR, AL).
            pipeline_stage: Filter by pipeline stage (NEW, CONTACTED, HOT).
            min_score: Minimum motivation score filter.
            status: Filter by status.
            tcpa_safe_only: If True, only count TCPA-safe leads.
        
        Returns:
            Total count of matching leads.
        """
        query = self.session.query(func.count(Lead.id)).join(Lead.owner)
        
        # Exclude soft-deleted leads
        query = query.filter(Lead.deleted_at.is_(None))
        
        if market_code:
            query = query.filter(Lead.market_code == market_code.upper())
        
        if pipeline_stage:
            query = query.filter(Lead.pipeline_stage == pipeline_stage.upper())
        
        if min_score is not None:
            query = query.filter(Lead.motivation_score >= min_score)
        
        if status:
            query = query.filter(Lead.status == status)
        
        if tcpa_safe_only:
            query = query.filter(Owner.is_tcpa_safe.is_(True))
        
        return query.scalar() or 0
    
    def get_lead(self, lead_id: int) -> Optional[LeadDetail]:
        """
        Get detailed information for a specific lead.
        
        Args:
            lead_id: The lead ID to fetch.
        
        Returns:
            LeadDetail object or None if not found.
        """
        lead = (
            self.session.query(Lead)
            .join(Lead.owner)
            .join(Lead.parcel)
            .options(
                selectinload(Lead.owner).selectinload(Owner.party),
                selectinload(Lead.parcel),
                selectinload(Lead.outreach_attempts),
            )
            .filter(Lead.id == lead_id)
            .one_or_none()
        )
        
        if lead is None:
            return None
        
        return self._lead_to_detail(lead)
    
    def get_lead_by_parcel(self, parcel_id: str) -> Optional[LeadDetail]:
        """
        Get lead by parcel ID.
        
        Args:
            parcel_id: The canonical parcel ID.
        
        Returns:
            LeadDetail object or None if not found.
        """
        lead = (
            self.session.query(Lead)
            .join(Lead.owner)
            .join(Lead.parcel)
            .options(
                selectinload(Lead.owner).selectinload(Owner.party),
                selectinload(Lead.parcel),
                selectinload(Lead.outreach_attempts),
            )
            .filter(Parcel.canonical_parcel_id == parcel_id)
            .first()
        )
        
        if lead is None:
            return None
        
        return self._lead_to_detail(lead)
    
    def update_lead_status(self, lead_id: int, status: str) -> Optional[LeadDetail]:
        """
        Update a lead's status.
        
        Args:
            lead_id: The lead ID to update.
            status: New status value.
        
        Returns:
            Updated LeadDetail or None if not found.
        """
        lead = self.session.query(Lead).filter(Lead.id == lead_id).one_or_none()
        if lead is None:
            return None
        
        lead.status = status
        lead.updated_at = datetime.now(timezone.utc)
        self.session.flush()
        
        return self.get_lead(lead_id)
    
    def get_statistics(self, market_code: Optional[str] = None) -> Dict[str, Any]:
        """
        Get lead statistics summary.
        
        Args:
            market_code: Optional filter by market.
        
        Returns:
            Dictionary with various counts and averages.
        """
        base_query = self.session.query(Lead)
        if market_code:
            base_query = base_query.filter(Lead.market_code == market_code.upper())
        
        total_leads = base_query.with_entities(func.count(Lead.id)).scalar() or 0
        
        tcpa_safe_query = base_query.join(Lead.owner).filter(Owner.is_tcpa_safe.is_(True))
        tcpa_safe = tcpa_safe_query.with_entities(func.count(Lead.id)).scalar() or 0
        
        avg_score = base_query.with_entities(func.avg(Lead.motivation_score)).scalar() or 0
        
        high_score = base_query.filter(
            Lead.motivation_score >= SETTINGS.min_motivation_score
        ).with_entities(func.count(Lead.id)).scalar() or 0
        
        # Status breakdown
        status_counts = dict(
            base_query.with_entities(Lead.status, func.count(Lead.id))
            .group_by(Lead.status)
            .all()
        )
        
        # Pipeline stage breakdown
        stage_counts = dict(
            base_query.with_entities(Lead.pipeline_stage, func.count(Lead.id))
            .group_by(Lead.pipeline_stage)
            .all()
        )
        
        # Hot leads (high score + INTERESTED/SEND_OFFER classification)
        hot_leads = base_query.filter(
            Lead.pipeline_stage == PipelineStage.HOT.value
        ).with_entities(func.count(Lead.id)).scalar() or 0
        
        return {
            "total_leads": total_leads,
            "tcpa_safe_leads": tcpa_safe,
            "high_score_leads": high_score,
            "hot_leads": hot_leads,
            "average_score": round(float(avg_score), 1),
            "min_score_threshold": SETTINGS.min_motivation_score,
            "status_breakdown": status_counts,
            "stage_breakdown": stage_counts,
            "market": market_code or "all",
        }
    
    def create_manual_lead(
        self,
        owner_name: str,
        address: str,
        city: str = "Baton Rouge",
        state: str = "LA",
        postal_code: Optional[str] = None,
        parish: str = "East Baton Rouge",
        phone: Optional[str] = None,
        notes: Optional[str] = None,
        tcpa_safe: bool = False,
        enrich: bool = True,
        market_code: str = "LA",
    ) -> LeadDetail:
        """
        Create a lead manually from provided owner and parcel information.
        
        This creates or reuses Party, Owner, and Parcel records, then creates
        the Lead linking them together. The lead is immediately scored.
        
        Optionally enriches with external data (USPS, Google, comps).
        
        Args:
            owner_name: Owner's full name (required).
            address: Property street address (required).
            city: City name.
            state: State abbreviation (2 chars).
            postal_code: ZIP code.
            parish: Parish/county name.
            phone: Owner's phone number (will be normalized).
            notes: Optional notes about the lead.
            tcpa_safe: Whether TCPA consent is confirmed.
            enrich: Whether to fetch external enrichment data.
            market_code: Market code (LA, TX, MS, AR, AL).
        
        Returns:
            LeadDetail of the created lead (with enrichment if enabled).
        
        Raises:
            ValueError: If required fields are missing.
        """
        import hashlib
        from outreach.phone import normalize_phone_e164
        from scoring.engine import compute_motivation_score
        
        if not owner_name or not address:
            raise ValueError("owner_name and address are required")
        
        # Normalize market code
        market_code = market_code.upper()
        
        # Normalize phone if provided
        normalized_phone = None
        if phone:
            normalized_phone = normalize_phone_e164(phone)
        
        # Run external enrichment first (to get standardized address)
        enrichment_data: Optional[Dict[str, Any]] = None
        standardized_address = address
        standardized_city = city
        standardized_state = state
        standardized_zip = postal_code
        latitude: Optional[float] = None
        longitude: Optional[float] = None
        
        if enrich:
            try:
                from services.external_data import get_external_data_service
                
                ext_service = get_external_data_service()
                enriched = ext_service.enrich_address(
                    address=address,
                    city=city,
                    state=state,
                    zip_code=postal_code,
                    include_usps=True,
                    include_geocode=True,
                    include_comps=True,
                    include_county=False,
                )
                enrichment_data = enriched.to_dict()
                
                if enriched.usps_verified and enriched.usps_standardized_address:
                    standardized_address = enriched.usps_standardized_address
                    standardized_city = enriched.usps_city or city
                    standardized_state = enriched.usps_state or state
                    standardized_zip = enriched.usps_zip5 or postal_code
                
                if enriched.has_coordinates:
                    latitude = enriched.latitude
                    longitude = enriched.longitude
                
                LOGGER.info(f"Enriched address: {enriched.best_address}")
                
            except Exception as e:
                LOGGER.warning(f"Enrichment failed (continuing without): {e}")
        
        # Generate parcel ID from (standardized) address
        address_key = f"{standardized_address}|{standardized_city}|{standardized_state}".upper()
        parcel_id = hashlib.sha256(address_key.encode()).hexdigest()[:12].upper()
        
        # Check for existing parcel
        parcel = self.session.query(Parcel).filter(
            Parcel.canonical_parcel_id == parcel_id
        ).first()
        
        if not parcel:
            parcel = Parcel(
                canonical_parcel_id=parcel_id,
                parish=parish,
                market_code=market_code,
                situs_address=standardized_address,
                city=standardized_city,
                state=standardized_state,
                postal_code=standardized_zip,
                latitude=latitude,
                longitude=longitude,
                is_adjudicated=False,
                years_tax_delinquent=0,
            )
            self.session.add(parcel)
            self.session.flush()
        
        # Create Party (owner identity)
        owner_normalized = owner_name.strip().upper()
        mailing_zip = standardized_zip or ""
        match_str = f"{owner_normalized}|{mailing_zip}"
        match_hash = hashlib.sha256(match_str.encode()).hexdigest()
        
        party = self.session.query(Party).filter(Party.match_hash == match_hash).first()
        
        if not party:
            party = Party(
                normalized_name=owner_normalized,
                normalized_zip=mailing_zip,
                match_hash=match_hash,
                display_name=owner_name.strip(),
                raw_mailing_address=f"{standardized_address}, {standardized_city}, {standardized_state} {standardized_zip or ''}".strip(),
                party_type="individual",
                market_code=market_code,
            )
            self.session.add(party)
            self.session.flush()
        
        # Create Owner (contact info)
        owner = self.session.query(Owner).filter(Owner.party_id == party.id).first()
        
        if not owner:
            owner = Owner(
                party_id=party.id,
                phone_primary=normalized_phone,
                market_code=market_code,
                is_tcpa_safe=tcpa_safe or bool(normalized_phone),
                is_dnr=False,
                opt_out=False,
            )
            self.session.add(owner)
            self.session.flush()
        else:
            if normalized_phone and not owner.phone_primary:
                owner.phone_primary = normalized_phone
                owner.is_tcpa_safe = tcpa_safe or True
        
        # Check for existing lead
        existing_lead = self.session.query(Lead).filter(
            Lead.owner_id == owner.id,
            Lead.parcel_id == parcel.id,
        ).first()
        
        if existing_lead:
            if notes:
                existing_lead.tags = [notes]
            lead_detail = self._lead_to_detail(existing_lead)
            lead_detail.enrichment_data = enrichment_data
            return lead_detail
        
        # Create Lead
        lead = Lead(
            owner_id=owner.id,
            parcel_id=parcel.id,
            market_code=market_code,
            pipeline_stage=PipelineStage.NEW.value,
            status="new",
            motivation_score=0,
            tags=[notes] if notes else [],
        )
        self.session.add(lead)
        self.session.flush()
        
        # Score the lead immediately
        score = compute_motivation_score(parcel, owner, is_adjudicated=parcel.is_adjudicated)
        lead.motivation_score = score
        
        LOGGER.info(f"Created manual lead {lead.id} with score {score} in market {market_code}")
        
        lead_detail = self._lead_to_detail(lead)
        lead_detail.enrichment_data = enrichment_data
        return lead_detail


__all__ = ["LeadService", "LeadSummary", "LeadDetail"]
