"""Buyer blast service for mass deal distribution."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from core.logging_config import get_logger
from core.models import Buyer, Lead, BuyerDeal, BuyerDealStage, OutreachAttempt
from core.utils import utcnow, generate_idempotency_key
from src.services.buyer_match import BuyerMatchService, BuyerMatch
from src.services.deal_sheet import DealSheetService, DealSheetContent
from src.services.timeline import TimelineService
from src.services.locking import get_send_lock_service
from src.services.idempotency import get_idempotency_service

LOGGER = get_logger(__name__)


@dataclass
class BlastResult:
    """Result of a buyer blast operation."""
    
    lead_id: int
    buyers_matched: int
    buyers_blasted: int
    buyers_skipped: int
    buyers_failed: int
    messages: List[Dict[str, Any]] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "lead_id": self.lead_id,
            "buyers_matched": self.buyers_matched,
            "buyers_blasted": self.buyers_blasted,
            "buyers_skipped": self.buyers_skipped,
            "buyers_failed": self.buyers_failed,
            "messages": self.messages,
            "errors": self.errors,
            "success": self.buyers_blasted > 0,
        }


class BuyerBlastService:
    """Service for sending deal blasts to buyers."""

    def __init__(self, session: Session):
        """Initialize the buyer blast service."""
        self.session = session
        self.match_service = BuyerMatchService(session)
        self.deal_sheet_service = DealSheetService(session)
        self.timeline = TimelineService(session)
        self.idempotency = get_idempotency_service(session)

    def send_blast(
        self,
        lead_id: int,
        buyer_ids: Optional[List[int]] = None,
        min_match_score: float = 50.0,
        max_buyers: int = 10,
        dry_run: bool = False,
    ) -> BlastResult:
        """
        Send deal blast to matched buyers.
        
        Args:
            lead_id: The lead ID to blast.
            buyer_ids: Specific buyer IDs to send to (if None, auto-match).
            min_match_score: Minimum match score to include.
            max_buyers: Maximum buyers to contact.
            dry_run: If True, don't actually send messages.
            
        Returns:
            BlastResult with operation summary.
        """
        result = BlastResult(
            lead_id=lead_id,
            buyers_matched=0,
            buyers_blasted=0,
            buyers_skipped=0,
            buyers_failed=0,
        )
        
        # Get lead
        lead = self.session.query(Lead).filter(Lead.id == lead_id).first()
        if not lead:
            result.errors.append("Lead not found")
            return result
        
        # Generate deal sheet
        deal_sheet = self.deal_sheet_service.generate_deal_sheet(lead_id)
        if not deal_sheet:
            result.errors.append("Failed to generate deal sheet")
            return result
        
        # Get matched buyers
        if buyer_ids:
            # Use specified buyers
            buyers = self.session.query(Buyer).filter(Buyer.id.in_(buyer_ids)).all()
            matches = [
                BuyerMatch(
                    buyer_id=b.id,
                    buyer_name=b.name,
                    buyer_phone=b.phone,
                    buyer_email=b.email,
                    total_score=100,
                    max_possible_score=100,
                    match_percentage=100,
                    vip=b.vip,
                    pof_verified=b.pof_verified,
                )
                for b in buyers
            ]
        else:
            # Auto-match buyers
            matches = self.match_service.match_buyers(
                lead,
                offer_price=deal_sheet.recommended_offer,
                limit=max_buyers * 2,  # Get more to filter
                min_score=min_match_score,
            )
        
        result.buyers_matched = len(matches)
        
        # Send to each buyer
        for match in matches[:max_buyers]:
            try:
                # Check for existing blast
                existing_deal = self.session.query(BuyerDeal).filter(
                    BuyerDeal.buyer_id == match.buyer_id,
                    BuyerDeal.lead_id == lead_id,
                ).first()
                
                if existing_deal and existing_deal.blast_sent_at:
                    result.buyers_skipped += 1
                    result.messages.append({
                        "buyer_id": match.buyer_id,
                        "buyer_name": match.buyer_name,
                        "status": "skipped",
                        "reason": "Already blasted",
                    })
                    continue
                
                # Check buyer has contact info
                if not match.buyer_phone:
                    result.buyers_skipped += 1
                    result.messages.append({
                        "buyer_id": match.buyer_id,
                        "buyer_name": match.buyer_name,
                        "status": "skipped",
                        "reason": "No phone number",
                    })
                    continue
                
                # Generate idempotency key
                idem_key = generate_idempotency_key(
                    "buyer_blast",
                    lead_id,
                    match.buyer_id,
                    utcnow().strftime("%Y-%m-%d"),
                )
                
                if self.idempotency.is_duplicate(idem_key):
                    result.buyers_skipped += 1
                    result.messages.append({
                        "buyer_id": match.buyer_id,
                        "buyer_name": match.buyer_name,
                        "status": "skipped",
                        "reason": "Duplicate prevented",
                    })
                    continue
                
                if dry_run:
                    result.buyers_skipped += 1
                    result.messages.append({
                        "buyer_id": match.buyer_id,
                        "buyer_name": match.buyer_name,
                        "status": "dry_run",
                        "message_preview": self._generate_message(match, deal_sheet)[:100],
                    })
                    continue
                
                # Create or update buyer deal
                if not existing_deal:
                    existing_deal = BuyerDeal(
                        buyer_id=match.buyer_id,
                        lead_id=lead_id,
                        stage=BuyerDealStage.NEW.value,
                        match_score=match.match_percentage,
                    )
                    self.session.add(existing_deal)
                    self.session.flush()
                
                # Send message
                success = self._send_blast_message(match, deal_sheet, idem_key)
                
                if success:
                    existing_deal.stage = BuyerDealStage.DEAL_SENT.value
                    existing_deal.blast_sent_at = utcnow()
                    
                    # Update buyer stats
                    buyer = self.session.query(Buyer).filter(Buyer.id == match.buyer_id).first()
                    if buyer:
                        buyer.deals_count = (buyer.deals_count or 0) + 1
                        buyer.last_deal_sent_at = utcnow()
                    
                    result.buyers_blasted += 1
                    result.messages.append({
                        "buyer_id": match.buyer_id,
                        "buyer_name": match.buyer_name,
                        "status": "sent",
                        "match_score": match.match_percentage,
                    })
                else:
                    result.buyers_failed += 1
                    result.messages.append({
                        "buyer_id": match.buyer_id,
                        "buyer_name": match.buyer_name,
                        "status": "failed",
                    })
                
            except Exception as e:
                LOGGER.error(f"Failed to blast buyer {match.buyer_id}: {e}")
                result.buyers_failed += 1
                result.errors.append(f"Buyer {match.buyer_id}: {str(e)}")
        
        # Log to timeline
        self.timeline.add_event(
            lead_id=lead_id,
            event_type="buyer_blast",
            title=f"Buyer blast sent to {result.buyers_blasted} buyers",
            description=f"Matched: {result.buyers_matched}, Sent: {result.buyers_blasted}, Skipped: {result.buyers_skipped}",
            metadata=result.to_dict(),
        )
        
        self.session.flush()
        
        return result

    def _generate_message(self, match: BuyerMatch, deal_sheet: DealSheetContent) -> str:
        """Generate blast message for a buyer."""
        message = f"""🏞️ NEW LAND DEAL - {deal_sheet.county}, {deal_sheet.state}

