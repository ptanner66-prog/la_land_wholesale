"""
Unified Lead Enrichment Pipeline

This module orchestrates the complete enrichment flow:
Raw Lead → USPS → Google Maps → PropStream → AI Scoring → Final Enriched Lead

The pipeline includes:
- Address cleaning and standardization
- Lat/long extraction via geocoding
- Property data enrichment
- Owner profile gathering
- Property classification
- Vacancy detection
- Motivation scoring
- Final normalized enrichment
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from enum import Enum

from sqlalchemy.orm import Session

from core.config import get_settings
from core.logging_config import get_logger
from core.models import Lead, Parcel, Owner, Party
from core.utils import utcnow
from src.services.usps import verify_address, USPSVerificationResult
from src.services.google_maps import geocode, GeocodeResult
from src.services.propstream import get_propstream_service, PropStreamProperty, is_propstream_available
from src.services.timeline import TimelineService

LOGGER = get_logger(__name__)
SETTINGS = get_settings()


class PropertyClassification(str, Enum):
    """Property type classification."""
    VACANT_LAND = "vacant_land"
    RESIDENTIAL_LOT = "residential_lot"
    IMPROVED_RESIDENTIAL = "improved_residential"
    MOBILE_HOME_LOT = "mobile_home_lot"
    COMMERCIAL = "commercial"
    AGRICULTURAL = "agricultural"
    UNKNOWN = "unknown"


class OwnerType(str, Enum):
    """Owner classification."""
    INDIVIDUAL = "individual"
    CORPORATE = "corporate"
    TRUST = "trust"
    ESTATE = "estate"
    GOVERNMENT = "government"
    UNKNOWN = "unknown"


@dataclass
class AddressEnrichment:
    """Standardized address data from USPS."""
    original_address: str
    standardized_address: str
    address1: str
    address2: Optional[str]
    city: str
    state: str
    zip5: str
    zip4: Optional[str]
    is_valid: bool
    is_residential: bool
    is_vacant: bool
    carrier_route: Optional[str]
    source: str
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "original_address": self.original_address,
            "standardized_address": self.standardized_address,
            "address1": self.address1,
            "address2": self.address2,
            "city": self.city,
            "state": self.state,
            "zip5": self.zip5,
            "zip4": self.zip4,
            "is_valid": self.is_valid,
            "is_residential": self.is_residential,
            "is_vacant": self.is_vacant,
            "carrier_route": self.carrier_route,
            "source": self.source,
        }


@dataclass
class LocationEnrichment:
    """Geocoded location data."""
    latitude: Optional[float]
    longitude: Optional[float]
    formatted_address: str
    place_id: Optional[str]
    county: Optional[str]
    verified: bool
    source: str
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "latitude": self.latitude,
            "longitude": self.longitude,
            "formatted_address": self.formatted_address,
            "place_id": self.place_id,
            "county": self.county,
            "verified": self.verified,
            "source": self.source,
        }


@dataclass 
class PropertyEnrichment:
    """Property characteristics from external sources."""
    apn: Optional[str]
    lot_size_acres: Optional[float]
    lot_size_sqft: Optional[float]
    zoning: Optional[str]
    property_type: PropertyClassification
    year_built: Optional[int]
    building_sqft: Optional[float]
    estimated_value: Optional[float]
    last_sale_price: Optional[float]
    last_sale_date: Optional[str]
    is_vacant: bool
    is_adjudicated: bool
    years_tax_delinquent: int
    source: str
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "apn": self.apn,
            "lot_size_acres": self.lot_size_acres,
            "lot_size_sqft": self.lot_size_sqft,
            "zoning": self.zoning,
            "property_type": self.property_type.value,
            "year_built": self.year_built,
            "building_sqft": self.building_sqft,
            "estimated_value": self.estimated_value,
            "last_sale_price": self.last_sale_price,
            "last_sale_date": self.last_sale_date,
            "is_vacant": self.is_vacant,
            "is_adjudicated": self.is_adjudicated,
            "years_tax_delinquent": self.years_tax_delinquent,
            "source": self.source,
        }


@dataclass
class OwnerEnrichment:
    """Enhanced owner profile."""
    name: str
    owner_type: OwnerType
    mailing_address: Optional[str]
    mailing_city: Optional[str]
    mailing_state: Optional[str]
    mailing_zip: Optional[str]
    phone_numbers: List[str]
    emails: List[str]
    is_absentee: bool
    years_owned: Optional[int]
    source: str
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "owner_type": self.owner_type.value,
            "mailing_address": self.mailing_address,
            "mailing_city": self.mailing_city,
            "mailing_state": self.mailing_state,
            "mailing_zip": self.mailing_zip,
            "phone_numbers": self.phone_numbers,
            "emails": self.emails,
            "is_absentee": self.is_absentee,
            "years_owned": self.years_owned,
            "source": self.source,
        }


@dataclass
class CompsEnrichment:
    """Comparable sales summary."""
    comp_count: int
    avg_price_per_acre: Optional[float]
    min_price_per_acre: Optional[float]
    max_price_per_acre: Optional[float]
    median_price_per_acre: Optional[float]
    avg_days_on_market: Optional[int]
    comps: List[Dict[str, Any]]
    is_mock_data: bool
    source: str
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "comp_count": self.comp_count,
            "avg_price_per_acre": self.avg_price_per_acre,
            "min_price_per_acre": self.min_price_per_acre,
            "max_price_per_acre": self.max_price_per_acre,
            "median_price_per_acre": self.median_price_per_acre,
            "avg_days_on_market": self.avg_days_on_market,
            "comps": self.comps,
            "is_mock_data": self.is_mock_data,
            "source": self.source,
        }


@dataclass
class ScoreBreakdown:
    """Detailed motivation score breakdown."""
    factor: str
    label: str
    points: int
    max_points: int
    description: str


@dataclass
class ScoringEnrichment:
    """AI-powered motivation score."""
    motivation_score: int
    confidence: float
    factors: List[ScoreBreakdown]
    recommendation: str
    pipeline_stage: str
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "motivation_score": self.motivation_score,
            "confidence": self.confidence,
            "factors": [
                {
                    "factor": f.factor,
                    "label": f.label,
                    "points": f.points,
                    "max_points": f.max_points,
                    "description": f.description,
                }
                for f in self.factors
            ],
            "recommendation": self.recommendation,
            "pipeline_stage": self.pipeline_stage,
        }


@dataclass
class EnrichedLead:
    """Complete enriched lead data."""
    lead_id: int
    market_code: str
    
    # Enrichment components
    address: Optional[AddressEnrichment] = None
    location: Optional[LocationEnrichment] = None
    property: Optional[PropertyEnrichment] = None
    owner: Optional[OwnerEnrichment] = None
    comps: Optional[CompsEnrichment] = None
    scoring: Optional[ScoringEnrichment] = None
    
    # Pipeline metadata
    enrichment_status: str = "pending"
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    enriched_at: Optional[str] = None
    duration_ms: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "lead_id": self.lead_id,
            "market_code": self.market_code,
            "address": self.address.to_dict() if self.address else None,
            "location": self.location.to_dict() if self.location else None,
            "property": self.property.to_dict() if self.property else None,
            "owner": self.owner.to_dict() if self.owner else None,
            "comps": self.comps.to_dict() if self.comps else None,
            "scoring": self.scoring.to_dict() if self.scoring else None,
            "enrichment_status": self.enrichment_status,
            "errors": self.errors,
            "warnings": self.warnings,
            "enriched_at": self.enriched_at,
            "duration_ms": self.duration_ms,
        }


class EnrichmentPipeline:
    """
    Unified lead enrichment pipeline.
    
    Orchestrates all enrichment stages:
    1. Address standardization (USPS)
    2. Geocoding (Google Maps)
    3. Property data (PropStream)
    4. Owner enrichment (PropStream)
    5. Comparable sales
    6. Motivation scoring
    """

    def __init__(self, session: Session):
        """Initialize the enrichment pipeline."""
        self.session = session
        self.timeline = TimelineService(session)
        self.propstream = get_propstream_service()

    def enrich_lead(
        self,
        lead_id: int,
        skip_external: bool = False,
        force_refresh: bool = False,
    ) -> EnrichedLead:
        """
        Run the complete enrichment pipeline on a lead.
        
        Args:
            lead_id: The lead ID to enrich.
            skip_external: Skip external API calls (use cached/existing data only).
            force_refresh: Force refresh even if recently enriched.
            
        Returns:
            EnrichedLead with all enrichment data.
        """
        import time
        start_time = time.perf_counter()
        
        # Load lead
        lead = self.session.query(Lead).filter(Lead.id == lead_id).first()
        if not lead:
            return EnrichedLead(
                lead_id=lead_id,
                market_code="UNKNOWN",
                enrichment_status="error",
                errors=["Lead not found"],
            )
        
        enriched = EnrichedLead(
            lead_id=lead_id,
            market_code=lead.market_code,
        )
        
        try:
            # Stage 1: Address standardization
            enriched.address = self._enrich_address(lead, skip_external)
            
            # Stage 2: Geocoding
            enriched.location = self._enrich_location(lead, enriched.address, skip_external)
            
            # Stage 3: Property data
            enriched.property = self._enrich_property(lead, skip_external)
            
            # Stage 4: Owner enrichment
            enriched.owner = self._enrich_owner(lead, skip_external)
            
            # Stage 5: Comps
            enriched.comps = self._enrich_comps(lead, skip_external)
            
            # Stage 6: Scoring
            enriched.scoring = self._calculate_score(lead, enriched)
            
            # Update lead with enriched data
            self._update_lead(lead, enriched)
            
            enriched.enrichment_status = "completed"
            
            # Log to timeline
            self.timeline.add_event(
                lead_id=lead_id,
                event_type="enrichment_completed",
                title="Lead enrichment completed",
                description=f"Score: {enriched.scoring.motivation_score if enriched.scoring else 'N/A'}",
                metadata={"stages_completed": self._count_stages(enriched)},
            )
            
        except Exception as e:
            LOGGER.exception(f"Enrichment pipeline failed for lead {lead_id}")
            enriched.enrichment_status = "error"
            enriched.errors.append(str(e))
        
        enriched.duration_ms = (time.perf_counter() - start_time) * 1000
        enriched.enriched_at = utcnow().isoformat()
        
        return enriched

    def _enrich_address(
        self,
        lead: Lead,
        skip_external: bool,
    ) -> Optional[AddressEnrichment]:
        """Stage 1: Standardize address via USPS."""
        parcel = lead.parcel
        if not parcel:
            return None
        
        original_address = parcel.situs_address or ""
        city = parcel.city or ""
        state = parcel.state or lead.market_code
        zip_code = parcel.postal_code
        
        if not original_address:
            return None
        
        if skip_external:
            # Return basic enrichment from existing data
            return AddressEnrichment(
                original_address=original_address,
                standardized_address=original_address.upper(),
                address1=original_address.upper(),
                address2=None,
                city=city.upper(),
                state=state.upper(),
                zip5=zip_code or "",
                zip4=None,
                is_valid=False,
                is_residential=True,
                is_vacant=False,
                carrier_route=None,
                source="local",
            )
        
        try:
            result = verify_address(
                address=original_address,
                city=city,
                state=state,
                zip_code=zip_code,
            )
            
            return AddressEnrichment(
                original_address=original_address,
                standardized_address=result.get("formatted_address", original_address),
                address1=result.get("address1", original_address),
                address2=result.get("address2"),
                city=result.get("city", city),
                state=result.get("state", state),
                zip5=result.get("zip5", zip_code or ""),
                zip4=result.get("zip4"),
                is_valid=result.get("is_valid", False),
                is_residential=result.get("is_residential", True),
                is_vacant=result.get("is_vacant", False),
                carrier_route=result.get("carrier_route"),
                source=result.get("source", "usps"),
            )
        except Exception as e:
            LOGGER.warning(f"USPS verification failed: {e}")
            return AddressEnrichment(
                original_address=original_address,
                standardized_address=original_address.upper(),
                address1=original_address.upper(),
                address2=None,
                city=city.upper(),
                state=state.upper(),
                zip5=zip_code or "",
                zip4=None,
                is_valid=False,
                is_residential=True,
                is_vacant=False,
                carrier_route=None,
                source="fallback",
            )

    def _enrich_location(
        self,
        lead: Lead,
        address: Optional[AddressEnrichment],
        skip_external: bool,
    ) -> Optional[LocationEnrichment]:
        """Stage 2: Geocode address via Google Maps."""
        parcel = lead.parcel
        
        # Check if we already have coordinates
        if parcel and parcel.latitude and parcel.longitude:
            return LocationEnrichment(
                latitude=parcel.latitude,
                longitude=parcel.longitude,
                formatted_address=parcel.situs_address or "",
                place_id=None,
                county=parcel.parish,
                verified=True,
                source="existing",
            )
        
        if skip_external:
            return None
        
        # Build address string for geocoding
        if address:
            geocode_address = f"{address.address1}, {address.city}, {address.state} {address.zip5}"
        elif parcel:
            geocode_address = f"{parcel.situs_address}, {parcel.city}, {parcel.state} {parcel.postal_code}"
        else:
            return None
        
        try:
            result = geocode(geocode_address)
            
            if result:
                return LocationEnrichment(
                    latitude=result.get("lat"),
                    longitude=result.get("lng"),
                    formatted_address=result.get("formatted_address", geocode_address),
                    place_id=result.get("place_id"),
                    county=result.get("county"),
                    verified=result.get("verified", False),
                    source=result.get("source", "google_maps"),
                )
        except Exception as e:
            LOGGER.warning(f"Geocoding failed: {e}")
        
        return None

    def _enrich_property(
        self,
        lead: Lead,
        skip_external: bool,
    ) -> Optional[PropertyEnrichment]:
        """Stage 3: Enrich property data."""
        parcel = lead.parcel
        if not parcel:
            return None
        
        # Start with existing data
        property_type = self._classify_property(parcel)
        
        enrichment = PropertyEnrichment(
            apn=parcel.canonical_parcel_id,
            lot_size_acres=float(parcel.lot_size_acres) if parcel.lot_size_acres else None,
            lot_size_sqft=float(parcel.lot_size_acres * 43560) if parcel.lot_size_acres else None,
            zoning=parcel.zoning_code,
            property_type=property_type,
            year_built=None,
            building_sqft=None,
            estimated_value=float(parcel.land_assessed_value) if parcel.land_assessed_value else None,
            last_sale_price=None,
            last_sale_date=None,
            is_vacant=False,
            is_adjudicated=parcel.is_adjudicated,
            years_tax_delinquent=parcel.years_tax_delinquent,
            source="local",
        )
        
        # Try PropStream enrichment
        if not skip_external and is_propstream_available():
            try:
                ps_property = self.propstream.get_property_by_apn(
                    apn=parcel.canonical_parcel_id,
                    county=parcel.parish,
                    state=parcel.state or lead.market_code,
                )
                
                if ps_property:
                    enrichment = self._merge_propstream_property(enrichment, ps_property)
            except Exception as e:
                LOGGER.warning(f"PropStream property enrichment failed: {e}")
        
        return enrichment

    def _enrich_owner(
        self,
        lead: Lead,
        skip_external: bool,
    ) -> Optional[OwnerEnrichment]:
        """Stage 4: Enrich owner data."""
        owner = lead.owner
        if not owner or not owner.party:
            return None
        
        party = owner.party
        
        # Start with existing data
        owner_type = self._classify_owner(party.party_type, party.display_name)
        
        # Determine if absentee
        parcel = lead.parcel
        is_absentee = False
        if parcel and party.raw_mailing_address:
            # Compare mailing address to property address
            mailing_zip = party.normalized_zip or ""
            property_zip = parcel.postal_code or ""
            is_absentee = mailing_zip != property_zip
        
        enrichment = OwnerEnrichment(
            name=party.display_name,
            owner_type=owner_type,
            mailing_address=party.raw_mailing_address,
            mailing_city=None,
            mailing_state=None,
            mailing_zip=party.normalized_zip,
            phone_numbers=[owner.phone_primary] if owner.phone_primary else [],
            emails=[owner.email] if owner.email else [],
            is_absentee=is_absentee,
            years_owned=None,
            source="local",
        )
        
        # Try PropStream enrichment
        if not skip_external and is_propstream_available() and parcel:
            try:
                ps_owner = self.propstream.get_owner_data(
                    apn=parcel.canonical_parcel_id,
                    county=parcel.parish,
                    state=parcel.state or lead.market_code,
                )
                
                if ps_owner:
                    enrichment = self._merge_propstream_owner(enrichment, ps_owner)
            except Exception as e:
                LOGGER.warning(f"PropStream owner enrichment failed: {e}")
        
        return enrichment

    def _enrich_comps(
        self,
        lead: Lead,
        skip_external: bool,
    ) -> Optional[CompsEnrichment]:
        """Stage 5: Get comparable sales."""
        parcel = lead.parcel
        if not parcel:
            return None
        
        # Use the comps service
        from services.comps import get_comps_service
        
        try:
            comps_service = get_comps_service(self.session)
            result = comps_service.get_comps_for_parcel(parcel)
            
            if result:
                return CompsEnrichment(
                    comp_count=result.total_comps_found,
                    avg_price_per_acre=result.avg_price_per_acre,
                    min_price_per_acre=result.min_price_per_acre,
                    max_price_per_acre=result.max_price_per_acre,
                    median_price_per_acre=result.median_price_per_acre,
                    avg_days_on_market=None,
                    comps=[c.to_dict() for c in result.comps] if hasattr(result, 'comps') else [],
                    is_mock_data=result.is_mock_data,
                    source="comps_service",
                )
        except Exception as e:
            LOGGER.warning(f"Comps enrichment failed: {e}")
        
        return None

    def _calculate_score(
        self,
        lead: Lead,
        enriched: EnrichedLead,
    ) -> ScoringEnrichment:
        """Stage 6: Calculate motivation score."""
        factors = []
        total_score = 0
        max_score = 100
        
        parcel = lead.parcel
        
        # Factor 1: Adjudicated property (40 points)
        adjudicated_points = 0
        if parcel and parcel.is_adjudicated:
            adjudicated_points = SETTINGS.score_weight_adjudicated
        factors.append(ScoreBreakdown(
            factor="adjudicated",
            label="Adjudicated Property",
            points=adjudicated_points,
            max_points=SETTINGS.score_weight_adjudicated,
            description="Property sold at tax sale" if adjudicated_points > 0 else "Not adjudicated",
        ))
        total_score += adjudicated_points
        
        # Factor 2: Tax delinquency (up to 20 points)
        tax_points = 0
        if parcel:
            years = parcel.years_tax_delinquent
            tax_points = min(
                years * SETTINGS.score_weight_tax_delinquent_per_year,
                SETTINGS.score_weight_tax_delinquent_max,
            )
        factors.append(ScoreBreakdown(
            factor="tax_delinquent",
            label="Tax Delinquency",
            points=tax_points,
            max_points=SETTINGS.score_weight_tax_delinquent_max,
            description=f"{parcel.years_tax_delinquent if parcel else 0} years delinquent",
        ))
        total_score += tax_points
        
        # Factor 3: Low improvement value (20 points)
        improvement_points = 0
        if parcel and parcel.land_assessed_value is not None and parcel.improvement_assessed_value is not None:
            try:
                land_val = float(parcel.land_assessed_value)
                improvement_val = float(parcel.improvement_assessed_value)
                if land_val > 0 and improvement_val < land_val * 0.1:
                    improvement_points = SETTINGS.score_weight_low_improvement
            except (ValueError, TypeError):
                # On conversion error, treat as vacant land
                improvement_points = SETTINGS.score_weight_low_improvement
        elif enriched.property and enriched.property.property_type == PropertyClassification.VACANT_LAND:
            improvement_points = SETTINGS.score_weight_low_improvement
        factors.append(ScoreBreakdown(
            factor="low_improvement",
            label="Low/No Improvements",
            points=improvement_points,
            max_points=SETTINGS.score_weight_low_improvement,
            description="Vacant land or minimal improvements" if improvement_points > 0 else "Has improvements",
        ))
        total_score += improvement_points
        
        # Factor 4: Absentee owner (10 points)
        absentee_points = 0
        if enriched.owner and enriched.owner.is_absentee:
            absentee_points = SETTINGS.score_weight_absentee
        factors.append(ScoreBreakdown(
            factor="absentee_owner",
            label="Absentee Owner",
            points=absentee_points,
            max_points=SETTINGS.score_weight_absentee,
            description="Owner lives elsewhere" if absentee_points > 0 else "Local owner",
        ))
        total_score += absentee_points
        
        # Factor 5: Lot size (10 points for 0.5-5 acres)
        lot_points = 0
        if parcel and parcel.lot_size_acres:
            acres = float(parcel.lot_size_acres)
            if 0.5 <= acres <= 5.0:
                lot_points = SETTINGS.score_weight_lot_size
        factors.append(ScoreBreakdown(
            factor="lot_size",
            label="Ideal Lot Size",
            points=lot_points,
            max_points=SETTINGS.score_weight_lot_size,
            description="Optimal acreage range" if lot_points > 0 else "Outside ideal range",
        ))
        total_score += lot_points
        
        # Determine recommendation
        if total_score >= 75:
            recommendation = "HIGH PRIORITY - Contact immediately"
            pipeline_stage = "HOT"
        elif total_score >= 50:
            recommendation = "GOOD PROSPECT - Add to outreach queue"
            pipeline_stage = "NEW"
        elif total_score >= 30:
            recommendation = "MODERATE - Worth a follow-up"
            pipeline_stage = "NEW"
        else:
            recommendation = "LOW PRIORITY - Monitor only"
            pipeline_stage = "NEW"
        
        # Calculate confidence based on data completeness
        data_points = sum([
            1 if enriched.address else 0,
            1 if enriched.location else 0,
            1 if enriched.property else 0,
            1 if enriched.owner else 0,
            1 if enriched.comps else 0,
        ])
        confidence = data_points / 5.0
        
        return ScoringEnrichment(
            motivation_score=total_score,
            confidence=confidence,
            factors=factors,
            recommendation=recommendation,
            pipeline_stage=pipeline_stage,
        )

    def _classify_property(self, parcel: Parcel) -> PropertyClassification:
        """Classify property type based on parcel data."""
        if parcel.improvement_assessed_value:
            improvement = float(parcel.improvement_assessed_value)
            if improvement > 1000:
                return PropertyClassification.IMPROVED_RESIDENTIAL
        
        zoning = (parcel.zoning_code or "").upper()
        if "COMM" in zoning or "C-" in zoning:
            return PropertyClassification.COMMERCIAL
        if "AG" in zoning or "A-" in zoning:
            return PropertyClassification.AGRICULTURAL
        if "R-" in zoning or "RES" in zoning:
            return PropertyClassification.RESIDENTIAL_LOT
        
        return PropertyClassification.VACANT_LAND

    def _classify_owner(self, party_type: str, name: str) -> OwnerType:
        """Classify owner type based on party data."""
        party_type = (party_type or "").lower()
        name = (name or "").upper()
        
        if party_type == "corporate" or any(x in name for x in ["LLC", "INC", "CORP", "LTD", "LP"]):
            return OwnerType.CORPORATE
        if party_type == "trust" or "TRUST" in name or "TRUSTEE" in name:
            return OwnerType.TRUST
        if "ESTATE" in name or "SUCCESSION" in name:
            return OwnerType.ESTATE
        if any(x in name for x in ["PARISH", "CITY OF", "STATE OF", "COUNTY"]):
            return OwnerType.GOVERNMENT
        
        return OwnerType.INDIVIDUAL

    def _merge_propstream_property(
        self,
        existing: PropertyEnrichment,
        ps_property: PropStreamProperty,
    ) -> PropertyEnrichment:
        """Merge PropStream data into existing property enrichment."""
        # Map PropStream property type
        ps_type = ps_property.property_type.value if ps_property.property_type else "UNKNOWN"
        if ps_type in ("LAND", "VACANT_LAND"):
            prop_type = PropertyClassification.VACANT_LAND
        elif ps_type == "MOBILE":
            prop_type = PropertyClassification.MOBILE_HOME_LOT
        elif ps_type in ("SFR", "SINGLE_FAMILY"):
            prop_type = PropertyClassification.IMPROVED_RESIDENTIAL
        elif ps_type == "COMMERCIAL":
            prop_type = PropertyClassification.COMMERCIAL
        else:
            prop_type = existing.property_type
        
        return PropertyEnrichment(
            apn=ps_property.apn or existing.apn,
            lot_size_acres=ps_property.lot_size_acres or existing.lot_size_acres,
            lot_size_sqft=ps_property.lot_size_sqft or existing.lot_size_sqft,
            zoning=ps_property.zoning or existing.zoning,
            property_type=prop_type,
            year_built=ps_property.year_built or existing.year_built,
            building_sqft=ps_property.building_sqft or existing.building_sqft,
            estimated_value=ps_property.estimated_value or existing.estimated_value,
            last_sale_price=ps_property.last_sale_price or existing.last_sale_price,
            last_sale_date=ps_property.last_sale_date or existing.last_sale_date,
            is_vacant=ps_property.is_vacant or existing.is_vacant,
            is_adjudicated=existing.is_adjudicated,  # Keep local adjudication status
            years_tax_delinquent=existing.years_tax_delinquent,  # Keep local tax data
            source="propstream",
        )

    def _merge_propstream_owner(
        self,
        existing: OwnerEnrichment,
        ps_owner,
    ) -> OwnerEnrichment:
        """Merge PropStream owner data into existing owner enrichment."""
        # Combine phone numbers
        all_phones = list(set(existing.phone_numbers + (ps_owner.phone_numbers or [])))
        
        # Combine emails
        all_emails = list(set(existing.emails + (ps_owner.emails or [])))
        
        return OwnerEnrichment(
            name=existing.name,  # Keep original name
            owner_type=existing.owner_type,  # Keep classification
            mailing_address=ps_owner.mailing_address or existing.mailing_address,
            mailing_city=ps_owner.mailing_city or existing.mailing_city,
            mailing_state=ps_owner.mailing_state or existing.mailing_state,
            mailing_zip=ps_owner.mailing_zip or existing.mailing_zip,
            phone_numbers=all_phones,
            emails=all_emails,
            is_absentee=ps_owner.is_absentee if ps_owner.is_absentee else existing.is_absentee,
            years_owned=ps_owner.years_owned or existing.years_owned,
            source="propstream",
        )

    def _update_lead(self, lead: Lead, enriched: EnrichedLead) -> None:
        """Update lead record with enriched data."""
        # Update parcel with location data
        if lead.parcel and enriched.location:
            if enriched.location.latitude:
                lead.parcel.latitude = enriched.location.latitude
            if enriched.location.longitude:
                lead.parcel.longitude = enriched.location.longitude
        
        # Update lead score
        if enriched.scoring:
            lead.motivation_score = enriched.scoring.motivation_score
            lead.score_details = enriched.scoring.to_dict()
        
        # Commit changes
        self.session.flush()

    def _count_stages(self, enriched: EnrichedLead) -> int:
        """Count completed enrichment stages."""
        count = 0
        if enriched.address:
            count += 1
        if enriched.location:
            count += 1
        if enriched.property:
            count += 1
        if enriched.owner:
            count += 1
        if enriched.comps:
            count += 1
        if enriched.scoring:
            count += 1
        return count


def get_enrichment_pipeline(session: Session) -> EnrichmentPipeline:
    """Get an EnrichmentPipeline instance."""
    return EnrichmentPipeline(session)


__all__ = [
    "EnrichmentPipeline",
    "EnrichedLead",
    "AddressEnrichment",
    "LocationEnrichment",
    "PropertyEnrichment",
    "OwnerEnrichment",
    "CompsEnrichment",
    "ScoringEnrichment",
    "PropertyClassification",
    "OwnerType",
    "get_enrichment_pipeline",
]

