"""Ingestion pipeline orchestrator for East Baton Rouge data feeds."""
from __future__ import annotations

import time
from pathlib import Path
from typing import Dict, Optional

from core.db import get_session
from core.exceptions import IngestionError
from core.logging_config import get_logger
from core.types import IngestionSummary
from ingestion.ebr_adjudicated import ingest_adjudicated_file
from ingestion.ebr_gis import ingest_gis_file
from ingestion.ebr_tax_roll import ingest_tax_roll_file

LOGGER = get_logger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw"
DEFAULT_TAX_ROLL_NAME = "ebr_tax_roll.csv"
DEFAULT_ADJUDICATED_NAME = "ebr_adjudicated.csv"
DEFAULT_GIS_NAME = "ebr_gis.geojson"


def _resolve_input(path: Optional[Path | str], default_name: str) -> Path:
    """
    Resolve an input file path, using defaults if not specified.

    Args:
        path: User-provided path or None.
        default_name: Default filename in the raw data directory.

    Returns:
        Resolved Path object.

    Raises:
        FileNotFoundError: If the resolved file doesn't exist.
    """
    if path:
        resolved = Path(path)
        if not resolved.exists():
            raise FileNotFoundError(f"Specified file not found: {resolved}")
        return resolved

    candidate = DEFAULT_RAW_DATA_DIR / default_name
    if not candidate.exists():
        raise FileNotFoundError(f"Expected ingestion file missing: {candidate}")
    return candidate


def run_full_ingestion(
    tax_roll_path: Optional[Path | str] = None,
    adjudicated_path: Optional[Path | str] = None,
    gis_path: Optional[Path | str] = None,
) -> IngestionSummary:
    """
    Execute the full ingestion workflow.

    Each stage runs in its own session context for isolation.
    Failures in one stage do not prevent other stages from running.

    Args:
        tax_roll_path: Path to tax roll CSV (uses default if None).
        adjudicated_path: Path to adjudicated CSV (uses default if None).
        gis_path: Path to GIS file (uses default if None).

    Returns:
        IngestionSummary with statistics from all stages.
    """
    start_time = time.time()

    # Resolve file paths
    tax_roll_file = _resolve_input(tax_roll_path, DEFAULT_TAX_ROLL_NAME)
    adjudicated_file = _resolve_input(adjudicated_path, DEFAULT_ADJUDICATED_NAME)
    gis_file = _resolve_input(gis_path, DEFAULT_GIS_NAME)

    LOGGER.info(
        "Starting full ingestion pipeline:\n  Tax Roll: %s\n  Adjudicated: %s\n  GIS: %s",
        tax_roll_file,
        adjudicated_file,
        gis_file,
    )

    # Stage 1: Tax Roll
    tax_roll_stats: Dict[str, int] = {}
    try:
        LOGGER.info("Stage 1/3: Ingesting tax roll data...")
        with get_session() as session:
            result = ingest_tax_roll_file(session, tax_roll_file)
            tax_roll_stats = result.as_dict()
        LOGGER.info("Stage 1/3 complete: %s", tax_roll_stats)
    except Exception as exc:
        LOGGER.error("Stage 1/3 FAILED (tax roll): %s", exc, exc_info=True)
        tax_roll_stats = {"error": 1, "message": str(exc)}

    # Stage 2: Adjudicated Parcels
    adjudicated_stats: Dict[str, int] = {}
    try:
        LOGGER.info("Stage 2/3: Updating adjudication flags...")
        with get_session() as session:
            result = ingest_adjudicated_file(session, adjudicated_file)
            adjudicated_stats = result.as_dict()
        LOGGER.info("Stage 2/3 complete: %s", adjudicated_stats)
    except Exception as exc:
        LOGGER.error("Stage 2/3 FAILED (adjudicated): %s", exc, exc_info=True)
        adjudicated_stats = {"error": 1, "message": str(exc)}

    # Stage 3: GIS Enrichment
    gis_stats: Dict[str, int] = {}
    try:
        LOGGER.info("Stage 3/3: Enriching parcels with GIS data...")
        with get_session() as session:
            result = ingest_gis_file(session, gis_file)
            gis_stats = result.as_dict()
        LOGGER.info("Stage 3/3 complete: %s", gis_stats)
    except Exception as exc:
        LOGGER.error("Stage 3/3 FAILED (GIS): %s", exc, exc_info=True)
        gis_stats = {"error": 1, "message": str(exc)}

    elapsed = time.time() - start_time
    LOGGER.info(
        "Ingestion pipeline complete in %.2f seconds:\n  Tax Roll: %s\n  Adjudicated: %s\n  GIS: %s",
        elapsed,
        tax_roll_stats,
        adjudicated_stats,
        gis_stats,
    )

    return IngestionSummary(
        tax_roll=tax_roll_stats,
        adjudicated=adjudicated_stats,
        gis=gis_stats,
    )


__all__ = ["run_full_ingestion"]
