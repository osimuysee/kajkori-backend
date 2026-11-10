from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.schema import CreateIndex, CreateTable

from app.database import Base
from app.models import User
from app.models_marketplace import (
    AuditLog,
    Booking,
    BookingStatus,
    Dispute,
    Location,
    LocationLevel,
    VerificationStatus,
    WorkerProfile,
    WorkerServiceArea,
    WorkerTrade,
)
from app.security.nid import hash_nid

DHAKA = timezone(timedelta(hours=6))
NID = "1234567890123"


def make_user(db, phone):
    user = User(phone=phone)
    db.add(user)
    db.flush()
    return user


def make_worker(db, phone="01711111111", nid_hash=None):
    user = make_user(db, phone)
    worker = WorkerProfile(user_id=user.id, display_name="Rahim", nid_hash=nid_hash)
    db.add(worker)
    db.flush()
    return worker


# ---- one NID, one account --------------------------------------------------
def test_same_nid_cannot_be_registered_twice(session):
    make_worker(session, "01711111111", hash_nid(NID))
    with pytest.raises(IntegrityError):
        make_worker(session, "01722222222", hash_nid(NID))


def test_same_nid_written_in_bangla_digits_is_still_a_duplicate(session):
    make_worker(session, "01711111111", hash_nid(NID))
    with pytest.raises(IntegrityError):
        make_worker(session, "01722222222", hash_nid("১২৩৪৫৬৭৮৯০১২৩"))


def test_many_profiles_without_nid_yet_are_allowed(session):
    make_worker(session, "01711111111", None)
    make_worker(session, "01722222222", None)
    assert session.query(WorkerProfile).count() == 2


def test_one_worker_profile_per_user(session):
    worker = make_worker(session)
    session.add(WorkerProfile(user_id=worker.user_id, display_name="Again"))
    with pytest.raises(IntegrityError):
        session.flush()


def test_new_profile_starts_pending_with_lowest_risk_tier(session):
    worker = make_worker(session)
    assert worker.verification_status == VerificationStatus.PENDING
    assert worker.risk_tier == 1
    assert worker.is_available is True


# ---- timestamps ------------------------------------------------------------
def test_datetimes_come_back_timezone_aware_utc(session):
    worker = make_worker(session)
    employer = make_user(session, "01733333333")
    when = datetime(2026, 11, 10, 9, 0, tzinfo=DHAKA)
    booking = Booking(employer_id=employer.id, worker_profile_id=worker.id, trade="electrician",
                      price=Decimal("500.00"), scheduled_at=when)
    session.add(booking)
    session.commit()
    session.expire_all()

    loaded = session.get(Booking, booking.id)
    assert loaded.scheduled_at.tzinfo is not None
    assert loaded.scheduled_at.utcoffset() == timedelta(0)
    assert loaded.scheduled_at == when  # same instant
    assert loaded.created_at.tzinfo is not None


def test_naive_datetime_is_rejected(session):
    worker = make_worker(session)
    employer = make_user(session, "01733333333")
    session.add(Booking(employer_id=employer.id, worker_profile_id=worker.id, trade="plumber",
                        price=Decimal("300"), scheduled_at=datetime(2026, 11, 10, 9, 0)))
    with pytest.raises((ValueError, StatementError)):
        session.flush()


# ---- booking ---------------------------------------------------------------
def test_booking_defaults_and_value_stored_as_lowercase_text(session):
    worker = make_worker(session)
    employer = make_user(session, "01733333333")
    booking = Booking(employer_id=employer.id, worker_profile_id=worker.id, trade="painter",
                      price=Decimal("1200.50"))
    session.add(booking)
    session.commit()

    assert booking.status == BookingStatus.REQUESTED
    assert session.execute(text("SELECT status FROM bookings")).scalar() == "requested"
    assert booking.price == Decimal("1200.50")


@pytest.mark.parametrize("bad_price", [Decimal("0"), Decimal("-5")])
def test_booking_price_must_be_positive(session, bad_price):
    worker = make_worker(session)
    employer = make_user(session, "01733333333")
    session.add(Booking(employer_id=employer.id, worker_profile_id=worker.id, trade="x", price=bad_price))
    with pytest.raises(IntegrityError):
        session.flush()


# ---- dispute ---------------------------------------------------------------
def test_only_one_dispute_per_booking(session):
    worker = make_worker(session)
    employer = make_user(session, "01733333333")
    booking = Booking(employer_id=employer.id, worker_profile_id=worker.id, trade="x", price=Decimal("100"))
    session.add(booking)
    session.flush()
    session.add(Dispute(booking_id=booking.id, opened_by_user_id=employer.id, reason_code="no_show"))
    session.flush()
    session.add(Dispute(booking_id=booking.id, opened_by_user_id=worker.user_id, reason_code="unpaid"))
    with pytest.raises(IntegrityError):
        session.flush()


# ---- worker trades and areas ----------------------------------------------
def test_deleting_a_worker_removes_trades_and_areas(session):
    worker = make_worker(session)
    division = Location(level=LocationLevel.DIVISION, name_bn="ঢাকা", name_en="Dhaka")
    session.add(division)
    session.flush()
    worker.trades.append(WorkerTrade(trade="electrician"))
    worker.service_areas.append(WorkerServiceArea(location_id=division.id))
    session.commit()

    session.delete(worker)
    session.commit()
    assert session.query(WorkerTrade).count() == 0
    assert session.query(WorkerServiceArea).count() == 0


def test_same_trade_twice_for_one_worker_is_rejected(session):
    worker = make_worker(session)
    worker.trades.append(WorkerTrade(trade="plumber"))
    worker.trades.append(WorkerTrade(trade="plumber"))
    with pytest.raises(IntegrityError):
        session.flush()


def test_audit_log_accepts_system_actor_and_json_details(session):
    session.add(AuditLog(action="booking.auto_confirmed", target_type="booking", target_id="7",
                         details={"after_hours": 24}))
    session.commit()
    entry = session.query(AuditLog).one()
    assert entry.actor_user_id is None
    assert entry.details == {"after_hours": 24}


# ---- PostgreSQL ------------------------------------------------------------
def test_every_table_compiles_for_postgresql():
    """No Postgres server here, but at least the DDL must be valid for it."""
    pg = postgresql.dialect()
    for table in Base.metadata.sorted_tables:
        str(CreateTable(table).compile(dialect=pg))
        for index in table.indexes:
            str(CreateIndex(index).compile(dialect=pg))
