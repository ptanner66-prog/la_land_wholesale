"""Buyer matching service for lead-to-buyer scoring."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from core.logging_config import get_logger
from core.models import Buyer, Lead, BuyerDeal, BuyerDealStage

LOGGER = get_logger(__name__)


@dataclass
class MatchScore:
    """Individual match score component."""
    
    factor: str
    label: str
    score: float
    max_score: float
    matched: bool
    details: Optional[str] = None


@dataclass
class BuyerMatch:
    """A matched buyer with score breakdown."""
    
    buyer_id: int
    buyer_name: str
    buyer_phone: Optional[str]
    buyer_email: Optional[str]
    total_score: float
    max_possible_score: float
    match_percentage: float
    vip: bool
    pof_verified: bool
    factors: List[MatchScore] = field(default_factory=list)
    existing_deal: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "buyer_id": self.buyer_id,
            "buyer_name": self.buyer_name,
            "buyer_phone": self.buyer_phone,
            "buyer_email": self.buyer_email,
            "total_score": round(self.total_score, 1),
            "max_possible_score": round(self.max_possible_score, 1),
            "match_percentage": round(self.match_percentage, 1),
            "vip": self.vip,
            "pof_verified": self.pof_verified,
            "factors": [
                {
                    "factor": f.factor,
                    "label": f.label,
                    "score": round(f.score, 1),
                    "max_score": round(f.max_score, 1),
                    "matched": f.matched,
                    "details": f.details,
                }
                for f in self.factors
            ],
            "existing_deal": self.existing_deal,
        }


class BuyerMatchService:
    """Service for matching buyers to leads."""

    # Scoring weights
    WEIGHTS = {
        "market": 25,      # Market match is critical
        "county": 20,      # County preference
        "acreage": 15,     # Acreage within range
        "budget": 15,      # Price within budget
        "vip": 10,         # VIP buyer bonus
        "pof_verified": 10, # POF verified bonus
        "spread": 5,       # Target spread compatible
    }

    def __init__(self, session: Session):
        """Initialize the match service."""
        self.session = session

    def match_buyers(
        self,
        lead: Lead,
        offer_price: Optional[float] = None,
        limit: int = 20,
        min_score: float = 30.0,
    ) -> List[BuyerMatch]:
        """
        Find matching buyers for a lead.
        
        Args:
            lead: The lead to match.
            offer_price: The anticipated offer price.
            limit: Maximum buyers to return.
            min_score: Minimum match percentage to include.
            
        Returns:
            Ranked list of matching buyers.
        """
        # Get all buyers
        buyers = self.session.query(Buyer).all()
        
        parcel = lead.parcel
        acreage = float(parcel.lot_size_acres or 0) if parcel else 0
        county = parcel.parish if parcel else None
        market = lead.market_code
        
        matches = []
        
        for buyer in buyers:
            match = self._score_buyer(buyer, lead, market, county, acreage, offer_price)
            
            if match.match_percentage >= min_score:
                # Check for existing deal
                existing = self.session.query(BuyerDeal).filter(
                    BuyerDeal.buyer_id == buyer.id,
                    BuyerDeal.lead_id == lead.id,
                ).first()
                
                if existing:
                    match.existing_deal = {
                        "id": existing.id,
                        "stage": existing.stage,
                        "created_at": existing.created_at.isoformat() if existing.created_at else None,
                    }
                
                matches.append(match)
        
        # Sort by total score descending
        matches.sort(key=lambda m: (m.vip, m.total_score), reverse=True)
        
        return matches[:limit]

    def _score_buyer(
        self,
        buyer: Buyer,
        lead: Lead,
        market: str,
        county: Optional[str],
        acreage: float,
        offer_price: Optional[float],
    ) -> BuyerMatch:
        """
        Calculate match score for a buyer against a lead.
        """
        factors = []
        total_score = 0.0
        max_possible = sum(self.WEIGHTS.values())
        
        # Market match
        market_matched = market in (buyer.market_codes or [])
        market_score = self.WEIGHTS["market"] if market_matched else 0
        factors.append(MatchScore(
            factor="market",
            label="Market Match",
            score=market_score,
            max_score=self.WEIGHTS["market"],
            matched=market_matched,
            details=f"Buyer wants: {', '.join(buyer.market_codes or ['Any'])}",
        ))
        total_score += market_score
        
        # County match
        county_matched = False
        if county and buyer.counties:
            county_upper = county.upper()
            county_matched = any(c.upper() in county_upper or county_upper in c.upper() 
                                for c in buyer.counties)
        elif not buyer.counties:
            county_matched = True  # No preference = match
        
        county_score = self.WEIGHTS["county"] if county_matched else 0
        factors.append(MatchScore(
            factor="county",
            label="County Match",
            score=county_score,
            max_score=self.WEIGHTS["county"],
            matched=county_matched,
            details=f"Buyer wants: {', '.join(buyer.counties or ['Any'])}",
        ))
        total_score += county_score
        
        # Acreage match
        acreage_matched = True
        acreage_details = "Within range"
        
        if buyer.min_acres and acreage < buyer.min_acres:
            acreage_matched = False
            acreage_details = f"Below min ({buyer.min_acres} ac)"
        elif buyer.max_acres and acreage > buyer.max_acres:
            acreage_matched = False
            acreage_details = f"Above max ({buyer.max_acres} ac)"
        
        acreage_score = self.WEIGHTS["acreage"] if acreage_matched else 0
        factors.append(MatchScore(
            factor="acreage",
            label="Acreage",
            score=acreage_score,
            max_score=self.WEIGHTS["acreage"],
            matched=acreage_matched,
            details=f"{acreage:.2f} ac - {acreage_details}",
        ))
        total_score += acreage_score
        
        # Budget match
        budget_matched = True
        budget_details = "Within budget"
        
        if offer_price:
            if buyer.price_min and offer_price < buyer.price_min:
                budget_matched = False
                budget_details = f"Below min (${buyer.price_min:,.0f})"
            elif buyer.price_max and offer_price > buyer.price_max:
                budget_matched = False
                budget_details = f"Above max (${buyer.price_max:,.0f})"
        elif buyer.price_min or buyer.price_max:
            budget_details = "No offer price to compare"
        
        budget_score = self.WEIGHTS["budget"] if budget_matched else 0
        factors.append(MatchScore(
            factor="budget",
            label="Budget",
            score=budget_score,
            max_score=self.WEIGHTS["budget"],
            matched=budget_matched,
            details=budget_details,
        ))
        total_score += budget_score
        
        # VIP bonus
        vip_score = self.WEIGHTS["vip"] if buyer.vip else 0
        factors.append(MatchScore(
            factor="vip",
            label="VIP Status",
            score=vip_score,
            max_score=self.WEIGHTS["vip"],
            matched=buyer.vip,
            details="VIP buyer" if buyer.vip else "Standard buyer",
        ))
        total_score += vip_score
        
        # POF verified bonus
        pof_score = self.WEIGHTS["pof_verified"] if buyer.pof_verified else 0
        factors.append(MatchScore(
            factor="pof_verified",
            label="POF Verified",
            score=pof_score,
            max_score=self.WEIGHTS["pof_verified"],
            matched=buyer.pof_verified,
            details="POF on file" if buyer.pof_verified else "No POF",
        ))
        total_score += pof_score
        
        # Target spread
        spread_matched = True
        if buyer.target_spread and offer_price:
            # Check if deal can support buyer's target spread
            spread_matched = True  # Simplified for now
        
        spread_score = self.WEIGHTS["spread"] if spread_matched else 0
        factors.append(MatchScore(
            factor="spread",
            label="Spread Compatible",
            score=spread_score,
            max_score=self.WEIGHTS["spread"],
            matched=spread_matched,
            details=f"Target: ${buyer.target_spread:,.0f}" if buyer.target_spread else "No target",
        ))
        total_score += spread_score
        
        match_percentage = (total_score / max_possible) * 100 if max_possible > 0 else 0
        
        return BuyerMatch(
            buyer_id=buyer.id,
            buyer_name=buyer.name,
            buyer_phone=buyer.phone,
            buyer_email=buyer.email,
            total_score=total_score,
            max_possible_score=max_possible,
            match_percentage=match_percentage,
            vip=buyer.vip,
            pof_verified=buyer.pof_verified,
            factors=factors,
        )

    def get_best_matches(
        self,
        lead_id: int,
        offer_price: Optional[float] = None,
        top_n: int = 5,
    ) -> List[BuyerMatch]:
        """
        Get top N matching buyers for a lead.
        
        Args:
            lead_id: The lead ID.
            offer_price: Optional offer price.
            top_n: Number of top matches to return.
            
        Returns:
            Top matching buyers.
        """
        lead = self.session.query(Lead).filter(Lead.id == lead_id).first()
        if not lead:
            return []
        
        return self.match_buyers(lead, offer_price=offer_price, limit=top_n)


def get_buyer_match_service(session: Session) -> BuyerMatchService:
    """Get a BuyerMatchService instance."""
    return BuyerMatchService(session)


__all__ = [
    "BuyerMatchService",
    "BuyerMatch",
    "MatchScore",
    "get_buyer_match_service",
]

