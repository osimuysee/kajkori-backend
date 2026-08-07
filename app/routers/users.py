import random
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.auth import create_access_token, get_current_user
from app.database import get_db
from app.limiter import limiter
from app.models import Job, JobApplication, Transaction, User, UserRole
from app.schemas import (
    ApplicationResponse,
    JobResponse,
    OTPRequest,
    OTPVerify,
    Token,
    TransactionResponse,
    UserResponse,
)
from app.services.sms import send_sms

router = APIRouter(prefix="/api/v1/users", tags=["User & Dashboard"])


# ১. OTP পাঠানো (Rate Limited + Database + Real/Dev SMS)
@router.post("/send-otp")
@limiter.limit("3/minute")
async def send_otp(
    http_request: Request,
    otp_data: OTPRequest,
    db: Session = Depends(get_db)
):
    # ১১ ডিজিট চেক
    if len(otp_data.phone) < 11:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="সঠিক ১১ ডিজিটের মোবাইল নম্বর দিন"
        )

    generated_otp = str(random.randint(1000, 9999))
    user = db.query(User).filter(User.phone == otp_data.phone).first()

    selected_role = (
        UserRole.EMPLOYER
        if otp_data.role and otp_data.role.lower() == "employer"
        else UserRole.WORKER
    )

    if not user:
        user = User(
            phone=otp_data.phone, role=selected_role, otp_code=generated_otp
        )
        db.add(user)
    else:
        user.otp_code = generated_otp

    db.commit()

    # Greenweb SMS Service কল করা
    sms_text = f"KajKori প্ল্যাটফর্মে আপনার ভেরিফিকেশন কোড (OTP): {generated_otp}"
    await send_sms(otp_data.phone, sms_text)

    return {
        "status": "success",
        "message": f"OTP sent to {otp_data.phone}",
        "debug_otp": generated_otp,
    }


# ২. OTP ভেরিফাই ও টোকেন জেনারেশন
@router.post("/verify-otp", response_model=Token)
def verify_otp(request: OTPVerify, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.phone == request.phone).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    if user.otp_code != request.otp_code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OTP code"
        )

    user.is_verified = True
    user.otp_code = None
    db.commit()
    db.refresh(user)

    access_token = create_access_token(data={"sub": str(user.id)})

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": user,
    }


# ৩. নিজের প্রোফাইল দেখা
@router.get("/me", response_model=UserResponse)
def get_my_profile(current_user: User = Depends(get_current_user)):
    return current_user


# ৪. ড্যাশবোর্ড: নিজের পোস্ট করা কাজের তালিকা (Employer Dashboard)
@router.get("/me/jobs", response_model=List[JobResponse])
def get_my_jobs(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return db.query(Job).filter(Job.employer_id == current_user.id).all()


# ৫. ড্যাশবোর্ড: নিজের করা আবেদনের তালিকা (Worker Dashboard)
@router.get("/me/applications", response_model=List[ApplicationResponse])
def get_my_applications(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return (
        db.query(JobApplication)
        .filter(JobApplication.worker_id == current_user.id)
        .all()
    )


# ৬. ড্যাশবোর্ড: লেনদেনের ইতিহাস (Payment History)
@router.get("/me/transactions", response_model=List[TransactionResponse])
def get_my_transactions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return (
        db.query(Transaction)
        .filter(Transaction.receiver_id == current_user.id)
        .all()
    )