"""Assignment Fee Optimizer for Land Wholesaling.

This module provides logic to calculate optimal assignment fees for land deals.
It considers:
- Market conditions
- Property characteristics
- Buyer demand
- Risk factors
- Historical data

The goal is to maximize profit while ensuring deals close quickly.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.config import get_settings
from core.logging_config import get_logger

LOGGER = get_logger(__name__)
SETTINGS = get_settings()


@dataclass
class AssignmentFeeRange:
    """Recommended assignment fee range."""
    # Recommended fee
    recommended_fee: float
    recommended_percentage: float
    
    # Range
    min_fee: float
    max_fee: float
    
    # Conservative vs aggressive
    conservative_fee: float
    aggressive_fee: float
    
    # Confidence
    confidence: float  # 0-1
    
    # Factors considered
    factors: List[Dict[str, Any]] = field(default_factory=list)
    
    # Warnings
    warnings: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "recommended_fee": round(self.recommended_fee, 2),
            "recommended_percentage": round(self.recommended_percentage, 2),
            "min_fee": round(self.min_fee, 2),
            "max_fee": round(self.max_fee, 2),
            "conservative_fee": round(self.conservative_fee, 2),
            "aggressive_fee": round(self.aggressive_fee, 2),
            "confidence": round(self.confidence, 2),
            "factors": self.factors,
            "warnings": self.warnings,
        }


@dataclass
class DealAnalysis:
    """Complete deal analysis with margins."""
    # Purchase side
    seller_asking_price: Optional[float]
    recommended_purchase_price: float
    max_purchase_price: float
    
    # Sale side
    estimated_retail_value: float
    quick_sale_value: float
    
    # Assignment
    assignment_fee: AssignmentFeeRange
    
    # Margins
    gross_margin: float
    gross_margin_percentage: float
    
    # ROI metrics
    roi_percentage: float
    annualized_roi: float  # Assuming 30-day flip
    
    # Risk
    risk_level: str  # low, medium, high
    risk_factors: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "seller_asking_price": self.seller_asking_price,
            "recommended_purchase_price": round(self.recommended_purchase_price, 2),
            "max_purchase_price": round(self.max_purchase_price, 2),
            "estimated_retail_value": round(self.estimated_retail_value, 2),
            "quick_sale_value": round(self.quick_sale_value, 2),
            "assignment_fee": self.assignment_fee.to_dict(),
            "gross_margin": round(self.gross_margin, 2),
            "gross_margin_percentage": round(self.gross_margin_percentage, 2),
            "roi_percentage": round(self.roi_percentage, 2),
            "annualized_roi": round(self.annualized_roi, 2),
            "risk_level": self.risk_level,
            "risk_factors": self.risk_factors,
        }


class AssignmentFeeOptimizer:
    """
    Optimizes assignment fees for land wholesale deals.
    
    Uses multiple factors to determine optimal pricing:
    1. Market velocity (how fast properties sell)
    2. Buyer demand (number of interested buyers)
    3. Property desirability
    4. Comparable margins
    5. Risk profile
    """
    
    # Default fee percentages by deal size
    DEFAULT_FEE_PERCENTAGES = {
        "under_10k": 0.25,     # 25% on small deals
        "10k_25k": 0.20,       # 20% on medium-small
        "25k_50k": 0.15,       # 15% on medium
        "50k_100k": 0.12,      # 12% on medium-large
        "over_100k": 0.10,     # 10% on large deals
    }
    
    # Minimum fees by market
    MIN_FEES = {
        "LA": 1500,
        "TX": 2000,
        "MS": 1200,
        "AR": 1000,
        "AL": 1200,
        "DEFAULT": 1500,
    }
    
    # Market velocity multipliers (1.0 = normal)
    MARKET_VELOCITY = {
        "LA": 1.0,
        "TX": 1.2,  # Hot market
        "MS": 0.8,  # Slower
        "AR": 0.9,
        "AL": 0.85,
    }
    
    def __init__(self):
        """Initialize the optimizer."""
        self.settings = SETTINGS
    
    def calculate_assignment_fee(
        self,
        purchase_price: float,
        retail_value: float,
        lot_size_acres: float,
        market_code: str = "LA",
        motivation_score: int = 50,
        buyer_count: int = 1,
        days_on_market: Optional[int] = None,
        is_adjudicated: bool = False,
        comp_price_per_acre: Optional[float] = None,
    ) -> AssignmentFeeRange:
        """
        Calculate the optimal assignment fee range.
        
        Args:
            purchase_price: Expected purchase price from seller.
            retail_value: Estimated retail/market value.
            lot_size_acres: Property size in acres.
            market_code: Market (LA, TX, MS, AR, AL).
            motivation_score: Seller motivation score (0-100).
            buyer_count: Number of matched buyers interested.
            days_on_market: How long property has been on market.
            is_adjudicated: Whether property is adjudicated.
            comp_price_per_acre: Average comp price per acre.
        
        Returns:
            AssignmentFeeRange with recommended fees.
        """
        factors = []
        warnings = []
        
        # 1. Calculate base margin
        margin = retail_value - purchase_price
        margin_percentage = (margin / retail_value) * 100 if retail_value > 0 else 0
        
        factors.append({
            "name": "base_margin",
            "value": margin,
            "percentage": margin_percentage,
            "description": f"Gross margin: ${margin:,.0f} ({margin_percentage:.1f}%)",
        })
        
        # 2. Determine base fee percentage based on deal size
        base_percentage = self._get_base_percentage(retail_value)
        base_fee = margin * base_percentage
        
        factors.append({
            "name": "deal_size",
            "value": base_percentage * 100,
            "description": f"Base fee: {base_percentage*100:.0f}% of margin",
        })
        
        # 3. Adjust for market velocity
        velocity_mult = self.MARKET_VELOCITY.get(market_code, 1.0)
        if velocity_mult > 1.0:
            factors.append({
                "name": "market_velocity",
                "value": velocity_mult,
                "description": f"Hot market: +{(velocity_mult-1)*100:.0f}% fee opportunity",
            })
        elif velocity_mult < 1.0:
            factors.append({
                "name": "market_velocity",
                "value": velocity_mult,
                "description": f"Slower market: -{(1-velocity_mult)*100:.0f}% fee reduction",
            })
        
        adjusted_fee = base_fee * velocity_mult
        
        # 4. Adjust for buyer demand
        if buyer_count >= 5:
            demand_mult = 1.15  # High demand
            factors.append({
                "name": "buyer_demand",
                "value": buyer_count,
                "description": f"High buyer demand ({buyer_count} buyers): +15% fee opportunity",
            })
        elif buyer_count >= 3:
            demand_mult = 1.05  # Good demand
            factors.append({
                "name": "buyer_demand",
                "value": buyer_count,
                "description": f"Good buyer demand ({buyer_count} buyers): +5% fee",
            })
        elif buyer_count == 0:
            demand_mult = 0.85  # Low demand
            warnings.append("No matched buyers - consider reducing fee")
            factors.append({
                "name": "buyer_demand",
                "value": 0,
                "description": "No buyers: -15% fee reduction recommended",
            })
        else:
            demand_mult = 1.0
        
        adjusted_fee *= demand_mult
        
        # 5. Adjust for motivation
        if motivation_score >= 75:
            motivation_mult = 1.10  # Can be more aggressive
            factors.append({
                "name": "seller_motivation",
                "value": motivation_score,
                "description": f"High motivation ({motivation_score}): +10% fee opportunity",
            })
        elif motivation_score < 40:
            motivation_mult = 0.95  # Need to be conservative
            factors.append({
                "name": "seller_motivation",
                "value": motivation_score,
                "description": f"Low motivation ({motivation_score}): -5% fee reduction",
            })
        else:
            motivation_mult = 1.0
        
        adjusted_fee *= motivation_mult
        
        # 6. Adjust for adjudicated status
        if is_adjudicated:
            # Adjudicated properties often have more motivated sellers
            adjusted_fee *= 1.05
            factors.append({
                "name": "adjudicated",
                "value": True,
                "description": "Adjudicated property: +5% fee opportunity",
            })
        
        # 7. Apply minimum fee floor
        min_fee = self.MIN_FEES.get(market_code, self.MIN_FEES["DEFAULT"])
        if adjusted_fee < min_fee:
            adjusted_fee = min_fee
            warnings.append(f"Fee raised to minimum: ${min_fee:,.0f}")
        
        # 8. Calculate range
        conservative_fee = adjusted_fee * 0.80  # 20% below
        aggressive_fee = adjusted_fee * 1.25   # 25% above
        
        # Ensure minimums
        conservative_fee = max(conservative_fee, min_fee * 0.8)
        
        # 9. Calculate confidence
        confidence = self._calculate_confidence(
            buyer_count=buyer_count,
            margin_percentage=margin_percentage,
            has_comps=comp_price_per_acre is not None,
            motivation_score=motivation_score,
        )
        
        # Calculate as percentage of purchase price
        fee_percentage = (adjusted_fee / purchase_price) * 100 if purchase_price > 0 else 0
        
        return AssignmentFeeRange(
            recommended_fee=adjusted_fee,
            recommended_percentage=fee_percentage,
            min_fee=conservative_fee,
            max_fee=aggressive_fee,
            conservative_fee=conservative_fee,
            aggressive_fee=aggressive_fee,
            confidence=confidence,
            factors=factors,
            warnings=warnings,
        )
    
    def analyze_deal(
        self,
        purchase_price: float,
        retail_value: float,
        lot_size_acres: float,
        market_code: str = "LA",
        motivation_score: int = 50,
        buyer_count: int = 1,
        seller_asking_price: Optional[float] = None,
        **kwargs,
    ) -> DealAnalysis:
        """
        Perform complete deal analysis.
        
        Args:
            purchase_price: Expected purchase price.
            retail_value: Estimated retail value.
            lot_size_acres: Property size.
            market_code: Market code.
            motivation_score: Seller motivation.
            buyer_count: Number of interested buyers.
            seller_asking_price: What seller is asking (if known).
            **kwargs: Additional params for fee calculation.
        
        Returns:
            Complete DealAnalysis.
        """
        # Calculate assignment fee
        fee_range = self.calculate_assignment_fee(
            purchase_price=purchase_price,
            retail_value=retail_value,
            lot_size_acres=lot_size_acres,
            market_code=market_code,
            motivation_score=motivation_score,
            buyer_count=buyer_count,
            **kwargs,
        )
        
        # Calculate gross margin
        gross_margin = retail_value - purchase_price
        gross_margin_percentage = (gross_margin / retail_value) * 100 if retail_value > 0 else 0
        
        # Calculate quick sale value (80% of retail)
        quick_sale_value = retail_value * 0.80
        
        # Calculate max purchase price (leaving room for fee)
        max_purchase = quick_sale_value - fee_range.recommended_fee
        
        # Calculate ROI
        roi = (fee_range.recommended_fee / purchase_price) * 100 if purchase_price > 0 else 0
        annualized_roi = roi * 12  # Assuming 30-day flip
        
        # Assess risk
        risk_factors = []
        if gross_margin_percentage < 20:
            risk_factors.append("Low margin")
        if buyer_count < 2:
            risk_factors.append("Limited buyer interest")
        if motivation_score < 40:
            risk_factors.append("Low seller motivation")
        if lot_size_acres > 10:
            risk_factors.append("Large lot may be harder to move")
        
        if len(risk_factors) >= 3:
            risk_level = "high"
        elif len(risk_factors) >= 1:
            risk_level = "medium"
        else:
            risk_level = "low"
        
        return DealAnalysis(
            seller_asking_price=seller_asking_price,
            recommended_purchase_price=purchase_price,
            max_purchase_price=max_purchase,
            estimated_retail_value=retail_value,
            quick_sale_value=quick_sale_value,
            assignment_fee=fee_range,
            gross_margin=gross_margin,
            gross_margin_percentage=gross_margin_percentage,
            roi_percentage=roi,
            annualized_roi=annualized_roi,
            risk_level=risk_level,
            risk_factors=risk_factors,
        )
    
    def _get_base_percentage(self, deal_value: float) -> float:
        """Get base fee percentage based on deal value."""
        if deal_value < 10000:
            return self.DEFAULT_FEE_PERCENTAGES["under_10k"]
        elif deal_value < 25000:
            return self.DEFAULT_FEE_PERCENTAGES["10k_25k"]
        elif deal_value < 50000:
            return self.DEFAULT_FEE_PERCENTAGES["25k_50k"]
        elif deal_value < 100000:
            return self.DEFAULT_FEE_PERCENTAGES["50k_100k"]
        else:
            return self.DEFAULT_FEE_PERCENTAGES["over_100k"]
    
    def _calculate_confidence(
        self,
        buyer_count: int,
        margin_percentage: float,
        has_comps: bool,
        motivation_score: int,
    ) -> float:
        """Calculate confidence score for fee recommendation."""
        confidence = 0.5  # Base
        
        # Buyer demand
        if buyer_count >= 3:
            confidence += 0.15
        elif buyer_count >= 1:
            confidence += 0.05
        
        # Margin
        if margin_percentage >= 30:
            confidence += 0.15
        elif margin_percentage >= 20:
            confidence += 0.10
        
        # Comps
        if has_comps:
            confidence += 0.10
        
        # Motivation
        if motivation_score >= 60:
            confidence += 0.10
        
        return min(confidence, 1.0)


# Module-level singleton
_optimizer: Optional[AssignmentFeeOptimizer] = None


def get_assignment_fee_optimizer() -> AssignmentFeeOptimizer:
    """Get the global AssignmentFeeOptimizer instance."""
    global _optimizer
    if _optimizer is None:
        _optimizer = AssignmentFeeOptimizer()
    return _optimizer


def calculate_assignment_fee(
    purchase_price: float,
    retail_value: float,
    lot_size_acres: float = 1.0,
    market_code: str = "LA",
    **kwargs,
) -> AssignmentFeeRange:
    """
    Convenience function to calculate assignment fee.
    
    Uses the global optimizer instance.
    """
    optimizer = get_assignment_fee_optimizer()
    return optimizer.calculate_assignment_fee(
        purchase_price=purchase_price,
        retail_value=retail_value,
        lot_size_acres=lot_size_acres,
        market_code=market_code,
        **kwargs,
    )


__all__ = [
    "AssignmentFeeOptimizer",
    "AssignmentFeeRange",
    "DealAnalysis",
    "get_assignment_fee_optimizer",
    "calculate_assignment_fee",
]

