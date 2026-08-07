import random
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.auth import create_access_token, get_current_user
from app.database import get_db
from app.limiter import limiter
from app.models import Job, JobStatus, Review, User, UserRole
from app.schemas import (
    OTPRequest,
    OTPVerify,
    ProfileUpdate,
    ReviewCreate,
    ReviewResponse,
    Token,
    UserResponse,
)
from app.services.sms import send_sms

router = APIRouter(prefix="/api/v1/users", tags=["User, Profile & Reviews"])


# ১. OTP পাঠানো
@router.post("/send-otp")
@limiter.limit("3/minute")
async def send_otp(
    request: Request,
    otp_data: OTPRequest,
    db: Session = Depends(get_db)
):
    try:
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

        sms_text = f"KajKori প্ল্যাটফর্মে আপনার ভেরিফিকেশন কোড (OTP): {generated_otp}"
        await send_sms(otp_data.phone, sms_text)

        return {
            "status": "success",
            "message": f"OTP sent to {otp_data.phone}",
            "debug_otp": generated_otp,
        }
    except HTTPException as http_ex:
        raise http_ex
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Server Execution Error: {str(e)}"
        )


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


# ৪. নিজের প্রোফাইল আপডেট করা (বিভাগ, জেলা, উপজেলা, ইউনিয়ন, গ্রাম সহ)
@router.put("/me", response_model=UserResponse)
def update_profile(
    profile_data: ProfileUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if profile_data.full_name is not None:
        current_user.full_name = profile_data.full_name
    if profile_data.location_division is not None:
        current_user.location_division = profile_data.location_division
    if profile_data.location_district is not None:
        current_user.location_district = profile_data.location_district
    if profile_data.location_upazila is not None:
        current_user.location_upazila = profile_data.location_upazila
    if profile_data.location_union is not None:
        current_user.location_union = profile_data.location_union
    if profile_data.location_village_area is not None:
        current_user.location_village_area = profile_data.location_village_area

    db.commit()
    db.refresh(current_user)
    return current_user


# ৫. যেকোনো ইউজারের পাবলিক প্রোফাইল দেখা
@router.get("/{user_id}", response_model=UserResponse)
def get_user_public_profile(user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="ইউজার পাওয়া যায়নি",
        )
    return user


# ৬. কাজ শেষে রেটিং/রিভিউ প্রদান করা
@router.post("/review", response_model=ReviewResponse)
def give_review(
    review_data: ReviewCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if review_data.rating < 1 or review_data.rating > 5:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="রেটিং ১ থেকে ৫ এর মধ্যে হতে হবে",
        )

    job = db.query(Job).filter(Job.id == review_data.job_id).first()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="কাজটি পাওয়া যায়নি"
        )

    if job.status != JobStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="কাজ সম্পন্ন হওয়ার আগে রিভিউ দেওয়া যাবে না",
        )

    if current_user.id not in [job.employer_id, job.worker_id]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="এই কাজের অংশীদার ছাড়া রিভিউ দেওয়া সম্ভব নয়",
        )

    new_review = Review(
        job_id=review_data.job_id,
        reviewer_id=current_user.id,
        target_user_id=review_data.target_user_id,
        rating=review_data.rating,
        comment=review_data.comment,
    )

    db.add(new_review)
    db.commit()
    db.refresh(new_review)
    return new_review


# ৭. নির্দিষ্ট ইউজারের রিভিউ তালিকা ও গড় রেটিং
@router.get("/{user_id}/reviews")
def get_user_reviews(user_id: int, db: Session = Depends(get_db)):
    reviews = db.query(Review).filter(Review.target_user_id == user_id).all()
    if not reviews:
        return {"target_user_id": user_id, "average_rating": 0.0, "total_reviews": 0, "reviews": []}

    avg_rating = sum(r.rating for r in reviews) / len(reviews)
    return {
        "target_user_id": user_id,
        "average_rating": round(avg_rating, 2),
        "total_reviews": len(reviews),
        "reviews": reviews,
    }