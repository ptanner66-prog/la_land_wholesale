"""Ingestion domain service - core business logic for data ingestion."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from core.config import get_settings
from core.logging_config import get_logger
from core.models import Lead, Owner, Parcel, Party
from core.types import IngestionSummary
from ingestion import pipeline as ingestion_pipeline

LOGGER = get_logger(__name__)
SETTINGS = get_settings()


@dataclass
class IngestionResult:
    """Result of an ingestion operation."""
    
    stage: str
    success: bool
    records_processed: int
    records_created: int
    records_updated: int
    records_skipped: int
    errors: List[str] = field(default_factory=list)
    duration_seconds: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "stage": self.stage,
            "success": self.success,
            "records_processed": self.records_processed,
            "records_created": self.records_created,
            "records_updated": self.records_updated,
            "records_skipped": self.records_skipped,
            "errors": self.errors,
            "duration_seconds": self.duration_seconds,
        }


@dataclass
class FullIngestionResult:
    """Result of a full ingestion pipeline run."""
    
    success: bool
    stages: List[IngestionResult]
    total_duration_seconds: float
    started_at: datetime
    completed_at: datetime
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "success": self.success,
            "stages": [s.to_dict() for s in self.stages],
            "total_duration_seconds": self.total_duration_seconds,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat(),
        }


class IngestionService:
    """Service for data ingestion operations."""
    
    def __init__(self, session: Optional[Session] = None) -> None:
        """
        Initialize the ingestion service.
        
        Note: Ingestion typically creates its own sessions per stage,
        so session is optional here.
        """
        self.session = session
    
    def run_full_pipeline(
        self,
        tax_roll_path: Optional[Path] = None,
        adjudicated_path: Optional[Path] = None,
        gis_path: Optional[Path] = None,
    ) -> FullIngestionResult:
        """
        Run the full ingestion pipeline.
        
        Args:
            tax_roll_path: Path to tax roll CSV (uses default if None).
            adjudicated_path: Path to adjudicated CSV (uses default if None).
            gis_path: Path to GIS file (uses default if None).
        
        Returns:
            FullIngestionResult with stage-by-stage details.
        """
        started_at = datetime.now(timezone.utc)
        
        try:
            # The existing pipeline returns an IngestionSummary
            summary = ingestion_pipeline.run_full_ingestion(
                tax_roll_path=tax_roll_path,
                adjudicated_path=adjudicated_path,
                gis_path=gis_path,
            )
            
            completed_at = datetime.now(timezone.utc)
            duration = (completed_at - started_at).total_seconds()
            
            # Convert summary to our result format
            # IngestionSummary has fields: tax_roll, adjudicated, gis (Dict[str, int])
            stages = []
            
            # Tax roll stage
            tax_stats = summary.tax_roll or {}
            stages.append(IngestionResult(
                stage="tax_roll",
                success="error" not in tax_stats,
                records_processed=tax_stats.get("rows_processed", 0),
                records_created=tax_stats.get("created_parcels", 0) + tax_stats.get("created_leads", 0),
                records_updated=tax_stats.get("updated_parcels", 0),
                records_skipped=tax_stats.get("rows_skipped", 0),
                errors=[str(tax_stats.get("message"))] if "error" in tax_stats else [],
            ))
            
            # Adjudicated stage
            adj_stats = summary.adjudicated or {}
            stages.append(IngestionResult(
                stage="adjudicated",
                success="error" not in adj_stats,
                records_processed=adj_stats.get("rows_processed", 0),
                records_created=0,
                records_updated=adj_stats.get("parcels_updated", 0),
                records_skipped=adj_stats.get("rows_skipped", 0),
                errors=[str(adj_stats.get("message"))] if "error" in adj_stats else [],
            ))
            
            # GIS stage
            gis_stats = summary.gis or {}
            stages.append(IngestionResult(
                stage="gis",
                success="error" not in gis_stats,
                records_processed=gis_stats.get("rows_processed", 0),
                records_created=0,
                records_updated=gis_stats.get("parcels_updated", 0),
                records_skipped=gis_stats.get("rows_skipped", 0),
                errors=[str(gis_stats.get("message"))] if "error" in gis_stats else [],
            ))
            
            all_success = all(s.success for s in stages)
            
            return FullIngestionResult(
                success=all_success,
                stages=stages,
                total_duration_seconds=duration,
                started_at=started_at,
                completed_at=completed_at,
            )
            
        except Exception as e:
            LOGGER.exception("Full ingestion pipeline failed: %s", e)
            completed_at = datetime.now(timezone.utc)
            duration = (completed_at - started_at).total_seconds()
            
            return FullIngestionResult(
                success=False,
                stages=[IngestionResult(
                    stage="pipeline",
                    success=False,
                    records_processed=0,
                    records_created=0,
                    records_updated=0,
                    records_skipped=0,
                    errors=[str(e)],
                    duration_seconds=duration,
                )],
                total_duration_seconds=duration,
                started_at=started_at,
                completed_at=completed_at,
            )
    
    def run_pipeline(
        self,
        tax_roll_path: Optional[str] = None,
        gis_path: Optional[str] = None,
        adjudicated_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Run the ingestion pipeline (simplified interface).
        
        Args:
            tax_roll_path: Path to tax roll CSV.
            gis_path: Path to GIS file.
            adjudicated_path: Path to adjudicated properties CSV.
            
        Returns:
            Dictionary of statistics.
        """
        result = self.run_full_pipeline(
            tax_roll_path=Path(tax_roll_path) if tax_roll_path else None,
            adjudicated_path=Path(adjudicated_path) if adjudicated_path else None,
            gis_path=Path(gis_path) if gis_path else None,
        )
        return result.to_dict()
    
    def get_data_statistics(self, session: Session) -> Dict[str, Any]:
        """
        Get statistics about ingested data.
        
        Args:
            session: Database session.
        
        Returns:
            Dictionary with counts and statistics matching frontend IngestionSummary type.
        """
        from datetime import datetime, timezone
        
        # Get parcel counts
        total_parcels = session.query(func.count(Parcel.id)).scalar() or 0
        adjudicated_count = session.query(func.count(Parcel.id)).filter(
            Parcel.is_adjudicated.is_(True)
        ).scalar() or 0
        with_geometry = session.query(func.count(Parcel.id)).filter(
            Parcel.geom.isnot(None)
        ).scalar() or 0
        
        # Get owner/party/lead counts
        total_owners = session.query(func.count(Owner.id)).scalar() or 0
        total_parties = session.query(func.count(Party.id)).scalar() or 0
        total_leads = session.query(func.count(Lead.id)).scalar() or 0
        
        # Return in frontend-expected format
        return {
            "tax_roll": {
                "total": total_parcels,
                "new": 0,  # Would need tracking to compute accurately
                "updated": 0,
            },
            "adjudicated": {
                "total": adjudicated_count,
                "new": 0,
            },
            "gis": {
                "total": with_geometry,
                "updated": 0,
            },
            "parties_created": total_parties,
            "owners_created": total_owners,
            "leads_created": total_leads,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            # Also include detailed breakdown for other uses
            "details": {
                "parcels": {
                    "total": total_parcels,
                    "adjudicated": adjudicated_count,
                    "tax_delinquent": session.query(func.count(Parcel.id)).filter(
                        Parcel.years_tax_delinquent > 0
                    ).scalar() or 0,
                    "with_geometry": with_geometry,
                },
                "owners": {
                    "total": total_owners,
                    "tcpa_safe": session.query(func.count(Owner.id)).filter(
                        Owner.is_tcpa_safe.is_(True)
                    ).scalar() or 0,
                    "with_phone": session.query(func.count(Owner.id)).filter(
                        Owner.phone_primary.isnot(None),
                        Owner.phone_primary != "",
                    ).scalar() or 0,
                },
                "parties": {
                    "total": total_parties,
                },
                "leads": {
                    "total": total_leads,
                },
            },
        }


__all__ = ["IngestionService", "IngestionResult", "FullIngestionResult"]
