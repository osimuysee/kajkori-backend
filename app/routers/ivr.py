from fastapi import APIRouter, Form, Depends
from sqlalchemy.orm import Session
from app.database import get_db

router = APIRouter(
    prefix="/api/v1/ivr",
    tags=["IVR Webhook"]
)

@router.post("/dtmf-response")
async def handle_ivr_keypress(
    job_id: int = Form(...),
    worker_phone: str = Form(...),
    digits: str = Form(...),
    db: Session = Depends(get_db)
):
    if digits == "1":
        # এখানে ডাটাবেজে আপডেট লজিক বসবে
        return {
            "status": "success",
            "message": "Job accepted successfully",
            "voice_response_text": "ধন্যবাদ। কাজটি আপনার জন্য নিশ্চিত করা হয়েছে।"
        }
    elif digits == "2":
        return {
            "status": "rejected",
            "message": "Job declined by worker",
            "voice_response_text": "ধন্যবাদ। পরবর্তী কাজের জন্য আপনাকে জানানো হবে।"
        }
    else:
        return {
            "status": "invalid_input",
            "voice_response_text": "সঠিক বোতাম চাপুন। রাজি থাকলে ১ চাপুন।"
        }