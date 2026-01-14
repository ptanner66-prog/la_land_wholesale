#!/usr/bin/env python
"""
CONTRACT TOMORROW - Complete workflow script.

This script runs the entire pipeline from enrichment queue to contract candidates.

USAGE:
    python scripts/contract_tomorrow.py queue          # Show enrichment queue
    python scripts/contract_tomorrow.py export-queue   # Export queue to CSV for manual lookup
    python scripts/contract_tomorrow.py import FILE    # Import enrichment CSV
    python scripts/contract_tomorrow.py score          # Score enriched leads only
    python scripts/contract_tomorrow.py candidates     # Show contract candidates
    python scripts/contract_tomorrow.py export         # Export candidates to CSV
    python scripts/contract_tomorrow.py offer LEAD_ID  # Mark lead as offer sent
    python scripts/contract_tomorrow.py contract LEAD_ID # Mark lead as under contract
    python scripts/contract_tomorrow.py full           # Run full pipeline report
"""
import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from core.db import get_session
from services.enrichment_queue import (
    get_enrichment_queue,
    get_enrichment_stats,
    export_enrichment_queue_csv,
)
from services.contract_pipeline import (
    score_enriched_leads,
    get_contract_candidates,
    export_contract_candidates_csv,
    mark_offer_sent,
    mark_under_contract,
)
from scoring.deterministic_engine import CONTACT_THRESHOLD, HOT_THRESHOLD


def show_queue(parish: str = None, limit: int = 20):
    """Show parcels ready for enrichment."""
    with get_session() as session:
        stats = get_enrichment_stats(session, parish=parish)
        parcels = get_enrichment_queue(session, parish=parish, limit=limit)
        
        print("\n" + "=" * 70)
        print("ENRICHMENT QUEUE")
        print("=" * 70)
        print(f"Parish:           {stats['parish']}")
        print(f"Total leads:      {stats['total_leads']:,}")
        print(f"Already enriched: {stats['enriched']:,}")
        print(f"Needs enrichment: {stats['needs_enrichment']:,}")
        print(f"Has phone:        {stats['with_phone']:,}")
        print("=" * 70)
        
        if parcels:
            print(f"\nTop {len(parcels)} parcels ready for enrichment:\n")
            for i, p in enumerate(parcels, 1):
                print(f"{i:2}. {p['canonical_parcel_id']}")
                print(f"    Owner: {p['owner_name']}")
                print(f"    Parish: {p['parish']}")
                addr = p['mailing_address'] or 'N/A'
                print(f"    Mailing: {addr[:60]}{'...' if len(addr) > 60 else ''}")
                print()
        else:
            print("\nNo parcels found in enrichment queue.")


def export_queue(parish: str = None, limit: int = 50, output: str = None):
    """Export enrichment queue to CSV."""
    with get_session() as session:
        csv_data = export_enrichment_queue_csv(session, parish=parish, limit=limit)
        
        if output:
            with open(output, 'w', encoding='utf-8') as f:
                f.write(csv_data)
            print(f"Exported {limit} parcels to {output}")
            print("\nNEXT STEPS:")
            print("1. Look up each parcel on parish tax assessor website")
            print("2. Fill in: lot_size_acres, land_assessed_value, years_tax_delinquent, is_adjudicated")
            print("3. Optionally add phone_primary if you find one")
            print(f"4. Run: python scripts/contract_tomorrow.py import {output}")
        else:
            print(csv_data)


def import_enrichment(filepath: str):
    """Import enrichment data from CSV."""
    # Import inline to avoid module issues
    import csv
    from datetime import datetime, timezone
    from core.db import get_session
    from core.models import Lead, Parcel
    from scoring.deterministic_engine import compute_deterministic_score, get_parish_median_values
    
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
        parish_medians = get_parish_median_values(session)
        
        for row in rows:
            results['processed'] += 1
            parcel_id = row.get('canonical_parcel_id', '').strip()
            
            if not parcel_id:
                results['errors'].append(f"Row {results['processed']}: Missing canonical_parcel_id")
                continue
            
            parcel = session.query(Parcel).filter(Parcel.canonical_parcel_id == parcel_id).first()
            
            if not parcel:
                results['not_found'] += 1
                results['errors'].append(f"Parcel not found: {parcel_id}")
                continue
            
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
                
                lead = session.query(Lead).filter(
                    Lead.parcel_id == parcel.id,
                    Lead.deleted_at.is_(None),
                ).first()
                
                if lead:
                    if row.get('phone_primary'):
                        lead.owner.phone_primary = row['phone_primary'].strip()
                        lead.owner.is_tcpa_safe = True
                    
                    parish = (parcel.parish or '').lower().strip()
                    parish_median = parish_medians.get(parish)
                    
                    score_result = compute_deterministic_score(lead, parish_median)
                    lead.motivation_score = score_result.motivation_score
                    lead.score_details = score_result.to_dict()
                    lead.updated_at = datetime.now(timezone.utc)
                    
                    results['scored'] += 1
                    print(f"  {parcel_id}: Updated + Scored = {score_result.motivation_score}")
        
        session.commit()
    
    print("\n" + "=" * 70)
    print("IMPORT RESULTS")
    print("=" * 70)
    print(f"Processed: {results['processed']}")
    print(f"Updated:   {results['updated']}")
    print(f"Scored:    {results['scored']}")
    print(f"Not found: {results['not_found']}")
    
    if results['errors']:
        print(f"\nErrors ({len(results['errors'])}):")
        for err in results['errors'][:5]:
            print(f"  - {err}")


