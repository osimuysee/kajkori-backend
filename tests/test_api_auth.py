"""Login (OTP) and token tests. Fake phone numbers only, SMS is faked."""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.models import User, UserRole
from app.routers import users as users_module
from app.services.sms import send_sms

PHONE = "01711111111"
SEND = "/api/v1/users/send-otp"
VERIFY = "/api/v1/users/verify-otp"
ME = "/api/v1/users/me"
TEST_KEY = "test-only-secret-key-not-used-anywhere-real"


def _user(api, phone=PHONE):
    with api.Session() as db:
        return db.query(User).filter(User.phone == phone).first()


def _naive_utc(delta: timedelta) -> datetime:
    """A value shaped like what the legacy naive column hands back."""
    return (datetime.now(timezone.utc) + delta).replace(tzinfo=None)


# ---- AUDIT #1: login used to answer 500 with the correct code ---------------
def test_correct_code_logs_in_and_the_token_works(api):
    assert api.client.post(SEND, json={"phone": PHONE, "role": "employer"}).status_code == 200
    r = api.client.post(VERIFY, json={"phone": PHONE, "otp_code": api.last_otp()})

    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "bearer"
    assert body["user"]["role"] == "employer"

    me = api.client.get(ME, headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200
    assert me.json()["phone"] == PHONE


def test_code_is_single_use(api):
    api.client.post(SEND, json={"phone": PHONE})
    code = api.last_otp()
    assert api.client.post(VERIFY, json={"phone": PHONE, "otp_code": code}).status_code == 200
    assert api.client.post(VERIFY, json={"phone": PHONE, "otp_code": code}).status_code == 400


def test_expired_code_is_rejected(api):
    api.client.post(SEND, json={"phone": PHONE})
    code = api.last_otp()
    with api.Session() as db:
        db.query(User).filter(User.phone == PHONE).one().otp_expires_at = _naive_utc(timedelta(seconds=-1))
        db.commit()

    assert api.client.post(VERIFY, json={"phone": PHONE, "otp_code": code}).status_code == 400


# ---- AUDIT #5: OTP storage and guessing --------------------------------------
def test_otp_is_stored_as_a_hash_never_in_plain_text(api):
    api.client.post(SEND, json={"phone": PHONE})
    code = api.last_otp()
    stored = _user(api).otp_code

    assert stored != code
    assert len(stored) == 64
    assert code not in stored


def test_five_wrong_codes_lock_the_code_even_for_the_right_one(api):
    api.client.post(SEND, json={"phone": PHONE})
    code = api.last_otp()
    wrong = "000000" if code != "000000" else "111111"

    for _ in range(5):
        assert api.client.post(VERIFY, json={"phone": PHONE, "otp_code": wrong}).status_code == 400
    assert _user(api).otp_attempts == 5

    r = api.client.post(VERIFY, json={"phone": PHONE, "otp_code": code})
    assert r.status_code == 429


def test_resend_is_refused_inside_the_cooldown_and_allowed_after_it(api):
    assert api.client.post(SEND, json={"phone": PHONE}).status_code == 200

    r = api.client.post(SEND, json={"phone": PHONE})
    assert r.status_code == 429
    assert int(r.headers["retry-after"]) >= 1
    assert len(api.sent) == 1  # no second SMS

    # Pretend the first code was sent 61 seconds ago.
    with api.Session() as db:
        db.query(User).filter(User.phone == PHONE).one().otp_expires_at = _naive_utc(
            users_module.OTP_TTL - timedelta(seconds=61)
        )
        db.commit()
    assert api.client.post(SEND, json={"phone": PHONE}).status_code == 200
    assert len(api.sent) == 2


def test_unknown_phone_and_wrong_code_get_the_same_answer(api):
    api.client.post(SEND, json={"phone": PHONE})
    wrong = api.client.post(VERIFY, json={"phone": PHONE, "otp_code": "000000" if api.last_otp() != "000000" else "111111"})
    unknown = api.client.post(VERIFY, json={"phone": "01799999999", "otp_code": "123456"})

    assert wrong.status_code == unknown.status_code == 400
    assert wrong.json() == unknown.json()


def test_ip_rate_limit_on_send_otp(api):
    codes = [
        api.client.post(SEND, json={"phone": f"0171111111{i}"}).status_code
        for i in range(4)
    ]
    assert codes == [200, 200, 200, 429]


# ---- phone handling ----------------------------------------------------------
@pytest.mark.parametrize("bad", ["abcdefghijk", "0171111111", "02711111111", ""])
def test_invalid_phone_gets_400_and_no_sms(api, bad):
    r = api.client.post(SEND, json={"phone": bad})
    assert r.status_code == 400
    assert api.sent == []


def test_different_formats_of_one_number_are_one_account(api):
    api.client.post(SEND, json={"phone": "+8801711111111"})
    r = api.client.post(VERIFY, json={"phone": "০১৭১১১১১১১১", "otp_code": api.last_otp()})
    assert r.status_code == 200

    with api.Session() as db:
        assert [u.phone for u in db.query(User).all()] == [PHONE]


def test_account_saved_in_an_old_format_can_still_log_in(api):
    with api.Session() as db:
        db.add(User(phone="+8801711111111", role=UserRole.EMPLOYER))
        db.commit()

    account = api.login(PHONE)

    with api.Session() as db:
        assert db.query(User).count() == 1
        assert db.get(User, account.id).role == UserRole.EMPLOYER


# ---- AUDIT #6 / #7: SMS failure and error text -------------------------------
def test_sms_failure_returns_503_and_drops_the_code(api, monkeypatch):
    async def _failing(phone, message):
        return False

    monkeypatch.setattr(users_module, "send_sms", _failing)
    r = api.client.post(SEND, json={"phone": PHONE})

    assert r.status_code == 503
    user = _user(api)
    assert user.otp_code is None and user.otp_expires_at is None


def test_unexpected_error_text_is_not_sent_to_the_client(api, monkeypatch):
    async def _boom(phone, message):
        raise RuntimeError("db password is hunter2")

    monkeypatch.setattr(users_module, "send_sms", _boom)
    r = api.client.post(SEND, json={"phone": PHONE})

    assert r.status_code == 500
    assert "hunter2" not in r.text
    assert "RuntimeError" not in r.text


def test_production_without_sms_token_fails_instead_of_logging_the_otp(monkeypatch, caplog):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("GREENWEB_TOKEN", raising=False)

    with caplog.at_level(logging.DEBUG):
        ok = asyncio.run(send_sms(PHONE, "code 654321"))

    assert ok is False
    assert "654321" not in caplog.text
    assert PHONE not in caplog.text


def test_development_sms_log_never_contains_the_full_phone(monkeypatch, caplog):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("GREENWEB_TOKEN", raising=False)

    with caplog.at_level(logging.DEBUG):
        assert asyncio.run(send_sms(PHONE, "code 654321")) is True

    assert PHONE not in caplog.text


# ---- AUDIT #3: tokens ---------------------------------------------------------
def test_token_signed_with_the_old_public_default_key_is_rejected(api):
    account = api.login(PHONE)
    forged = jwt.encode(
        {"sub": str(account.id), "exp": datetime.now(timezone.utc) + timedelta(days=1)},
        "default_secret_key",
        algorithm="HS256",
    )
    assert api.client.get(ME, headers={"Authorization": f"Bearer {forged}"}).status_code == 401


@pytest.mark.parametrize(
    "claims",
    [
        {"sub": "abc", "exp": datetime.now(timezone.utc) + timedelta(days=1)},  # used to be a 500
        {"sub": "1"},  # no expiry
        {"exp": datetime.now(timezone.utc) + timedelta(days=1)},  # no subject
        {"sub": "1", "exp": datetime.now(timezone.utc) - timedelta(seconds=5)},  # expired
        {"sub": "999999", "exp": datetime.now(timezone.utc) + timedelta(days=1)},  # no such user
    ],
)
def test_bad_tokens_get_401_not_500(api, claims):
    api.login(PHONE)
    token = jwt.encode(claims, TEST_KEY, algorithm="HS256")
    assert api.client.get(ME, headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_production_without_secret_key_refuses_tokens_with_503(api, monkeypatch):
    account = api.login(PHONE)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("SECRET_KEY", raising=False)

    r = api.client.get(ME, headers=account.headers)
    assert r.status_code == 503
    assert "SECRET_KEY" not in r.text

    # And nobody can sign their way in with the old default either.
    forged = jwt.encode(
        {"sub": str(account.id), "exp": datetime.now(timezone.utc) + timedelta(days=1)},
        "default_secret_key",
        algorithm="HS256",
    )
    assert api.client.get(ME, headers={"Authorization": f"Bearer {forged}"}).status_code == 503
