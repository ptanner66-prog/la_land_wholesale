"""
Universal Tax Roll Ingestion - Works with any Louisiana parish tax roll.

This module provides ingestion that auto-detects column mappings and
handles various file formats (CSV, XLSX, ZIP).
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.config import get_settings
from core.logging_config import get_logger
from core.models import Lead, Owner, Parcel, Party
from ingestion.normalizer import ParishKeyNormalizer
from ingestion.parish_normalizer import ParishNormalizer, ParishNormalizerResult, StandardColumns
from outreach.phone import normalize_phone_e164

LOGGER = get_logger(__name__)
SETTINGS = get_settings()

# Batch settings
BATCH_COMMIT_SIZE = 500


@dataclass
class UniversalIngestionStats:
    """Statistics from universal tax roll ingestion."""
    
    rows_processed: int = 0
    rows_skipped: int = 0
    created_parties: int = 0
    updated_parties: int = 0
    created_owners: int = 0
    created_parcels: int = 0
    updated_parcels: int = 0
    created_leads: int = 0
    errors: int = 0
    warnings: List[str] = field(default_factory=list)
    error_details: List[str] = field(default_factory=list)
    parish_detected: Optional[str] = None
    column_mapping: Dict[str, str] = field(default_factory=dict)
    
    def as_dict(self) -> Dict[str, Any]:
        return {
            "rows_processed": self.rows_processed,
            "rows_skipped": self.rows_skipped,
            "created_parties": self.created_parties,
            "updated_parties": self.updated_parties,
            "created_owners": self.created_owners,
            "created_parcels": self.created_parcels,
            "updated_parcels": self.updated_parcels,
            "created_leads": self.created_leads,
            "errors": self.errors,
            "warnings": self.warnings,
            "error_details": self.error_details[:10],  # Limit error details
            "parish_detected": self.parish_detected,
            "column_mapping": self.column_mapping,
        }


def ingest_universal_tax_roll(
    session: Session,
    file_path: Path | str,
    parish_override: Optional[str] = None,
    dry_run: bool = False,
) -> UniversalIngestionStats:
    """
    Ingest any Louisiana parish tax roll file.
    
    Supports CSV, XLSX, and ZIP files with auto-detection of:
    - File format and delimiter
    - Column mappings
    - Parish identification
    
    Args:
        session: Database session.
        file_path: Path to tax roll file (CSV, XLSX, or ZIP).
        parish_override: Force a specific parish name.
        dry_run: If True, don't commit changes.
    
    Returns:
        UniversalIngestionStats with detailed results.
    """
    stats = UniversalIngestionStats()
    path = Path(file_path)
    
    if not path.exists():
        LOGGER.error(f"File not found: {path}")
        stats.error_details.append(f"File not found: {path}")
        return stats
    
    LOGGER.info(f"Starting universal tax roll ingestion: {path}")
    
    # Step 1: Normalize the file
    normalizer = ParishNormalizer(parish_override=parish_override)
    result = normalizer.normalize_file(path)
    
    if result.errors:
        stats.error_details.extend(result.errors)
        LOGGER.error(f"Normalization errors: {result.errors}")
        return stats
    
    stats.parish_detected = result.parish_name
    stats.column_mapping = result.column_mapping
    stats.warnings.extend(result.warnings)
    
    df = result.df
    LOGGER.info(f"Normalized {len(df)} rows from {result.parish_name or 'unknown'} parish")
    LOGGER.info(f"Column mapping: {result.column_mapping}")
    
    # Step 2: Process each row
    for idx, row in df.iterrows():
        stats.rows_processed += 1
        
        try:
            # Get parcel ID
            raw_parcel_id = row.get(StandardColumns.PARCEL_ID)
            if pd.isna(raw_parcel_id) or str(raw_parcel_id).strip() == "":
                stats.rows_skipped += 1
                continue
            
            parcel_id = ParishKeyNormalizer.normalize(str(raw_parcel_id))
            
            # Get parish (use detected or default)
            parish = result.parish_name or SETTINGS.default_parish
            
            # Upsert Parcel
            parcel = session.scalar(
                select(Parcel).where(Parcel.canonical_parcel_id == parcel_id)
            )
            is_new_parcel = False
            
            if not parcel:
                parcel = Parcel(
                    canonical_parcel_id=parcel_id,
                    parish=parish,
                )
                session.add(parcel)
                stats.created_parcels += 1
                is_new_parcel = True
            else:
                stats.updated_parcels += 1
            
            # Update Parcel Fields
            situs_addr = _get_str(row, StandardColumns.SITUS_ADDRESS)
            if situs_addr:
                parcel.situs_address = situs_addr
            
            situs_city = _get_str(row, StandardColumns.SITUS_CITY)
            if situs_city:
                parcel.city = situs_city
            
            situs_state = _get_str(row, StandardColumns.SITUS_STATE, default="LA")
            parcel.state = situs_state
            
            situs_zip = _get_str(row, StandardColumns.SITUS_ZIP)
            if situs_zip:
                parcel.postal_code = situs_zip
            
            # Values
            land_val = _get_float(row, StandardColumns.LAND_VALUE)
            if land_val is not None:
                parcel.land_assessed_value = land_val
            
            improv_val = _get_float(row, StandardColumns.IMPROVEMENT_VALUE)
            if improv_val is not None:
                parcel.improvement_assessed_value = improv_val
            
            acres = _get_float(row, StandardColumns.ACRES)
            if acres is not None:
                parcel.lot_size_acres = acres
            
            # Process Owner
            owner_name = _get_str(row, StandardColumns.OWNER_NAME)
            if not owner_name:
                # No owner - skip owner/lead creation but keep parcel
                if stats.rows_processed % BATCH_COMMIT_SIZE == 0:
                    if not dry_run:
                        session.commit()
                    LOGGER.info(f"Processed {stats.rows_processed} rows...")
                continue
            
            # Build mailing address
            mailing_parts = [
                _get_str(row, StandardColumns.MAILING_ADDRESS),
                _get_str(row, StandardColumns.MAILING_CITY),
                _get_str(row, StandardColumns.MAILING_STATE),
                _get_str(row, StandardColumns.MAILING_ZIP),
            ]
            full_mailing = ", ".join(filter(None, mailing_parts))
            mailing_zip = _get_str(row, StandardColumns.MAILING_ZIP, default="")
            
            # Generate match hash for Party
            match_str = f"{owner_name}|{mailing_zip}".upper()
            match_hash = hashlib.sha256(match_str.encode()).hexdigest()
            
            # Upsert Party
            party = session.scalar(
                select(Party).where(Party.match_hash == match_hash)
            )
            
            if not party:
                party = Party(
                    normalized_name=owner_name.upper(),
                    normalized_zip=mailing_zip,
                    match_hash=match_hash,
                    display_name=owner_name,
                    raw_mailing_address=full_mailing,
                    party_type="unknown",
                )
                session.add(party)
                session.flush()
                stats.created_parties += 1
            else:
                stats.updated_parties += 1
            
            # Upsert Owner
            owner_link = session.scalar(
                select(Owner).where(Owner.party_id == party.id)
            )
            
            if not owner_link:
                owner_link = Owner(party_id=party.id)
                session.add(owner_link)
                session.flush()
                stats.created_owners += 1
            
            # Update Owner Contact Info
            phone = _get_str(row, StandardColumns.PHONE)
            if phone:
                e164 = normalize_phone_e164(phone)
                if e164:
                    owner_link.phone_primary = e164
                    owner_link.is_tcpa_safe = True
            
            email = _get_str(row, StandardColumns.EMAIL)
            if email and "@" in email:
                owner_link.email = email
            
            # Flush to ensure parcel.id is available
            session.flush()
            
            # Upsert Lead
            lead = session.scalar(
                select(Lead).where(
                    Lead.parcel_id == parcel.id,
                    Lead.owner_id == owner_link.id,
                )
            )
            
            if not lead:
                lead = Lead(
                    parcel_id=parcel.id,
                    owner_id=owner_link.id,
                    status="new",
                )
                session.add(lead)
                stats.created_leads += 1
            
            # Batch commit
            if stats.rows_processed % BATCH_COMMIT_SIZE == 0:
                if not dry_run:
                    session.commit()
                LOGGER.info(f"Processed {stats.rows_processed} rows...")
        
        except Exception as e:
            LOGGER.error(f"Error processing row {idx}: {e}")
            stats.errors += 1
            stats.error_details.append(f"Row {idx}: {str(e)}")
            continue
    
    # Final commit
    if not dry_run:
        session.commit()
    
    LOGGER.info(f"Universal ingestion complete. Stats: {stats.as_dict()}")
    return stats


def _get_str(row: pd.Series, col: str, default: str = "") -> str:
    """Get string value from row, handling NaN."""
    val = row.get(col)
    if pd.isna(val) or val is None:
        return default
    return str(val).strip()


def _get_float(row: pd.Series, col: str) -> Optional[float]:
    """Get float value from row, handling NaN."""
    val = row.get(col)
    if pd.isna(val) or val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


__all__ = ["ingest_universal_tax_roll", "UniversalIngestionStats"]

