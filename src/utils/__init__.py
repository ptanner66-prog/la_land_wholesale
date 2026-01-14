"""Utility helpers for normalization and deduplication."""
from .dedupe import (
    FuzzyMatchResult,
    generate_match_key,
    normalize_owner_name,
    extract_zip,
    fuzzy_name_match,
)

__all__ = [
    "FuzzyMatchResult",
    "generate_match_key",
    "normalize_owner_name",
    "extract_zip",
    "fuzzy_name_match",
]
