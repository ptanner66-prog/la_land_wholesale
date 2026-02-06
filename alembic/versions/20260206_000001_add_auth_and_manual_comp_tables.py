"""Add user, refresh_token, and manual_comp tables.

Revision ID: a1b2c3d4e5f6
Revises: 20251205_023617_add_result_column_to_outreach_attempt
Create Date: 2026-02-06 00:00:01
"""
from alembic import op
import sqlalchemy as sa

revision = "a1b2c3d4e5f6"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("role", sa.String(20), nullable=False, server_default="user"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_email", "user", ["email"], unique=True)

    op.create_table(
        "refresh_token",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(255), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_refresh_token_user_id", "refresh_token", ["user_id"])
    op.create_index("ix_refresh_token_hash", "refresh_token", ["token_hash"], unique=True)

    op.create_table(
        "manual_comp",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("parcel_id", sa.Integer(), nullable=True),
        sa.Column("address", sa.String(255), nullable=False),
        sa.Column("sale_date", sa.String(20), nullable=False),
        sa.Column("sale_price", sa.Float(), nullable=False),
        sa.Column("lot_size_acres", sa.Float(), nullable=False),
        sa.Column("parish", sa.String(100), nullable=True),
        sa.Column("market_code", sa.String(2), nullable=False, server_default="LA"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["parcel_id"], ["parcel.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_manual_comp_parcel_id", "manual_comp", ["parcel_id"])
    op.create_index("ix_manual_comp_parish", "manual_comp", ["parish"])
    op.create_index("ix_manual_comp_market", "manual_comp", ["market_code"])


def downgrade() -> None:
    op.drop_table("manual_comp")
    op.drop_table("refresh_token")
    op.drop_table("user")
