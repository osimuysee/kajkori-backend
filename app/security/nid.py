"""NID handling. The raw NID number must never be stored or logged.

What we store is nid_hash = HMAC-SHA256(secret pepper, normalised digits).
A UNIQUE index on that column makes "one NID, one worker account" a database
guarantee, and a leaked database alone does not reveal NID numbers.

Limits you should know about:
- The NID space is small (10-17 digits). If the pepper leaks together with the
  database, hashes can be brute-forced. Keep NID_HMAC_PEPPER OUT of the
  database and out of git. Changing it later invalidates every stored hash.
- Different number formats are NOT linked. NIDs can be 10, 13 or 17 digits
  (UK Home Office country note, Nov 2024). I could not confirm from an official
  source how a 17-digit number relates to a 13-digit one, so this module does
  not guess. The same person with two number formats is NOT caught here; that
  needs face matching and an eKYC provider or Election Commission check.
"""
import hashlib
import hmac

from app.core.config import require_secret

ALLOWED_LENGTHS = (10, 13, 17)

# Bangla digits to ASCII, so "১২৩..." and "123..." hash identically.
_BANGLA_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")

_DEV_PEPPER = "dev-only-pepper-never-use-in-production-0000"


def normalize_nid(raw: str) -> str:
    """Return digits only. Accepts Bangla digits, spaces and dashes."""
    if not isinstance(raw, str):
        raise ValueError("NID must be text.")
    cleaned = raw.translate(_BANGLA_DIGITS)
    for ch in (" ", "-", "‌", "‍"):
        cleaned = cleaned.replace(ch, "")
    if not (cleaned.isascii() and cleaned.isdigit()):
        raise ValueError("NID may contain digits only.")
    if len(cleaned) not in ALLOWED_LENGTHS:
        raise ValueError("NID must be 10, 13 or 17 digits.")
    return cleaned


def hash_nid(raw: str) -> str:
    """HMAC-SHA256 hex digest (64 chars) of the normalised NID."""
    nid = normalize_nid(raw)
    pepper = require_secret("NID_HMAC_PEPPER", dev_fallback=_DEV_PEPPER)
    return hmac.new(pepper.encode("utf-8"), nid.encode("ascii"), hashlib.sha256).hexdigest()
