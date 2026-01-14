"""East Baton Rouge tax roll ingestion utilities."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Any
import hashlib

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.config import get_settings
from core.logging_config import get_logger
from core.models import Lead, Owner, Parcel, Party
from ingestion.normalizer import ParishKeyNormalizer
from outreach.phone import normalize_phone_e164

LOGGER = get_logger(__name__)
SETTINGS = get_settings()

# Column mappings based on EBR Tax Roll CSV format
PARCEL_ID_COL = "parcel_number"
OWNER_NAME_COL = "owner_name"
MAILING_ADDRESS_COL = "mailing_address"
MAILING_CITY_COL = "mailing_city"
MAILING_STATE_COL = "mailing_state"
MAILING_ZIP_COL = "mailing_zip"
PHONE_COL = "phone"
EMAIL_COL = "email"
LAND_VALUE_COL = "land_value"
IMPROVEMENT_VALUE_COL = "improvement_value"
LOT_SIZE_ACRES_COL = "acreage"
SITUS_ADDRESS_COL = "situs_address"
SITUS_CITY_COL = "situs_city"
SITUS_STATE_COL = "situs_state"
SITUS_ZIP_COL = "situs_zip"
LEGAL_DESC_COL = "legal_description"
SUBDIVISION_COL = "subdivision"
WARD_COL = "ward"

# Batch settings
BATCH_COMMIT_SIZE = 1000


@dataclass
class TaxRollIngestionStats:
    """Statistics from tax roll ingestion."""

    rows_processed: int = 0
    rows_skipped: int = 0
    created_parties: int = 0
    updated_parties: int = 0
    created_owners: int = 0
    created_parcels: int = 0
    updated_parcels: int = 0
    created_leads: int = 0
    errors: int = 0

    def as_dict(self) -> Dict[str, int]:
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
        }


def _parse_currency(value: Any) -> Optional[float]:
    """Parse currency string to float."""
    if pd.isna(value) or value == "":
        return None
    try:
        clean = str(value).replace("$", "").replace(",", "").strip()
        return float(clean)
    except (ValueError, TypeError):
        return None


def _parse_float(value: Any) -> Optional[float]:
    """Parse float string."""
    if pd.isna(value) or value == "":
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def ingest_tax_roll_file(session: Session, file_path: Path | str) -> TaxRollIngestionStats:
    """
    Ingest EBR tax roll CSV file.

    Args:
        session: Database session.
        file_path: Path to CSV file.

    Returns:
        TaxRollIngestionStats object.
    """
    stats = TaxRollIngestionStats()
    path = Path(file_path)

    if not path.exists():
        LOGGER.error(f"File not found: {path}")
        return stats

    LOGGER.info(f"Reading tax roll file: {path}")
    try:
        # Read CSV with low_memory=False to avoid type inference warnings
        df = pd.read_csv(path, low_memory=False)
    except Exception as e:
        LOGGER.error(f"Failed to read CSV: {e}")
        return stats

    LOGGER.info(f"Processing {len(df)} rows...")

    for idx, row in df.iterrows():
        stats.rows_processed += 1

        try:
            # 1. Extract Parcel ID
            raw_parcel_id = row.get(PARCEL_ID_COL)
            if pd.isna(raw_parcel_id):
                stats.rows_skipped += 1
                continue

            parcel_id = ParishKeyNormalizer.normalize(str(raw_parcel_id))

            # 2. Upsert Parcel
            parcel = session.scalar(
                select(Parcel).where(Parcel.canonical_parcel_id == parcel_id)
            )
            is_new_parcel = False

            if not parcel:
                parcel = Parcel(
                    canonical_parcel_id=parcel_id,
                    parish=SETTINGS.default_parish,
                )
                session.add(parcel)
                stats.created_parcels += 1
                is_new_parcel = True
            else:
                stats.updated_parcels += 1

            # Update Parcel Fields
            parcel.situs_address = str(row.get(SITUS_ADDRESS_COL, "") or "").strip()
            parcel.city = str(row.get(SITUS_CITY_COL, "") or "").strip()
            parcel.state = str(row.get(SITUS_STATE_COL, "LA") or "LA").strip()
            parcel.postal_code = str(row.get(SITUS_ZIP_COL, "") or "").strip()

            parcel.land_assessed_value = _parse_currency(row.get(LAND_VALUE_COL))
            parcel.improvement_assessed_value = _parse_currency(row.get(IMPROVEMENT_VALUE_COL))
            parcel.lot_size_acres = _parse_float(row.get(LOT_SIZE_ACRES_COL))

            # 3. Upsert Party (Owner)
            owner_name = str(row.get(OWNER_NAME_COL, "") or "").strip()
            mailing_address = str(row.get(MAILING_ADDRESS_COL, "") or "").strip()
            mailing_city = str(row.get(MAILING_CITY_COL, "") or "").strip()
            mailing_state = str(row.get(MAILING_STATE_COL, "") or "").strip()
            mailing_zip = str(row.get(MAILING_ZIP_COL, "") or "").strip()

            # Build full mailing address
            full_mailing = ", ".join(
                filter(None, [mailing_address, mailing_city, mailing_state, mailing_zip])
            )

            # Generate match hash for Party
            match_str = f"{owner_name}|{mailing_zip}".upper()
            match_hash = hashlib.sha256(match_str.encode()).hexdigest()

            party = None
            owner_link = None

            if owner_name:
                stmt = select(Party).where(Party.match_hash == match_hash)
                party = session.scalar(stmt)

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
                    session.flush()  # Get party.id
                    stats.created_parties += 1
                else:
                    stats.updated_parties += 1

                # 4. Link Owner (Party -> Owner)
                # Check if Owner link exists for this party
                owner_link = session.scalar(
                    select(Owner).where(Owner.party_id == party.id)
                )

                if not owner_link:
                    owner_link = Owner(party_id=party.id)
                    session.add(owner_link)
                    session.flush()  # Get owner_link.id
                    stats.created_owners += 1

                # Update Owner Contact Info
                raw_phone = row.get(PHONE_COL)
                if not pd.isna(raw_phone):
                    e164 = normalize_phone_e164(str(raw_phone))
                    if e164:
                        owner_link.phone_primary = e164
                        # Mark as TCPA safe if we have a valid phone
                        owner_link.is_tcpa_safe = True

                raw_email = row.get(EMAIL_COL)
                if not pd.isna(raw_email):
                    owner_link.email = str(raw_email).strip()

                # 5. Create Lead (Link Owner and Parcel)
                # Flush to ensure parcel.id is available
                session.flush()

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

            # Commit batch
            if stats.rows_processed % BATCH_COMMIT_SIZE == 0:
                session.commit()
                LOGGER.info(f"Processed {stats.rows_processed} rows...")

        except Exception as e:
            LOGGER.error(f"Error processing row {idx}: {e}")
            stats.errors += 1
            continue

    session.commit()
    LOGGER.info(f"Ingestion complete. Stats: {stats.as_dict()}")
    return stats


# Alias for backward compatibility
ingest_tax_roll_csv = ingest_tax_roll_file

__all__ = ["ingest_tax_roll_file", "ingest_tax_roll_csv", "TaxRollIngestionStats"]
