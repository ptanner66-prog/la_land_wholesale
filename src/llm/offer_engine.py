"""Calculate offer amounts for parcels."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from core.logging_config import get_logger
from core.models import Parcel

LOGGER = get_logger(__name__)


@dataclass
class OfferResult:
    """Result of an offer calculation."""
    
    offer_amount: float
    explanation: str
    confidence: float  # 0.0 to 1.0


def calculate_offer(parcel: Parcel) -> OfferResult:
    """
    Calculate a preliminary offer amount for a parcel.
    
    This is a heuristic-based calculation, not an appraisal.
    
    Args:
        parcel: The parcel to evaluate.
        
    Returns:
        OfferResult with amount and explanation.
    """
    # Base value logic
    assessed_value = float(parcel.land_assessed_value or 0)
    market_value_estimate = assessed_value * 10.0  # Rough heuristic: assessed is 10% of market
    
    # Adjustments
    offer_ratio = 0.40  # Start at 40% of market value
    
    if parcel.is_adjudicated:
        offer_ratio -= 0.10  # Reduce for adjudicated properties (title issues)
        
    if parcel.years_tax_delinquent > 0:
        offer_ratio -= (parcel.years_tax_delinquent * 0.02)  # Reduce 2% per delinquent year
        
    # Floor ratio
    offer_ratio = max(0.10, offer_ratio)
    
    offer_amount = market_value_estimate * offer_ratio
    
    # Sanity checks
    if offer_amount < 500:
        offer_amount = 500.0  # Minimum offer
        
    explanation = (
        f"Based on assessed land value of ${assessed_value:,.0f} "
        f"and estimated market value of ${market_value_estimate:,.0f}. "
        f"Applied offer ratio of {offer_ratio:.0%} due to "
        f"{'adjudicated status' if parcel.is_adjudicated else 'standard status'} "
        f"and {parcel.years_tax_delinquent} years delinquency."
    )
    
    return OfferResult(
        offer_amount=round(offer_amount, -2),  # Round to nearest 100
        explanation=explanation,
        confidence=0.7 if assessed_value > 0 else 0.1,
    )
