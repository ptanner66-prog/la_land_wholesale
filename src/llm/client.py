"""Centralized LLM client supporting Anthropic (Claude) and OpenAI with timeout, retry, and error handling."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log,
)

from core.config import get_settings
from core.exceptions import LLMAPIError, LLMRateLimitError, LLMTimeoutError
from core.logging_config import get_logger

LOGGER = get_logger(__name__)
SETTINGS = get_settings()

# Import Anthropic with graceful fallback
try:
    import anthropic
    from anthropic import Anthropic, APIError as AnthropicAPIError, RateLimitError as AnthropicRateLimitError
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    Anthropic = None  # type: ignore
    AnthropicAPIError = Exception  # type: ignore
    AnthropicRateLimitError = Exception  # type: ignore

# Import OpenAI with graceful fallback
try:
    from openai import OpenAI, APIError, RateLimitError, APITimeoutError
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    OpenAI = None  # type: ignore
    APIError = Exception  # type: ignore
    RateLimitError = Exception  # type: ignore
    APITimeoutError = Exception  # type: ignore


def _create_anthropic_client() -> Optional["Anthropic"]:
    """Create a new Anthropic client instance."""
    if not ANTHROPIC_AVAILABLE:
        return None

    if not SETTINGS.anthropic_api_key:
        return None

    return Anthropic(
        api_key=SETTINGS.anthropic_api_key,
        timeout=SETTINGS.anthropic_timeout_seconds,
        max_retries=0,  # We handle retries via tenacity
    )


def _create_openai_client() -> Optional["OpenAI"]:
    """Create a new OpenAI client instance with configured timeout."""
    if not OPENAI_AVAILABLE:
        return None

    if not SETTINGS.openai_api_key:
        return None

    return OpenAI(
        api_key=SETTINGS.openai_api_key,
        timeout=SETTINGS.openai_timeout_seconds,
        max_retries=0,
    )


class LLMClient:
    """Unified LLM client supporting OpenAI (primary) and Anthropic (fallback) with retry logic and error handling."""

    def __init__(self) -> None:
        """Initialize the LLM client, preferring OpenAI over Anthropic."""
        self.anthropic_client = _create_anthropic_client()
        self.openai_client = _create_openai_client()
        
        # Determine which provider to use - OpenAI is PRIMARY
        if self.openai_client:
            self.provider = "openai"
            self.model = SETTINGS.openai_model
            self.temperature = SETTINGS.openai_temperature
            LOGGER.info(f"LLM client initialized with OpenAI as primary (model: {self.model})")
        elif self.anthropic_client:
            self.provider = "anthropic"
            self.model = SETTINGS.anthropic_model
            self.temperature = SETTINGS.anthropic_temperature
            LOGGER.info(f"LLM client initialized with Anthropic as fallback (model: {self.model})")
        else:
            self.provider = None
            self.model = None
            self.temperature = 0.3
            LOGGER.warning("No LLM provider configured - LLM features unavailable")

    def is_available(self) -> bool:
        """Check if any LLM provider is available."""
        return self.provider is not None

    @retry(
        retry=retry_if_exception_type((ConnectionError, TimeoutError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        before_sleep=before_sleep_log(LOGGER, logging.WARNING),
        reraise=True,
    )
    def generate_completion(
        self,
        prompt: str,
        system_prompt: str = "You are a helpful real estate assistant specializing in land wholesaling.",
        temperature: Optional[float] = None,
        max_tokens: int = 500,
        timeout: Optional[int] = None,
    ) -> str:
        """
        Generate a completion from the LLM.

        Args:
            prompt: The user prompt.
            system_prompt: The system prompt.
            temperature: Optional override for temperature.
            max_tokens: Maximum tokens to generate.
            timeout: Optional timeout override.

        Returns:
            Generated text content.

        Raises:
            LLMAPIError: If the API call fails after retries.
            LLMRateLimitError: If rate limit is exceeded.
            LLMTimeoutError: If the request times out.
        """
        if not self.is_available():
            LOGGER.warning("LLM client not available, returning empty string")
            return ""

        temp = temperature if temperature is not None else self.temperature

        # Try primary provider (OpenAI) with fallback to Anthropic
        if self.provider == "openai":
            try:
                return self._generate_openai(prompt, system_prompt, temp, max_tokens)
            except (LLMAPIError, LLMRateLimitError, LLMTimeoutError) as e:
                LOGGER.warning(f"OpenAI failed ({e}), attempting Anthropic fallback")
                if self.anthropic_client:
                    try:
                        return self._generate_anthropic(prompt, system_prompt, temp, max_tokens)
                    except Exception as fallback_error:
                        LOGGER.error(f"Anthropic fallback also failed: {fallback_error}")
                        raise
                else:
                    LOGGER.error("No fallback available, Anthropic not configured")
                    raise
        elif self.provider == "anthropic":
            return self._generate_anthropic(prompt, system_prompt, temp, max_tokens)
        else:
            LOGGER.warning("No LLM provider available")
            return ""

    def _generate_anthropic(
        self,
        prompt: str,
        system_prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> str:
        """Generate completion using Anthropic Claude."""
        try:
            message = self.anthropic_client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=system_prompt,
                messages=[
                    {"role": "user", "content": prompt}
                ],
                temperature=temperature,
            )
            
            content = message.content[0].text if message.content else ""
            return content.strip()

        except AnthropicRateLimitError as exc:
            LOGGER.error("Anthropic rate limit exceeded: %s", exc)
            raise LLMRateLimitError(f"Rate limit exceeded: {exc}") from exc
        except AnthropicAPIError as exc:
            LOGGER.error("Anthropic API error: %s", exc)
            raise LLMAPIError(f"API error: {exc}") from exc
        except Exception as exc:
            LOGGER.exception("Unexpected error during Anthropic generation")
            raise LLMAPIError(f"Unexpected error: {exc}") from exc

    def _generate_openai(
        self,
        prompt: str,
        system_prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> str:
        """Generate completion using OpenAI."""
        try:
            response = self.openai_client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            
            content = response.choices[0].message.content
            return content.strip() if content else ""

        except RateLimitError as exc:
            LOGGER.error("OpenAI rate limit exceeded: %s", exc)
            raise LLMRateLimitError(f"Rate limit exceeded: {exc}") from exc
        except APITimeoutError as exc:
            LOGGER.error("OpenAI request timed out: %s", exc)
            raise LLMTimeoutError(f"Request timed out: {exc}") from exc
        except APIError as exc:
            LOGGER.error("OpenAI API error: %s", exc)
            raise LLMAPIError(f"API error: {exc}") from exc
        except Exception as exc:
            LOGGER.exception("Unexpected error during OpenAI generation")
            raise LLMAPIError(f"Unexpected error: {exc}") from exc

    def classify_intent(self, message: str) -> Dict[str, Any]:
        """
        Classify the intent of an incoming message from a seller.
        
        Returns dict with intent classification and confidence.
        """
        prompt = f"""Analyze this SMS message from a property seller and classify their intent.

