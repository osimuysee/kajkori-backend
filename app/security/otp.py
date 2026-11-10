"""One-time login codes. The code itself is never stored and never logged.

What we store in users.otp_code is HMAC-SHA256(SECRET_KEY, phone + code), so a
leaked database does not reveal a usable code, and a hash made for one phone
cannot be replayed for another.
"""
import hashlib
import hmac
import secrets

from app.core.config import secret_key

OTP_DIGITS = 6
_BANGLA_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")


def generate_otp() -> str:
    """Six digits from the OS random source (leading zeros kept)."""
    return f"{secrets.randbelow(10 ** OTP_DIGITS):0{OTP_DIGITS}d}"


def clean_otp(raw: str) -> str:
    """What the user typed, as ASCII digits ("১২৩ ৪৫৬" -> "123456")."""
    return str(raw or "").translate(_BANGLA_DIGITS).replace(" ", "").strip()


def hash_otp(phone: str, code: str) -> str:
    message = f"kajkori-otp-v1|{phone}|{code}".encode("utf-8")
    return hmac.new(secret_key().encode("utf-8"), message, hashlib.sha256).hexdigest()


def otp_matches(phone: str, code: str, stored_hash: str | None) -> bool:
    """Constant-time comparison of a typed code against the stored hash."""
    if not stored_hash:
        return False
    return hmac.compare_digest(hash_otp(phone, clean_otp(code)), stored_hash)
