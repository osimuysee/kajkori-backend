"""Unit tests for phone normalisation and OTP hashing. Fake numbers only."""
import re

import pytest

from app.core.phone import mask_phone, normalize_bd_phone, phone_lookup_forms
from app.security.otp import clean_otp, generate_otp, hash_otp, otp_matches

PHONE = "01711111111"


@pytest.mark.parametrize(
    "raw",
    ["01711111111", "+8801711111111", "8801711111111", "017-1111 1111", "০১৭১১১১১১১১", "+880 1711-111111"],
)
def test_every_common_format_becomes_one_canonical_number(raw):
    assert normalize_bd_phone(raw) == PHONE


@pytest.mark.parametrize(
    "bad",
    ["", "abcdefghijk", "0171111111", "017111111111", "01211111111", "02711111111", "+9101711111111", "1711111111"],
)
def test_invalid_numbers_are_rejected(bad):
    with pytest.raises(ValueError):
        normalize_bd_phone(bad)


def test_non_text_phone_is_rejected():
    with pytest.raises(ValueError):
        normalize_bd_phone(1711111111)  # type: ignore[arg-type]


def test_lookup_forms_cover_legacy_storage_formats():
    assert phone_lookup_forms(PHONE) == [PHONE, "8801711111111", "+8801711111111"]


def test_mask_phone_hides_the_middle():
    masked = mask_phone(PHONE)
    assert masked == "017******11"
    assert PHONE not in masked
    assert mask_phone("") == "***"


def test_generated_otp_is_always_six_digits():
    for _ in range(200):
        assert re.fullmatch(r"[0-9]{6}", generate_otp())


def test_clean_otp_accepts_bangla_digits_and_spaces():
    assert clean_otp(" ১২৩ ৪৫৬ ") == "123456"


def test_hash_does_not_contain_the_code_and_is_bound_to_the_phone():
    h = hash_otp(PHONE, "123456")
    assert re.fullmatch(r"[0-9a-f]{64}", h)
    assert "123456" not in h
    assert h != hash_otp("01722222222", "123456")


def test_otp_matches_only_the_right_code():
    h = hash_otp(PHONE, "123456")
    assert otp_matches(PHONE, "123456", h) is True
    assert otp_matches(PHONE, "১২৩৪৫৬", h) is True
    assert otp_matches(PHONE, "123457", h) is False
    assert otp_matches(PHONE, "123456", None) is False
    # A plain-text code left over from the old scheme must never match itself.
    assert otp_matches(PHONE, "123456", "123456") is False


def test_changing_the_secret_key_invalidates_old_hashes(monkeypatch):
    h = hash_otp(PHONE, "123456")
    monkeypatch.setenv("SECRET_KEY", "k" * 40)
    assert otp_matches(PHONE, "123456", h) is False
