from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import (
    ApplicationStatus,
    Job,
    JobApplication,
    JobStatus,
    User,
    UserRole,
)
from app.schemas import (
    ApplicationCreate,
    ApplicationResponse,
    JobCreate,
    JobResponse,
)

router = APIRouter(prefix="/api/v1/jobs", tags=["Jobs & Applications"])


# ১. নতুন পোস্ট তৈরি করা (Employer)
@router.post("/", response_model=JobResponse)
def create_job(
    job_data: JobCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != UserRole.EMPLOYER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="শুধুমাত্র নিয়োগকর্তা (Employer) কাজ পোস্ট করতে পারবেন",
        )

    new_job = Job(
        employer_id=current_user.id,
        title=job_data.title,
        description=job_data.description,
        category=job_data.category,
        budget=job_data.budget,
        location_district=job_data.location_district,
        location_upazila=job_data.location_upazila,
        status=JobStatus.OPEN,
    )
    db.add(new_job)
    db.commit()
    db.refresh(new_job)
    return new_job


# ২. অ্যাডভান্সড সার্চ ও ফিল্টারিং সহ সব কাজের তালিকা (Worker & Public)
@router.get("/", response_model=List[JobResponse])
def get_jobs(
    search: Optional[str] = None,
    category: Optional[str] = None,
    district: Optional[str] = None,
    upazila: Optional[str] = None,
    min_budget: Optional[float] = None,
    max_budget: Optional[float] = None,
    status_filter: Optional[JobStatus] = JobStatus.OPEN,
    db: Session = Depends(get_db),
):
    query = db.query(Job)

    if status_filter:
        query = query.filter(Job.status == status_filter)

    if category:
        query = query.filter(Job.category.ilike(f"%{category}%"))

    if district:
        query = query.filter(Job.location_district.ilike(f"%{district}%"))

    if upazila:
        query = query.filter(Job.location_upazila.ilike(f"%{upazila}%"))

    if min_budget is not None:
        query = query.filter(Job.budget >= min_budget)

    if max_budget is not None:
        query = query.filter(Job.budget <= max_budget)

    if search:
        search_pattern = f"%{search}%"
        query = query.filter(
            or_(
                Job.title.ilike(search_pattern),
                Job.description.ilike(search_pattern),
            )
        )

    return query.all()


# ৩. নির্দিষ্ট কাজের বিস্তারিত দেখা
@router.get("/{job_id}", response_model=JobResponse)
def get_job_detail(job_id: int, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="কাজটি পাওয়া যায়নি"
        )
    return job


# ৪. কাজের আবেদন করা (Worker)
@router.post("/{job_id}/apply", response_model=ApplicationResponse)
def apply_to_job(
    job_id: int,
    app_data: ApplicationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != UserRole.WORKER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="শুধুমাত্র কর্মীরা (Worker) আবেদন করতে পারবেন",
        )

    job = db.query(Job).filter(Job.id == job_id).first()
    if not job or job.status != JobStatus.OPEN:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="কাজটি আবেদনের জন্য উন্মুক্ত নয়",
        )

    existing_app = (
        db.query(JobApplication)
        .filter(
            JobApplication.job_id == job_id,
            JobApplication.worker_id == current_user.id,
        )
        .first()
    )
    if existing_app:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="আপনি ইতিমধ্যে এই কাজে আবেদন করেছেন",
        )

    proposed_rate = app_data.proposed_rate or app_data.proposed_budget or job.budget

    new_application = JobApplication(
        job_id=job_id,
        worker_id=current_user.id,
        proposed_rate=proposed_rate,
        cover_note=app_data.cover_note,
        status=ApplicationStatus.PENDING,
    )
    db.add(new_application)
    db.commit()
    db.refresh(new_application)
    return new_application


# ৫. নিয়োগকর্তার আবেদনের তালিকা দেখা
@router.get("/{job_id}/applications", response_model=List[ApplicationResponse])
def get_job_applications(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="কাজটি পাওয়া যায়নি"
        )

    if job.employer_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="শুধুমাত্র পোস্টদাতা এই আবেদনগুলো দেখতে পারবেন",
        )

    return (
        db.query(JobApplication)
        .filter(JobApplication.job_id == job_id)
        .all()
    )


# ৬. কর্মীকে কাজ বরাদ্দ করা (Employer)
@router.post("/{job_id}/assign/{worker_id}")
def assign_worker(
    job_id: int,
    worker_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job or job.employer_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="কাজ বরাদ্দ করার অনুমতি নেই",
        )

    job.worker_id = worker_id
    job.status = JobStatus.ASSIGNED

    app = (
        db.query(JobApplication)
        .filter(
            JobApplication.job_id == job_id,
            JobApplication.worker_id == worker_id,
        )
        .first()
    )
    if app:
        app.status = ApplicationStatus.ACCEPTED

    db.commit()
    return {"status": "success", "message": "কর্মীকে সফলভাবে কাজটি বরাদ্দ করা হয়েছে"}


# ৭. কাজ সম্পন্ন ঘোষণা করা (Employer)
@router.post("/{job_id}/complete")
def complete_job(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job or job.employer_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="কাজ সম্পূর্ণ ঘোষণা করার অনুমতি নেই",
        )

    job.status = JobStatus.COMPLETED
    db.commit()
    return {"status": "success", "message": "কাজটি সম্পন্ন হিসেবে চিহ্নিত করা হয়েছে"}