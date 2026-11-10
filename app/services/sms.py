import logging
import os

import httpx

from app.core.config import is_production
from app.core.phone import mask_phone

logger = logging.getLogger("kajkori.sms")

GREENWEB_URL = "https://api.greenweb.com.bd/api.php"


async def send_sms(to_phone: str, message: str) -> bool:
    """
    Greenweb BD API ব্যবহার করে SMS পাঠানোর সার্ভিস

    Returns True only when the gateway accepted the message. Never logs the
    message text or the full phone number outside development.
    """
    # Read at call time so a token added later (or removed) is respected.
    token = os.getenv("GREENWEB_TOKEN", "").strip()

    if not token:
        if is_production():
            # Fail instead of "succeeding": otherwise the user waits for an SMS
            # that never arrives and the OTP ends up in the server log.
            logger.error("GREENWEB_TOKEN is not set: SMS was NOT sent.")
            return False
        # Local development only (APP_ENV=development/test). ascii() keeps this
        # from crashing on consoles that cannot print Bangla.
        logger.warning("[DEV SMS, not sent] to=%s message=%s", mask_phone(to_phone), ascii(message))
        return True

    # নম্বরটিকে ৮৮০১... ফরম্যাটে কনভার্ট করা
    clean_phone = to_phone.strip()
    if clean_phone.startswith("+88"):
        clean_phone = clean_phone[1:]
    elif clean_phone.startswith("01"):
        clean_phone = "88" + clean_phone

    payload = {
        "token": token,
        "to": clean_phone,
        "message": message,
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(GREENWEB_URL, data=payload, timeout=10.0)
    except Exception as exc:
        # Type name only: the exception text can contain request details.
        logger.error("SMS gateway request failed (%s) to=%s", type(exc).__name__, mask_phone(to_phone))
        return False

    # The gateway can answer HTTP 200 with a body that starts with "Error".
    body = (response.text or "").strip()
    accepted = response.status_code == 200 and not body.lower().startswith("error")
    if not accepted:
        logger.error("SMS gateway rejected the message: http=%s to=%s", response.status_code, mask_phone(to_phone))
    return accepted
