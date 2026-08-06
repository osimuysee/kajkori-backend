from fastapi import APIRouter, Response, Form, Depends
from sqlalchemy.orm import Session
from app.database import get_db

router = APIRouter(prefix="/api/ivr", tags=["SMS & IVR Service"])


@router.post("/voice")
async def ivr_voice_handler(Digits: str = Form(None)):
    """
    বাটন ফোনে কল দেওয়ার পর কিপ্যাড প্রেস (DTMF) হ্যান্ডেল করার এন্ডপয়েন্ট
    """
    if Digits == "1":
        message = "কাজ খোঁজার জন্য ধন্যবাদ। আপনার এলাকায় নতুন কাজের তথ্য থাকলে এসএমএস এর মাধ্যমে জানানো হবে।"
    elif Digits == "2":
        message = "শ্রমিক হিসেবে রেজিস্ট্রেশন করতে আপনার নাম এবং কাজের ধরন লিখে মেসেজ পাঠান।"
    else:
        message = "কাজকর্মে আপনাকে স্বাগতম। কাজের তথ্য জানতে ১ চাপুন, শ্রমিক হিসেবে নাম লেখাতে ২ চাপুন।"

    # Twilio / Voice Gateway সামঞ্জস্যপূর্ণ TwiML XML রেসপন্স
    twiml_response = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="alice" language="bn-BD">{message}</Say>
</Response>"""

    return Response(content=twiml_response, media_type="application/xml")


@router.post("/sms")
async def sms_webhook_handler(
    Body: str = Form(...), From: str = Form(...), db: Session = Depends(get_db)
):
    """
    বাটন ফোন থেকে আসা সাধারণ SMS প্রসেস করার এন্ডপয়েন্ট
    উদাহরণ: "WORKER Rahim Painter" অথবা "JOB Plumber 500"
    """
    text = Body.strip().upper()

    if text.startswith("WORKER"):
        reply = "আপনার কর্মী প্রোফাইল সফলভাবে তৈরি হয়েছে। ধন্যবাদ!"
    elif text.startswith("JOB"):
        reply = "আপনার কাজ পোস্ট করার অনুরোধ গ্রহণ করা হয়েছে। নিকটস্থ কর্মীদের কাছে নোটিফিকেশন পাঠানো হচ্ছে।"
    else:
        reply = (
            "কাজকর্ম হেল্পডেস্ক:\n"
            "১. কর্মী হতে লিখুন: WORKER <নাম> <কাজের ধরন>\n"
            "২. কাজ পোস্ট করতে লিখুন: JOB <কাজের নাম> <বাজেট>"
        )

    twiml_sms = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Message>{reply}</Message>
</Response>"""

    return Response(content=twiml_sms, media_type="application/xml")