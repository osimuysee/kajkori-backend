"""Marketplace tables: locations, verified worker profiles, bookings, disputes, audit log.

Kept separate from app/models.py so the existing job/wallet code is untouched.
Both files share the same Base, so Alembic and create_all see everything.

Conventions for every table in this file:
- Enums are stored as lowercase VARCHAR (no native PostgreSQL ENUM), so adding a
  state later is a code change, not an ALTER TYPE.
- Timestamps use UTCDateTime: always timezone-aware UTC in Python.
- Money is Numeric(12, 2), never float.
- Files (NID photos, selfie) are stored as *references* to encrypted storage,
  never as public URLs, and never the NID number itself.
"""
import enum

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.core.types import UTCDateTime, utcnow
from app.database import Base


def _enum(enum_cls, name: str) -> Enum:
    return Enum(
        enum_cls,
        name=name,
        native_enum=False,
        length=24,
        values_callable=lambda members: [m.value for m in members],
        validate_strings=True,
    )


# --------------------------------------------------------------------------- #
# Locations: division > district > upazila > union (village is free text)
# --------------------------------------------------------------------------- #
class LocationLevel(str, enum.Enum):
    DIVISION = "division"
    DISTRICT = "district"
    UPAZILA = "upazila"
    UNION = "union"


class Location(Base):
    __tablename__ = "locations"
    __table_args__ = (
        # NULL parent (divisions) is not covered by this constraint on SQL
        # databases; seed divisions idempotently by bbs_code instead.
        UniqueConstraint("parent_id", "name_en", name="uq_location_parent_name_en"),
    )

    id = Column(Integer, primary_key=True)
    level = Column(_enum(LocationLevel, "location_level"), nullable=False, index=True)
    parent_id = Column(Integer, ForeignKey("locations.id"), nullable=True, index=True)
    name_bn = Column(String(120), nullable=False)
    name_en = Column(String(120), nullable=False)
    bbs_code = Column(String(16), nullable=True, unique=True)  # official geocode, set by the seed
    is_active = Column(Boolean, nullable=False, default=True)  # area opens when enough workers exist


# --------------------------------------------------------------------------- #
# Worker profile (the "worker card" + verification state)
# --------------------------------------------------------------------------- #
class VerificationStatus(str, enum.Enum):
    PENDING = "pending"  # started, documents not complete
    AUTO_APPROVED = "auto_approved"  # all checks passed, card is live
    IN_REVIEW = "in_review"  # suspicious, waits in the review queue
    REJECTED = "rejected"
    SUSPENDED = "suspended"


class PayoutProvider(str, enum.Enum):
    BKASH = "bkash"
    NAGAD = "nagad"
    ROCKET = "rocket"


class WorkerProfile(Base):
    __tablename__ = "worker_profiles"
    __table_args__ = (
        CheckConstraint("risk_tier BETWEEN 1 AND 3", name="ck_worker_risk_tier"),
        CheckConstraint("rating_avg >= 0 AND rating_avg <= 5", name="ck_worker_rating_range"),
        Index("ix_worker_profiles_status_available", "verification_status", "is_available"),
        # NOT unique on purpose: a family may share one bKash number. Treat a
        # shared payout number as a review-queue signal instead of a hard block.
        Index("ix_worker_profiles_payout", "payout_provider", "payout_number"),
    )

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True, index=True)

    display_name = Column(String(120), nullable=False)
    bio = Column(Text, nullable=True)
    photo_ref = Column(String(255), nullable=True)

    payout_provider = Column(_enum(PayoutProvider, "payout_provider"), nullable=True)
    payout_number = Column(String(20), nullable=True)
    payout_verified_at = Column(UTCDateTime(), nullable=True)

    # HMAC of the NID (see app/security/nid.py). UNIQUE = one NID, one account.
    # NULL until submitted; several NULLs are allowed.
    nid_hash = Column(String(64), nullable=True, unique=True, index=True)
    nid_front_ref = Column(String(255), nullable=True)
    nid_back_ref = Column(String(255), nullable=True)
    selfie_ref = Column(String(255), nullable=True)

    verification_status = Column(
        _enum(VerificationStatus, "verification_status"),
        nullable=False,
        default=VerificationStatus.PENDING,
    )
    # Machine reason code such as "face_mismatch". Never raw NID data.
    verification_note = Column(String(255), nullable=True)
    verified_at = Column(UTCDateTime(), nullable=True)

    risk_tier = Column(Integer, nullable=False, default=1)  # 1 low risk, 3 enters homes
    is_available = Column(Boolean, nullable=False, default=True)
    rating_avg = Column(Numeric(3, 2), nullable=False, default=0)
    rating_count = Column(Integer, nullable=False, default=0)
    jobs_completed = Column(Integer, nullable=False, default=0)

    created_at = Column(UTCDateTime(), nullable=False, default=utcnow)
    updated_at = Column(UTCDateTime(), nullable=False, default=utcnow, onupdate=utcnow)

    trades = relationship(
        "WorkerTrade", back_populates="worker", cascade="all, delete-orphan"
    )
    service_areas = relationship(
        "WorkerServiceArea", back_populates="worker", cascade="all, delete-orphan"
    )


