"""Bangladeshi mobile numbers: one canonical form, and masking for logs."""
import re

# Bangla digits to ASCII, so "০১৭..." and "017..." are the same number.
_BANGLA_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")
_BD_MOBILE = re.compile(r"01[3-9][0-9]{8}")


def normalize_bd_phone(raw: str) -> str:
    """Return the number as 01XXXXXXXXX (11 digits).

    Accepts +8801..., 8801..., 01..., spaces, dashes and Bangla digits.
    Raises ValueError for anything that is not a Bangladeshi mobile number.
    """
    if not isinstance(raw, str):
        raise ValueError("Phone must be text.")
    cleaned = raw.translate(_BANGLA_DIGITS)
    for ch in (" ", "-", "(", ")"):
        cleaned = cleaned.replace(ch, "")
    if cleaned.startswith("+880"):
        cleaned = "0" + cleaned[4:]
    elif cleaned.startswith("880") and len(cleaned) == 13:
        cleaned = "0" + cleaned[3:]
    if not _BD_MOBILE.fullmatch(cleaned):
        raise ValueError("Not a valid Bangladeshi mobile number.")
    return cleaned


def phone_lookup_forms(canonical: str) -> list[str]:
    """Every way the same number may already be stored in users.phone.

    Before normalisation existed, "+88017..." and "017..." were saved as typed.
    Looking up all forms keeps those accounts reachable.
    """
    return [canonical, "88" + canonical, "+88" + canonical]


def mask_phone(phone: str) -> str:
    """For logs only: 017******78. Never log a full phone number."""
    digits = str(phone or "")
    if len(digits) < 6:
        return "***"
    return f"{digits[:3]}{'*' * (len(digits) - 5)}{digits[-2:]}"