def run_scoring(parish: str = None):
    """Score only enriched leads."""
    with get_session() as session:
        print("Scoring enriched leads only...")
        results = score_enriched_leads(session, parish=parish)
        
        print("\n" + "=" * 70)
        print("SCORING RESULTS")
        print("=" * 70)
        print(f"Processed:    {results['processed']}")
        print(f"Hot (>={HOT_THRESHOLD}):     {results['hot']}")
        print(f"Contact (>={CONTACT_THRESHOLD}): {results['contact']}")
        print(f"Low:          {results['low']}")
        print(f"Disqualified: {results['disqualified']}")
        print("=" * 70)


def show_candidates(parish: str = None, min_score: int = CONTACT_THRESHOLD, limit: int = 20):
    """Show contract candidates."""
    with get_session() as session:
        candidates = get_contract_candidates(session, parish=parish, min_score=min_score, limit=limit)
        
        print("\n" + "=" * 70)
        print(f"CONTRACT CANDIDATES (Score >= {min_score})")
        print("=" * 70)
        
        if not candidates:
            print("\nNo contract candidates found.")
            print("\nTo get candidates:")
            print("1. Export enrichment queue: python scripts/contract_tomorrow.py export-queue -o queue.csv")
            print("2. Manually fill in parcel data from tax assessor")
            print("3. Import: python scripts/contract_tomorrow.py import queue.csv")
            print("4. Run again: python scripts/contract_tomorrow.py candidates")
            return
        
        print(f"\nFound {len(candidates)} candidates:\n")
        
        for i, c in enumerate(candidates, 1):
            score_label = "[HOT]" if c['score'] >= HOT_THRESHOLD else "[CONTACT]"
            print(f"{i:2}. [{c['score']:2}] {score_label} - Lead #{c['lead_id']}")
            print(f"    Parcel: {c['canonical_parcel_id']}")
            print(f"    Owner:  {c['owner_name']}")
            print(f"    Acres:  {c['acreage']:.2f}")
            print(f"    Value:  ${c['land_assessed_value']:,.0f}")
            print(f"    Offer:  ${c['offer_price']:,.0f} (70%)")
            
            if c['phone']:
                print(f"    Phone:  {c['phone']} [OK]")
            if c['mailing_address']:
                addr = c['mailing_address']
                print(f"    Mail:   {addr[:50]}{'...' if len(addr) > 50 else ''}")
            
            if c['is_adjudicated']:
                print(f"    ** ADJUDICATED **")
            if c['years_delinquent'] > 0:
                print(f"    ** {c['years_delinquent']} years delinquent **")
            
            # Show score factors
            factors = [f for f in c.get('score_factors', []) if f.get('value', 0) > 0]
            if factors:
                print(f"    Factors: {', '.join(f['name'] for f in factors)}")
            
            print()


def export_candidates(parish: str = None, min_score: int = CONTACT_THRESHOLD, output: str = None):
    """Export contract candidates to CSV."""
    with get_session() as session:
        csv_data = export_contract_candidates_csv(session, parish=parish, min_score=min_score)
        
        if output:
            with open(output, 'w', encoding='utf-8') as f:
                f.write(csv_data)
            print(f"Exported to {output}")
        else:
            print(csv_data)


def mark_offer(lead_id: int, amount: float = None):
    """Mark lead as offer sent."""
    with get_session() as session:
        if mark_offer_sent(session, lead_id, amount):
            print(f"[OK] Lead {lead_id} marked as OFFER SENT")
            if amount:
                print(f"  Offer amount: ${amount:,.0f}")
        else:
            print(f"[ERROR] Lead {lead_id} not found")


def mark_contract(lead_id: int, amount: float = None):
    """Mark lead as under contract."""
    with get_session() as session:
        if mark_under_contract(session, lead_id, amount):
            print(f"[OK] Lead {lead_id} marked as UNDER CONTRACT")
            if amount:
                print(f"  Contract price: ${amount:,.0f}")
        else:
            print(f"[ERROR] Lead {lead_id} not found")


