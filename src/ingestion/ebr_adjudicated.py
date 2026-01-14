"""Adjudicated parcel ingestion for East Baton Rouge."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.logging_config import get_logger
from core.models import Parcel
from ingestion.normalizer import ParishKeyNormalizer

LOGGER = get_logger(__name__)

PARCEL_ID_COL = "parcel_number"
YEARS_DELINQUENT_COL = "years_tax_delinquent"
IS_ADJUDICATED_COL = "is_adjudicated"

BATCH_COMMIT_SIZE = 1000


@dataclass
class AdjudicationStats:
    """Statistics from adjudication update."""

    rows_processed: int = 0
    rows_skipped: int = 0
    parcels_updated: int = 0
    parcels_missing: int = 0
    errors: int = 0

    def as_dict(self) -> Dict[str, int]:
        return {
            "rows_processed": self.rows_processed,
            "rows_skipped": self.rows_skipped,
            "parcels_updated": self.parcels_updated,
            "parcels_missing": self.parcels_missing,
            "errors": self.errors,
        }


def ingest_adjudicated_file(session: Session, file_path: Path | str) -> AdjudicationStats:
    """
    Ingest adjudicated parcels CSV.

    Args:
        session: Database session.
        file_path: Path to CSV file.

    Returns:
        AdjudicationStats object.
    """
    stats = AdjudicationStats()
    path = Path(file_path)

    if not path.exists():
        LOGGER.error(f"File not found: {path}")
        return stats

    LOGGER.info(f"Reading adjudicated file: {path}")
    try:
        df = pd.read_csv(path)
    except Exception as e:
        LOGGER.error(f"Failed to read CSV: {e}")
        return stats

    LOGGER.info(f"Processing {len(df)} rows...")

    for idx, row in df.iterrows():
        stats.rows_processed += 1

        try:
            # 1. Extract Parcel ID
            raw_id = row.get(PARCEL_ID_COL)
            if pd.isna(raw_id):
                stats.rows_skipped += 1
                continue

            parcel_id = ParishKeyNormalizer.normalize(str(raw_id))

            # 2. Find Parcel (using canonical_parcel_id)
            parcel = session.scalar(
                select(Parcel).where(Parcel.canonical_parcel_id == parcel_id)
            )

            if not parcel:
                stats.parcels_missing += 1
                # We could create a stub parcel, but usually we want tax roll data first.
                continue

            # 3. Update Status
            parcel.is_adjudicated = True

            # Update years delinquent if available
            if YEARS_DELINQUENT_COL in df.columns:
                val = row.get(YEARS_DELINQUENT_COL)
                if not pd.isna(val):
                    try:
                        parcel.years_tax_delinquent = int(float(val))
                    except (ValueError, TypeError):
                        pass

            stats.parcels_updated += 1

            if stats.rows_processed % BATCH_COMMIT_SIZE == 0:
                session.commit()
                LOGGER.info(f"Processed {stats.rows_processed} rows...")

        except Exception as e:
            LOGGER.error(f"Error processing row {idx}: {e}")
            stats.errors += 1
            continue

    session.commit()
    LOGGER.info(f"Adjudication ingestion complete. Stats: {stats.as_dict()}")
    return stats


# Alias for backward compatibility
update_adjudicated_flags = ingest_adjudicated_file

__all__ = ["ingest_adjudicated_file", "update_adjudicated_flags", "AdjudicationStats"]
