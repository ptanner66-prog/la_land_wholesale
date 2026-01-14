"""Offer calculator service."""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from core.logging_config import get_logger

LOGGER = get_logger(__name__)


@dataclass
class OfferResult:
    """Result from offer calculation."""
    
    recommended_offer: float
    low_offer: float
    high_offer: float
    price_per_acre: float
    lot_size_acres: float
    comp_avg_price_per_acre: Optional[float]
    distress_discount: float  # Percentage discount applied
    explanation: List[str]
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "recommended_offer": round(self.recommended_offer, 2),
            "low_offer": round(self.low_offer, 2),
            "high_offer": round(self.high_offer, 2),
            "price_per_acre": round(self.price_per_acre, 2),
            "lot_size_acres": round(self.lot_size_acres, 4),
            "comp_avg_price_per_acre": round(self.comp_avg_price_per_acre, 2) if self.comp_avg_price_per_acre else None,
            "distress_discount": round(self.distress_discount * 100, 1),
            "explanation": self.explanation,
        }


class OfferCalculatorService:
    """Service for calculating property offers."""

    # Default price per acre when no comps available
    DEFAULT_PRICE_PER_ACRE = 5000  # $5,000/acre fallback
    
    # Target profit margin
    TARGET_MARGIN = 0.30  # 30% margin
    
    # Discount ranges based on distress score
    DISTRESS_DISCOUNTS = {
        90: 0.50,  # 50% discount for score 90+
        80: 0.45,
        70: 0.40,
        60: 0.35,
        50: 0.30,
        0: 0.25,   # Minimum 25% discount
    }

    def calculate_distress_discount(self, motivation_score: int) -> float:
        """
        Calculate discount percentage based on motivation score.
        
        Higher scores = more distressed = higher discount.
        """
        for threshold, discount in sorted(self.DISTRESS_DISCOUNTS.items(), reverse=True):
            if motivation_score >= threshold:
                return discount
        return 0.25

    def calculate_offer(
        self,
        lot_size_acres: float,
        motivation_score: int,
        comp_avg_price_per_acre: Optional[float] = None,
        land_assessed_value: Optional[float] = None,
        is_adjudicated: bool = False,
    ) -> OfferResult:
        """
        Calculate a recommended offer for a property.
        
        Args:
            lot_size_acres: Size of the lot in acres.
            motivation_score: Lead motivation score (0-100).
            comp_avg_price_per_acre: Average price per acre from comps.
            land_assessed_value: Assessed land value from county.
            is_adjudicated: Whether the property is adjudicated.
            
        Returns:
            OfferResult with recommended offer and explanation.
        """
        explanation = []
        
        # Validate inputs
        if lot_size_acres <= 0:
            lot_size_acres = 0.5  # Assume 0.5 acres if unknown
            explanation.append("Assumed 0.5 acres (lot size unknown)")
        
        # Determine base price per acre
        if comp_avg_price_per_acre and comp_avg_price_per_acre > 0:
            base_price_per_acre = comp_avg_price_per_acre
            explanation.append(f"Using comp average: ${comp_avg_price_per_acre:,.0f}/acre")
        elif land_assessed_value and land_assessed_value > 0:
            # Assessed values are typically 10-20% of market value
            estimated_market_value = land_assessed_value * 5
            base_price_per_acre = estimated_market_value / max(lot_size_acres, 0.1)
            explanation.append(f"Estimated from assessed value: ${base_price_per_acre:,.0f}/acre")
        else:
            base_price_per_acre = self.DEFAULT_PRICE_PER_ACRE
            explanation.append(f"Using default price: ${base_price_per_acre:,.0f}/acre")
        
        # Calculate raw property value
        raw_value = base_price_per_acre * lot_size_acres
        explanation.append(f"Raw property value: ${raw_value:,.0f} ({lot_size_acres:.2f} acres)")
        
        # Apply distress discount
        distress_discount = self.calculate_distress_discount(motivation_score)
        
        if is_adjudicated:
            distress_discount = min(distress_discount + 0.10, 0.60)  # Extra 10% for adjudicated
            explanation.append(f"Adjudicated property: additional 10% discount")
        
        explanation.append(f"Distress discount: {distress_discount * 100:.0f}% (score: {motivation_score})")
        
        # Calculate target purchase price (what we'd pay)
        target_price = raw_value * (1 - distress_discount)
        
        # Apply target margin to get our offer
        recommended_offer = target_price * (1 - self.TARGET_MARGIN)
        explanation.append(f"Target margin: {self.TARGET_MARGIN * 100:.0f}%")
        
        # Calculate offer range
        low_offer = recommended_offer * 0.80  # 20% below recommended
        high_offer = recommended_offer * 1.15  # 15% above recommended
        
        explanation.append(f"Recommended offer: ${recommended_offer:,.0f}")
        explanation.append(f"Offer range: ${low_offer:,.0f} - ${high_offer:,.0f}")
        
        return OfferResult(
            recommended_offer=recommended_offer,
            low_offer=low_offer,
            high_offer=high_offer,
            price_per_acre=base_price_per_acre,
            lot_size_acres=lot_size_acres,
            comp_avg_price_per_acre=comp_avg_price_per_acre,
            distress_discount=distress_discount,
            explanation=explanation,
        )


# Module-level singleton
_service: Optional[OfferCalculatorService] = None


def get_offer_calculator() -> OfferCalculatorService:
    """Get the global OfferCalculatorService instance."""
    global _service
    if _service is None:
        _service = OfferCalculatorService()
    return _service


__all__ = [
    "OfferCalculatorService",
    "OfferResult",
    "get_offer_calculator",
]

