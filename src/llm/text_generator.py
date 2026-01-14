"""Generate SMS and email content using LLM."""
from __future__ import annotations

from typing import Optional, Dict, Any

from core.logging_config import get_logger
from .client import get_llm_client

LOGGER = get_logger(__name__)

SYSTEM_PROMPT_SMS = """
You are a professional real estate assistant for a land investment company.
Your goal is to write short, polite, and direct SMS messages to property owners.
Keep messages under 160 characters if possible.
Do not use emojis unless specifically requested.
Be respectful and professional.
"""


class TextGenerator:
    """Service for generating text content via LLM."""

    def __init__(self) -> None:
        self.client = get_llm_client()

    def generate_sms(
        self,
        prompt_template: str,
        context: Dict[str, Any],
    ) -> str:
        """
        Generate an SMS message based on a template and context.

        Args:
            prompt_template: Name of the template (e.g., 'initial_outreach').
            context: Dictionary of context variables.

        Returns:
            Generated SMS content.
        """
        # Simple template selection for now
        if prompt_template == "initial_outreach":
            owner_name = context.get("owner_name", "Property Owner")
            address = context.get("property_address", "your property")
            offer = context.get("offer_amount", "")

            prompt = (
                f"Write a first-contact SMS to {owner_name} regarding {address}. "
                f"We are interested in buying it. "
            )
            if offer:
                prompt += f"We can offer around {offer}. "

            prompt += (
                "Ask if they are interested in selling. "
                "Keep it under 160 chars. No spammy language."
            )
        else:
            # Fallback
            prompt = f"Write a real estate SMS with context: {context}"

        try:
            response = self.client.generate_completion(
                prompt=prompt,
                system_prompt=SYSTEM_PROMPT_SMS,
                max_tokens=100,
            )
            return response.strip()
        except Exception as e:
            LOGGER.error(f"Failed to generate SMS: {e}")
            # Fallback static message
            owner = context.get("owner_name", "there")
            address = context.get("property_address", "your property")
            return f"Hi {owner}, I'm interested in buying {address}. Are you open to selling? Reply STOP to opt out."


# Global instance
_text_generator: Optional[TextGenerator] = None


def get_text_generator() -> TextGenerator:
    """Get or create the global TextGenerator instance."""
    global _text_generator
    if _text_generator is None:
        _text_generator = TextGenerator()
    return _text_generator


def generate_first_touch_sms(
    owner_name: str,
    parish: str,
    lot_size_acres: Optional[float] = None,
    offer_price: Optional[float] = None,
) -> str:
    """
    Generate a first-touch SMS message for a property owner.

    Args:
        owner_name: Name of the property owner.
        parish: Parish where property is located.
        lot_size_acres: Lot size in acres (optional).
        offer_price: Offer price in dollars (optional).

    Returns:
        Generated SMS message body (< 160 chars).
    """
    generator = get_text_generator()

    # Build address string
    address_parts = []
    if lot_size_acres:
        address_parts.append(f"{lot_size_acres:.1f}-acre lot")
    address_parts.append(f"in {parish}")
    property_desc = " ".join(address_parts) if address_parts else "your property"

    context = {
        "owner_name": owner_name or "Property Owner",
        "property_address": property_desc,
    }

    if offer_price:
        context["offer_amount"] = f"${offer_price:,.0f}"

    try:
        message = generator.generate_sms("initial_outreach", context)
        # Ensure message fits SMS limit
        if len(message) > 160:
            message = message[:157] + "..."
        return message
    except Exception as e:
        LOGGER.error(f"LLM generation failed, using fallback: {e}")
        # Fallback message
        name = owner_name.split()[0] if owner_name else "there"
        return f"Hi {name}, interested in buying your {parish} property. Open to selling? Reply STOP to opt out."


__all__ = [
    "TextGenerator",
    "get_text_generator",
    "generate_first_touch_sms",
]
