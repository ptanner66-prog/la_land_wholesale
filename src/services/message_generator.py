"""Message template generation service using LLM."""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from core.config import get_settings
from core.logging_config import get_logger
from core.models import Lead
from llm.client import get_llm_client

LOGGER = get_logger(__name__)
SETTINGS = get_settings()


@dataclass
class MessageVariant:
    """A generated message variant."""
    
    style: str  # casual, neutral, direct
    message: str
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "style": self.style,
            "message": self.message,
        }


INTRO_PROMPT = """Generate 3 SMS message variants for a land wholesaler reaching out to a property owner for the first time.

Property details:
- Owner name: {owner_name}
- Property address: {address}
- Property size: {lot_size} acres
- Parish/County: {parish}

Generate 3 variants:
1. CASUAL - Friendly and conversational
2. NEUTRAL - Professional but warm
3. DIRECT - Straightforward and to the point

Each message should:
- Be under 160 characters
- Mention their property
- Ask if they'd consider selling
- NOT include a specific price
- NOT sound like spam

Format your response as:
CASUAL: [message]
NEUTRAL: [message]
DIRECT: [message]"""

FOLLOWUP_PROMPT = """Generate 3 follow-up SMS variants for a land wholesaler. This is a second contact attempt.

Property details:
- Owner name: {owner_name}
- Property address: {address}
- Days since first contact: {days_since_first}

Generate 3 variants:
1. CASUAL - Friendly check-in
2. NEUTRAL - Professional follow-up
3. DIRECT - Clear and concise

Each message should:
- Be under 160 characters
- Reference previous outreach
- Restate interest in property
- Be respectful of their time

Format your response as:
CASUAL: [message]
NEUTRAL: [message]
DIRECT: [message]"""

FINAL_PROMPT = """Generate 3 final SMS message variants for a land wholesaler. This is the last contact attempt.

Property details:
- Owner name: {owner_name}
- Property address: {address}

Generate 3 variants:
1. CASUAL - Friendly final check
2. NEUTRAL - Professional closing
3. DIRECT - Last chance tone

Each message should:
- Be under 160 characters
- Indicate this is a final contact
- Leave door open for future
- Be respectful

Format your response as:
CASUAL: [message]
NEUTRAL: [message]
DIRECT: [message]"""


class MessageGeneratorService:
    """Service for generating outreach message templates."""

    def __init__(self):
        """Initialize the message generator."""
        self.llm_client = get_llm_client()

    def generate_messages(
        self,
        lead: Lead,
        context: str,  # intro, followup, final
        days_since_first: int = 0,
    ) -> List[MessageVariant]:
        """
        Generate message variants for a lead.
        
        Args:
            lead: The lead to generate messages for.
            context: Message context (intro, followup, final).
            days_since_first: Days since first contact (for followups).
            
        Returns:
            List of MessageVariant objects.
        """
        # Extract lead details
        owner_name = "there"
        if lead.owner and lead.owner.party:
            owner_name = lead.owner.party.display_name.split()[0]  # First name
        
        address = "your property"
        if lead.parcel:
            address = lead.parcel.situs_address or f"property in {lead.parcel.parish}"
        
        parish = lead.parcel.parish if lead.parcel else "the area"
        lot_size = lead.parcel.lot_size_acres if lead.parcel else 1.0
        
        # Select prompt template
        if context == "intro":
            prompt = INTRO_PROMPT.format(
                owner_name=owner_name,
                address=address,
                lot_size=f"{lot_size:.2f}" if lot_size else "N/A",
                parish=parish,
            )
        elif context == "followup":
            prompt = FOLLOWUP_PROMPT.format(
                owner_name=owner_name,
                address=address,
                days_since_first=days_since_first or 3,
            )
        else:  # final
            prompt = FINAL_PROMPT.format(
                owner_name=owner_name,
                address=address,
            )
        
        try:
            result = self.llm_client.generate_completion(
                prompt=prompt,
                max_tokens=300,
                temperature=0.7,
            )
            
            return self._parse_response(result)
            
        except Exception as e:
            LOGGER.error(f"LLM message generation failed: {e}")
            return self._get_fallback_messages(context, owner_name, address)

    def _parse_response(self, response: str) -> List[MessageVariant]:
        """Parse LLM response into MessageVariants."""
        variants = []
        
        for style in ["CASUAL", "NEUTRAL", "DIRECT"]:
            try:
                if f"{style}:" in response:
                    # Extract message after style label
                    start = response.index(f"{style}:") + len(f"{style}:")
                    end = len(response)
                    
                    # Find next style label
                    for next_style in ["CASUAL", "NEUTRAL", "DIRECT"]:
                        if next_style != style and f"{next_style}:" in response[start:]:
                            potential_end = response.index(f"{next_style}:", start)
                            if potential_end > start:
                                end = potential_end
                                break
                    
                    message = response[start:end].strip()
                    # Clean up message
                    message = message.replace("\n", " ").strip()
                    if message:
                        variants.append(MessageVariant(
                            style=style.lower(),
                            message=message[:160],  # Ensure SMS length
                        ))
            except (ValueError, IndexError):
                continue
        
        return variants

    def _get_fallback_messages(
        self,
        context: str,
        owner_name: str,
        address: str,
    ) -> List[MessageVariant]:
        """Get fallback messages when LLM fails."""
        if context == "intro":
            return [
                MessageVariant(
                    style="casual",
                    message=f"Hey {owner_name}! I noticed your land on {address}. Would you ever consider selling? No pressure - just curious!",
                ),
                MessageVariant(
                    style="neutral",
                    message=f"Hi {owner_name}, I'm interested in your property at {address}. Would you be open to discussing a sale?",
                ),
                MessageVariant(
                    style="direct",
                    message=f"{owner_name} - I buy land and I'm interested in {address}. Are you open to selling? I pay cash and close fast.",
                ),
            ]
        elif context == "followup":
            return [
                MessageVariant(
                    style="casual",
                    message=f"Hey {owner_name}! Just checking in about {address}. Still interested if you'd like to chat!",
                ),
                MessageVariant(
                    style="neutral",
                    message=f"Hi {owner_name}, following up on my message about {address}. Happy to answer any questions.",
                ),
                MessageVariant(
                    style="direct",
                    message=f"{owner_name} - Following up on {address}. My offer still stands. Let me know if interested.",
                ),
            ]
        else:  # final
            return [
                MessageVariant(
                    style="casual",
                    message=f"Hi {owner_name}! Last check-in about {address}. Feel free to reach out anytime if things change!",
                ),
                MessageVariant(
                    style="neutral",
                    message=f"{owner_name}, final follow-up on {address}. I remain interested - contact me anytime.",
                ),
                MessageVariant(
                    style="direct",
                    message=f"{owner_name} - Last message about {address}. Here if you want to sell. Thanks!",
                ),
            ]


# Module-level singleton
_service: Optional[MessageGeneratorService] = None


def get_message_generator() -> MessageGeneratorService:
    """Get the global MessageGeneratorService instance."""
    global _service
    if _service is None:
        _service = MessageGeneratorService()
    return _service


__all__ = [
    "MessageGeneratorService",
    "MessageVariant",
    "get_message_generator",
]

