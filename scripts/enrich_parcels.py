"""
Manual Parcel Enrichment Script.

This script allows you to enrich parcels from a CSV file.

CSV FORMAT (columns):
- canonical_parcel_id (required)
- lot_size_acres
- land_assessed_value
- years_tax_delinquent
- is_adjudicated (true/false/1/0)
- phone_primary (optional - will update owner)

USAGE:
    python scripts/enrich_parcels.py import enrichment_data.csv
    python scripts/enrich_parcels.py export --parish "East Baton Rouge" --limit 50
    python scripts/enrich_parcels.py stats --parish "East Baton Rouge"
"""
import sys
import csv
import argparse
from pathlib import Path
from typing import Dict, Any, List

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from core.db import get_session
from core.models import Lead, Parcel, Owner
from services.enrichment_queue import (
    get_enrichment_queue,
    get_enrichment_stats,
    export_enrichment_queue_csv,
)
from scoring.deterministic_engine import (
    compute_deterministic_score,
    get_parish_median_values,
)


def import_enrichment_csv(filepath: str) -> Dict[str, Any]:
    """
    Import enrichment data from CSV and update parcels.
    
    Args:
        filepath: Path to CSV file.
    
    Returns:
        Summary of updates.
    """
    results = {
        'processed': 0,
        'updated': 0,
        'not_found': 0,
        'errors': [],
        'scored': 0,
    }
    
    with open(filepath, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    
    print(f"Found {len(rows)} rows in CSV")
    
    with get_session() as session:
        # Pre-compute parish medians for scoring
        parish_medians = get_parish_median_values(session)
        
        for row in rows:
            results['processed'] += 1
            parcel_id = row.get('canonical_parcel_id', '').strip()
            
            if not parcel_id:
                results['errors'].append(f"Row {results['processed']}: Missing canonical_parcel_id")
                continue
            
            # Find parcel
            parcel = session.query(Parcel).filter(
                Parcel.canonical_parcel_id == parcel_id
            ).first()
            
            if not parcel:
                results['not_found'] += 1
                results['errors'].append(f"Parcel not found: {parcel_id}")
                continue
            
            # Update parcel fields
            updated = False
            
            if row.get('lot_size_acres'):
                try:
                    parcel.lot_size_acres = float(row['lot_size_acres'])
                    updated = True
                except ValueError:
                    pass
            
            if row.get('land_assessed_value'):
                try:
                    parcel.land_assessed_value = float(row['land_assessed_value'])
                    updated = True
                except ValueError:
                    pass
            
            if row.get('years_tax_delinquent'):
                try:
                    parcel.years_tax_delinquent = int(row['years_tax_delinquent'])
                    updated = True
                except ValueError:
                    pass
            
            if row.get('is_adjudicated'):
                val = row['is_adjudicated'].lower().strip()
                parcel.is_adjudicated = val in ('true', '1', 'yes', 'y')
                updated = True
            
            if updated:
                results['updated'] += 1
                
                # Find lead for this parcel and re-score
                lead = session.query(Lead).filter(
                    Lead.parcel_id == parcel.id,
                    Lead.deleted_at.is_(None),
                ).first()
                
                if lead:
                    # Update phone if provided
                    if row.get('phone_primary'):
                        lead.owner.phone_primary = row['phone_primary'].strip()
                        lead.owner.is_tcpa_safe = True  # Assume manual entry is safe
                    
                    # Re-score
                    parish = (parcel.parish or '').lower().strip()
                    parish_median = parish_medians.get(parish)
                    
                    score_result = compute_deterministic_score(lead, parish_median)
                    lead.motivation_score = score_result.motivation_score
                    lead.score_details = score_result.to_dict()
                    
                    results['scored'] += 1
                    print(f"  {parcel_id}: Updated + Scored = {score_result.motivation_score}")
        
        session.commit()
    
    return results


def export_queue(parish: str, limit: int, output: str = None):
    """Export enrichment queue to CSV."""
    with get_session() as session:
        csv_data = export_enrichment_queue_csv(session, parish=parish, limit=limit)
        
        if output:
            with open(output, 'w', encoding='utf-8') as f:
                f.write(csv_data)
            print(f"Exported to {output}")
        else:
            print(csv_data)


def show_stats(parish: str = None):
    """Show enrichment queue statistics."""
    with get_session() as session:
        stats = get_enrichment_stats(session, parish=parish)
        
        print("\n" + "=" * 50)
        print("ENRICHMENT QUEUE STATS")
        print("=" * 50)
        print(f"Parish:            {stats['parish']}")
        print(f"Total leads:       {stats['total_leads']:,}")
        print(f"Already enriched:  {stats['enriched']:,}")
        print(f"Needs enrichment:  {stats['needs_enrichment']:,}")
        print(f"Has phone:         {stats['with_phone']:,}")
        print(f"Vacant land:       {stats['vacant_land']:,}")
        print("=" * 50)


def show_queue(parish: str = None, limit: int = 20):
    """Show enrichment queue."""
    with get_session() as session:
        parcels = get_enrichment_queue(session, parish=parish, limit=limit)
        
        print(f"\nFound {len(parcels)} parcels ready for enrichment:\n")
        
        for i, p in enumerate(parcels, 1):
            print(f"{i}. {p['canonical_parcel_id']}")
            print(f"   Owner: {p['owner_name']}")
            print(f"   Address: {p['situs_address'] or 'N/A'}")
            print(f"   Mailing: {p['mailing_address'][:50]}..." if p['mailing_address'] and len(p['mailing_address']) > 50 else f"   Mailing: {p['mailing_address']}")
            print(f"   Parish: {p['parish']}")
            print()


def main():
    parser = argparse.ArgumentParser(description="Parcel Enrichment Tool")
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # Import command
    import_parser = subparsers.add_parser('import', help='Import enrichment data from CSV')
    import_parser.add_argument('filepath', help='Path to CSV file')
    
    # Export command
    export_parser = subparsers.add_parser('export', help='Export enrichment queue to CSV')
    export_parser.add_argument('--parish', '-p', help='Filter by parish')
    export_parser.add_argument('--limit', '-l', type=int, default=50, help='Max parcels')
    export_parser.add_argument('--output', '-o', help='Output file path')
    
    # Stats command
    stats_parser = subparsers.add_parser('stats', help='Show enrichment statistics')
    stats_parser.add_argument('--parish', '-p', help='Filter by parish')
    
    # Queue command
    queue_parser = subparsers.add_parser('queue', help='Show enrichment queue')
    queue_parser.add_argument('--parish', '-p', help='Filter by parish')
    queue_parser.add_argument('--limit', '-l', type=int, default=20, help='Max parcels')
    
    args = parser.parse_args()
    
    if args.command == 'import':
        print(f"Importing enrichment data from {args.filepath}...")
        results = import_enrichment_csv(args.filepath)
        
        print("\n" + "=" * 50)
        print("IMPORT RESULTS")
        print("=" * 50)
        print(f"Processed: {results['processed']}")
        print(f"Updated:   {results['updated']}")
        print(f"Scored:    {results['scored']}")
        print(f"Not found: {results['not_found']}")
        if results['errors']:
            print(f"\nErrors ({len(results['errors'])}):")
            for err in results['errors'][:10]:
                print(f"  - {err}")
    
    elif args.command == 'export':
        export_queue(args.parish, args.limit, args.output)
    
    elif args.command == 'stats':
        show_stats(args.parish)
    
    elif args.command == 'queue':
        show_queue(args.parish, args.limit)
    
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

