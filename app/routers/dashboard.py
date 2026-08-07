from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import Job, JobApplication, User, UserRole
from app.schemas import ApplicationResponse, JobResponse

router = APIRouter(prefix="/api/v1/dashboard", tags=["Dashboard & My Activity"])


# ১. নিয়োগকর্তা: আমার পোস্ট করা সব কাজের তালিকা
@router.get("/my-jobs", response_model=List[JobResponse])
def get_my_posted_jobs(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != UserRole.EMPLOYER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="শুধুমাত্র নিয়োগকর্তারা এই পেজটি দেখতে পারবেন",
        )
    return db.query(Job).filter(Job.employer_id == current_user.id).all()


# ২. কর্মী: আমার করা সব আবেদনের তালিকা
@router.get("/my-applications", response_model=List[ApplicationResponse])
def get_my_applications(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != UserRole.WORKER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="শুধুমাত্র কর্মীরা এই পেজটি দেখতে পারবেন",
        )
    return (
        db.query(JobApplication)
        .filter(JobApplication.worker_id == current_user.id)
        .all()
    )