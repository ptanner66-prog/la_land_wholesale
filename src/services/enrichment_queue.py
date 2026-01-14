"""
Enrichment Queue Service - Identifies parcels ready for manual enrichment.

This module provides queries to find parcels that:
- Are vacant land (no improvements)
- Are privately owned (not government)
- Have owner mailing address
- Are NOT already enriched (missing acreage or land value)
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import and_, or_, func
from sqlalchemy.orm import Session

from core.models import Lead, Parcel, Owner, Party
from core.logging_config import get_logger

LOGGER = get_logger(__name__)


def get_enrichment_queue(
    session: Session,
    parish: Optional[str] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """
    Get parcels ready for enrichment.
    
    Criteria:
    - Vacant land (improvement_assessed_value == 0 or NULL)
    - Privately owned (party_type not government/municipality/etc)
    - Has owner mailing address
    - NOT already enriched (acreage OR land value missing)
    
    Args:
        session: Database session.
        parish: Filter by parish name (optional).
        limit: Max parcels to return.
    
    Returns:
        List of parcel dicts ready for enrichment.
    """
    # Government owner types to exclude
    gov_types = [
        'government', 'municipality', 'utility', 'state', 'federal', 
        'county', 'city', 'parish', 'school', 'church'
    ]
    
    query = (
        session.query(
            Lead.id.label('lead_id'),
            Parcel.id.label('parcel_id'),
            Parcel.canonical_parcel_id,
            Parcel.parish,
            Parcel.situs_address,
            Parcel.lot_size_acres,
            Parcel.land_assessed_value,
            Parcel.improvement_assessed_value,
            Parcel.is_adjudicated,
            Parcel.years_tax_delinquent,
            Party.display_name.label('owner_name'),
            Party.raw_mailing_address.label('mailing_address'),
            Party.party_type,
            Owner.phone_primary,
        )
        .join(Lead.parcel)
        .join(Lead.owner)
        .join(Owner.party)
        .filter(
            # Not deleted
            Lead.deleted_at.is_(None),
            # Vacant land (no improvement or low improvement)
            or_(
                Parcel.improvement_assessed_value.is_(None),
                Parcel.improvement_assessed_value == 0,
            ),
            # Has mailing address
            Party.raw_mailing_address.isnot(None),
            Party.raw_mailing_address != '',
            # Not government owned
            ~Party.party_type.in_(gov_types),
            # NOT already enriched (missing acreage OR land value)
            or_(
                Parcel.lot_size_acres.is_(None),
                Parcel.lot_size_acres == 0,
                Parcel.land_assessed_value.is_(None),
                Parcel.land_assessed_value == 0,
            ),
        )
    )
    
    if parish:
        query = query.filter(func.lower(Parcel.parish) == parish.lower())
    
    results = query.limit(limit).all()
    
    return [
        {
            'lead_id': r.lead_id,
            'parcel_id': r.parcel_id,
            'canonical_parcel_id': r.canonical_parcel_id,
            'parish': r.parish,
            'situs_address': r.situs_address,
            'lot_size_acres': float(r.lot_size_acres) if r.lot_size_acres else None,
            'land_assessed_value': float(r.land_assessed_value) if r.land_assessed_value else None,
            'improvement_assessed_value': float(r.improvement_assessed_value) if r.improvement_assessed_value else None,
            'is_adjudicated': r.is_adjudicated,
            'years_tax_delinquent': r.years_tax_delinquent,
            'owner_name': r.owner_name,
            'mailing_address': r.mailing_address,
            'party_type': r.party_type,
            'phone_primary': r.phone_primary,
            'needs_enrichment': True,
        }
        for r in results
    ]


def get_enrichment_stats(session: Session, parish: Optional[str] = None) -> Dict[str, int]:
    """
    Get enrichment queue statistics.
    
    Args:
        session: Database session.
        parish: Filter by parish name (optional).
    
    Returns:
        Dict with counts.
    """
    base_query = session.query(func.count(Lead.id)).join(Lead.parcel).join(Lead.owner).join(Owner.party)
    
    if parish:
        base_query = base_query.filter(func.lower(Parcel.parish) == parish.lower())
    
    total = base_query.filter(Lead.deleted_at.is_(None)).scalar() or 0
    
    # Already enriched (has acreage AND land value)
    enriched = base_query.filter(
        Lead.deleted_at.is_(None),
        Parcel.lot_size_acres > 0,
        Parcel.land_assessed_value > 0,
    ).scalar() or 0
    
    # Has phone
    with_phone = base_query.filter(
        Lead.deleted_at.is_(None),
        Owner.phone_primary.isnot(None),
    ).scalar() or 0
    
    # Vacant land
    vacant = base_query.filter(
        Lead.deleted_at.is_(None),
        or_(
            Parcel.improvement_assessed_value.is_(None),
            Parcel.improvement_assessed_value == 0,
        ),
    ).scalar() or 0
    
    return {
        'total_leads': total,
        'enriched': enriched,
        'needs_enrichment': total - enriched,
        'with_phone': with_phone,
        'vacant_land': vacant,
        'parish': parish or 'all',
    }


def export_enrichment_queue_csv(
    session: Session,
    parish: Optional[str] = None,
    limit: int = 50,
) -> str:
    """
    Export enrichment queue as CSV string for manual lookup.
    
    Args:
        session: Database session.
        parish: Filter by parish name.
        limit: Max parcels.
    
    Returns:
        CSV string.
    """
    parcels = get_enrichment_queue(session, parish=parish, limit=limit)
    
    if not parcels:
        return "No parcels found for enrichment"
    
    # CSV header
    lines = [
        "canonical_parcel_id,parish,situs_address,owner_name,mailing_address,lot_size_acres,land_assessed_value,years_tax_delinquent,is_adjudicated"
    ]
    
    for p in parcels:
        lines.append(
            f'"{p["canonical_parcel_id"]}","{p["parish"]}","{p["situs_address"] or ""}","{p["owner_name"]}","{p["mailing_address"] or ""}",{p["lot_size_acres"] or ""},{ p["land_assessed_value"] or ""},{p["years_tax_delinquent"] or 0},{p["is_adjudicated"]}'
        )
    
    return "\n".join(lines)


__all__ = [
    'get_enrichment_queue',
    'get_enrichment_stats', 
    'export_enrichment_queue_csv',
]

