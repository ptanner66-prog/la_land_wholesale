"""Utilities for deduplicating owner records."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Optional, Sequence

from rapidfuzz import fuzz

ZIP_REGEX = re.compile(r"(\d{5})(?:-\d{4})?")
NON_ALPHA_NUM = re.compile(r"[^a-z0-9]")
WHITESPACE = re.compile(r"\s+")


def normalize_owner_name(raw_name: str) -> str:
    """
    Return a lowercased, whitespace-collapsed version of an owner name.
    
    Args:
        raw_name: Raw name string.
        
    Returns:
        Normalized name.
    """
    if not raw_name:
        return ""
    cleaned = WHITESPACE.sub(" ", raw_name.strip())
    return cleaned.lower()


def extract_zip(value: str) -> Optional[str]:
    """
    Extract the first ZIP code found in a mailing address string.
    
    Args:
        value: Address string.
        
    Returns:
        5-digit ZIP code or None.
    """
    if not value:
        return None
    match = ZIP_REGEX.search(value)
    return match.group(1) if match else None


def generate_match_key(name: str, zip_code: Optional[str]) -> str:
    """
    Generate a deterministic hash for a party using normalized inputs.
    
    Args:
        name: Owner name.
        zip_code: ZIP code.
        
    Returns:
        SHA256 hash string.
    """
    norm_name = normalize_owner_name(name)
    norm_zip = zip_code or ""
    payload = f"{norm_name}|{norm_zip}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass
class FuzzyMatchResult:
    name: str
    score: float


def fuzzy_name_match(candidate: str, choices: Sequence[str]) -> Optional[FuzzyMatchResult]:
    """
    Return the best fuzzy match score for the candidate among choices (0-100).
    
    Args:
        candidate: Name to match.
        choices: List of potential matches.
        
    Returns:
        FuzzyMatchResult or None.
    """
    if not candidate or not choices:
        return None
        
    best_match = None
    best_score = 0.0
    
    for choice in choices:
        score = fuzz.ratio(candidate.lower(), choice.lower())
        if score > best_score:
            best_score = score
            best_match = choice
            
    if best_match:
        return FuzzyMatchResult(name=best_match, score=best_score)
    return None
