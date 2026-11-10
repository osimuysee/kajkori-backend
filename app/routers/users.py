import logging
from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.auth import create_access_token, get_current_user
from app.core.phone import mask_phone, normalize_bd_phone, phone_lookup_forms
from app.core.types import ensure_utc, utcnow
from app.database import get_db
from app.limiter import limiter
from app.models import Job, JobStatus, Review, User, UserRole
from app.schemas import (
    OTPRequest,
    OTPVerify,
    ProfileUpdate,
    PublicUserResponse,
    ReviewCreate,
    ReviewResponse,
    Token,
    UserResponse,
)
from app.security.otp import generate_otp, hash_otp, otp_matches
from app.services.sms import send_sms

logger = logging.getLogger("kajkori.users")

router = APIRouter(prefix="/api/v1/users", tags=["User, Profile & Reviews"])

OTP_TTL = timedelta(minutes=5)
# One SMS per phone per minute, whatever IP asks for it. The slowapi limit is
# per IP only, so rotating IPs would otherwise allow SMS flooding and an
# unlimited supply of fresh guesses.
OTP_RESEND_COOLDOWN = timedelta(seconds=60)
OTP_MAX_ATTEMPTS = 5

# Same answer for "no such user", "no code", "expired" and "wrong code", so the
# endpoint cannot be used to find out which phone numbers have an account.
_OTP_INVALID_DETAIL = "OTP সঠিক নয় অথবা মেয়াদ শেষ হয়ে গেছে"


def _find_user_by_phone(db: Session, canonical_phone: str, *, lock: bool = False) -> Optional[User]:
    query = db.query(User).filter(User.phone.in_(phone_lookup_forms(canonical_phone)))
    if lock:
        # Row lock on PostgreSQL so parallel guesses cannot skip the attempt
        # counter. SQLite ignores FOR UPDATE.
        query = query.with_for_update()
    return query.order_by(User.id).first()


# ১. OTP পাঠানো
@router.post("/send-otp")
@limiter.limit("3/minute")
async def send_otp(
    request: Request,
    otp_data: OTPRequest,
    db: Session = Depends(get_db)
):
    try:
        phone = normalize_bd_phone(otp_data.phone)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="সঠিক ১১ ডিজিটের মোবাইল নম্বর দিন"
        )

    try:
        user = _find_user_by_phone(db, phone)
        now = utcnow()

        if user and user.otp_expires_at:
            last_sent_at = ensure_utc(user.otp_expires_at) - OTP_TTL
            wait = OTP_RESEND_COOLDOWN - (now - last_sent_at)
            if wait > timedelta(0):
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="একটু আগেই OTP পাঠানো হয়েছে। কিছুক্ষণ পর আবার চেষ্টা করুন।",
                    headers={"Retry-After": str(max(1, int(wait.total_seconds())))},
                )

        # ৬-ডিজিট crypto-secure OTP. Only its hash is stored.
        generated_otp = generate_otp()
        otp_hash = hash_otp(phone, generated_otp)
        expires_at = now + OTP_TTL

        if not user:
            selected_role = (
                UserRole.EMPLOYER
                if otp_data.role and otp_data.role.lower() == "employer"
                else UserRole.WORKER
            )
            user = User(
                phone=phone, role=selected_role, otp_code=otp_hash,
                otp_expires_at=expires_at, otp_attempts=0
            )
            db.add(user)
        else:
            user.otp_code = otp_hash
            user.otp_expires_at = expires_at
            user.otp_attempts = 0

        db.commit()

        sms_text = f"KajKori প্ল্যাটফর্মে আপনার ভেরিফিকেশন কোড (OTP): {generated_otp}"
        sms_ok = await send_sms(phone, sms_text)
        if not sms_ok:
            # The code never reached the user: drop it so it cannot be guessed
            # and so the resend cooldown does not block an immediate retry.
            user.otp_code = None
            user.otp_expires_at = None
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="এই মুহূর্তে SMS পাঠানো যাচ্ছে না। কিছুক্ষণ পর আবার চেষ্টা করুন।"
            )

        # Do NOT return the OTP in responses — never expose in production
        return {
            "status": "success",
            "message": "আপনার মোবাইল নম্বরে OTP পাঠানো হয়েছে",
        }
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        # Details stay in the server log (type name and masked phone only);
        # the client gets a generic message.
        logger.error("send-otp failed (%s) for %s", type(exc).__name__, mask_phone(phone))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="সার্ভারে সমস্যা হয়েছে। কিছুক্ষণ পর আবার চেষ্টা করুন।"
        )


# ২. OTP ভেরিফাই ও টোকেন জেনারেশন
@router.post("/verify-otp", response_model=Token)
@limiter.limit("10/minute")
def verify_otp(request: Request, otp_data: OTPVerify, db: Session = Depends(get_db)):
    invalid = HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST, detail=_OTP_INVALID_DETAIL
    )

    try:
        phone = normalize_bd_phone(otp_data.phone)
    except ValueError:
        raise invalid

    user = _find_user_by_phone(db, phone, lock=True)
    if not user or not user.otp_code or not user.otp_expires_at:
        raise invalid

    # otp_expires_at is a legacy naive column: make it aware before comparing.
    # Comparing naive with aware raised TypeError, i.e. HTTP 500 on every login.
    if ensure_utc(user.otp_expires_at) < utcnow():
        raise invalid

    if (user.otp_attempts or 0) >= OTP_MAX_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="অনেকবার ভুল কোড দেওয়া হয়েছে। নতুন OTP নিন।"
        )

    if not otp_matches(phone, otp_data.otp_code, user.otp_code):
        user.otp_attempts = (user.otp_attempts or 0) + 1
        db.commit()
        raise invalid

    # Successful verification: the code is single-use.
    user.is_verified = True
    user.otp_code = None
    user.otp_expires_at = None
    user.otp_attempts = 0
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


# ৪. নিজের প্রোফাইল আপডেট করা (বিভাগ, জেলা, উপজেলা, ইউনিয়ন, গ্রাম সহ)
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
# PublicUserResponse on purpose: this route needs no login and IDs are
# sequential, so it must never return phone, wallet or exact address.
@router.get("/{user_id}", response_model=PublicUserResponse)
def get_user_public_profile(user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="ইউজার পাওয়া যায়নি",
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
            status_code=status.HTTP_404_NOT_FOUND, detail="কাজটি পাওয়া যায়নি"
        )

    if job.status != JobStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="কাজ সম্পন্ন হওয়ার আগে রিভিউ দেওয়া যাবে না",
        )

    if current_user.id not in [job.employer_id, job.worker_id]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="এই কাজের অংশীদার ছাড়া রিভিউ দেওয়া সম্ভব নয়",
        )

    # A review can only be about the OTHER party of this job: never yourself,
    # never somebody who had nothing to do with it.
    other_party_id = job.worker_id if current_user.id == job.employer_id else job.employer_id
    if other_party_id is None or other_party_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="এই কাজে রিভিউ দেওয়ার মতো অপর পক্ষ নেই",
        )
    if review_data.target_user_id != other_party_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="শুধুমাত্র এই কাজের অপর পক্ষকে রিভিউ দেওয়া যাবে",
        )

    already_reviewed = (
        db.query(Review)
        .filter(Review.job_id == job.id, Review.reviewer_id == current_user.id)
        .first()
    )
    if already_reviewed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="আপনি ইতিমধ্যে এই কাজের রিভিউ দিয়েছেন",
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


# ৭. নির্দিষ্ট ইউজারের রিভিউ তালিকা ও গড় রেটিং
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
