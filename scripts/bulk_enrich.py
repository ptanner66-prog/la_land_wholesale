#!/usr/bin/env python
"""
Bulk Parcel Enrichment CLI.

This script enriches existing parcels with assessor data from a CSV/XLSX file.

USAGE:
    python scripts/bulk_enrich.py FILE [--parish PARISH] [--dry-run] [--no-phones]
    
EXAMPLE:
    python scripts/bulk_enrich.py data/raw/ebr_assessor_export.csv --parish "East Baton Rouge"
    
CSV FORMAT:
    Required: parcel_number OR parcel_id
    Optional: acreage, land_value, improvement_value, years_tax_delinquent, is_adjudicated, phone
"""
import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from core.db import get_session
from core.models import Parcel, Lead
from ingestion.bulk_enrichment import enrich_parcels_from_file
from sqlalchemy import func


def show_parcel_stats():
    """Show current parcel statistics."""
    with get_session() as session:
        total = session.query(func.count(Parcel.id)).scalar() or 0
        with_acres = session.query(func.count(Parcel.id)).filter(
            Parcel.lot_size_acres.isnot(None), 
            Parcel.lot_size_acres > 0
        ).scalar() or 0
        with_land_val = session.query(func.count(Parcel.id)).filter(
            Parcel.land_assessed_value.isnot(None),
            Parcel.land_assessed_value > 0
        ).scalar() or 0
        with_delinq = session.query(func.count(Parcel.id)).filter(
            Parcel.years_tax_delinquent.isnot(None),
            Parcel.years_tax_delinquent > 0
        ).scalar() or 0
        adjudicated = session.query(func.count(Parcel.id)).filter(
            Parcel.is_adjudicated == True
        ).scalar() or 0
        
        print("\n" + "=" * 60)
        print("PARCEL DATA STATISTICS")
        print("=" * 60)
        print(f"Total parcels:       {total:,}")
        print(f"With acreage:        {with_acres:,} ({with_acres/total*100:.2f}%)" if total else "With acreage: 0")
        print(f"With land value:     {with_land_val:,} ({with_land_val/total*100:.2f}%)" if total else "With land value: 0")
        print(f"With delinquency:    {with_delinq:,} ({with_delinq/total*100:.2f}%)" if total else "With delinquency: 0")
        print(f"Adjudicated:         {adjudicated:,} ({adjudicated/total*100:.2f}%)" if total else "Adjudicated: 0")
        print("=" * 60)
        
        return {
            "total": total,
            "with_acres": with_acres,
            "with_land_val": with_land_val,
            "with_delinq": with_delinq,
            "adjudicated": adjudicated,
        }


def main():
    parser = argparse.ArgumentParser(
        description="Bulk enrich parcels with assessor data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument("file", nargs="?", help="Path to CSV/XLSX file with assessor data")
    parser.add_argument("--parish", "-p", help="Override parish name")
    parser.add_argument("--dry-run", "-d", action="store_true", help="Don't commit changes")
    parser.add_argument("--no-phones", action="store_true", help="Don't update phone numbers")
    parser.add_argument("--stats", "-s", action="store_true", help="Show current statistics only")
    
    args = parser.parse_args()
    
    # Show stats before
    print("\nBEFORE ENRICHMENT:")
    before_stats = show_parcel_stats()
    
    if args.stats or not args.file:
        if not args.file:
            print("\nNo file specified. Use --help for usage.")
        return
    
    file_path = Path(args.file)
    if not file_path.exists():
        print(f"\nERROR: File not found: {file_path}")
        sys.exit(1)
    
    print(f"\nEnriching parcels from: {file_path}")
    if args.parish:
        print(f"Parish override: {args.parish}")
    if args.dry_run:
        print("DRY RUN - no changes will be saved")
    
    # Run enrichment
    with get_session() as session:
        stats = enrich_parcels_from_file(
            session=session,
            file_path=file_path,
            parish_override=args.parish,
            update_phones=not args.no_phones,
            dry_run=args.dry_run,
        )
    
    # Show results
    print("\n" + "=" * 60)
    print("ENRICHMENT RESULTS")
    print("=" * 60)
    print(f"Rows processed:      {stats.rows_processed:,}")
    print(f"Rows skipped:        {stats.rows_skipped:,}")
    print(f"Parcels found:       {stats.parcels_found:,}")
    print(f"Parcels not found:   {stats.parcels_not_found:,}")
    print(f"Parcels enriched:    {stats.parcels_enriched:,}")
    print(f"Phones added:        {stats.phones_added:,}")
    print(f"Errors:              {stats.errors:,}")
    print("\nField updates:")
    print(f"  Acreage:           {stats.acres_updated:,}")
    print(f"  Land value:        {stats.land_value_updated:,}")
    print(f"  Improvement value: {stats.improvement_value_updated:,}")
    print(f"  Delinquency:       {stats.delinquency_updated:,}")
    print(f"  Adjudication:      {stats.adjudication_updated:,}")
    print("=" * 60)
    
    if stats.warnings:
        print("\nWarnings:")
        for w in stats.warnings[:5]:
            print(f"  - {w}")
    
    # Show stats after
    if not args.dry_run:
        print("\nAFTER ENRICHMENT:")
        after_stats = show_parcel_stats()
        
        # Show delta
        print("\nCHANGE:")
        print(f"  Acreage:     +{after_stats['with_acres'] - before_stats['with_acres']:,}")
        print(f"  Land value:  +{after_stats['with_land_val'] - before_stats['with_land_val']:,}")
        print(f"  Delinquency: +{after_stats['with_delinq'] - before_stats['with_delinq']:,}")
        print(f"  Adjudicated: +{after_stats['adjudicated'] - before_stats['adjudicated']:,}")


if __name__ == "__main__":
    main()

