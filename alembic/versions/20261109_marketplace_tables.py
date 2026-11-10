"""Marketplace tables, and merge of the two existing Alembic heads.

Revision ID: 20261109_marketplace_tables
Revises: 88e104190a1d, 20260819_payment_and_numeric
Create Date: 2026-11-09

Adds locations, worker_profiles, worker_trades, worker_service_areas, bookings,
disputes and audit_logs. Listing both old revisions in down_revision merges them,
so `alembic upgrade head` works again (before this it failed with "Multiple head
revisions").

This migration only ADDS tables; it does not touch users/jobs/transactions.

The app still calls Base.metadata.create_all at import time, so a database may
already contain these tables. In that case the migration does nothing. If only
SOME of them exist it stops with an error rather than guessing.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20261109_marketplace_tables"
down_revision: Union[str, Sequence[str], None] = (
    "88e104190a1d",
    "20260819_payment_and_numeric",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Reverse dependency order: safe to drop from the top of this list down.
NEW_TABLES = (
    "disputes",
    "worker_trades",
    "worker_service_areas",
    "bookings",
    "worker_profiles",
    "audit_logs",
    "locations",
)


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing = [t for t in NEW_TABLES if inspector.has_table(t)]
    if len(existing) == len(NEW_TABLES):
        return  # create_all already built everything
    if existing:
        raise RuntimeError(
            f"Partial state: {existing} already exist but not all marketplace tables. "
            "Resolve manually before running this migration."
        )

    op.create_table('locations',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('level', sa.Enum('division', 'district', 'upazila', 'union', name='location_level', native_enum=False, length=24), nullable=False),
    sa.Column('parent_id', sa.Integer(), nullable=True),
    sa.Column('name_bn', sa.String(length=120), nullable=False),
    sa.Column('name_en', sa.String(length=120), nullable=False),
    sa.Column('bbs_code', sa.String(length=16), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['parent_id'], ['locations.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('bbs_code'),
    sa.UniqueConstraint('parent_id', 'name_en', name='uq_location_parent_name_en')
    )
    op.create_index(op.f('ix_locations_level'), 'locations', ['level'], unique=False)
    op.create_index(op.f('ix_locations_parent_id'), 'locations', ['parent_id'], unique=False)
    op.create_table('audit_logs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('actor_user_id', sa.Integer(), nullable=True),
    sa.Column('actor_role', sa.String(length=20), nullable=True),
    sa.Column('action', sa.String(length=80), nullable=False),
    sa.Column('target_type', sa.String(length=40), nullable=True),
    sa.Column('target_id', sa.String(length=64), nullable=True),
    sa.Column('ip_address', sa.String(length=45), nullable=True),
    sa.Column('user_agent', sa.String(length=255), nullable=True),
    sa.Column('details', sa.JSON(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['actor_user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_audit_logs_action'), 'audit_logs', ['action'], unique=False)
    op.create_index(op.f('ix_audit_logs_created_at'), 'audit_logs', ['created_at'], unique=False)
    op.create_table('worker_profiles',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('display_name', sa.String(length=120), nullable=False),
    sa.Column('bio', sa.Text(), nullable=True),
    sa.Column('photo_ref', sa.String(length=255), nullable=True),
    sa.Column('payout_provider', sa.Enum('bkash', 'nagad', 'rocket', name='payout_provider', native_enum=False, length=24), nullable=True),
    sa.Column('payout_number', sa.String(length=20), nullable=True),
    sa.Column('payout_verified_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('nid_hash', sa.String(length=64), nullable=True),
    sa.Column('nid_front_ref', sa.String(length=255), nullable=True),
    sa.Column('nid_back_ref', sa.String(length=255), nullable=True),
    sa.Column('selfie_ref', sa.String(length=255), nullable=True),
    sa.Column('verification_status', sa.Enum('pending', 'auto_approved', 'in_review', 'rejected', 'suspended', name='verification_status', native_enum=False, length=24), nullable=False),
    sa.Column('verification_note', sa.String(length=255), nullable=True),
    sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('risk_tier', sa.Integer(), nullable=False),
    sa.Column('is_available', sa.Boolean(), nullable=False),
    sa.Column('rating_avg', sa.Numeric(precision=3, scale=2), nullable=False),
    sa.Column('rating_count', sa.Integer(), nullable=False),
    sa.Column('jobs_completed', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint('rating_avg >= 0 AND rating_avg <= 5', name='ck_worker_rating_range'),
    sa.CheckConstraint('risk_tier BETWEEN 1 AND 3', name='ck_worker_risk_tier'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_worker_profiles_nid_hash'), 'worker_profiles', ['nid_hash'], unique=True)
    op.create_index('ix_worker_profiles_payout', 'worker_profiles', ['payout_provider', 'payout_number'], unique=False)
    op.create_index('ix_worker_profiles_status_available', 'worker_profiles', ['verification_status', 'is_available'], unique=False)
    op.create_index(op.f('ix_worker_profiles_user_id'), 'worker_profiles', ['user_id'], unique=True)
    op.create_table('bookings',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('employer_id', sa.Integer(), nullable=False),
    sa.Column('worker_profile_id', sa.Integer(), nullable=False),
    sa.Column('trade', sa.String(length=50), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('location_id', sa.Integer(), nullable=True),
    sa.Column('address_text', sa.String(length=255), nullable=True),
    sa.Column('scheduled_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('price', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('commission_rate', sa.Numeric(precision=5, scale=4), nullable=False),
    sa.Column('commission_amount', sa.Numeric(precision=12, scale=2), nullable=True),
    sa.Column('status', sa.Enum('requested', 'accepted', 'paid_hold', 'started', 'completed', 'released', 'declined', 'expired', 'cancelled', 'disputed', 'refunded', name='booking_status', native_enum=False, length=24), nullable=False),
    sa.Column('start_code_hash', sa.String(length=64), nullable=True),
    sa.Column('start_code_attempts', sa.Integer(), nullable=False),
    sa.Column('requested_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('accepted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('paid_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('confirm_deadline_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('released_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('cancelled_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('cancel_reason', sa.String(length=255), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint('commission_rate >= 0 AND commission_rate <= 1', name='ck_booking_commission_range'),
    sa.CheckConstraint('price > 0', name='ck_booking_price_positive'),
    sa.ForeignKeyConstraint(['employer_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['location_id'], ['locations.id'], ),
    sa.ForeignKeyConstraint(['worker_profile_id'], ['worker_profiles.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_bookings_employer_status', 'bookings', ['employer_id', 'status'], unique=False)
    op.create_index(op.f('ix_bookings_status'), 'bookings', ['status'], unique=False)
    op.create_index('ix_bookings_worker_status', 'bookings', ['worker_profile_id', 'status'], unique=False)
    op.create_table('worker_service_areas',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('worker_id', sa.Integer(), nullable=False),
    sa.Column('location_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['location_id'], ['locations.id'], ),
    sa.ForeignKeyConstraint(['worker_id'], ['worker_profiles.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('worker_id', 'location_id', name='uq_worker_area')
    )
    op.create_index(op.f('ix_worker_service_areas_location_id'), 'worker_service_areas', ['location_id'], unique=False)
    op.create_index(op.f('ix_worker_service_areas_worker_id'), 'worker_service_areas', ['worker_id'], unique=False)
    op.create_table('worker_trades',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('worker_id', sa.Integer(), nullable=False),
    sa.Column('trade', sa.String(length=50), nullable=False),
    sa.Column('experience_years', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['worker_id'], ['worker_profiles.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('worker_id', 'trade', name='uq_worker_trade')
    )
    op.create_index(op.f('ix_worker_trades_trade'), 'worker_trades', ['trade'], unique=False)
    op.create_index(op.f('ix_worker_trades_worker_id'), 'worker_trades', ['worker_id'], unique=False)
    op.create_table('disputes',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('booking_id', sa.Integer(), nullable=False),
    sa.Column('opened_by_user_id', sa.Integer(), nullable=False),
    sa.Column('reason_code', sa.String(length=40), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('evidence_refs', sa.JSON(), nullable=False),
    sa.Column('status', sa.Enum('open', 'resolved_for_employer', 'resolved_for_worker', 'closed', name='dispute_status', native_enum=False, length=24), nullable=False),
    sa.Column('resolution_note', sa.Text(), nullable=True),
    sa.Column('resolved_by_user_id', sa.Integer(), nullable=True),
    sa.Column('opened_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['booking_id'], ['bookings.id'], ),
    sa.ForeignKeyConstraint(['opened_by_user_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['resolved_by_user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('booking_id')
    )
    op.create_index(op.f('ix_disputes_status'), 'disputes', ['status'], unique=False)


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    for table in NEW_TABLES:
        if inspector.has_table(table):
            op.drop_table(table)  # drops the table's indexes with it
