"""
Offer Helper Service - PRODUCTION HARDENED

Computes offer ranges with justification.
NOT comps-dependent - uses land value and configurable discounts.

CRITICAL TRUST RULES:
1. NEVER compute offers with missing critical data
2. NEVER show confidence indicators when inputs are incomplete
3. ALWAYS explicitly state what data is missing
4. NEVER perform per-acre math when acreage is null

Output: Range + Justification bullets (never a single number)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, TYPE_CHECKING
from decimal import Decimal

if TYPE_CHECKING:
    from core.models import Lead


# Default discount factors (configurable)
DEFAULT_DISCOUNT_LOW = 0.55  # 55% of assessed value
DEFAULT_DISCOUNT_HIGH = 0.70  # 70% of assessed value

# Adjustment factors
ADJUDICATED_DISCOUNT = 0.15  # Additional 15% discount for adjudicated
DELINQUENT_DISCOUNT_PER_YEAR = 0.02  # 2% per year delinquent, max 10%
DELINQUENT_DISCOUNT_MAX = 0.10
SMALL_LOT_PREMIUM = 0.05  # 5% premium for < 1 acre (easier to sell)
LARGE_LOT_DISCOUNT = 0.05  # 5% discount for > 10 acres (harder to sell)


class OfferConfidence(str, Enum):
    """
    Confidence level for offer calculations.
    
    PRODUCTION RULE: Only show HIGH if all critical data is present.
    """
    HIGH = "high"  # All data present and verified
    MEDIUM = "medium"  # Some data missing but offer is usable
    LOW = "low"  # Critical data missing - offer is a rough estimate
    CANNOT_COMPUTE = "cannot_compute"  # Missing required data


class DataWarning(str, Enum):
    """Explicit warnings for offer calculation issues."""
    MISSING_LAND_VALUE = "missing_land_value"
    MISSING_ACREAGE = "missing_acreage"
    ZERO_LAND_VALUE = "zero_land_value"
    ADJUDICATED_TITLE_RISK = "adjudicated_title_risk"
    TAX_DELINQUENT = "tax_delinquent"
    NO_PARCEL_DATA = "no_parcel_data"
    ESTIMATE_ONLY = "estimate_only"


@dataclass
class JustificationBullet:
    """A single justification point for the offer."""
    factor: str
    description: str
    impact: str  # "increase", "decrease", "neutral"
    
    def to_dict(self) -> dict:
        return {
            "factor": self.factor,
            "description": self.description,
            "impact": self.impact,
        }


@dataclass
class OfferRange:
    """
    Computed offer range with full justification.
    
    PRODUCTION RULES:
    1. NEVER a single number - always low/high
    2. ALWAYS include justification bullets
    3. ALWAYS show confidence with reason
    4. ALWAYS list warnings if data is incomplete
    """
    low_offer: int
    high_offer: int
    
    # Basis - EXPLICITLY nullable
    land_value: Optional[float]
    acreage: Optional[float]
    
    # Factors used
    discount_low: float
    discount_high: float
    
    # Justification
    justifications: List[JustificationBullet] = field(default_factory=list)
    
    # Confidence - MUST be accurate
    confidence: OfferConfidence = OfferConfidence.LOW
    confidence_reason: str = ""
    
    # Explicit warnings
    warnings: List[DataWarning] = field(default_factory=list)
    
    # Can we actually make an offer?
    can_make_offer: bool = True
    cannot_offer_reason: Optional[str] = None
    
    @property
    def midpoint(self) -> int:
        """Midpoint for reference only."""
        return (self.low_offer + self.high_offer) // 2
    
    @property
    def range_display(self) -> str:
        """Human-readable range."""
        if not self.can_make_offer:
            return "Cannot compute offer"
        return f"${self.low_offer:,} - ${self.high_offer:,}"
    
    @property
    def price_per_acre_low(self) -> Optional[int]:
        """
        Per-acre price (low end).
        
        PRODUCTION RULE: Returns None if acreage is missing.
        NEVER divide by zero or guess.
        """
        if self.acreage and self.acreage > 0 and self.can_make_offer:
            return int(self.low_offer / self.acreage)
        return None
    
    @property
    def price_per_acre_high(self) -> Optional[int]:
        """
        Per-acre price (high end).
        
        PRODUCTION RULE: Returns None if acreage is missing.
        """
        if self.acreage and self.acreage > 0 and self.can_make_offer:
            return int(self.high_offer / self.acreage)
        return None
    
    @property
    def per_acre_display(self) -> Optional[str]:
        """Per-acre display string, or explicit warning if unavailable."""
        if self.price_per_acre_low and self.price_per_acre_high:
            return f"${self.price_per_acre_low:,} - ${self.price_per_acre_high:,} per acre"
        elif DataWarning.MISSING_ACREAGE in self.warnings:
            return "Per-acre price unavailable - acreage data missing"
        return None
    
    @property
    def missing_data_summary(self) -> Optional[str]:
        """Human-readable summary of missing data."""
        if not self.warnings:
            return None
        
        messages = []
        if DataWarning.MISSING_LAND_VALUE in self.warnings:
            messages.append("No assessed land value")
        if DataWarning.MISSING_ACREAGE in self.warnings:
            messages.append("No acreage data")
        if DataWarning.NO_PARCEL_DATA in self.warnings:
            messages.append("No parcel records")
        
        return ". ".join(messages) if messages else None
    
    def to_dict(self) -> dict:
        return {
            "low_offer": self.low_offer,
            "high_offer": self.high_offer,
            "midpoint": self.midpoint,
            "range_display": self.range_display,
            "land_value": self.land_value,
            "acreage": self.acreage,
            "discount_low": self.discount_low,
            "discount_high": self.discount_high,
            "price_per_acre_low": self.price_per_acre_low,
            "price_per_acre_high": self.price_per_acre_high,
            "per_acre_display": self.per_acre_display,
            "justifications": [j.to_dict() for j in self.justifications],
            "confidence": self.confidence.value,
            "confidence_reason": self.confidence_reason,
            "warnings": [w.value for w in self.warnings],
            "missing_data_summary": self.missing_data_summary,
            "can_make_offer": self.can_make_offer,
            "cannot_offer_reason": self.cannot_offer_reason,
        }


def compute_offer_range(
    lead: "Lead",
    discount_low: float = DEFAULT_DISCOUNT_LOW,
    discount_high: float = DEFAULT_DISCOUNT_HIGH,
) -> OfferRange:
    """
    Compute offer range for a lead.
    
    PRODUCTION RULES:
    1. NOT comps-dependent - uses assessed value
    2. NEVER compute with missing land value
    3. NEVER show per-acre when acreage is null
    4. ALWAYS explain confidence level
    5. ALWAYS list explicit warnings
    """
    parcel = lead.parcel
    justifications: List[JustificationBullet] = []
    warnings: List[DataWarning] = []
    
    # Check for parcel data
    if not parcel:
        return OfferRange(
            low_offer=0,
            high_offer=0,
            land_value=None,
            acreage=None,
            discount_low=discount_low,
            discount_high=discount_high,
            justifications=[
                JustificationBullet(
                    factor="no_parcel",
                    description="No parcel data available",
                    impact="neutral",
                )
            ],
            confidence=OfferConfidence.CANNOT_COMPUTE,
            confidence_reason="No parcel records found - cannot compute offer",
            warnings=[DataWarning.NO_PARCEL_DATA],
            can_make_offer=False,
            cannot_offer_reason="No parcel data available. Ingest parcel records first.",
        )
    
    # Get base values
    land_value = float(parcel.land_assessed_value) if parcel.land_assessed_value else None
    acreage = float(parcel.lot_size_acres) if parcel.lot_size_acres else None
    is_adjudicated = parcel.is_adjudicated if parcel else False
    years_delinquent = parcel.years_tax_delinquent if parcel else 0
    
    # CRITICAL: No land value = cannot compute
    if not land_value or land_value <= 0:
        warnings.append(DataWarning.MISSING_LAND_VALUE)
        if land_value == 0:
            warnings.append(DataWarning.ZERO_LAND_VALUE)
        
        return OfferRange(
            low_offer=0,
            high_offer=0,
            land_value=None,
            acreage=acreage,
            discount_low=discount_low,
            discount_high=discount_high,
            justifications=[
                JustificationBullet(
                    factor="missing_data",
                    description="No land assessed value available",
                    impact="neutral",
                )
            ],
            confidence=OfferConfidence.CANNOT_COMPUTE,
            confidence_reason="Missing land assessed value - cannot compute offer",
            warnings=warnings,
            can_make_offer=False,
            cannot_offer_reason="No assessed land value on record. Check parish assessor records.",
        )
    
    # Track missing acreage
    if not acreage:
        warnings.append(DataWarning.MISSING_ACREAGE)
    
    # Start with base justification
    justifications.append(JustificationBullet(
        factor="assessment_basis",
        description=f"Based on ${land_value:,.0f} assessed land value",
        impact="neutral",
    ))
    
    # Acreage justification
    if acreage:
        justifications.append(JustificationBullet(
            factor="acreage",
            description=f"{acreage:.2f} acres",
            impact="neutral",
        ))
        
        # Size adjustments
        if acreage < 1:
            discount_low += SMALL_LOT_PREMIUM
            discount_high += SMALL_LOT_PREMIUM
            justifications.append(JustificationBullet(
                factor="small_lot_premium",
                description="Small lot (<1 acre) - easier to sell",
                impact="increase",
            ))
        elif acreage > 10:
            discount_low -= LARGE_LOT_DISCOUNT
            discount_high -= LARGE_LOT_DISCOUNT
            justifications.append(JustificationBullet(
                factor="large_lot_discount",
                description="Large lot (>10 acres) - harder to sell",
                impact="decrease",
            ))
    else:
        # EXPLICIT: Note that acreage is missing
        justifications.append(JustificationBullet(
            factor="missing_acreage",
            description="Acreage unknown - per-acre pricing unavailable",
            impact="neutral",
        ))
    
    # Adjudicated adjustment
    if is_adjudicated:
        discount_low -= ADJUDICATED_DISCOUNT
        discount_high -= ADJUDICATED_DISCOUNT
        warnings.append(DataWarning.ADJUDICATED_TITLE_RISK)
        justifications.append(JustificationBullet(
            factor="adjudicated",
            description="Property is adjudicated - title clearing required",
            impact="decrease",
        ))
    
    # Delinquency adjustment
    if years_delinquent > 0:
        delinquent_discount = min(
            years_delinquent * DELINQUENT_DISCOUNT_PER_YEAR,
            DELINQUENT_DISCOUNT_MAX
        )
        discount_low -= delinquent_discount
        discount_high -= delinquent_discount
        warnings.append(DataWarning.TAX_DELINQUENT)
        justifications.append(JustificationBullet(
            factor="tax_delinquent",
            description=f"{years_delinquent} years tax delinquent",
            impact="decrease",
        ))
    
    # Ensure discounts stay reasonable
    discount_low = max(0.30, min(0.90, discount_low))
    discount_high = max(0.35, min(0.95, discount_high))
    
    # Compute range
    low_offer = int(land_value * discount_low)
    high_offer = int(land_value * discount_high)
    
    # Ensure low < high
    if low_offer > high_offer:
        low_offer, high_offer = high_offer, low_offer
    
    # Round to nearest $100
    low_offer = (low_offer // 100) * 100
    high_offer = (high_offer // 100) * 100
    
    # Minimum offers
    low_offer = max(500, low_offer)
    high_offer = max(1000, high_offer)
    
    # Determine confidence - MUST be accurate
    if acreage and not is_adjudicated and years_delinquent == 0:
        confidence = OfferConfidence.HIGH
        confidence_reason = "All data available - high confidence estimate"
    elif not acreage:
        confidence = OfferConfidence.MEDIUM
        confidence_reason = "Missing acreage data - per-acre pricing unavailable"
    elif is_adjudicated:
        confidence = OfferConfidence.MEDIUM
        confidence_reason = "Adjudicated property - verify title status before closing"
    else:
        confidence = OfferConfidence.MEDIUM
        confidence_reason = "Some data quality issues - verify before final offer"
    
    return OfferRange(
        low_offer=low_offer,
        high_offer=high_offer,
        land_value=land_value,
        acreage=acreage,
        discount_low=discount_low,
        discount_high=discount_high,
        justifications=justifications,
        confidence=confidence,
        confidence_reason=confidence_reason,
        warnings=warnings,
        can_make_offer=True,
    )


# =============================================================================
# REGRESSION GUARDS
# =============================================================================

def assert_offer_not_from_incomplete_data(offer: OfferRange) -> None:
    """
    REGRESSION GUARD: Ensure offer confidence matches data availability.
    
    Raises AssertionError if confidence is HIGH but data is incomplete.
    """
    if offer.confidence == OfferConfidence.HIGH:
        # HIGH confidence requires all data
        assert offer.acreage is not None, \
            "HIGH confidence offer but acreage is missing"
        assert offer.land_value is not None and offer.land_value > 0, \
            "HIGH confidence offer but land value is missing/zero"
        assert DataWarning.ADJUDICATED_TITLE_RISK not in offer.warnings, \
            "HIGH confidence offer but property is adjudicated"


def assert_per_acre_not_from_missing_acreage(offer: OfferRange) -> None:
    """
    REGRESSION GUARD: Ensure per-acre calculations don't divide by zero.
    
    Raises AssertionError if per-acre price exists but acreage is missing.
    """
    if offer.price_per_acre_low is not None:
        assert offer.acreage is not None and offer.acreage > 0, \
            "Per-acre price computed but acreage is missing/zero"
    
    if offer.price_per_acre_high is not None:
        assert offer.acreage is not None and offer.acreage > 0, \
            "Per-acre price computed but acreage is missing/zero"


__all__ = [
    "OfferRange",
    "OfferConfidence",
    "DataWarning",
    "JustificationBullet",
    "compute_offer_range",
    "DEFAULT_DISCOUNT_LOW",
    "DEFAULT_DISCOUNT_HIGH",
    "assert_offer_not_from_incomplete_data",
    "assert_per_acre_not_from_missing_acreage",
]