{deal_sheet.acreage:.2f} acres
📍 {deal_sheet.address or 'See details'}

💰 Price: ${deal_sheet.recommended_offer:,.0f}
📊 ${deal_sheet.price_per_acre:,.0f}/acre

{deal_sheet.ai_description or deal_sheet.owner_situation}

Interested? Reply YES for full details.
Reply STOP to opt out."""
        
        return message

    def _send_blast_message(
        self,
        match: BuyerMatch,
        deal_sheet: DealSheetContent,
        idem_key: str,
    ) -> bool:
        """Send the actual blast message via SMS."""
        try:
            from core.config import get_settings
            settings = get_settings()
            
            if settings.dry_run:
                LOGGER.info(f"[DRY RUN] Would send blast to buyer {match.buyer_id}")
                return True
            
            message = self._generate_message(match, deal_sheet)
            
            # Use Twilio client
            from outreach import get_twilio_client
            client = get_twilio_client()
            
            result = client.send_sms(
                to=match.buyer_phone,
                body=message,
            )
            
            LOGGER.info(f"Sent blast to buyer {match.buyer_id}, SID: {result.get('sid')}")
            return True
            
        except Exception as e:
            LOGGER.error(f"Failed to send blast to buyer {match.buyer_id}: {e}")
            return False

    def preview_blast(
        self,
        lead_id: int,
        max_buyers: int = 10,
        min_match_score: float = 50.0,
    ) -> Dict[str, Any]:
        """
        Preview a blast without sending.
        
        Args:
            lead_id: The lead ID.
            max_buyers: Maximum buyers to preview.
            min_match_score: Minimum match score.
            
        Returns:
            Preview data including deal sheet and matched buyers.
        """
        lead = self.session.query(Lead).filter(Lead.id == lead_id).first()
        if not lead:
            return {"error": "Lead not found"}
        
        deal_sheet = self.deal_sheet_service.generate_deal_sheet(lead_id)
        if not deal_sheet:
            return {"error": "Failed to generate deal sheet"}
        
        matches = self.match_service.match_buyers(
            lead,
            offer_price=deal_sheet.recommended_offer,
            limit=max_buyers,
            min_score=min_match_score,
        )
        
        return {
            "lead_id": lead_id,
            "deal_sheet": deal_sheet.to_dict(),
            "matched_buyers": [m.to_dict() for m in matches],
            "sample_message": self._generate_message(matches[0], deal_sheet) if matches else None,
        }


def get_buyer_blast_service(session: Session) -> BuyerBlastService:
    """Get a BuyerBlastService instance."""
    return BuyerBlastService(session)


__all__ = [
    "BuyerBlastService",
    "BlastResult",
    "get_buyer_blast_service",
]

