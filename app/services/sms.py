import os
import httpx

GREENWEB_TOKEN = os.getenv("GREENWEB_TOKEN", "")

async def send_sms(to_phone: str, message: str) -> bool:
    """
    Greenweb BD API ব্যবহার করে SMS পাঠানোর সার্ভিস
    """
    # যদি API Token না থাকে (Local Dev Mode)
    if not GREENWEB_TOKEN:
        print(f"\n[DEV MODE SMS Log] -> To: {to_phone} | Message: {message}\n")
        return True

    url = "https://api.greenweb.com.bd/api.php"
    payload = {
        "token": GREENWEB_TOKEN,
        "to": to_phone,
        "message": message
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, data=payload, timeout=10.0)
            return response.status_code == 200
    except Exception as e:
        print(f"SMS Sending Failed: {e}")
        return False