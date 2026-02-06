"""Ingestion routes with path traversal protection."""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Any, Optional

from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from api.deps import get_db
from core.config import get_settings, PROJECT_ROOT
from core.logging_config import get_logger
from domain.ingestion import IngestionService
from ingestion.universal_tax_roll import ingest_universal_tax_roll

router = APIRouter()
LOGGER = get_logger(__name__)
SETTINGS = get_settings()

# Resolve the allowed ingestion directory once at import time
_ingestion_base = (
    Path(SETTINGS.ingestion_data_dir).resolve()
    if SETTINGS.ingestion_data_dir
    else (PROJECT_ROOT / "data").resolve()
)


def _validate_ingestion_path(raw_path: str) -> Path:
    """
    Validate that a file path is within the allowed ingestion directory.

    Raises HTTPException 403 if path traversal is detected.
    """
    resolved = Path(raw_path).resolve()
    if not str(resolved).startswith(str(_ingestion_base)):
        LOGGER.warning(f"Path traversal blocked: {raw_path} resolved to {resolved}")
        raise HTTPException(
            status_code=403,
            detail=f"Access denied: path must be within {_ingestion_base}",
        )
    return resolved


class UniversalIngestionRequest(BaseModel):
    """Request for universal tax roll ingestion."""
    file_path: str
    parish_override: Optional[str] = None
    dry_run: bool = False


