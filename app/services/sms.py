import os
import httpx

GREENWEB_TOKEN = os.getenv("GREENWEB_TOKEN", "")

async def send_sms(to_phone: str, message: str) -> bool:
    """
    Greenweb BD API ব্যবহার করে SMS পাঠানোর সার্ভিস
    """
    if not GREENWEB_TOKEN:
        print(f"\n[DEV MODE SMS Log] -> To: {to_phone} | Message: {message}\n")
        return True

    # নম্বরটিকে ৮৮০১... ফরম্যাটে কনভার্ট করা
    clean_phone = to_phone.strip()
    if clean_phone.startswith("+88"):
        clean_phone = clean_phone[1:]
    elif clean_phone.startswith("01"):
        clean_phone = "88" + clean_phone

    url = "https://api.greenweb.com.bd/api.php"
    payload = {
        "token": GREENWEB_TOKEN,
        "to": clean_phone,
        "message": message
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, data=payload, timeout=10.0)
            print(f"Greenweb Response: {response.text}") # লগে Greenweb-এর আসল রেসপন্স দেখতে
            return response.status_code == 200
    except Exception as e:
        print(f"SMS Sending Failed: {e}")
        return False