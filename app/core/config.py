"""Environment handling for NEW code.

Older modules (app/auth.py, app/database.py, app/services/sms.py) still call
os.getenv directly. Move them here one file at a time, not all at once.

Design rule: fail CLOSED. If APP_ENV is not set we assume production, so a
forgotten variable on the server stops the app instead of silently falling
back to a development value.
"""
import os

from dotenv import load_dotenv

load_dotenv()

DEV_ENVS = {"development", "test"}


class ConfigError(RuntimeError):
    """A required setting is missing or too weak."""


def app_env() -> str:
    return os.getenv("APP_ENV", "production").strip().lower()


def is_production() -> bool:
    return app_env() not in DEV_ENVS


def require_secret(name: str, *, dev_fallback: str, min_length: int = 32) -> str:
    """Return a secret from the environment.

    - Set but shorter than min_length  -> always an error (even in dev).
    - Not set, production              -> error.
    - Not set, development/test        -> dev_fallback (never use it in prod).
    """
    value = os.getenv(name, "").strip()
    if value:
        if len(value) < min_length:
            raise ConfigError(f"{name} is too short: need at least {min_length} characters.")
        return value
    if is_production():
        raise ConfigError(
            f"{name} is not set. Generate one with: "
            'python -c "import secrets; print(secrets.token_urlsafe(48))"'
        )
    return dev_fallback


# Only reachable when APP_ENV is explicitly "development" or "test".
_DEV_SECRET_KEY = "dev-only-secret-key-never-use-in-production-0000"


def secret_key() -> str:
    """Key that signs JWTs and keys the OTP hashes.

    Read on every call (not cached at import) so a missing key in production
    raises ConfigError where it is used instead of silently using a default.
    """
    return require_secret("SECRET_KEY", dev_fallback=_DEV_SECRET_KEY)


def cors_allowed_origins() -> list[str]:
    """Comma-separated CORS_ALLOWED_ORIGINS, e.g. "https://kajkori.com,https://www.kajkori.com"."""
    raw = os.getenv("CORS_ALLOWED_ORIGINS", "")
    return [o.strip().rstrip("/") for o in raw.split(",") if o.strip()]
