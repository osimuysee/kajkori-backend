import pytest

from app.core.config import ConfigError, is_production, require_secret

LONG = "x" * 40


def test_unset_app_env_is_treated_as_production(monkeypatch):
    monkeypatch.delenv("APP_ENV", raising=False)
    assert is_production() is True


def test_missing_secret_in_production_raises(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("SOME_SECRET", raising=False)
    with pytest.raises(ConfigError):
        require_secret("SOME_SECRET", dev_fallback=LONG)


def test_missing_secret_in_test_env_uses_fallback(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.delenv("SOME_SECRET", raising=False)
    assert require_secret("SOME_SECRET", dev_fallback=LONG) == LONG


def test_short_secret_is_rejected_even_in_dev(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("SOME_SECRET", "short")
    with pytest.raises(ConfigError):
        require_secret("SOME_SECRET", dev_fallback=LONG)


def test_strong_secret_is_returned(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SOME_SECRET", LONG)
    assert require_secret("SOME_SECRET", dev_fallback="unused" * 10) == LONG