def full_report(parish: str = None):
    """Run full pipeline report."""
    print("\n" + "=" * 70)
    print("CONTRACT TOMORROW - FULL PIPELINE REPORT")
    print("=" * 70)
    
    with get_session() as session:
        # Stats
        stats = get_enrichment_stats(session, parish=parish)
        print(f"\n[DATABASE STATUS] ({stats['parish']})")
        print(f"   Total leads:      {stats['total_leads']:,}")
        print(f"   Enriched:         {stats['enriched']:,}")
        print(f"   Needs enrichment: {stats['needs_enrichment']:,}")
        print(f"   Has phone:        {stats['with_phone']:,}")
        
        # Score enriched
        print(f"\n[SCORING ENRICHED LEADS]...")
        results = score_enriched_leads(session, parish=parish)
        print(f"   Processed:    {results['processed']}")
        print(f"   Hot (>={HOT_THRESHOLD}):     {results['hot']}")
        print(f"   Contact (>={CONTACT_THRESHOLD}): {results['contact']}")
        
        # Candidates
        candidates = get_contract_candidates(session, parish=parish, limit=10)
        print(f"\n[TOP CONTRACT CANDIDATES]")
        
        if candidates:
            for i, c in enumerate(candidates[:5], 1):
                print(f"   {i}. [{c['score']}] {c['owner_name'][:30]} - ${c['offer_price']:,.0f}")
        else:
            print("   No candidates yet. Enrich some parcels first!")
    
    print("\n" + "=" * 70)
    print("NEXT STEPS FOR TOMORROW")
    print("=" * 70)
    print("""
1. EXPORT ENRICHMENT QUEUE:
   python scripts/contract_tomorrow.py export-queue -p "East Baton Rouge" -o queue.csv

2. MANUALLY ENRICH (10-20 parcels):
   - Go to parish tax assessor website
   - Look up each parcel ID
   - Fill in: lot_size_acres, land_assessed_value, years_tax_delinquent, is_adjudicated
   - Add phone if available

3. IMPORT ENRICHED DATA:
   python scripts/contract_tomorrow.py import queue.csv

4. VIEW CONTRACT CANDIDATES:
   python scripts/contract_tomorrow.py candidates

5. EXPORT FOR OUTREACH:
   python scripts/contract_tomorrow.py export -o candidates.csv

6. CONTACT SELLERS:
   - Call or mail top candidates
   - Make offer at 70% of assessed value
   - Get signed purchase agreement

7. MARK PROGRESS:
   python scripts/contract_tomorrow.py offer LEAD_ID --amount 5000
   python scripts/contract_tomorrow.py contract LEAD_ID --amount 5500
""")


def main():
    parser = argparse.ArgumentParser(
        description="Contract Tomorrow - Full pipeline workflow",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument('--parish', '-p', default=None, help='Filter by parish')
    
    subparsers = parser.add_subparsers(dest='command')
    
    # Queue
    queue_p = subparsers.add_parser('queue', help='Show enrichment queue')
    queue_p.add_argument('--limit', '-l', type=int, default=20)
    
    # Export queue
    eq_p = subparsers.add_parser('export-queue', help='Export enrichment queue to CSV')
    eq_p.add_argument('--limit', '-l', type=int, default=50)
    eq_p.add_argument('--output', '-o', default='enrichment_queue.csv')
    
    # Import
    imp_p = subparsers.add_parser('import', help='Import enrichment CSV')
    imp_p.add_argument('filepath', help='CSV file path')
    
    # Score
    subparsers.add_parser('score', help='Score enriched leads')
    
    # Candidates
    cand_p = subparsers.add_parser('candidates', help='Show contract candidates')
    cand_p.add_argument('--min-score', '-s', type=int, default=CONTACT_THRESHOLD)
    cand_p.add_argument('--limit', '-l', type=int, default=20)
    
    # Export candidates
    exp_p = subparsers.add_parser('export', help='Export candidates to CSV')
    exp_p.add_argument('--min-score', '-s', type=int, default=CONTACT_THRESHOLD)
    exp_p.add_argument('--output', '-o', default='contract_candidates.csv')
    
    # Offer
    offer_p = subparsers.add_parser('offer', help='Mark lead as offer sent')
    offer_p.add_argument('lead_id', type=int)
    offer_p.add_argument('--amount', '-a', type=float)
    
    # Contract
    contract_p = subparsers.add_parser('contract', help='Mark lead as under contract')
    contract_p.add_argument('lead_id', type=int)
    contract_p.add_argument('--amount', '-a', type=float)
    
    # Full
    subparsers.add_parser('full', help='Run full pipeline report')
    
    args = parser.parse_args()
    parish = args.parish
    
    if args.command == 'queue':
        show_queue(parish=parish, limit=args.limit)
    elif args.command == 'export-queue':
        export_queue(parish=parish, limit=args.limit, output=args.output)
    elif args.command == 'import':
        import_enrichment(args.filepath)
    elif args.command == 'score':
        run_scoring(parish=parish)
    elif args.command == 'candidates':
        show_candidates(parish=parish, min_score=args.min_score, limit=args.limit)
    elif args.command == 'export':
        export_candidates(parish=parish, min_score=args.min_score, output=args.output)
    elif args.command == 'offer':
        mark_offer(args.lead_id, args.amount)
    elif args.command == 'contract':
        mark_contract(args.lead_id, args.amount)
    elif args.command == 'full':
        full_report(parish=parish)
    else:
        full_report(parish=parish)


if __name__ == "__main__":
    main()

