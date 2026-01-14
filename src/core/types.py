"""Shared dataclasses and type helpers."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


@dataclass(slots=True, frozen=True)
class IngestionSummary:
    """Snapshot of ingestion results across all upstream sources."""

    tax_roll: Dict[str, int]
    adjudicated: Dict[str, int]
    gis: Dict[str, int]

    def as_dict(self) -> Dict[str, Dict[str, int]]:
        return {
            "tax_roll": self.tax_roll,
            "adjudicated": self.adjudicated,
            "gis": self.gis,
        }

    @property
    def total_rows_processed(self) -> int:
        return sum(stat.get("rows_processed", 0) for stat in self.as_dict().values())

    def summary(self, max_metrics_per_source: int = 3) -> str:
        """Return a compact human-readable summary for logging/CLI output."""

        def _format_stats(name: str, stats: Dict[str, int]) -> str:
            priority_keys = (
                "rows_processed",
                "rows_skipped",
                "rows_errored",
                "parcels_updated",
                "parcels_missing",
                "created_leads",
                "created_parcels",
                "updated_parcels",
            )
            ordered_keys = [key for key in priority_keys if key in stats]
            if len(ordered_keys) < max_metrics_per_source:
                extras = [key for key in sorted(stats.keys()) if key not in ordered_keys]
                ordered_keys.extend(extras)
            metrics = ", ".join(f"{key}={stats[key]}" for key in ordered_keys[:max_metrics_per_source])
            return f"{name}({metrics or 'no-stats'})"

        return " | ".join(_format_stats(name, stats) for name, stats in self.as_dict().items())

    def __str__(self) -> str:  # pragma: no cover - convenience for logging
        return self.summary()


__all__ = ["IngestionSummary"]
