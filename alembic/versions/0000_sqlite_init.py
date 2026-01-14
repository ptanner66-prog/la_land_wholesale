"""SQLite-compatible initial schema.

Revision ID: 0000_sqlite_init
Revises: 
Create Date: 2024-12-04

This migration creates all tables using SQLite-compatible types.
It replaces 0001-0004 migrations when running on SQLite.
"""
from __future__ import annotations

import os
import sys

from alembic import op
import sqlalchemy as sa

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

# revision identifiers
revision = '0000_sqlite_init'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create all tables for SQLite."""
    
    # =========================================================================
    # Table: party
    # =========================================================================
    op.create_table(
        'party',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('normalized_name', sa.String(255), nullable=False),
        sa.Column('normalized_zip', sa.String(10), nullable=False),
        sa.Column('match_hash', sa.String(64), nullable=False),
        sa.Column('display_name', sa.String(255), nullable=False),
        sa.Column('raw_mailing_address', sa.Text(), nullable=True),
        sa.Column('party_type', sa.String(50), nullable=False, server_default='individual'),
        sa.Column('market_code', sa.String(2), nullable=False, server_default='LA'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.current_timestamp()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.current_timestamp()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('match_hash'),
    )
    op.create_index('ix_party_normalized_name', 'party', ['normalized_name'])
    op.create_index('ix_party_normalized_zip', 'party', ['normalized_zip'])
    op.create_index('ix_party_market_code', 'party', ['market_code'])
    op.create_index('ix_party_match', 'party', ['normalized_name', 'normalized_zip'])

    # =========================================================================
    # Table: owner
    # =========================================================================
    op.create_table(
        'owner',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('party_id', sa.Integer(), nullable=False),
        sa.Column('phone_primary', sa.String(20), nullable=True),
        sa.Column('phone_secondary', sa.String(20), nullable=True),
        sa.Column('email', sa.String(255), nullable=True),
        sa.Column('market_code', sa.String(2), nullable=False, server_default='LA'),
        sa.Column('is_tcpa_safe', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('is_dnr', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('opt_out', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('opt_out_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.current_timestamp()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.current_timestamp()),
        sa.ForeignKeyConstraint(['party_id'], ['party.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_owner_party_id', 'owner', ['party_id'])
    op.create_index('ix_owner_phone_primary', 'owner', ['phone_primary'])
    op.create_index('ix_owner_market_code', 'owner', ['market_code'])
    op.create_index('ix_owner_is_tcpa_safe', 'owner', ['is_tcpa_safe'])
    op.create_index('ix_owner_is_dnr', 'owner', ['is_dnr'])
    op.create_index('ix_owner_opt_out', 'owner', ['opt_out'])
    op.create_index('ix_owner_market_tcpa', 'owner', ['market_code', 'is_tcpa_safe'])

    # =========================================================================
    # Table: parcel
    # =========================================================================
    op.create_table(
        'parcel',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('canonical_parcel_id', sa.String(50), nullable=False),
        sa.Column('parish', sa.String(100), nullable=False),
        sa.Column('market_code', sa.String(2), nullable=False, server_default='LA'),
        sa.Column('situs_address', sa.String(255), nullable=True),
        sa.Column('city', sa.String(100), nullable=True),
        sa.Column('state', sa.String(2), nullable=True),
        sa.Column('postal_code', sa.String(10), nullable=True),
        sa.Column('latitude', sa.Float(), nullable=True),
        sa.Column('longitude', sa.Float(), nullable=True),
        sa.Column('zoning_code', sa.String(20), nullable=True),
        sa.Column('geom', sa.Text(), nullable=True),
        sa.Column('inside_city_limits', sa.Boolean(), nullable=True),
        sa.Column('land_assessed_value', sa.Numeric(14, 2), nullable=True),
        sa.Column('improvement_assessed_value', sa.Numeric(14, 2), nullable=True),
        sa.Column('lot_size_acres', sa.Numeric(10, 4), nullable=True),
        sa.Column('is_adjudicated', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('years_tax_delinquent', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('raw_data', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.current_timestamp()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.current_timestamp()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('canonical_parcel_id'),
    )
    op.create_index('ix_parcel_canonical_parcel_id', 'parcel', ['canonical_parcel_id'])
    op.create_index('ix_parcel_parish', 'parcel', ['parish'])
    op.create_index('ix_parcel_market_code', 'parcel', ['market_code'])
    op.create_index('ix_parcel_is_adjudicated', 'parcel', ['is_adjudicated'])
    op.create_index('ix_parcel_market_adjudicated', 'parcel', ['market_code', 'is_adjudicated'])

    # =========================================================================
    # Table: lead
    # =========================================================================
    op.create_table(
        'lead',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('owner_id', sa.Integer(), nullable=False),
        sa.Column('parcel_id', sa.Integer(), nullable=False),
        sa.Column('market_code', sa.String(2), nullable=False, server_default='LA'),
        sa.Column('motivation_score', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('score_details', sa.JSON(), nullable=True),
        sa.Column('pipeline_stage', sa.String(20), nullable=False, server_default='NEW'),
        sa.Column('status', sa.String(50), nullable=False, server_default='new'),
        sa.Column('last_reply_classification', sa.String(20), nullable=True),
        sa.Column('last_reply_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('followup_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_followup_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('next_followup_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_alerted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('send_locked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('send_locked_by', sa.String(64), nullable=True),
        sa.Column('tags', sa.JSON(), nullable=True, server_default='[]'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.current_timestamp()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.current_timestamp()),
        sa.ForeignKeyConstraint(['owner_id'], ['owner.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['parcel_id'], ['parcel.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_lead_owner_id', 'lead', ['owner_id'])
    op.create_index('ix_lead_parcel_id', 'lead', ['parcel_id'])
    op.create_index('ix_lead_market_code', 'lead', ['market_code'])
    op.create_index('ix_lead_motivation_score', 'lead', ['motivation_score'])
    op.create_index('ix_lead_pipeline_stage', 'lead', ['pipeline_stage'])
    op.create_index('ix_lead_status', 'lead', ['status'])
    op.create_index('ix_lead_last_reply_classification', 'lead', ['last_reply_classification'])
    op.create_index('ix_lead_next_followup_at', 'lead', ['next_followup_at'])
    op.create_index('ix_lead_market_score', 'lead', ['market_code', 'motivation_score'])
    op.create_index('ix_lead_market_stage', 'lead', ['market_code', 'pipeline_stage'])
    op.create_index('ix_lead_followup', 'lead', ['next_followup_at', 'pipeline_stage'])
    op.create_index('ix_lead_last_alerted', 'lead', ['last_alerted_at'])

    # =========================================================================
    # Table: outreach_attempt
    # =========================================================================
    op.create_table(
        'outreach_attempt',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('lead_id', sa.Integer(), nullable=False),
        sa.Column('idempotency_key', sa.String(64), nullable=True),
        sa.Column('channel', sa.String(20), nullable=False, server_default='sms'),
        sa.Column('message_body', sa.Text(), nullable=True),
        sa.Column('message_context', sa.String(20), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('external_id', sa.String(100), nullable=True),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('delivered_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('response_received_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('response_body', sa.Text(), nullable=True),
        sa.Column('reply_classification', sa.String(20), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.current_timestamp()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.current_timestamp()),
        sa.ForeignKeyConstraint(['lead_id'], ['lead.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_outreach_lead_id', 'outreach_attempt', ['lead_id'])
    op.create_index('ix_outreach_idempotency_key', 'outreach_attempt', ['idempotency_key'], unique=True)
    op.create_index('ix_outreach_status', 'outreach_attempt', ['status'])
    op.create_index('ix_outreach_external_id', 'outreach_attempt', ['external_id'])
    op.create_index('ix_outreach_lead_status', 'outreach_attempt', ['lead_id', 'status'])

    # =========================================================================
    # Table: timeline_event
    # =========================================================================
    op.create_table(
        'timeline_event',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('lead_id', sa.Integer(), nullable=False),
        sa.Column('event_type', sa.String(50), nullable=False),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('metadata', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.current_timestamp()),
        sa.ForeignKeyConstraint(['lead_id'], ['lead.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_timeline_event_lead_id', 'timeline_event', ['lead_id'])
    op.create_index('ix_timeline_event_type', 'timeline_event', ['event_type'])

    # =========================================================================
    # Table: alert_config
    # =========================================================================
    op.create_table(
        'alert_config',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('market_code', sa.String(2), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('hot_score_threshold', sa.Integer(), nullable=False, server_default='75'),
        sa.Column('alert_phone', sa.String(20), nullable=True),
        sa.Column('slack_webhook_url', sa.String(500), nullable=True),
        sa.Column('dedup_hours', sa.Integer(), nullable=False, server_default='24'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.current_timestamp()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.current_timestamp()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('market_code'),
    )

    # =========================================================================
    # Table: background_task
    # =========================================================================
    op.create_table(
        'background_task',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('task_id', sa.String(64), nullable=False),
        sa.Column('task_type', sa.String(50), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('market_code', sa.String(2), nullable=True),
        sa.Column('params', sa.JSON(), nullable=True),
        sa.Column('result', sa.JSON(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.current_timestamp()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('task_id'),
    )
    op.create_index('ix_background_task_task_id', 'background_task', ['task_id'])
    op.create_index('ix_background_task_task_type', 'background_task', ['task_type'])
    op.create_index('ix_background_task_status', 'background_task', ['status'])

    # =========================================================================
    # Table: scheduler_lock
    # =========================================================================
    op.create_table(
        'scheduler_lock',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('lock_name', sa.String(100), nullable=False),
        sa.Column('locked_by', sa.String(64), nullable=False),
        sa.Column('locked_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('lock_name'),
    )
    op.create_index('ix_scheduler_lock_lock_name', 'scheduler_lock', ['lock_name'])
    op.create_index('ix_scheduler_lock_expires_at', 'scheduler_lock', ['expires_at'])

    # =========================================================================
    # Table: buyer
    # =========================================================================
    op.create_table(
        'buyer',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('phone', sa.String(20), nullable=True),
        sa.Column('email', sa.String(255), nullable=True),
        sa.Column('market_codes', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('counties', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('min_acres', sa.Float(), nullable=True),
        sa.Column('max_acres', sa.Float(), nullable=True),
        sa.Column('property_types', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('price_min', sa.Float(), nullable=True),
        sa.Column('price_max', sa.Float(), nullable=True),
        sa.Column('target_spread', sa.Float(), nullable=True),
        sa.Column('closing_speed_days', sa.Integer(), nullable=True),
        sa.Column('vip', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('pof_url', sa.String(500), nullable=True),
        sa.Column('pof_verified', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('pof_last_updated', sa.DateTime(timezone=True), nullable=True),
        sa.Column('deals_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('response_rate', sa.Float(), nullable=True),
        sa.Column('last_deal_sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.current_timestamp()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.current_timestamp()),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_buyer_name', 'buyer', ['name'])
    op.create_index('ix_buyer_vip', 'buyer', ['vip'])
    op.create_index('ix_buyer_pof_verified', 'buyer', ['pof_verified'])

    # =========================================================================
    # Table: buyer_deal
    # =========================================================================
    op.create_table(
        'buyer_deal',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('buyer_id', sa.Integer(), nullable=False),
        sa.Column('lead_id', sa.Integer(), nullable=False),
        sa.Column('stage', sa.String(20), nullable=False, server_default='NEW'),
        sa.Column('match_score', sa.Float(), nullable=True),
        sa.Column('offer_amount', sa.Float(), nullable=True),
        sa.Column('assignment_fee', sa.Float(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('blast_sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('viewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('responded_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.current_timestamp()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.current_timestamp()),
        sa.ForeignKeyConstraint(['buyer_id'], ['buyer.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['lead_id'], ['lead.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_buyer_deal_buyer_id', 'buyer_deal', ['buyer_id'])
    op.create_index('ix_buyer_deal_lead_id', 'buyer_deal', ['lead_id'])
    op.create_index('ix_buyer_deal_stage', 'buyer_deal', ['stage'])
    op.create_index('ix_buyer_deal_buyer_lead', 'buyer_deal', ['buyer_id', 'lead_id'], unique=True)

    # =========================================================================
    # Table: deal_sheet
    # =========================================================================
    op.create_table(
        'deal_sheet',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('lead_id', sa.Integer(), nullable=False),
        sa.Column('content', sa.JSON(), nullable=False),
        sa.Column('ai_description', sa.Text(), nullable=True),
        sa.Column('generated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.current_timestamp()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.current_timestamp()),
        sa.ForeignKeyConstraint(['lead_id'], ['lead.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('lead_id'),
    )
    op.create_index('ix_deal_sheet_lead_id', 'deal_sheet', ['lead_id'])


def downgrade() -> None:
    """Drop all tables."""
    op.drop_table('deal_sheet')
    op.drop_table('buyer_deal')
    op.drop_table('buyer')
    op.drop_table('scheduler_lock')
    op.drop_table('background_task')
    op.drop_table('alert_config')
    op.drop_table('timeline_event')
    op.drop_table('outreach_attempt')
    op.drop_table('lead')
    op.drop_table('parcel')
    op.drop_table('owner')
    op.drop_table('party')

