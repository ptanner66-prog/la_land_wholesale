"""
Seller AI Conversation Engine

Intelligent SMS conversation management for land wholesaling:
- Intent detection and classification
- Lead qualification through conversation
- Tone control and negotiation rules
- TCPA/STOP/DNC enforcement
- Follow-up sequence management
- Booking and scheduling logic
- Structured output for pipeline integration
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from core.config import get_settings
from core.logging_config import get_logger
from core.models import Lead, Owner, OutreachAttempt, ReplyClassification, PipelineStage
from core.utils import utcnow
from llm.client import get_llm_client
from src.services.timeline import TimelineService

LOGGER = get_logger(__name__)
SETTINGS = get_settings()


class ConversationIntent(str, Enum):
    """Detected conversation intents."""
    INTERESTED = "interested"
    NOT_INTERESTED = "not_interested"
    ASKING_PRICE = "asking_price"
    NEGOTIATING = "negotiating"
    SCHEDULING = "scheduling"
    CONFUSED = "confused"
    STOP = "stop"
    WRONG_NUMBER = "wrong_number"
    DECEASED = "deceased"
    SPAM = "spam"
    GREETING = "greeting"
    QUESTION = "question"


class ConversationTone(str, Enum):
    """Response tone settings."""
    FRIENDLY = "friendly"
    PROFESSIONAL = "professional"
    DIRECT = "direct"
    EMPATHETIC = "empathetic"
    URGENT = "urgent"


class ConversationStage(str, Enum):
    """Conversation stage in the pipeline."""
    INITIAL_OUTREACH = "initial_outreach"
    FIRST_RESPONSE = "first_response"
    QUALIFICATION = "qualification"
    PRICE_DISCUSSION = "price_discussion"
    NEGOTIATION = "negotiation"
    CLOSING = "closing"
    DEAD = "dead"


@dataclass
class IntentDetectionResult:
    """Result of intent detection."""
    intent: ConversationIntent
    confidence: float
    sentiment: str  # positive, neutral, negative
    keywords_found: List[str]
    requires_action: bool
    action_type: Optional[str]  # respond, escalate, stop, schedule
    raw_analysis: Optional[Dict[str, Any]] = None


@dataclass
class QualificationResult:
    """Lead qualification from conversation."""
    is_qualified: bool
    qualification_score: int  # 0-100
    factors: Dict[str, bool]
    missing_info: List[str]
    next_question: Optional[str]
    notes: str


@dataclass
class ResponseGeneration:
    """Generated response with metadata."""
    message: str
    tone: ConversationTone
    intent_addressed: ConversationIntent
    includes_question: bool
    includes_offer: bool
    fallback_used: bool
    reasoning: Optional[str] = None


@dataclass
class ConversationContext:
    """Full conversation context for a lead."""
    lead_id: int
    owner_name: str
    property_address: str
    property_county: str
    property_acreage: float
    market_code: str
    motivation_score: int
    pipeline_stage: str
    
    # Conversation history
    message_count: int
    last_message_at: Optional[datetime]
    last_intent: Optional[ConversationIntent]
    conversation_stage: ConversationStage
    
    # Qualification status
    has_confirmed_ownership: bool
    has_expressed_interest: bool
    has_asked_price: bool
    has_received_offer: bool
    
    # Contact preferences
    preferred_contact_method: str
    best_time_to_call: Optional[str]
    
    # DNC/Compliance
    is_opted_out: bool
    stop_requested: bool


@dataclass
class ConversationAction:
    """Action to take after processing a message."""
    action_type: str  # respond, escalate, stop, schedule, update_lead
    response: Optional[ResponseGeneration]
    lead_updates: Dict[str, Any]
    timeline_event: Optional[Dict[str, Any]]
    schedule_followup: Optional[datetime]
    alert_needed: bool
    alert_message: Optional[str]


class ConversationEngine:
    """
    AI-powered conversation engine for seller interactions.
    
    Features:
    - Intent detection with keyword and LLM analysis
    - Lead qualification through conversation
    - Dynamic response generation
    - TCPA compliance and STOP handling
    - Follow-up sequence management
    - Pipeline stage progression
    """

    # STOP/DNC keywords - CRITICAL for TCPA compliance
    STOP_KEYWORDS = {
        'stop', 'unsubscribe', 'remove', 'opt out', 'opt-out',
        'cancel', 'quit', 'end', 'do not contact', "don't contact",
        'no more', 'leave me alone', 'take me off', 'remove me',
    }
    
    # Deceased/wrong number indicators
    DECEASED_KEYWORDS = {
        'deceased', 'passed away', 'died', 'death', 'no longer with us',
        'passed on', 'rest in peace', 'rip',
    }
    
    WRONG_NUMBER_KEYWORDS = {
        'wrong number', 'wrong person', "don't own", 'not my property',
        'never owned', 'sold it', 'already sold', 'not the owner',
    }
    
    # Positive interest indicators
    INTEREST_KEYWORDS = {
        'interested', 'tell me more', 'how much', 'what price',
        'make an offer', 'send offer', 'yes', 'sure', 'okay',
        'let me know', 'what can you offer', 'cash offer',
    }
    
    # Negative indicators
    NOT_INTERESTED_KEYWORDS = {
        'not interested', 'no thanks', 'no thank you', 'not selling',
        'not for sale', 'keeping it', 'no', "don't want", 'pass',
    }

    # Follow-up intervals (days)
    FOLLOWUP_INTERVALS = [3, 7, 14, 30]
    
    # Max followups before marking dead
    MAX_FOLLOWUPS = 4

    def __init__(self, session: Session):
        """Initialize the conversation engine."""
        self.session = session
        self.llm = get_llm_client()
        self.timeline = TimelineService(session)

    def process_incoming_message(
        self,
        lead_id: int,
        message: str,
        from_number: str,
    ) -> ConversationAction:
        """
        Process an incoming SMS message from a seller.
        
        Args:
            lead_id: The lead ID.
            message: The incoming message text.
            from_number: The sender's phone number.
            
        Returns:
            ConversationAction with response and updates.
        """
        # Load lead and context
        lead = self.session.query(Lead).filter(Lead.id == lead_id).first()
        if not lead:
            return ConversationAction(
                action_type="error",
                response=None,
                lead_updates={},
                timeline_event=None,
                schedule_followup=None,
                alert_needed=False,
                alert_message=None,
            )
        
        context = self._build_context(lead)
        
        # Step 1: Detect intent
        intent_result = self.detect_intent(message)
        
        # Step 2: Handle STOP/compliance immediately
        if intent_result.intent == ConversationIntent.STOP:
            return self._handle_stop_request(lead, message, intent_result)
        
        if intent_result.intent == ConversationIntent.DECEASED:
            return self._handle_deceased(lead, message, intent_result)
        
        if intent_result.intent == ConversationIntent.WRONG_NUMBER:
            return self._handle_wrong_number(lead, message, intent_result)
        
        # Step 3: Update qualification
        qualification = self._update_qualification(lead, message, intent_result)
        
        # Step 4: Generate response
        response = self._generate_response(context, message, intent_result, qualification)
        
        # Step 5: Determine lead updates
        lead_updates = self._calculate_lead_updates(lead, intent_result, qualification)
        
        # Step 6: Check if alert needed
        alert_needed, alert_message = self._check_alert_needed(intent_result, qualification)
        
        # Step 7: Schedule followup if needed
        followup = self._calculate_followup(lead, intent_result)
        
        # Log to timeline
        timeline_event = {
            "event_type": "message_received",
            "title": f"Reply received: {intent_result.intent.value}",
            "description": f"Message: {message[:100]}...",
            "metadata": {
                "intent": intent_result.intent.value,
                "confidence": intent_result.confidence,
                "sentiment": intent_result.sentiment,
            },
        }
        
        return ConversationAction(
            action_type="respond",
            response=response,
            lead_updates=lead_updates,
            timeline_event=timeline_event,
            schedule_followup=followup,
            alert_needed=alert_needed,
            alert_message=alert_message,
        )

    def detect_intent(self, message: str) -> IntentDetectionResult:
        """
        Detect the intent of an incoming message.
        
        Uses keyword matching first, then LLM for ambiguous cases.
        """
        message_lower = message.lower().strip()
        keywords_found = []
        
        # Priority 1: STOP keywords (TCPA compliance)
        for keyword in self.STOP_KEYWORDS:
            if keyword in message_lower:
                keywords_found.append(keyword)
                return IntentDetectionResult(
                    intent=ConversationIntent.STOP,
                    confidence=1.0,
                    sentiment="negative",
                    keywords_found=keywords_found,
                    requires_action=True,
                    action_type="stop",
                )
        
        # Priority 2: Deceased indicators
        for keyword in self.DECEASED_KEYWORDS:
            if keyword in message_lower:
                keywords_found.append(keyword)
                return IntentDetectionResult(
                    intent=ConversationIntent.DECEASED,
                    confidence=0.95,
                    sentiment="negative",
                    keywords_found=keywords_found,
                    requires_action=True,
                    action_type="stop",
                )
        
        # Priority 3: Wrong number
        for keyword in self.WRONG_NUMBER_KEYWORDS:
            if keyword in message_lower:
                keywords_found.append(keyword)
                return IntentDetectionResult(
                    intent=ConversationIntent.WRONG_NUMBER,
                    confidence=0.9,
                    sentiment="neutral",
                    keywords_found=keywords_found,
                    requires_action=True,
                    action_type="stop",
                )
        
        # Priority 4: Not interested
        for keyword in self.NOT_INTERESTED_KEYWORDS:
            if keyword in message_lower:
                keywords_found.append(keyword)
                return IntentDetectionResult(
                    intent=ConversationIntent.NOT_INTERESTED,
                    confidence=0.85,
                    sentiment="negative",
                    keywords_found=keywords_found,
                    requires_action=False,
                    action_type="respond",
                )
        
        # Priority 5: Positive interest / asking price
        for keyword in self.INTEREST_KEYWORDS:
            if keyword in message_lower:
                keywords_found.append(keyword)
                
                # Check if asking for price specifically
                price_keywords = ['how much', 'what price', 'offer', 'cash']
                is_asking_price = any(pk in message_lower for pk in price_keywords)
                
                return IntentDetectionResult(
                    intent=ConversationIntent.ASKING_PRICE if is_asking_price else ConversationIntent.INTERESTED,
                    confidence=0.8,
                    sentiment="positive",
                    keywords_found=keywords_found,
                    requires_action=True,
                    action_type="respond",
                )
        
        # If no clear keywords, use LLM for classification
        return self._llm_intent_detection(message)

    def _llm_intent_detection(self, message: str) -> IntentDetectionResult:
        """Use LLM to detect intent for ambiguous messages."""
        try:
            analysis = self.llm.classify_intent(message)
            
            # Map LLM intent to our enum
            intent_map = {
                "INTERESTED": ConversationIntent.INTERESTED,
                "NOT_INTERESTED": ConversationIntent.NOT_INTERESTED,
                "ASKING_PRICE": ConversationIntent.ASKING_PRICE,
                "CONFUSED": ConversationIntent.CONFUSED,
                "STOP": ConversationIntent.STOP,
                "SPAM": ConversationIntent.SPAM,
            }
            
            intent_str = analysis.get("intent", "CONFUSED").upper()
            intent = intent_map.get(intent_str, ConversationIntent.CONFUSED)
            
            return IntentDetectionResult(
                intent=intent,
                confidence=analysis.get("confidence", 0.5),
                sentiment=analysis.get("sentiment", "neutral"),
                keywords_found=[],
                requires_action=intent in (ConversationIntent.INTERESTED, ConversationIntent.ASKING_PRICE),
                action_type="respond" if intent != ConversationIntent.STOP else "stop",
                raw_analysis=analysis,
            )
            
        except Exception as e:
            LOGGER.error(f"LLM intent detection failed: {e}")
            return IntentDetectionResult(
                intent=ConversationIntent.CONFUSED,
                confidence=0.3,
                sentiment="neutral",
                keywords_found=[],
                requires_action=True,
                action_type="respond",
            )

    def qualify_lead(
        self,
        lead: Lead,
        conversation_history: List[Dict[str, Any]],
    ) -> QualificationResult:
        """
        Qualify a lead based on conversation history.
        
        Evaluates:
        - Ownership confirmation
        - Motivation level
        - Timeline/urgency
        - Price expectations
        - Decision maker status
        """
        factors = {
            "confirmed_owner": False,
            "motivated": False,
            "realistic_price": False,
            "decision_maker": False,
            "willing_to_discuss": False,
            "timeline_known": False,
        }
        
        missing_info = []
        
        # Analyze conversation for qualification signals
        for msg in conversation_history:
            text = msg.get("message", "").lower()
            direction = msg.get("direction", "")
            
            if direction == "inbound":
                # Check for ownership confirmation
                if any(x in text for x in ["my property", "i own", "my land", "yes"]):
                    factors["confirmed_owner"] = True
                
                # Check for motivation signals
                if any(x in text for x in ["need to sell", "have to sell", "want to sell", "ready to"]):
                    factors["motivated"] = True
                
                # Check for willingness to discuss
                if any(x in text for x in ["tell me more", "interested", "how much", "offer"]):
                    factors["willing_to_discuss"] = True
        
        # Calculate score
        score = sum(20 for v in factors.values() if v)
        
        # Determine missing info
        if not factors["confirmed_owner"]:
            missing_info.append("ownership_confirmation")
        if not factors["motivated"]:
            missing_info.append("motivation_level")
        if not factors["timeline_known"]:
            missing_info.append("selling_timeline")
        
        # Generate next question
        next_question = None
        if not factors["confirmed_owner"]:
            next_question = "Just to confirm, you're the owner of this property, right?"
        elif not factors["motivated"] and factors["willing_to_discuss"]:
            next_question = "What's your main reason for considering selling?"
        elif not factors["timeline_known"] and factors["motivated"]:
            next_question = "What kind of timeline are you looking at for selling?"
        
        return QualificationResult(
            is_qualified=score >= 60,
            qualification_score=score,
            factors=factors,
            missing_info=missing_info,
            next_question=next_question,
            notes=f"Qualified with {score}% confidence" if score >= 60 else "Needs more qualification",
        )

    def generate_response(
        self,
        context: ConversationContext,
        intent: ConversationIntent,
        tone: ConversationTone = ConversationTone.PROFESSIONAL,
        include_offer: bool = False,
        offer_amount: Optional[float] = None,
    ) -> ResponseGeneration:
        """
        Generate a response message for the conversation.
        
        Args:
            context: The conversation context.
            intent: The detected intent to address.
            tone: The desired response tone.
            include_offer: Whether to include a price offer.
            offer_amount: The offer amount if including.
            
        Returns:
            ResponseGeneration with the message and metadata.
        """
        # Build context for LLM
        lead_info = {
            "owner_name": context.owner_name.split()[0] if context.owner_name else "there",
            "address": context.property_address,
            "county": context.property_county,
            "acreage": context.property_acreage,
        }
        
        # Determine response strategy based on intent
        if intent == ConversationIntent.INTERESTED:
            response_context = "The seller expressed interest"
        elif intent == ConversationIntent.ASKING_PRICE:
            response_context = "The seller is asking about price"
        elif intent == ConversationIntent.NOT_INTERESTED:
            response_context = "The seller said they're not interested - be respectful but leave door open"
        elif intent == ConversationIntent.CONFUSED:
            response_context = "The seller seems confused - clarify who you are and why you're contacting them"
        elif intent == ConversationIntent.NEGOTIATING:
            response_context = "The seller is negotiating - be firm but flexible"
        else:
            response_context = "Continue the conversation naturally"
        
        try:
            message = self.llm.generate_response(
                context=response_context,
                seller_message="",  # We already know the intent
                lead_info=lead_info,
                tone=tone.value,
            )
            
            # Add offer if requested
            if include_offer and offer_amount:
                message = f"{message} I can offer ${offer_amount:,.0f} cash, quick closing."
            
            # Ensure message is SMS-appropriate length
            if len(message) > 160:
                message = message[:157] + "..."
            
            return ResponseGeneration(
                message=message,
                tone=tone,
                intent_addressed=intent,
                includes_question="?" in message,
                includes_offer=include_offer,
                fallback_used=False,
            )
            
        except Exception as e:
            LOGGER.error(f"Response generation failed: {e}")
            return self._get_fallback_response(context, intent, tone)

    def _get_fallback_response(
        self,
        context: ConversationContext,
        intent: ConversationIntent,
        tone: ConversationTone,
    ) -> ResponseGeneration:
        """Get a fallback response when LLM fails."""
        name = context.owner_name.split()[0] if context.owner_name else "there"
        
        responses = {
            ConversationIntent.INTERESTED: f"Great to hear {name}! I'd love to discuss the property with you. What questions do you have?",
            ConversationIntent.ASKING_PRICE: f"Thanks for asking {name}. I'd need to verify a few details first. Is now a good time to chat briefly?",
            ConversationIntent.NOT_INTERESTED: f"No problem at all {name}. If anything changes, feel free to reach out. Have a great day!",
            ConversationIntent.CONFUSED: f"Hi {name}, this is about your property. I'm a local land buyer interested in making a cash offer. Any interest in selling?",
        }
        
        message = responses.get(intent, f"Thanks for your response {name}. Would you like to discuss your property?")
        
        return ResponseGeneration(
            message=message[:160],
            tone=tone,
            intent_addressed=intent,
            includes_question="?" in message,
            includes_offer=False,
            fallback_used=True,
        )

    def _build_context(self, lead: Lead) -> ConversationContext:
        """Build conversation context from lead."""
        owner = lead.owner
        parcel = lead.parcel
        party = owner.party if owner else None
        
        # Get conversation history
        attempts = self.session.query(OutreachAttempt).filter(
            OutreachAttempt.lead_id == lead.id
        ).order_by(OutreachAttempt.created_at.desc()).all()
        
        last_message_at = attempts[0].created_at if attempts else None
        
        # Determine conversation stage
        if not attempts:
            stage = ConversationStage.INITIAL_OUTREACH
        elif lead.pipeline_stage == "HOT":
            stage = ConversationStage.NEGOTIATION
        elif lead.last_reply_classification:
            if lead.last_reply_classification in ("INTERESTED", "SEND_OFFER"):
                stage = ConversationStage.QUALIFICATION
            else:
                stage = ConversationStage.FIRST_RESPONSE
        else:
            stage = ConversationStage.INITIAL_OUTREACH
        
        return ConversationContext(
            lead_id=lead.id,
            owner_name=party.display_name if party else "Property Owner",
            property_address=parcel.situs_address if parcel else "Unknown",
            property_county=parcel.parish if parcel else "Unknown",
            property_acreage=float(parcel.lot_size_acres or 1.0) if parcel else 1.0,
            market_code=lead.market_code,
            motivation_score=lead.motivation_score,
            pipeline_stage=lead.pipeline_stage,
            message_count=len(attempts),
            last_message_at=last_message_at,
            last_intent=ConversationIntent(lead.last_reply_classification.lower()) if lead.last_reply_classification else None,
            conversation_stage=stage,
            has_confirmed_ownership=False,
            has_expressed_interest=lead.pipeline_stage == "HOT",
            has_asked_price=lead.last_reply_classification == "SEND_OFFER" if lead.last_reply_classification else False,
            has_received_offer=False,
            preferred_contact_method="sms",
            best_time_to_call=None,
            is_opted_out=owner.opt_out if owner else False,
            stop_requested=False,
        )

    def _handle_stop_request(
        self,
        lead: Lead,
        message: str,
        intent: IntentDetectionResult,
    ) -> ConversationAction:
        """Handle STOP/opt-out request - TCPA compliance critical."""
        # Update owner opt-out status
        if lead.owner:
            lead.owner.opt_out = True
            lead.owner.opt_out_at = utcnow()
        
        # Update lead status
        lead.pipeline_stage = "CONTACTED"
        lead.last_reply_classification = "DEAD"
        
        self.session.flush()
        
        # Log to timeline
        self.timeline.add_event(
            lead_id=lead.id,
            event_type="opt_out",
            title="STOP request received",
            description="Owner opted out of communications",
            metadata={"original_message": message[:200]},
        )
        
        return ConversationAction(
            action_type="stop",
            response=ResponseGeneration(
                message="You have been unsubscribed and will not receive further messages.",
                tone=ConversationTone.PROFESSIONAL,
                intent_addressed=ConversationIntent.STOP,
                includes_question=False,
                includes_offer=False,
                fallback_used=False,
            ),
            lead_updates={"opt_out": True, "pipeline_stage": "CONTACTED"},
            timeline_event={
                "event_type": "opt_out",
                "title": "STOP request processed",
                "description": "Owner removed from outreach",
            },
            schedule_followup=None,
            alert_needed=False,
            alert_message=None,
        )

    def _handle_deceased(
        self,
        lead: Lead,
        message: str,
        intent: IntentDetectionResult,
    ) -> ConversationAction:
        """Handle deceased owner notification."""
        lead.pipeline_stage = "CONTACTED"
        lead.last_reply_classification = "DEAD"
        
        self.session.flush()
        
        return ConversationAction(
            action_type="stop",
            response=ResponseGeneration(
                message="We apologize for the inconvenience. Our condolences.",
                tone=ConversationTone.EMPATHETIC,
                intent_addressed=ConversationIntent.DECEASED,
                includes_question=False,
                includes_offer=False,
                fallback_used=False,
            ),
            lead_updates={"pipeline_stage": "CONTACTED", "status": "deceased"},
            timeline_event={
                "event_type": "deceased_notification",
                "title": "Owner reported as deceased",
                "description": message[:200],
            },
            schedule_followup=None,
            alert_needed=False,
            alert_message=None,
        )

    def _handle_wrong_number(
        self,
        lead: Lead,
        message: str,
        intent: IntentDetectionResult,
    ) -> ConversationAction:
        """Handle wrong number notification."""
        lead.pipeline_stage = "CONTACTED"
        lead.last_reply_classification = "DEAD"
        
        self.session.flush()
        
        return ConversationAction(
            action_type="stop",
            response=ResponseGeneration(
                message="Apologies for the confusion. We'll remove this number from our list.",
                tone=ConversationTone.PROFESSIONAL,
                intent_addressed=ConversationIntent.WRONG_NUMBER,
                includes_question=False,
                includes_offer=False,
                fallback_used=False,
            ),
            lead_updates={"pipeline_stage": "CONTACTED", "status": "wrong_number"},
            timeline_event={
                "event_type": "wrong_number",
                "title": "Wrong number reported",
                "description": message[:200],
            },
            schedule_followup=None,
            alert_needed=False,
            alert_message=None,
        )

    def _update_qualification(
        self,
        lead: Lead,
        message: str,
        intent: IntentDetectionResult,
    ) -> QualificationResult:
        """Update lead qualification based on new message."""
        # Get conversation history
        history = self.session.query(OutreachAttempt).filter(
            OutreachAttempt.lead_id == lead.id
        ).order_by(OutreachAttempt.created_at).all()
        
        conversation = [
            {
                "direction": "inbound" if a.response_body else "outbound",
                "message": a.response_body or a.message_body or "",
            }
            for a in history
        ]
        
        # Add current message
        conversation.append({"direction": "inbound", "message": message})
        
        return self.qualify_lead(lead, conversation)

    def _generate_response(
        self,
        context: ConversationContext,
        message: str,
        intent: IntentDetectionResult,
        qualification: QualificationResult,
    ) -> ResponseGeneration:
        """Generate appropriate response based on intent and qualification."""
        # Determine tone based on context
        if intent.sentiment == "negative":
            tone = ConversationTone.EMPATHETIC
        elif context.conversation_stage == ConversationStage.NEGOTIATION:
            tone = ConversationTone.DIRECT
        else:
            tone = ConversationTone.PROFESSIONAL
        
        # Check if we should ask the qualification question
        if qualification.next_question and intent.intent in (ConversationIntent.INTERESTED, ConversationIntent.CONFUSED):
            return ResponseGeneration(
                message=qualification.next_question[:160],
                tone=tone,
                intent_addressed=intent.intent,
                includes_question=True,
                includes_offer=False,
                fallback_used=False,
                reasoning="Asking qualification question",
            )
        
        return self.generate_response(context, intent.intent, tone)

    def _calculate_lead_updates(
        self,
        lead: Lead,
        intent: IntentDetectionResult,
        qualification: QualificationResult,
    ) -> Dict[str, Any]:
        """Calculate updates to apply to the lead."""
        updates = {
            "last_reply_classification": intent.intent.value.upper(),
            "last_reply_at": utcnow().isoformat(),
        }
        
        # Update pipeline stage based on intent
        if intent.intent in (ConversationIntent.INTERESTED, ConversationIntent.ASKING_PRICE):
            updates["pipeline_stage"] = "HOT"
        elif intent.intent == ConversationIntent.NOT_INTERESTED:
            updates["pipeline_stage"] = "CONTACTED"
        
        # Update followup tracking
        updates["followup_count"] = lead.followup_count + 1
        updates["last_followup_at"] = utcnow().isoformat()
        
        return updates

    def _check_alert_needed(
        self,
        intent: IntentDetectionResult,
        qualification: QualificationResult,
    ) -> Tuple[bool, Optional[str]]:
        """Check if this conversation needs an alert."""
        if intent.intent == ConversationIntent.ASKING_PRICE:
            return True, "HOT LEAD: Seller asking for price!"
        
        if intent.intent == ConversationIntent.INTERESTED and qualification.is_qualified:
            return True, "Qualified lead expressing interest"
        
        return False, None

    def _calculate_followup(
        self,
        lead: Lead,
        intent: IntentDetectionResult,
    ) -> Optional[datetime]:
        """Calculate when to schedule the next followup."""
        if intent.intent in (ConversationIntent.STOP, ConversationIntent.DECEASED, ConversationIntent.WRONG_NUMBER):
            return None  # No followup
        
        if intent.intent == ConversationIntent.NOT_INTERESTED:
            # Longer delay for not interested
            return utcnow() + timedelta(days=30)
        
        if lead.followup_count >= self.MAX_FOLLOWUPS:
            return None  # Max followups reached
        
        # Get appropriate interval
        interval_index = min(lead.followup_count, len(self.FOLLOWUP_INTERVALS) - 1)
        days = self.FOLLOWUP_INTERVALS[interval_index]
        
        return utcnow() + timedelta(days=days)


def get_conversation_engine(session: Session) -> ConversationEngine:
    """Get a ConversationEngine instance."""
    return ConversationEngine(session)


__all__ = [
    "ConversationEngine",
    "ConversationIntent",
    "ConversationTone",
    "ConversationStage",
    "ConversationContext",
    "ConversationAction",
    "IntentDetectionResult",
    "QualificationResult",
    "ResponseGeneration",
    "get_conversation_engine",
]

