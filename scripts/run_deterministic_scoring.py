"""Run deterministic scoring on all leads and report results."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from core.db import get_session
from core.models import Lead
from scoring.deterministic_engine import (
    score_all_leads_deterministic,
    CONTACT_THRESHOLD,
    HOT_THRESHOLD,
    REJECT_THRESHOLD,
)
from sqlalchemy import func


def main():
    print("=" * 70)
    print("DETERMINISTIC LEAD SCORING")
    print("=" * 70)
    print(f"\nThresholds:")
    print(f"  Contact: >= {CONTACT_THRESHOLD}")
    print(f"  Hot:     >= {HOT_THRESHOLD}")
    print(f"  Reject:  <  {REJECT_THRESHOLD}")
    print()
    
    with get_session() as session:
        # Run scoring
        print("Running deterministic scoring...")
        result = score_all_leads_deterministic(session)
        
        print("\n" + "=" * 70)
        print("RESULTS")
        print("=" * 70)
        print(f"Total Processed:  {result['total_processed']:,}")
        print(f"Disqualified:     {result['disqualified']:,}")
        print(f"Qualified:        {result['qualified']:,}")
        print(f"Hot Leads:        {result['hot_leads']:,}")
        print(f"Contact Ready:    {result['contact_ready']:,}")
        print(f"Average Score:    {result['average_score']:.1f}")
        print(f"Duration:         {result['duration_seconds']:.2f}s")
        
        # Get distribution
        print("\n" + "=" * 70)
        print("SCORE DISTRIBUTION")
        print("=" * 70)
        
        buckets = [
            (0, REJECT_THRESHOLD - 1, "Reject"),
            (REJECT_THRESHOLD, CONTACT_THRESHOLD - 1, "Low"),
            (CONTACT_THRESHOLD, HOT_THRESHOLD - 1, "Contact"),
            (HOT_THRESHOLD, 100, "Hot"),
        ]
        
        for low, high, label in buckets:
            count = session.query(func.count(Lead.id)).filter(
                Lead.motivation_score >= low,
                Lead.motivation_score <= high,
                Lead.deleted_at.is_(None),
            ).scalar() or 0
            pct = (count / result['total_processed'] * 100) if result['total_processed'] > 0 else 0
            bar = "█" * int(pct / 2)
            print(f"  {label:10} ({low:2}-{high:3}): {count:6,} ({pct:5.1f}%) {bar}")
        
        # Show sample hot leads
        print("\n" + "=" * 70)
        print("SAMPLE HOT LEADS (Top 10)")
        print("=" * 70)
        
        hot_leads = (
            session.query(Lead)
            .filter(
                Lead.motivation_score >= HOT_THRESHOLD,
                Lead.deleted_at.is_(None),
            )
            .order_by(Lead.motivation_score.desc())
            .limit(10)
            .all()
        )
        
        if hot_leads:
            for lead in hot_leads:
                owner_name = lead.owner.party.display_name if lead.owner and lead.owner.party else "Unknown"
                parish = lead.parcel.parish if lead.parcel else "Unknown"
                acres = float(lead.parcel.lot_size_acres or 0) if lead.parcel else 0
                phone = lead.owner.phone_primary if lead.owner else "N/A"
                
                print(f"\n  Lead #{lead.id} - Score: {lead.motivation_score}")
                print(f"    Owner:  {owner_name[:40]}")
                print(f"    Parish: {parish}")
                print(f"    Acres:  {acres:.2f}")
                print(f"    Phone:  {phone}")
                
                # Show score breakdown
                if lead.score_details:
                    factors = lead.score_details.get("factors", [])
                    if factors:
                        print(f"    Factors:")
                        for f in factors:
                            if f.get("value", 0) > 0:
                                print(f"      + {f.get('value', 0):2} {f.get('label', f.get('name', 'Unknown'))}")
        else:
            print("  No hot leads found!")
        
        # Show disqualification reasons
        print("\n" + "=" * 70)
        print("DISQUALIFICATION BREAKDOWN")
        print("=" * 70)
        
        disqualified_leads = (
            session.query(Lead)
            .filter(
                Lead.motivation_score == 0,
                Lead.deleted_at.is_(None),
            )
            .limit(1000)
            .all()
        )
        
        reasons = {}
        for lead in disqualified_leads:
            if lead.score_details:
                reason = lead.score_details.get("disqualified_reason", "unknown")
                reason_key = reason.split(":")[0] if reason else "unknown"
                reasons[reason_key] = reasons.get(reason_key, 0) + 1
        
        for reason, count in sorted(reasons.items(), key=lambda x: -x[1]):
            print(f"  {reason}: {count:,}")
        
        print("\n" + "=" * 70)
        print("DONE")
        print("=" * 70)


if __name__ == "__main__":
    main()

