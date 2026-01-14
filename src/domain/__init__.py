"""Domain layer for la_land_wholesale business logic.

This module provides a clean separation between business logic and
infrastructure (CLI, API, etc.). All core operations should go through
the domain services.
"""
from __future__ import annotations

from .leads import LeadService, LeadSummary, LeadDetail
from .outreach import OutreachService, OutreachResult, BatchOutreachResult
from .ingestion import IngestionService, IngestionResult, FullIngestionResult
from .scoring import ScoringService, ScoreBreakdown, ScoringResult

__all__ = [
    # Lead Service
    "LeadService",
    "LeadSummary",
    "LeadDetail",
    # Outreach Service
    "OutreachService",
    "OutreachResult",
    "BatchOutreachResult",
    # Ingestion Service
    "IngestionService",
    "IngestionResult",
    "FullIngestionResult",
    # Scoring Service
    "ScoringService",
    "ScoreBreakdown",
    "ScoringResult",
]