class WorkerTrade(Base):
    """One row per trade a worker offers (electrician, plumber, ...)."""

    __tablename__ = "worker_trades"
    __table_args__ = (UniqueConstraint("worker_id", "trade", name="uq_worker_trade"),)

    id = Column(Integer, primary_key=True)
    worker_id = Column(
        Integer, ForeignKey("worker_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    trade = Column(String(50), nullable=False, index=True)  # slug, validated in the API layer
    experience_years = Column(Integer, nullable=True)

    worker = relationship("WorkerProfile", back_populates="trades")


class WorkerServiceArea(Base):
    """Where a worker works. Any level: a union, an upazila or a whole district."""

    __tablename__ = "worker_service_areas"
    __table_args__ = (UniqueConstraint("worker_id", "location_id", name="uq_worker_area"),)

    id = Column(Integer, primary_key=True)
    worker_id = Column(
        Integer, ForeignKey("worker_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=False, index=True)

    worker = relationship("WorkerProfile", back_populates="service_areas")


# --------------------------------------------------------------------------- #
# Booking (user hires worker directly, no admin in the normal flow)
# --------------------------------------------------------------------------- #
class BookingStatus(str, enum.Enum):
    REQUESTED = "requested"
    ACCEPTED = "accepted"
    PAID_HOLD = "paid_hold"  # money is held (escrow)
    STARTED = "started"
    COMPLETED = "completed"  # worker finished, waiting for confirmation
    RELEASED = "released"  # money paid out to the worker
    DECLINED = "declined"
    EXPIRED = "expired"  # worker did not answer in time
    CANCELLED = "cancelled"
    DISPUTED = "disputed"
    REFUNDED = "refunded"


class Booking(Base):
    __tablename__ = "bookings"
    __table_args__ = (
        CheckConstraint("price > 0", name="ck_booking_price_positive"),
        CheckConstraint("commission_rate >= 0 AND commission_rate <= 1", name="ck_booking_commission_range"),
        Index("ix_bookings_worker_status", "worker_profile_id", "status"),
        Index("ix_bookings_employer_status", "employer_id", "status"),
    )

    id = Column(Integer, primary_key=True)
    employer_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    worker_profile_id = Column(Integer, ForeignKey("worker_profiles.id"), nullable=False)

    trade = Column(String(50), nullable=False)
    description = Column(Text, nullable=True)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=True)
    # Exact address: only reveal to the worker after the booking is accepted/paid.
    address_text = Column(String(255), nullable=True)
    scheduled_at = Column(UTCDateTime(), nullable=True)

    price = Column(Numeric(12, 2), nullable=False)
    commission_rate = Column(Numeric(5, 4), nullable=False, default=0)  # 0.0800 = 8%
    commission_amount = Column(Numeric(12, 2), nullable=True)  # fixed when released

    status = Column(
        _enum(BookingStatus, "booking_status"),
        nullable=False,
        default=BookingStatus.REQUESTED,
        index=True,
    )

    # One-time code the user gives the worker to start. Only the hash is stored.
    start_code_hash = Column(String(64), nullable=True)
    start_code_attempts = Column(Integer, nullable=False, default=0)

    requested_at = Column(UTCDateTime(), nullable=False, default=utcnow)
    accepted_at = Column(UTCDateTime(), nullable=True)
    paid_at = Column(UTCDateTime(), nullable=True)
    started_at = Column(UTCDateTime(), nullable=True)
    completed_at = Column(UTCDateTime(), nullable=True)
    confirm_deadline_at = Column(UTCDateTime(), nullable=True)  # auto-confirm after 24h
    released_at = Column(UTCDateTime(), nullable=True)
    cancelled_at = Column(UTCDateTime(), nullable=True)
    cancel_reason = Column(String(255), nullable=True)

    created_at = Column(UTCDateTime(), nullable=False, default=utcnow)
    updated_at = Column(UTCDateTime(), nullable=False, default=utcnow, onupdate=utcnow)


# --------------------------------------------------------------------------- #
# Dispute (the only place an admin steps in)
# --------------------------------------------------------------------------- #
class DisputeStatus(str, enum.Enum):
    OPEN = "open"
    RESOLVED_FOR_EMPLOYER = "resolved_for_employer"
    RESOLVED_FOR_WORKER = "resolved_for_worker"
    CLOSED = "closed"


class Dispute(Base):
    __tablename__ = "disputes"

    id = Column(Integer, primary_key=True)
    booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=False, unique=True)  # one per booking
    opened_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    reason_code = Column(String(40), nullable=False)
    description = Column(Text, nullable=True)
    evidence_refs = Column(JSON, nullable=False, default=list)  # storage keys, not URLs

    status = Column(_enum(DisputeStatus, "dispute_status"), nullable=False, default=DisputeStatus.OPEN, index=True)
    resolution_note = Column(Text, nullable=True)
    resolved_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    opened_at = Column(UTCDateTime(), nullable=False, default=utcnow)
    resolved_at = Column(UTCDateTime(), nullable=True)


# --------------------------------------------------------------------------- #
# Audit log (append-only by convention; make the DB role insert-only in prod)
# --------------------------------------------------------------------------- #
class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True)
    actor_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # NULL = system job
    actor_role = Column(String(20), nullable=True)
    action = Column(String(80), nullable=False, index=True)  # e.g. "booking.released"
    target_type = Column(String(40), nullable=True)
    target_id = Column(String(64), nullable=True)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(255), nullable=True)
    # Never put NID numbers, OTPs, tokens or full phone numbers in here.
    details = Column(JSON, nullable=True)
    created_at = Column(UTCDateTime(), nullable=False, default=utcnow, index=True)
