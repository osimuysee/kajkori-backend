"""Migration tests.

The repo's two older revisions both have down_revision = None, so Alembic saw two
heads. These tests simulate a database where BOTH older revisions are already
applied (two rows in alembic_version) and check the new migration on top of it.

Scope: SQLite only. A real PostgreSQL run is still needed before deploying.
"""
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory

from app.database import Base
import app.models  # noqa: F401
import app.models_marketplace  # noqa: F401

ROOT = Path(__file__).resolve().parent.parent
NEW_REV = "20261109_marketplace_tables"
OLD_REVS = ("88e104190a1d", "20260819_payment_and_numeric")
NEW_TABLES = {
    "locations", "worker_profiles", "worker_trades", "worker_service_areas",
    "bookings", "disputes", "audit_logs",
}


def _cfg() -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    return cfg


def _db(tmp_path, monkeypatch, *, include_new_tables=False, only=None):
    """SQLite file with the pre-existing tables, stamped at both old revisions."""
    url = f"sqlite:///{tmp_path}/m.db"
    monkeypatch.setenv("DATABASE_URL", url)
    engine = sa.create_engine(url)
    if only is not None:
        tables = [Base.metadata.tables[n] for n in only]
    else:
        tables = [t for n, t in Base.metadata.tables.items() if include_new_tables or n not in NEW_TABLES]
    Base.metadata.create_all(engine, tables=tables)
    with engine.begin() as conn:
        conn.execute(sa.text(
            "CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL, "
            "CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num))"
        ))
        for rev in OLD_REVS:
            conn.execute(sa.text("INSERT INTO alembic_version VALUES (:r)"), {"r": rev})
    return engine


def _versions(engine):
    with engine.connect() as conn:
        return sorted(r[0] for r in conn.execute(sa.text("SELECT version_num FROM alembic_version")))


def _flatten(diffs):
    for d in diffs:
        if isinstance(d, list):
            yield from _flatten(d)
        else:
            yield d


def _table_of(diff):
    kind = diff[0]
    if kind in ("add_table", "remove_table"):
        return diff[1].name
    if kind in ("add_column", "remove_column") or kind.startswith("modify_"):
        return diff[2]
    return diff[1].table.name  # index / constraint / fk


def test_there_is_exactly_one_head():
    assert ScriptDirectory.from_config(_cfg()).get_heads() == [NEW_REV]


def test_upgrade_from_both_old_revisions_creates_the_new_tables(tmp_path, monkeypatch):
    engine = _db(tmp_path, monkeypatch)
    command.upgrade(_cfg(), "head")

    assert NEW_TABLES <= set(sa.inspect(engine).get_table_names())
    assert _versions(engine) == [NEW_REV]


def test_migrated_schema_matches_the_models(tmp_path, monkeypatch):
    """Catches a model change that nobody wrote a migration for."""
    engine = _db(tmp_path, monkeypatch)
    command.upgrade(_cfg(), "head")

    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn, opts={"compare_type": True})
        drift = [d for d in _flatten(compare_metadata(ctx, Base.metadata)) if _table_of(d) in NEW_TABLES]
    assert drift == []


def test_rollback_drops_only_the_new_tables(tmp_path, monkeypatch):
    """Rollback command is `alembic downgrade 88e104190a1d`.

    `downgrade -1` does NOT work from a merge revision (Alembic: "Ambiguous walk").
    Going to one parent returns to BOTH old revisions without running the older
    migration's own downgrade, which would drop real columns.
    """
    engine = _db(tmp_path, monkeypatch)
    command.upgrade(_cfg(), "head")
    command.downgrade(_cfg(), OLD_REVS[0])

    inspector = sa.inspect(engine)
    names = set(inspector.get_table_names())
    assert not (NEW_TABLES & names)
    assert {"users", "jobs", "transactions"} <= names
    assert "reserved_balance" in {c["name"] for c in inspector.get_columns("users")}
    assert _versions(engine) == sorted(OLD_REVS)


def test_upgrade_is_a_noop_when_create_all_already_made_the_tables(tmp_path, monkeypatch):
    engine = _db(tmp_path, monkeypatch, include_new_tables=True)
    command.upgrade(_cfg(), "head")

    assert NEW_TABLES <= set(sa.inspect(engine).get_table_names())
    assert _versions(engine) == [NEW_REV]


def test_partial_state_stops_with_a_clear_error(tmp_path, monkeypatch):
    _db(tmp_path, monkeypatch, only=["users", "locations"])
    with pytest.raises(RuntimeError, match="Partial state"):
        command.upgrade(_cfg(), "head")
