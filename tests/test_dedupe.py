"""Test deduplication utilities."""
from __future__ import annotations

import sys
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from utils.dedupe import normalize_owner_name, extract_zip, generate_match_key, fuzzy_name_match


def test_normalize_owner_name():
    """Test owner name normalization."""
    assert normalize_owner_name("  John   Doe  ") == "john doe"
    assert normalize_owner_name("LLC, Inc.") == "llc, inc."
    assert normalize_owner_name("") == ""
    assert normalize_owner_name("   ") == ""


def test_normalize_owner_name_whitespace():
    """Test that multiple whitespaces are collapsed."""
    assert normalize_owner_name("John    Doe") == "john doe"
    assert normalize_owner_name("  Jane   Smith   Jr  ") == "jane smith jr"


def test_extract_zip():
    """Test ZIP code extraction from addresses."""
    assert extract_zip("123 Main St, 70808") == "70808"
    assert extract_zip("123 Main St, 70808-1234") == "70808"
    assert extract_zip("No Zip Here") is None
    assert extract_zip("") is None
    assert extract_zip(None) is None


def test_extract_zip_multiple():
    """Test that first ZIP is extracted when multiple present."""
    assert extract_zip("PO Box 70808, Baton Rouge, LA 70809") == "70808"


def test_generate_match_key():
    """Test that match keys are deterministic."""
    key1 = generate_match_key("John Doe", "70808")
    key2 = generate_match_key("john doe ", "70808")
    assert key1 == key2
    
    # Different name should produce different key
    key3 = generate_match_key("Jane Doe", "70808")
    assert key1 != key3
    
    # Different ZIP should produce different key
    key4 = generate_match_key("John Doe", "70801")
    assert key1 != key4


def test_generate_match_key_empty():
    """Test match key generation with empty/None values."""
    key1 = generate_match_key("John Doe", None)
    key2 = generate_match_key("John Doe", "")
    # Both should produce same key since empty and None normalize the same
    assert key1 == key2


def test_fuzzy_name_match():
    """Test fuzzy name matching."""
    choices = ["John Doe", "Jane Smith", "Bob Johnson"]
    
    result = fuzzy_name_match("Jon Doe", choices)
    assert result is not None
    assert result.name == "John Doe"
    assert result.score > 80


def test_fuzzy_name_match_exact():
    """Test fuzzy matching with exact match."""
    choices = ["John Doe", "Jane Smith"]
    
    result = fuzzy_name_match("John Doe", choices)
    assert result is not None
    assert result.name == "John Doe"
    assert result.score == 100


def test_fuzzy_name_match_empty():
    """Test fuzzy matching with empty inputs."""
    assert fuzzy_name_match("", ["John Doe"]) is None
    assert fuzzy_name_match("John Doe", []) is None
    assert fuzzy_name_match("", []) is None
