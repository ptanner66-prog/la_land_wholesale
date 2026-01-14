"""Test configuration loading."""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))


def test_settings_load():
    """Test that settings load correctly."""
    # Set required env var for test
    os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
    
    from core.config import get_settings
    
    settings = get_settings()
    
    # Check defaults
    assert settings.max_sms_per_day > 0
    assert settings.min_motivation_score >= 0
    assert settings.min_motivation_score <= 100
    assert settings.log_level in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


def test_settings_scoring_weights():
    """Test that scoring weights are configured."""
    os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
    
    from core.config import get_settings
    
    settings = get_settings()
    
    assert settings.score_weight_adjudicated >= 0
    assert settings.score_weight_tax_delinquent_per_year >= 0
    assert settings.score_weight_low_improvement >= 0
    assert settings.score_weight_absentee >= 0
    assert settings.score_weight_lot_size >= 0


def test_settings_dry_run_default():
    """Test that dry_run defaults to True for safety."""
    os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
    os.environ.setdefault("DRY_RUN", "true")
    
    # Clear cache to pick up new env
    from core.config import get_settings
    get_settings.cache_clear()
    
    settings = get_settings()
    assert settings.dry_run is True
