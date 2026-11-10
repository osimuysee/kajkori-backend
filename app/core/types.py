"""Shared SQLAlchemy column types."""
from datetime import datetime, timezone

from sqlalchemy import DateTime
from sqlalchemy.types import TypeDecorator


def utcnow() -> datetime:
    """Timezone-aware 'now' in UTC. Use this instead of datetime.utcnow()."""
    return datetime.now(timezone.utc)


class UTCDateTime(TypeDecorator):
    """Always timezone-aware UTC in Python, whatever the database does.

    SQLite and PostgreSQL 'timestamp without time zone' hand back NAIVE
    datetimes. Comparing one with an aware datetime raises TypeError (this is
    what currently breaks verify-otp). This type converts on the way in and out.

    Writing a naive datetime is rejected on purpose: it is almost always a bug.
    """

    impl = DateTime
    cache_ok = True

    def __init__(self) -> None:
        super().__init__(timezone=True)

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("Naive datetime not allowed; pass a timezone-aware UTC datetime.")
        return value.astimezone(timezone.utc)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


def ensure_utc(value: datetime | None) -> datetime | None:
    """Make a datetime read from a LEGACY plain DateTime column timezone-aware.

    Older columns (users.otp_expires_at, transactions.created_at, ...) are
    'timestamp without time zone', so the database hands back naive values that
    were written as UTC. Use this before comparing them with utcnow().
    New columns should be UTCDateTime instead and never need this.
    """
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
