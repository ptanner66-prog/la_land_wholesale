"""Market configuration service."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from core.models import MarketCode


@dataclass
class MarketConfig:
    """Configuration for a specific market."""
    
    code: str
    name: str
    default_parish: str
    
    # Scoring weights (0-100)
    score_weight_adjudicated: int = 40
    score_weight_tax_delinquent_per_year: int = 5
    score_weight_tax_delinquent_max: int = 20
    score_weight_low_improvement: int = 20
    score_weight_absentee: int = 10
    score_weight_lot_size: int = 10
    
    # Outreach settings
    outreach_window_start: int = 9  # 9 AM
    outreach_window_end: int = 18   # 6 PM
    followup_day_1: int = 3  # Day 3 for first followup
    followup_day_2: int = 7  # Day 7 for second followup
    max_followups: int = 2
    
    # Thresholds
    min_motivation_score: int = 65
    hot_score_threshold: int = 75
    
    # Alert settings
    alerts_enabled: bool = True


# Market configurations
MARKET_CONFIGS: Dict[str, MarketConfig] = {
    MarketCode.LA.value: MarketConfig(
        code="LA",
        name="Louisiana",
        default_parish="East Baton Rouge",
        min_motivation_score=65,
        hot_score_threshold=75,
    ),
    MarketCode.TX.value: MarketConfig(
        code="TX",
        name="Texas",
        default_parish="Harris County",
        min_motivation_score=60,
        hot_score_threshold=70,
    ),
    MarketCode.MS.value: MarketConfig(
        code="MS",
        name="Mississippi",
        default_parish="Hinds County",
        min_motivation_score=65,
        hot_score_threshold=75,
    ),
    MarketCode.AR.value: MarketConfig(
        code="AR",
        name="Arkansas",
        default_parish="Pulaski County",
        min_motivation_score=65,
        hot_score_threshold=75,
    ),
    MarketCode.AL.value: MarketConfig(
        code="AL",
        name="Alabama",
        default_parish="Jefferson County",
        min_motivation_score=65,
        hot_score_threshold=75,
    ),
}


class MarketService:
    """Service for market configuration management."""

    @staticmethod
    def get_all_markets() -> List[MarketConfig]:
        """Get all market configurations."""
        return list(MARKET_CONFIGS.values())

    @staticmethod
    def get_market(market_code: str) -> Optional[MarketConfig]:
        """Get configuration for a specific market."""
        return MARKET_CONFIGS.get(market_code.upper())

    @staticmethod
    def get_market_codes() -> List[str]:
        """Get list of all market codes."""
        return list(MARKET_CONFIGS.keys())

    @staticmethod
    def is_valid_market(market_code: str) -> bool:
        """Check if a market code is valid."""
        return market_code.upper() in MARKET_CONFIGS

    @staticmethod
    def get_default_market() -> MarketConfig:
        """Get the default market (Louisiana)."""
        return MARKET_CONFIGS[MarketCode.LA.value]

    @staticmethod
    def get_scoring_weights(market_code: str) -> Dict[str, int]:
        """Get scoring weights for a market."""
        config = MarketService.get_market(market_code)
        if not config:
            config = MarketService.get_default_market()
        
        return {
            "adjudicated": config.score_weight_adjudicated,
            "tax_delinquent_per_year": config.score_weight_tax_delinquent_per_year,
            "tax_delinquent_max": config.score_weight_tax_delinquent_max,
            "low_improvement": config.score_weight_low_improvement,
            "absentee": config.score_weight_absentee,
            "lot_size": config.score_weight_lot_size,
        }

    @staticmethod
    def get_followup_schedule(market_code: str) -> Dict[str, int]:
        """Get followup schedule for a market."""
        config = MarketService.get_market(market_code)
        if not config:
            config = MarketService.get_default_market()
        
        return {
            "day_1": config.followup_day_1,
            "day_2": config.followup_day_2,
            "max_followups": config.max_followups,
        }


# Module-level singleton
_service: Optional[MarketService] = None


def get_market_service() -> MarketService:
    """Get the global MarketService instance."""
    global _service
    if _service is None:
        _service = MarketService()
    return _service


__all__ = [
    "MarketConfig",
    "MarketService",
    "get_market_service",
    "MARKET_CONFIGS",
]

