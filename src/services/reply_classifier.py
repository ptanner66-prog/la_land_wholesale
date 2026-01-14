"""AI-powered reply classification service with timeout and circuit breaker."""
from __future__ import annotations

from typing import Optional, Tuple

from core.config import get_settings
from core.logging_config import get_logger
from core.models import ReplyClassification
from core.utils import CircuitBreaker

LOGGER = get_logger(__name__)
SETTINGS = get_settings()

# Circuit breaker for LLM calls
_llm_circuit = CircuitBreaker(
    name="reply_classifier_llm",
    failure_threshold=3,
    recovery_timeout=120,  # 2 minutes
)

CLASSIFICATION_PROMPT = """You are an AI assistant that classifies SMS replies from property sellers.

Classify the following reply into ONE of these categories:
- INTERESTED: The seller shows genuine interest in selling their property
- NOT_INTERESTED: The seller explicitly says no or shows no interest
- SEND_OFFER: The seller asks for a price, offer, or more details about the deal
- CONFUSED: The seller is confused, asks unrelated questions, or doesn't understand
- DEAD: Wrong number, deceased owner, profanity, threats, or spam response

Reply ONLY with the classification category name (e.g., "INTERESTED").

Seller's reply:
"{reply_text}"

Classification:"""


class ReplyClassifierService:
    """Service for classifying seller replies using AI with safeguards."""

    # LLM call timeout in seconds
    LLM_TIMEOUT = 30

    def __init__(self):
        """Initialize the classifier service."""
        self.circuit_breaker = _llm_circuit

    def classify_reply(self, reply_text: str) -> ReplyClassification:
        """
        Classify a seller's reply text.
        
        Uses keyword-based pre-classification for common cases,
        falls back to LLM for ambiguous cases.
        
        Args:
            reply_text: The text of the seller's reply.
            
        Returns:
            ReplyClassification enum value.
        """
        if not reply_text or not reply_text.strip():
            return ReplyClassification.CONFUSED

        # Quick keyword-based pre-classification
        lower_text = reply_text.lower().strip()
        
        # Dead/Stop keywords - CRITICAL for TCPA compliance
        if any(word in lower_text for word in ['stop', 'unsubscribe', 'remove', 'opt out', 'opt-out']):
            LOGGER.info(f"Classified as DEAD (stop word): {reply_text[:50]}...")
            return ReplyClassification.DEAD
        
        # Profanity/spam
        if any(word in lower_text for word in ['fuck', 'spam', 'scam', 'lawsuit']):
            return ReplyClassification.DEAD
        
        # Wrong number / deceased
        if any(phrase in lower_text for phrase in ['wrong number', 'deceased', 'passed away', 'died']):
            return ReplyClassification.DEAD
        
        # Clear not interested
        if any(phrase in lower_text for phrase in ['not interested', 'no thanks', "don't contact", 'do not contact']):
            return ReplyClassification.NOT_INTERESTED
        
        # Clear interested indicators
        if any(phrase in lower_text for phrase in [
            'how much', "what's your offer", 'what are you offering', 
            'send me an offer', 'make an offer', 'interested in selling',
            'what can you offer', 'price'
        ]):
            return ReplyClassification.SEND_OFFER
        
        # Positive responses
        if any(phrase in lower_text for phrase in ['yes', 'sure', 'tell me more', 'interested']):
            return ReplyClassification.INTERESTED
        
        # Use LLM for ambiguous cases
        return self._classify_with_llm(reply_text)

    def _classify_with_llm(self, reply_text: str) -> ReplyClassification:
        """
        Use LLM to classify ambiguous replies.
        
        Has timeout and circuit breaker protection.
        """
        if not self.circuit_breaker.can_execute():
            LOGGER.warning("LLM circuit breaker is open, defaulting to CONFUSED")
            return ReplyClassification.CONFUSED
        
        try:
            from llm.client import get_llm_client
            
            prompt = CLASSIFICATION_PROMPT.format(reply_text=reply_text[:500])
            
            llm_client = get_llm_client()
            result = llm_client.generate_completion(
                prompt=prompt,
                max_tokens=20,
                temperature=0.1,
                timeout=self.LLM_TIMEOUT,
            )
            
            self.circuit_breaker.record_success()
            
            classification_text = result.strip().upper()
            
            # Map to enum
            for classification in ReplyClassification:
                if classification.value in classification_text:
                    LOGGER.info(f"LLM classified reply as {classification.value}: {reply_text[:50]}...")
                    return classification
            
            # Default to CONFUSED if no match
            LOGGER.warning(f"Could not map LLM response '{result}' to classification")
            return ReplyClassification.CONFUSED
            
        except TimeoutError:
            self.circuit_breaker.record_failure()
            LOGGER.error("LLM classification timed out")
            return ReplyClassification.CONFUSED
        except Exception as e:
            self.circuit_breaker.record_failure()
            LOGGER.error(f"LLM classification failed: {e}")
            return ReplyClassification.CONFUSED

    def get_pipeline_action(self, classification: ReplyClassification) -> Tuple[Optional[str], Optional[str]]:
        """
        Get the pipeline action based on classification.
        
        Args:
            classification: The reply classification.
            
        Returns:
            Tuple of (new_stage, reason).
        """
        if classification in (ReplyClassification.INTERESTED, ReplyClassification.SEND_OFFER):
            return ("HOT", f"Reply classified as {classification.value}")
        elif classification in (ReplyClassification.NOT_INTERESTED, ReplyClassification.DEAD):
            return ("CONTACTED", f"Reply classified as {classification.value}")
        else:
            return (None, None)  # No stage change for CONFUSED


# Module-level singleton
_service: Optional[ReplyClassifierService] = None


def get_reply_classifier() -> ReplyClassifierService:
    """Get the global ReplyClassifierService instance."""
    global _service
    if _service is None:
        _service = ReplyClassifierService()
    return _service


__all__ = [
    "ReplyClassifierService",
    "get_reply_classifier",
]
