import re

import pytest

from app.core.config import ConfigError
from app.security.nid import hash_nid, normalize_nid

NID13 = "1234567890123"


def test_normalize_strips_spaces_and_dashes():
    assert normalize_nid("123 456-7890123") == NID13


def test_normalize_converts_bangla_digits():
    assert normalize_nid("১২৩৪৫৬৭৮৯০১২৩") == NID13


@pytest.mark.parametrize("bad", ["", "123", "12345678901234", "abcdefghij", "12345678901X", "١٢٣٤٥٦٧٨٩٠"])
def test_normalize_rejects_bad_input(bad):
    with pytest.raises(ValueError):
        normalize_nid(bad)


@pytest.mark.parametrize("length", [10, 13, 17])
def test_allowed_lengths(length):
    assert normalize_nid("1" * length) == "1" * length


def test_normalize_rejects_non_text():
    with pytest.raises(ValueError):
        normalize_nid(1234567890123)  # type: ignore[arg-type]


def test_hash_is_64_hex_and_does_not_contain_the_nid():
    h = hash_nid(NID13)
    assert re.fullmatch(r"[0-9a-f]{64}", h)
    assert NID13 not in h


def test_hash_is_stable_and_format_independent():
    assert hash_nid(NID13) == hash_nid("123 456-7890123") == hash_nid("১২৩৪৫৬৭৮৯০১২৩")


def test_different_nid_gives_different_hash():
    assert hash_nid(NID13) != hash_nid("1234567890124")


def test_pepper_changes_the_hash(monkeypatch):
    before = hash_nid(NID13)
    monkeypatch.setenv("NID_HMAC_PEPPER", "p" * 40)
    assert hash_nid(NID13) != before


def test_production_without_pepper_refuses_to_hash(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("NID_HMAC_PEPPER", raising=False)
    with pytest.raises(ConfigError):
        hash_nid(NID13)