Message: "{message}"

Respond in this exact JSON format:
{{
    "intent": "one of: INTERESTED, NOT_INTERESTED, ASKING_PRICE, CONFUSED, STOP, SPAM",
    "confidence": 0.0-1.0,
    "sentiment": "positive, neutral, or negative",
    "action_needed": "description of what action to take"
}}"""

        try:
            result = self.generate_completion(
                prompt=prompt,
                max_tokens=150,
                temperature=0.1,
            )
            
            # Parse JSON from response
            import json
            # Find JSON in response
            start = result.find('{')
            end = result.rfind('}') + 1
            if start >= 0 and end > start:
                return json.loads(result[start:end])
            
            return {
                "intent": "CONFUSED",
                "confidence": 0.5,
                "sentiment": "neutral",
                "action_needed": "Manual review needed"
            }
        except Exception as e:
            LOGGER.error(f"Intent classification failed: {e}")
            return {
                "intent": "CONFUSED",
                "confidence": 0.0,
                "sentiment": "neutral",
                "action_needed": "Classification failed - manual review"
            }

    def generate_response(
        self,
        context: str,
        seller_message: str,
        lead_info: Dict[str, Any],
        tone: str = "professional",
    ) -> str:
        """
        Generate a contextual response to a seller message.
        
        Args:
            context: Conversation context (intro, followup, negotiation, etc.)
            seller_message: The seller's message to respond to.
            lead_info: Dictionary with lead/property details.
            tone: Response tone (professional, friendly, direct).
            
        Returns:
            Generated response message.
        """
        property_desc = f"{lead_info.get('acreage', 'N/A')} acres in {lead_info.get('county', 'the area')}"
        
        prompt = f"""You are a land wholesaler having an SMS conversation with a property seller.

Context: {context}
Property: {property_desc}
Seller's message: "{seller_message}"
Desired tone: {tone}

Generate a brief, natural SMS response (under 160 characters) that:
- Addresses their message directly
- Maintains rapport
- Moves toward a potential deal
- Sounds human, not like a bot
- Does NOT include specific dollar amounts unless asked

Response:"""

        return self.generate_completion(
            prompt=prompt,
            max_tokens=100,
            temperature=0.7,
        )


# Global instance
_llm_client: Optional[LLMClient] = None


def get_llm_client() -> LLMClient:
    """Get or create the global LLM client instance."""
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client


def reset_llm_client() -> None:
    """Reset the global LLM client (useful for testing)."""
    global _llm_client
    _llm_client = None


__all__ = [
    "LLMClient",
    "get_llm_client",
    "reset_llm_client",
]
