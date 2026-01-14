"""Buyer service for CRUD and preference management."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from core.logging_config import get_logger
from core.models import Buyer, BuyerDeal, BuyerDealStage
from core.utils import utcnow

LOGGER = get_logger(__name__)


@dataclass
class BuyerSummary:
    """Summary view of a buyer."""
    
    id: int
    name: str
    phone: Optional[str]
    email: Optional[str]
    market_codes: List[str]
    counties: List[str]
    min_acres: Optional[float]
    max_acres: Optional[float]
    price_min: Optional[float]
    price_max: Optional[float]
    vip: bool
    pof_verified: bool
    deals_count: int
    last_deal_sent_at: Optional[str]
    created_at: str
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "phone": self.phone,
            "email": self.email,
            "market_codes": self.market_codes,
            "counties": self.counties,
            "min_acres": self.min_acres,
            "max_acres": self.max_acres,
            "price_min": self.price_min,
            "price_max": self.price_max,
            "vip": self.vip,
            "pof_verified": self.pof_verified,
            "deals_count": self.deals_count,
            "last_deal_sent_at": self.last_deal_sent_at,
            "created_at": self.created_at,
        }


@dataclass
class BuyerDetail(BuyerSummary):
    """Detailed view of a buyer."""
    
    property_types: List[str] = field(default_factory=list)
    target_spread: Optional[float] = None
    closing_speed_days: Optional[int] = None
    notes: Optional[str] = None
    pof_url: Optional[str] = None
    pof_last_updated: Optional[str] = None
    response_rate: Optional[float] = None
    recent_deals: List[Dict[str, Any]] = field(default_factory=list)
    updated_at: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            "property_types": self.property_types,
            "target_spread": self.target_spread,
            "closing_speed_days": self.closing_speed_days,
            "notes": self.notes,
            "pof_url": self.pof_url,
            "pof_last_updated": self.pof_last_updated,
            "response_rate": self.response_rate,
            "recent_deals": self.recent_deals,
            "updated_at": self.updated_at,
        })
        return base


@dataclass
class BuyerCreate:
    """Data for creating a buyer."""
    
    name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    market_codes: List[str] = field(default_factory=list)
    counties: List[str] = field(default_factory=list)
    min_acres: Optional[float] = None
    max_acres: Optional[float] = None
    property_types: List[str] = field(default_factory=list)
    price_min: Optional[float] = None
    price_max: Optional[float] = None
    target_spread: Optional[float] = None
    closing_speed_days: Optional[int] = None
    vip: bool = False
    notes: Optional[str] = None
    pof_url: Optional[str] = None


class BuyerService:
    """Service for buyer CRUD operations."""

    def __init__(self, session: Session):
        """Initialize the buyer service."""
        self.session = session

    def _buyer_to_summary(self, buyer: Buyer) -> BuyerSummary:
        """Convert Buyer model to BuyerSummary."""
        return BuyerSummary(
            id=buyer.id,
            name=buyer.name,
            phone=buyer.phone,
            email=buyer.email,
            market_codes=buyer.market_codes or [],
            counties=buyer.counties or [],
            min_acres=buyer.min_acres,
            max_acres=buyer.max_acres,
            price_min=buyer.price_min,
            price_max=buyer.price_max,
            vip=buyer.vip,
            pof_verified=buyer.pof_verified,
            deals_count=buyer.deals_count,
            last_deal_sent_at=buyer.last_deal_sent_at.isoformat() if buyer.last_deal_sent_at else None,
            created_at=buyer.created_at.isoformat() if buyer.created_at else None,
        )

    def _buyer_to_detail(self, buyer: Buyer) -> BuyerDetail:
        """Convert Buyer model to BuyerDetail."""
        # Get recent deals
        recent_deals = []
        for deal in (buyer.deals or [])[:5]:
            recent_deals.append({
                "id": deal.id,
                "lead_id": deal.lead_id,
                "stage": deal.stage,
                "match_score": deal.match_score,
                "created_at": deal.created_at.isoformat() if deal.created_at else None,
            })
        
        return BuyerDetail(
            id=buyer.id,
            name=buyer.name,
            phone=buyer.phone,
            email=buyer.email,
            market_codes=buyer.market_codes or [],
            counties=buyer.counties or [],
            min_acres=buyer.min_acres,
            max_acres=buyer.max_acres,
            price_min=buyer.price_min,
            price_max=buyer.price_max,
            vip=buyer.vip,
            pof_verified=buyer.pof_verified,
            deals_count=buyer.deals_count,
            last_deal_sent_at=buyer.last_deal_sent_at.isoformat() if buyer.last_deal_sent_at else None,
            created_at=buyer.created_at.isoformat() if buyer.created_at else None,
            property_types=buyer.property_types or [],
            target_spread=buyer.target_spread,
            closing_speed_days=buyer.closing_speed_days,
            notes=buyer.notes,
            pof_url=buyer.pof_url,
            pof_last_updated=buyer.pof_last_updated.isoformat() if buyer.pof_last_updated else None,
            response_rate=buyer.response_rate,
            recent_deals=recent_deals,
            updated_at=buyer.updated_at.isoformat() if buyer.updated_at else None,
        )

    def create_buyer(self, data: BuyerCreate) -> BuyerDetail:
        """
        Create a new buyer.
        
        Args:
            data: Buyer creation data.
            
        Returns:
            Created buyer details.
        """
        buyer = Buyer(
            name=data.name,
            phone=data.phone,
            email=data.email,
            market_codes=data.market_codes,
            counties=data.counties,
            min_acres=data.min_acres,
            max_acres=data.max_acres,
            property_types=data.property_types,
            price_min=data.price_min,
            price_max=data.price_max,
            target_spread=data.target_spread,
            closing_speed_days=data.closing_speed_days,
            vip=data.vip,
            notes=data.notes,
            pof_url=data.pof_url,
        )
        
        self.session.add(buyer)
        self.session.flush()
        
        LOGGER.info(f"Created buyer {buyer.id}: {buyer.name}")
        return self._buyer_to_detail(buyer)

    def get_buyer(self, buyer_id: int) -> Optional[BuyerDetail]:
        """
        Get a buyer by ID.
        
        Args:
            buyer_id: The buyer ID.
            
        Returns:
            Buyer details or None.
        """
        buyer = self.session.query(Buyer).filter(Buyer.id == buyer_id).first()
        if not buyer:
            return None
        return self._buyer_to_detail(buyer)

    def list_buyers(
        self,
        market_code: Optional[str] = None,
        vip_only: bool = False,
        pof_verified_only: bool = False,
        search: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[BuyerSummary]:
        """
        List buyers with optional filtering.
        
        Args:
            market_code: Filter by market code.
            vip_only: Only return VIP buyers.
            pof_verified_only: Only return POF-verified buyers.
            search: Search by name, phone, or email.
            limit: Maximum results.
            offset: Skip results.
            
        Returns:
            List of buyer summaries.
        """
        query = self.session.query(Buyer)
        
        if vip_only:
            query = query.filter(Buyer.vip == True)
        
        if pof_verified_only:
            query = query.filter(Buyer.pof_verified == True)
        
        if search:
            search_term = f"%{search}%"
            query = query.filter(
                or_(
                    Buyer.name.ilike(search_term),
                    Buyer.phone.ilike(search_term),
                    Buyer.email.ilike(search_term),
                )
            )
        
        # Market code filtering (JSON array contains)
        # This is database-specific; for PostgreSQL use @> operator
        # For SQLite/generic, we filter in Python
        
        buyers = query.order_by(Buyer.vip.desc(), Buyer.name.asc()).offset(offset).limit(limit).all()
        
        # Filter by market_code if specified
        if market_code:
            buyers = [b for b in buyers if market_code.upper() in (b.market_codes or [])]
        
        return [self._buyer_to_summary(b) for b in buyers]

    def update_buyer(
        self,
        buyer_id: int,
        updates: Dict[str, Any],
    ) -> Optional[BuyerDetail]:
        """
        Update a buyer.
        
        Args:
            buyer_id: The buyer ID.
            updates: Fields to update.
            
        Returns:
            Updated buyer details or None.
        """
        buyer = self.session.query(Buyer).filter(Buyer.id == buyer_id).first()
        if not buyer:
            return None
        
        # Update allowed fields
        allowed_fields = {
            "name", "phone", "email", "market_codes", "counties",
            "min_acres", "max_acres", "property_types", "price_min",
            "price_max", "target_spread", "closing_speed_days", "vip",
            "notes", "pof_url",
        }
        
        for field, value in updates.items():
            if field in allowed_fields:
                setattr(buyer, field, value)
        
        buyer.updated_at = utcnow()
        self.session.flush()
        
        LOGGER.info(f"Updated buyer {buyer_id}")
        return self._buyer_to_detail(buyer)

    def delete_buyer(self, buyer_id: int) -> bool:
        """
        Delete a buyer.
        
        Args:
            buyer_id: The buyer ID.
            
        Returns:
            True if deleted, False if not found.
        """
        buyer = self.session.query(Buyer).filter(Buyer.id == buyer_id).first()
        if not buyer:
            return False
        
        self.session.delete(buyer)
        self.session.flush()
        
        LOGGER.info(f"Deleted buyer {buyer_id}")
        return True

    def update_pof(
        self,
        buyer_id: int,
        pof_url: str,
        verified: bool = False,
    ) -> Optional[BuyerDetail]:
        """
        Update buyer's proof of funds.
        
        Args:
            buyer_id: The buyer ID.
            pof_url: URL to POF document.
            verified: Whether POF is verified.
            
        Returns:
            Updated buyer details or None.
        """
        buyer = self.session.query(Buyer).filter(Buyer.id == buyer_id).first()
        if not buyer:
            return None
        
        buyer.pof_url = pof_url
        buyer.pof_verified = verified
        buyer.pof_last_updated = utcnow()
        buyer.updated_at = utcnow()
        
        self.session.flush()
        
        LOGGER.info(f"Updated POF for buyer {buyer_id}, verified={verified}")
        return self._buyer_to_detail(buyer)

    def get_buyer_deals(
        self,
        buyer_id: int,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Get deals for a buyer.
        
        Args:
            buyer_id: The buyer ID.
            limit: Maximum results.
            
        Returns:
            List of deal details.
        """
        deals = self.session.query(BuyerDeal).filter(
            BuyerDeal.buyer_id == buyer_id
        ).order_by(BuyerDeal.created_at.desc()).limit(limit).all()
        
        return [
            {
                "id": d.id,
                "lead_id": d.lead_id,
                "stage": d.stage,
                "match_score": d.match_score,
                "offer_amount": d.offer_amount,
                "assignment_fee": d.assignment_fee,
                "blast_sent_at": d.blast_sent_at.isoformat() if d.blast_sent_at else None,
                "created_at": d.created_at.isoformat() if d.created_at else None,
            }
            for d in deals
        ]

    def get_statistics(self) -> Dict[str, Any]:
        """Get buyer statistics."""
        total = self.session.query(func.count(Buyer.id)).scalar() or 0
        vip_count = self.session.query(func.count(Buyer.id)).filter(Buyer.vip == True).scalar() or 0
        pof_verified = self.session.query(func.count(Buyer.id)).filter(Buyer.pof_verified == True).scalar() or 0
        
        return {
            "total_buyers": total,
            "vip_buyers": vip_count,
            "pof_verified_buyers": pof_verified,
        }


def get_buyer_service(session: Session) -> BuyerService:
    """Get a BuyerService instance."""
    return BuyerService(session)


__all__ = [
    "BuyerService",
    "BuyerSummary",
    "BuyerDetail",
    "BuyerCreate",
    "get_buyer_service",
]

