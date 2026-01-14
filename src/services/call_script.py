"""
Call Script Generator

Generates call scripts with live property/offer injection.
Script updates when offer params change.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING

from core.address_utils import compute_display_location, compute_mailing_address
from services.offer_helper import compute_offer_range, OfferRange

if TYPE_CHECKING:
    from core.models import Lead


@dataclass
class CallScript:
    """
    Generated call script with all injected values.
    """
    # Lead info
    lead_id: int
    owner_name: str
    
    # Property info (injected)
    property_location: str
    acreage: Optional[float]
    parish: str
    
    # Offer info (injected)
    offer_range: OfferRange
    
    # Script sections
    opening: str
    discovery: str
    price_discussion: str
    objection_handlers: list
    closing: str
    
    def to_dict(self) -> dict:
        return {
            "lead_id": self.lead_id,
            "owner_name": self.owner_name,
            "property_location": self.property_location,
            "acreage": self.acreage,
            "parish": self.parish,
            "offer_range": self.offer_range.to_dict(),
            "opening": self.opening,
            "discovery": self.discovery,
            "price_discussion": self.price_discussion,
            "objection_handlers": self.objection_handlers,
            "closing": self.closing,
        }


def generate_call_script(
    lead: "Lead",
    discount_low: float = 0.55,
    discount_high: float = 0.70,
) -> CallScript:
    """
    Generate a call script for a lead.
    
    All values are injected from lead data:
    - Property location (from address_utils)
    - Acreage
    - Offer range (from offer_helper)
    
    Script updates live when params change.
    """
    # Get owner info
    owner = lead.owner
    party = owner.party if owner else None
    owner_name = party.display_name if party else "Property Owner"
    first_name = owner_name.split()[0] if owner_name else "there"
    
    # Get property location
    location = compute_display_location(lead)
    property_location = location.location_descriptor
    parish = location.parish
    
    # Get parcel info
    parcel = lead.parcel
    acreage = float(parcel.lot_size_acres) if parcel and parcel.lot_size_acres else None
    acreage_text = f"{acreage:.2f} acres" if acreage else "your property"
    
    # Compute offer range
    offer_range = compute_offer_range(lead, discount_low, discount_high)
    
    # Build script sections
    opening = f"""Hi, is this {first_name}?

Great! My name is [YOUR NAME], and I'm a local land buyer here in Louisiana. 

I was looking at some properties in {parish} Parish and came across your {acreage_text} on {location.short_address}.

I'm reaching out because I buy land for cash, and I wanted to see if you'd ever consider selling?"""

    discovery = f"""Perfect! Before I can give you a number, I just need to ask a few quick questions:

1. How long have you owned this property?
2. Do you know roughly what it's worth or what you paid for it?
3. Is there anything on the land - structures, utilities, easements?
4. Any back taxes or liens you're aware of?
5. What would you do with the money if you sold?

[LISTEN - their motivation matters more than the answers]"""

    if offer_range.low_offer > 0:
        price_discussion = f"""Based on what I'm seeing, I could offer somewhere in the range of {offer_range.range_display}.

Here's how I got there:
{chr(10).join('• ' + j.description for j in offer_range.justifications)}

The exact number depends on a few things I'd need to verify, but that's the ballpark.

How does that sound to you?"""
    else:
        price_discussion = """I'd need to do a bit more research to give you a solid number, but I can tell you I typically pay 50-70% of assessed value for land like this.

Would you be open to me running the numbers and getting back to you with a specific offer?"""

    objection_handlers = [
        {
            "objection": "That's too low",
            "response": f"I understand - what number did you have in mind? [LISTEN] I'm at {offer_range.range_display} because [refer to justifications]. Is there something I'm missing about the property that would make it worth more?"
        },
        {
            "objection": "I need to think about it",
            "response": "Absolutely, take your time. When would be a good time for me to follow up? [GET SPECIFIC DATE/TIME] And just so I know - is it the price, or is there something else you're considering?"
        },
        {
            "objection": "I'm not sure I want to sell",
            "response": "No pressure at all. Out of curiosity, what would have to be true for you to consider it? [LISTEN FOR MOTIVATION]"
        },
        {
            "objection": "I need to talk to my spouse/family",
            "response": "Of course! Would it help if I sent over some information they could look at? And when do you think you'll have a chance to discuss it?"
        },
    ]

    closing = f"""Great! Here's what happens next:

1. I'll send you a simple one-page offer in writing
2. You review it with whoever you need to
3. If it works, we can close in as little as 2 weeks
4. I handle all the paperwork and closing costs

What's the best email to send the offer to?

[IF NO EMAIL] No problem - I can mail it to you. What's the best address?

Thanks {first_name}! I'll get that over to you today. Talk soon!"""

    return CallScript(
        lead_id=lead.id,
        owner_name=owner_name,
        property_location=property_location,
        acreage=acreage,
        parish=parish,
        offer_range=offer_range,
        opening=opening,
        discovery=discovery,
        price_discussion=price_discussion,
        objection_handlers=objection_handlers,
        closing=closing,
    )


__all__ = [
    "CallScript",
    "generate_call_script",
]
