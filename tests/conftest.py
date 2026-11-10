"""Test setup. This file is imported before any app module.

Tests must never touch a real database, a real SMS gateway or real secrets.
"""
import os
import re
import tempfile
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

_TMP = tempfile.mkdtemp(prefix="kajkori-tests-")
os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP}/app_test.db"
# Fake value, tests only. At least 32 characters: require_secret() rejects shorter keys.
os.environ["SECRET_KEY"] = "test-only-secret-key-not-used-anywhere-real"
os.environ.pop("CORS_ALLOWED_ORIGINS", None)
os.environ.pop("NID_HMAC_PEPPER", None)
os.environ.pop("GREENWEB_TOKEN", None)

from app.database import Base  # noqa: E402
import app.models  # noqa: E402,F401
import app.models_marketplace  # noqa: E402,F401


@pytest.fixture()
def session():
    """Fresh in-memory SQLite with every table and foreign keys enforced."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_conn, _record):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, autoflush=False)()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


class ApiHarness:
    """The real FastAPI app on a private in-memory database, with SMS faked.

    `sent` collects (phone, message) for every SMS the app tried to send, so a
    test can read the OTP the way a user would read it from their phone.
    """

    def __init__(self, client, session_factory, sent):
        self.client = client
        self.Session = session_factory
        self.sent = sent

    def last_otp(self) -> str:
        return re.search(r"(\d{6})\s*$", self.sent[-1][1]).group(1)

    def login(self, phone: str, role: str = "worker") -> SimpleNamespace:
        """Full OTP login. Returns .id, .token and .headers for the user."""
        from app.limiter import limiter

        limiter.reset()  # the per-IP limit is tested on its own
        r = self.client.post("/api/v1/users/send-otp", json={"phone": phone, "role": role})
        assert r.status_code == 200, r.text
        r = self.client.post("/api/v1/users/verify-otp", json={"phone": phone, "otp_code": self.last_otp()})
        assert r.status_code == 200, r.text
        body = r.json()
        token = body["access_token"]
        return SimpleNamespace(id=body["user"]["id"], token=token, headers={"Authorization": f"Bearer {token}"})


@pytest.fixture()
def api(monkeypatch):
    from fastapi.testclient import TestClient

    from app.database import get_db
    from app.limiter import limiter
    from app.main import app as fastapi_app
    from app.routers import users as users_module

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False)

    def _get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    sent = []

    async def _fake_send_sms(phone, message):
        sent.append((phone, message))
        return True

    monkeypatch.setattr(users_module, "send_sms", _fake_send_sms)
    fastapi_app.dependency_overrides[get_db] = _get_db
    limiter.reset()
    try:
        yield ApiHarness(TestClient(fastapi_app, raise_server_exceptions=False), session_factory, sent)
    finally:
        fastapi_app.dependency_overrides.clear()
        limiter.reset()
        engine.dispose()
