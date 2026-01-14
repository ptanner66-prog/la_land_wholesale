"""Normalization utilities for ingestion pipelines."""
from __future__ import annotations

import re
from typing import Optional


class ParishKeyNormalizer:
    """Utility for normalizing parish parcel keys."""

    NON_ALPHANUM = re.compile(r"[^0-9a-zA-Z]")

    @classmethod
    def normalize(cls, raw_key: Optional[str], pad_to: int = 12) -> str:
        """
        Normalize a parcel key by stripping non-alphanumeric characters.

        Args:
            raw_key: Raw parcel key string.
            pad_to: Target length for padding (default 12).

        Returns:
            Normalized, uppercased, and padded parcel key.
        """
        if not raw_key:
            return "0" * pad_to
            
        cleaned = cls.NON_ALPHANUM.sub("", str(raw_key)).upper()
        
        if not cleaned:
            return "0" * pad_to
            
        # Pad with zeros to the right (standard for some LA parishes, check specific requirements if needed)
        # For EBR, it seems they use a 12-char string often.
        return cleaned.ljust(pad_to, "0")[:pad_to]
