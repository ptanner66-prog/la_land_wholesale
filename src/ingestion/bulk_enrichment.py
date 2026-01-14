"""
Bulk Parcel Enrichment - Updates existing parcels with assessor data.

This module enriches parcels that were created without assessor fields
by matching on parcel ID and updating:
- lot_size_acres
- land_assessed_value
- improvement_assessed_value
- years_tax_delinquent
- is_adjudicated
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from core.config import get_settings
from core.logging_config import get_logger
from core.models import Lead, Owner, Parcel, Party
from ingestion.normalizer import ParishKeyNormalizer
from outreach.phone import normalize_phone_e164

LOGGER = get_logger(__name__)
SETTINGS = get_settings()

BATCH_SIZE = 500


@dataclass
class BulkEnrichmentStats:
    """Statistics from bulk enrichment."""
    
    rows_processed: int = 0
    rows_skipped: int = 0
    parcels_found: int = 0
    parcels_not_found: int = 0
    parcels_enriched: int = 0
    owners_updated: int = 0
    phones_added: int = 0
    leads_rescored: int = 0
    errors: int = 0
    warnings: List[str] = field(default_factory=list)
    
    # Field-level stats
    acres_updated: int = 0
    land_value_updated: int = 0
    improvement_value_updated: int = 0
    delinquency_updated: int = 0
    adjudication_updated: int = 0
    
    def as_dict(self) -> Dict[str, Any]:
        return {
            "rows_processed": self.rows_processed,
            "rows_skipped": self.rows_skipped,
            "parcels_found": self.parcels_found,
            "parcels_not_found": self.parcels_not_found,
            "parcels_enriched": self.parcels_enriched,
            "owners_updated": self.owners_updated,
            "phones_added": self.phones_added,
            "leads_rescored": self.leads_rescored,
            "errors": self.errors,
            "warnings": self.warnings[:10],
            "field_updates": {
                "acres": self.acres_updated,
                "land_value": self.land_value_updated,
                "improvement_value": self.improvement_value_updated,
                "delinquency": self.delinquency_updated,
                "adjudication": self.adjudication_updated,
            },
        }


def enrich_parcels_from_file(
    session: Session,
    file_path: Path | str,
    parish_override: Optional[str] = None,
    update_phones: bool = True,
    dry_run: bool = False,
) -> BulkEnrichmentStats:
    """
    Enrich existing parcels with assessor data from a CSV/XLSX file.
    
    This function:
    1. Reads the source file directly (no normalization to preserve all columns)
    2. For each row, finds the matching parcel by canonical_parcel_id
    3. Updates parcel fields if they are NULL or 0
    4. Optionally updates owner phone numbers
    
    Args:
        session: Database session.
        file_path: Path to enrichment file (CSV, XLSX).
        parish_override: Force a specific parish name.
        update_phones: Whether to update owner phone numbers.
        dry_run: If True, don't commit changes.
    
    Returns:
        BulkEnrichmentStats with detailed results.
    """
    stats = BulkEnrichmentStats()
    path = Path(file_path)
    
    if not path.exists():
        LOGGER.error(f"File not found: {path}")
        stats.warnings.append(f"File not found: {path}")
        return stats
    
    LOGGER.info(f"Starting bulk parcel enrichment from: {path}")
    
    # Read file directly to preserve all columns
    try:
        if path.suffix.lower() in ['.xlsx', '.xls']:
            df = pd.read_excel(path)
        else:
            try:
                df = pd.read_csv(path, low_memory=False)
            except UnicodeDecodeError:
                df = pd.read_csv(path, encoding='latin-1', low_memory=False)
    except Exception as e:
        LOGGER.error(f"Failed to read file: {e}")
        stats.warnings.append(f"Failed to read file: {e}")
        return stats
    
    # Normalize column names (lowercase, strip)
    df.columns = [str(c).lower().strip().replace(' ', '_') for c in df.columns]
    
    LOGGER.info(f"Read {len(df)} rows. Columns: {list(df.columns)}")
    
    # Step 2: Process each row
    # Find parcel ID column
    parcel_id_col = None
    for col in ['parcel_id', 'parcel_number', 'parcel_num', 'parcel', 'apn', 'pin']:
        if col in df.columns:
            parcel_id_col = col
            break
    
    if not parcel_id_col:
        LOGGER.error("No parcel ID column found")
        stats.warnings.append("No parcel ID column found in file")
        return stats
    
    LOGGER.info(f"Using parcel ID column: {parcel_id_col}")
    
    for idx, row in df.iterrows():
        stats.rows_processed += 1
        
        try:
            # Get parcel ID
            raw_parcel_id = row.get(parcel_id_col)
            if pd.isna(raw_parcel_id) or str(raw_parcel_id).strip() == "":
                stats.rows_skipped += 1
                continue
            
            parcel_id = ParishKeyNormalizer.normalize(str(raw_parcel_id))
            
            # Find existing parcel
            parcel = session.scalar(
                select(Parcel).where(Parcel.canonical_parcel_id == parcel_id)
            )
            
            if not parcel:
                stats.parcels_not_found += 1
                continue
            
            stats.parcels_found += 1
            enriched = False
            
            # Update acreage if missing - check multiple column names
            acres = None
            for col in ['acres', 'acreage', 'lot_size_acres', 'lot_size', 'land_area']:
                acres = _get_float(row, col)
                if acres is not None:
                    break
            if acres is not None and acres > 0:
                if parcel.lot_size_acres is None or parcel.lot_size_acres == 0:
                    parcel.lot_size_acres = acres
                    stats.acres_updated += 1
                    enriched = True
            
            # Update land value if missing - check multiple column names
            land_val = None
            for col in ['land_value', 'land_assessed_value', 'land_val', 'assessed_land']:
                land_val = _get_float(row, col)
                if land_val is not None:
                    break
            if land_val is not None and land_val > 0:
                if parcel.land_assessed_value is None or parcel.land_assessed_value == 0:
                    parcel.land_assessed_value = land_val
                    stats.land_value_updated += 1
                    enriched = True
            
            # Update improvement value if missing - check multiple column names
            improv_val = None
            for col in ['improvement_value', 'improvement_assessed_value', 'improv_value', 'building_value']:
                improv_val = _get_float(row, col)
                if improv_val is not None:
                    break
            if improv_val is not None:
                if parcel.improvement_assessed_value is None:
                    parcel.improvement_assessed_value = improv_val
                    stats.improvement_value_updated += 1
                    enriched = True
            
            # Update delinquency - check multiple possible column names
            delinq = None
            for col in ["years_tax_delinquent", "delinquent_years", "tax_delinquent", "delinquency"]:
                delinq = _get_int(row, col)
                if delinq is not None:
                    break
            if delinq is not None and delinq > 0:
                if parcel.years_tax_delinquent is None or parcel.years_tax_delinquent == 0:
                    parcel.years_tax_delinquent = delinq
                    stats.delinquency_updated += 1
                    enriched = True
            
            # Update adjudication - check multiple possible column names
            adjud = False
            for col in ["is_adjudicated", "adjudicated", "adjudication"]:
                adjud = _get_bool(row, col)
                if adjud:
                    break
            if adjud:
                if not parcel.is_adjudicated:
                    parcel.is_adjudicated = True
                    stats.adjudication_updated += 1
                    enriched = True
            
            if enriched:
                stats.parcels_enriched += 1
                
                # Re-score the lead after enrichment to update pipeline_stage
                lead = session.scalar(
                    select(Lead).where(
                        Lead.parcel_id == parcel.id,
                        Lead.deleted_at.is_(None),
                    )
                )
                if lead and lead.owner:
                    from scoring.deterministic_engine import compute_deterministic_score, get_parish_median_values, HOT_THRESHOLD, CONTACT_THRESHOLD, REJECT_THRESHOLD
                    from core.models import PipelineStage
                    from datetime import datetime, timezone
                    
                    # Get parish median for scoring
                    parish_key = (parcel.parish or "").lower().strip()
                    parish_medians = get_parish_median_values(session)
                    parish_median = parish_medians.get(parish_key)
                    
                    # Score the lead
                    score_result = compute_deterministic_score(lead, parish_median)
                    lead.motivation_score = score_result.motivation_score
                    lead.score_details = score_result.to_dict()
                    lead.updated_at = datetime.now(timezone.utc)
                    
                    # Update pipeline_stage atomically based on score
                    manual_stages = {
                        PipelineStage.CONTACTED.value,
                        PipelineStage.REVIEW.value,
                        PipelineStage.OFFER.value,
                        PipelineStage.CONTRACT.value,
                    }
                    if lead.pipeline_stage not in manual_stages:
                        if score_result.disqualified:
                            lead.pipeline_stage = PipelineStage.INGESTED.value
                        elif score_result.motivation_score >= HOT_THRESHOLD:
                            lead.pipeline_stage = PipelineStage.HOT.value
                        elif score_result.motivation_score >= CONTACT_THRESHOLD:
                            lead.pipeline_stage = PipelineStage.NEW.value
                        else:
                            lead.pipeline_stage = PipelineStage.PRE_SCORE.value
                    
                    stats.leads_rescored += 1
            
            # Update owner phone if requested
            if update_phones:
                phone = None
                for col in ['phone', 'phone_primary', 'telephone', 'cell', 'mobile']:
                    phone = _get_str(row, col)
                    if phone:
                        break
                if phone:
                    e164 = normalize_phone_e164(phone)
                    if e164:
                        # Find lead for this parcel
                        lead = session.scalar(
                            select(Lead).where(
                                Lead.parcel_id == parcel.id,
                                Lead.deleted_at.is_(None),
                            )
                        )
                        if lead and lead.owner:
                            if not lead.owner.phone_primary:
                                lead.owner.phone_primary = e164
                                lead.owner.is_tcpa_safe = True
                                stats.phones_added += 1
                                stats.owners_updated += 1
            
            # Batch commit
            if stats.rows_processed % BATCH_SIZE == 0:
                if not dry_run:
                    session.commit()
                LOGGER.info(
                    f"Processed {stats.rows_processed} rows... "
                    f"(enriched: {stats.parcels_enriched}, not found: {stats.parcels_not_found})"
                )
        
        except Exception as e:
            LOGGER.error(f"Error processing row {idx}: {e}")
            stats.errors += 1
            continue
    
    # Final commit
    if not dry_run:
        session.commit()
    
    LOGGER.info(f"Bulk enrichment complete. Stats: {stats.as_dict()}")
    return stats


def _get_str(row: pd.Series, col: str, default: str = "") -> str:
    """Get string value from row."""
    val = row.get(col)
    if pd.isna(val) or val is None:
        return default
    # Handle floats that should be strings (e.g., phone numbers read as floats)
    if isinstance(val, float):
        # Remove .0 suffix if it's a whole number
        if val == int(val):
            return str(int(val)).strip()
    return str(val).strip()


def _get_float(row: pd.Series, col: str) -> Optional[float]:
    """Get float value from row."""
    val = row.get(col)
    if pd.isna(val) or val is None:
        return None
    try:
        # Handle currency strings
        if isinstance(val, str):
            val = val.replace("$", "").replace(",", "").strip()
        return float(val)
    except (ValueError, TypeError):
        return None


def _get_int(row: pd.Series, col: str) -> Optional[int]:
    """Get int value from row."""
    val = row.get(col)
    if pd.isna(val) or val is None:
        return None
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return None


def _get_bool(row: pd.Series, col: str) -> bool:
    """Get bool value from row."""
    val = row.get(col)
    if pd.isna(val) or val is None:
        return False
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return val > 0
    val_str = str(val).lower().strip()
    return val_str in ("true", "1", "yes", "y", "t")


__all__ = ["enrich_parcels_from_file", "BulkEnrichmentStats"]