@router.post("/tax-roll")
async def ingest_tax_roll(
    file_path: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> Dict[str, str]:
    """Trigger tax roll ingestion in background."""
    safe_path = _validate_ingestion_path(file_path)

    def _run() -> None:
        service = IngestionService()
        try:
            service.run_pipeline(tax_roll_path=str(safe_path))
        except Exception as e:
            LOGGER.error(f"Background ingestion failed: {e}")

    background_tasks.add_task(_run)
    return {"message": "Ingestion started in background", "file": str(safe_path)}


@router.post("/gis")
async def ingest_gis(
    file_path: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> Dict[str, str]:
    """Trigger GIS ingestion in background."""
    safe_path = _validate_ingestion_path(file_path)

    def _run() -> None:
        service = IngestionService()
        try:
            service.run_pipeline(gis_path=str(safe_path))
        except Exception as e:
            LOGGER.error(f"Background GIS ingestion failed: {e}")

    background_tasks.add_task(_run)
    return {"message": "GIS ingestion started in background", "file": str(safe_path)}


@router.post("/adjudicated")
async def ingest_adjudicated(
    file_path: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> Dict[str, str]:
    """Trigger adjudicated property ingestion in background."""
    safe_path = _validate_ingestion_path(file_path)

    def _run() -> None:
        service = IngestionService()
        try:
            service.run_pipeline(adjudicated_path=str(safe_path))
        except Exception as e:
            LOGGER.error(f"Background adjudicated ingestion failed: {e}")

    background_tasks.add_task(_run)
    return {"message": "Adjudicated ingestion started in background", "file": str(safe_path)}


@router.post("/full")
async def run_full_ingestion(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> Dict[str, str]:
    """Run full ingestion pipeline with default files."""
    def _run() -> None:
        service = IngestionService()
        try:
            result = service.run_full_pipeline()
            LOGGER.info(f"Full ingestion completed: {result.success}")
        except Exception as e:
            LOGGER.error(f"Full ingestion failed: {e}")

    background_tasks.add_task(_run)
    return {"message": "Full ingestion pipeline started in background"}


@router.get("/statistics")
async def get_ingestion_statistics(
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Get statistics about ingested data."""
    service = IngestionService()
    return service.get_data_statistics(db)


@router.post("/universal")
async def ingest_universal(
    request: UniversalIngestionRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Universal tax roll ingestion - works with any Louisiana parish.
    
    Supports CSV, XLSX, and ZIP files with auto-detection of:
    - File format and delimiter
    - Column mappings  
    - Parish identification
    
    Args:
        request: Ingestion request with file_path and options.
    
    Returns:
        Status message and job info.
    """
    safe_path = _validate_ingestion_path(request.file_path)

    if not safe_path.exists():
        return {
            "status": "error",
            "message": f"File not found: {safe_path}",
        }

    def _run() -> None:
        from core.db import get_session_factory
        session_factory = get_session_factory()
        with session_factory() as session:
            try:
                stats = ingest_universal_tax_roll(
                    session=session,
                    file_path=safe_path,
                    parish_override=request.parish_override,
                    dry_run=request.dry_run,
                )
                LOGGER.info(f"Universal ingestion completed: {stats.as_dict()}")
            except Exception as e:
                LOGGER.exception(f"Universal ingestion failed: {e}")

    background_tasks.add_task(_run)
    return {
        "status": "started",
        "message": "Universal ingestion started in background",
        "file": str(safe_path),
        "parish_override": request.parish_override,
        "dry_run": request.dry_run,
    }


@router.post("/auctions")
async def ingest_auctions(
    file_path: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> Dict[str, str]:
    """Trigger auction property ingestion in background."""
    safe_path = _validate_ingestion_path(file_path)

    def _run() -> None:
        from core.db import get_session_factory
        session_factory = get_session_factory()
        with session_factory() as session:
            try:
                stats = ingest_universal_tax_roll(
                    session=session,
                    file_path=safe_path,
                )
                LOGGER.info(f"Auction ingestion completed: {stats.as_dict()}")
            except Exception as e:
                LOGGER.exception(f"Auction ingestion failed: {e}")

    background_tasks.add_task(_run)
    return {"message": "Auction ingestion started in background", "file": str(safe_path)}


@router.post("/expired")
async def ingest_expired_listings(
    file_path: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> Dict[str, str]:
    """Trigger expired listings ingestion in background."""
    safe_path = _validate_ingestion_path(file_path)

    def _run() -> None:
        from core.db import get_session_factory
        session_factory = get_session_factory()
        with session_factory() as session:
            try:
                stats = ingest_universal_tax_roll(
                    session=session,
                    file_path=safe_path,
                )
                LOGGER.info(f"Expired listings ingestion completed: {stats.as_dict()}")
            except Exception as e:
                LOGGER.exception(f"Expired listings ingestion failed: {e}")

    background_tasks.add_task(_run)
    return {"message": "Expired listings ingestion started in background", "file": str(safe_path)}


@router.post("/tax-delinquent")
async def ingest_tax_delinquent(
    file_path: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> Dict[str, str]:
    """Trigger tax delinquent list ingestion in background."""
    safe_path = _validate_ingestion_path(file_path)

    def _run() -> None:
        from core.db import get_session_factory
        session_factory = get_session_factory()
        with session_factory() as session:
            try:
                stats = ingest_universal_tax_roll(
                    session=session,
                    file_path=safe_path,
                )
                LOGGER.info(f"Tax delinquent ingestion completed: {stats.as_dict()}")
            except Exception as e:
                LOGGER.exception(f"Tax delinquent ingestion failed: {e}")

    background_tasks.add_task(_run)
    return {"message": "Tax delinquent ingestion started in background", "file": str(safe_path)}


@router.post("/absentee")
async def ingest_absentee_owners(
    file_path: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> Dict[str, str]:
    """Trigger absentee owner list ingestion in background."""
    safe_path = _validate_ingestion_path(file_path)

    def _run() -> None:
        from core.db import get_session_factory
        session_factory = get_session_factory()
        with session_factory() as session:
            try:
                stats = ingest_universal_tax_roll(
                    session=session,
                    file_path=safe_path,
                )
                LOGGER.info(f"Absentee owner ingestion completed: {stats.as_dict()}")
            except Exception as e:
                LOGGER.exception(f"Absentee owner ingestion failed: {e}")

    background_tasks.add_task(_run)
    return {"message": "Absentee owner ingestion started in background", "file": str(safe_path)}


class BulkEnrichmentRequest(BaseModel):
    """Request for bulk parcel enrichment."""
    file_path: str
    parish_override: Optional[str] = None
    update_phones: bool = True
    dry_run: bool = False


@router.post("/enrich")
async def bulk_enrich_parcels(
    request: BulkEnrichmentRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Bulk enrich existing parcels with assessor data.
    
    This updates parcels that were created without assessor fields:
    - lot_size_acres
    - land_assessed_value
    - improvement_assessed_value
    - years_tax_delinquent
    - is_adjudicated
    
    The source file should have a parcel_id/parcel_number column to match
    against existing parcels.
    """
    from ingestion.bulk_enrichment import enrich_parcels_from_file

    safe_path = _validate_ingestion_path(request.file_path)

    if not safe_path.exists():
        return {
            "status": "error",
            "message": f"File not found: {safe_path}",
        }

    def _run() -> None:
        from core.db import get_session_factory
        session_factory = get_session_factory()
        with session_factory() as session:
            try:
                stats = enrich_parcels_from_file(
                    session=session,
                    file_path=safe_path,
                    parish_override=request.parish_override,
                    update_phones=request.update_phones,
                    dry_run=request.dry_run,
                )
                LOGGER.info(f"Bulk enrichment completed: {stats.as_dict()}")
            except Exception as e:
                LOGGER.exception(f"Bulk enrichment failed: {e}")

    background_tasks.add_task(_run)
    return {
        "status": "started",
        "message": "Bulk enrichment started in background",
        "file": str(safe_path),
        "parish_override": request.parish_override,
        "update_phones": request.update_phones,
        "dry_run": request.dry_run,
    }