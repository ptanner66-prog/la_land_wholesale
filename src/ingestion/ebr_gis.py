"""GIS enrichment for East Baton Rouge parcels."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any

import geopandas as gpd
import pandas as pd
from geoalchemy2.shape import from_shape
from shapely.geometry import MultiPolygon
from shapely.validation import make_valid
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.logging_config import get_logger
from core.models import Parcel
from ingestion.normalizer import ParishKeyNormalizer

LOGGER = get_logger(__name__)

PARCEL_ID_FIELD = "parcel_number"
ZONING_FIELD = "zoning_code"
LOT_SIZE_SQFT_FIELD = "lot_sqft"
INSIDE_CITY_LIMITS_FIELD = "inside_city"
LOT_SIZE_ACRES_FIELD = "lot_acres"
GEOMETRY_FIELD = "geometry"

BATCH_COMMIT_SIZE = 500


@dataclass
class GISIngestionStats:
    """Statistics from GIS enrichment."""

    rows_processed: int = 0
    rows_skipped: int = 0
    parcels_updated: int = 0
    parcels_missing: int = 0
    geometries_added: int = 0
    errors: int = 0

    def as_dict(self) -> Dict[str, int]:
        return {
            "rows_processed": self.rows_processed,
            "rows_skipped": self.rows_skipped,
            "parcels_updated": self.parcels_updated,
            "parcels_missing": self.parcels_missing,
            "geometries_added": self.geometries_added,
            "errors": self.errors,
        }


def ingest_gis_file(session: Session, file_path: Path | str) -> GISIngestionStats:
    """
    Ingest GIS data (GeoJSON/Shapefile) and enrich parcels.

    Args:
        session: Database session.
        file_path: Path to GIS file.

    Returns:
        GISIngestionStats object.
    """
    stats = GISIngestionStats()
    path = Path(file_path)

    if not path.exists():
        LOGGER.error(f"File not found: {path}")
        return stats

    LOGGER.info(f"Reading GIS file: {path}")
    try:
        gdf = gpd.read_file(path)
    except Exception as e:
        LOGGER.error(f"Failed to read GIS file: {e}")
        return stats

    # Ensure CRS is WGS84 (EPSG:4326)
    if gdf.crs and gdf.crs.to_string() != "EPSG:4326":
        LOGGER.info(f"Reprojecting from {gdf.crs} to EPSG:4326...")
        gdf = gdf.to_crs(epsg=4326)

    LOGGER.info(f"Processing {len(gdf)} geometries...")

    for idx, row in gdf.iterrows():
        stats.rows_processed += 1

        try:
            # 1. Extract Parcel ID
            # Try multiple common column names if the constant doesn't match
            raw_id = row.get(PARCEL_ID_FIELD)
            if pd.isna(raw_id):
                # Fallback or skip
                stats.rows_skipped += 1
                continue

            parcel_id = ParishKeyNormalizer.normalize(str(raw_id))

            # 2. Find Parcel (using canonical_parcel_id)
            parcel = session.scalar(
                select(Parcel).where(Parcel.canonical_parcel_id == parcel_id)
            )

            if not parcel:
                stats.parcels_missing += 1
                # We generally don't create parcels from GIS alone as we need tax roll data for ownership
                continue

            # 3. Update Geometry (field is 'geom' not 'geometry')
            geom = row.geometry
            if geom:
                # Fix invalid geometries
                if not geom.is_valid:
                    geom = make_valid(geom)

                # Convert to MultiPolygon if it's a Polygon (for consistency)
                if geom.geom_type == "Polygon":
                    geom = MultiPolygon([geom])

                if geom.geom_type == "MultiPolygon":
                    # Convert to WKBElement for SQLAlchemy
                    parcel.geom = from_shape(geom, srid=4326)
                    stats.geometries_added += 1

            # 4. Update Attributes
            if ZONING_FIELD in row.index:
                val = row[ZONING_FIELD]
                if not pd.isna(val):
                    parcel.zoning_code = str(val)

            if INSIDE_CITY_LIMITS_FIELD in row.index:
                val = row[INSIDE_CITY_LIMITS_FIELD]
                if isinstance(val, str):
                    parcel.inside_city_limits = val.lower() in ("y", "yes", "true", "1")
                elif not pd.isna(val):
                    parcel.inside_city_limits = bool(val)

            if LOT_SIZE_SQFT_FIELD in row.index:
                val = row[LOT_SIZE_SQFT_FIELD]
                if not pd.isna(val):
                    try:
                        parcel.lot_size_sqft = float(val)
                    except (ValueError, TypeError):
                        pass

            stats.parcels_updated += 1

            if stats.rows_processed % BATCH_COMMIT_SIZE == 0:
                session.commit()
                LOGGER.info(f"Processed {stats.rows_processed} geometries...")

        except Exception as e:
            LOGGER.error(f"Error processing GIS row {idx}: {e}")
            stats.errors += 1
            continue

    session.commit()
    LOGGER.info(f"GIS ingestion complete. Stats: {stats.as_dict()}")
    return stats


# Alias for backward compatibility
enrich_parcels_from_gis = ingest_gis_file

__all__ = ["ingest_gis_file", "enrich_parcels_from_gis", "GISIngestionStats"]
