from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import (
    ApplicationStatus,
    Job,
    JobApplication,
    JobStatus,
    Transaction,
    TransactionStatus,
    User,
    UserRole,
)
from app.schemas import (
    ApplicationCreate,
    ApplicationResponse,
    JobCreate,
    JobResponse,
    TransactionResponse,
)

router = APIRouter(prefix="/api/v1/jobs", tags=["Jobs & Applications"])


# ১. সমস্ত উন্মুক্ত কাজের তালিকা দেখা (Public Feed)
@router.get("/", response_model=List[JobResponse])
def get_all_jobs(db: Session = Depends(get_db)):
    return db.query(Job).filter(Job.status == JobStatus.OPEN).all()


# ২. নতুন কাজ পোস্ট করা (শুধুমাত্র Employer করতে পারবে)
@router.post("/", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
def create_job(
    job_data: JobCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != UserRole.EMPLOYER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="শুধুমাত্র Employer রোলধারী ইউজাররা কাজ পোস্ট করতে পারবেন",
        )

    new_job = Job(
        title=job_data.title,
        description=getattr(job_data, "description", None),
        budget=job_data.budget,
        location_district=getattr(job_data, "location_district", None),
        location_upazila=job_data.location_upazila,
        category=getattr(job_data, "category", None),
        employer_id=current_user.id,
        status=JobStatus.OPEN,
    )

    db.add(new_job)
    db.commit()
    db.refresh(new_job)
    return new_job


# ৩. নির্দিষ্ট একটি কাজের ডিটেইলস দেখা
@router.get("/{job_id}", response_model=JobResponse)
def get_job_detail(job_id: int, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="কাজটি পাওয়া যায়নি"
        )
    return job


# ৪. কাজে আবেদন করা (শুধুমাত্র Worker করতে পারবে)
@router.post("/{job_id}/apply", response_model=ApplicationResponse, status_code=status.HTTP_201_CREATED)
def apply_to_job(
    job_id: int,
    app_data: ApplicationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != UserRole.WORKER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="শুধুমাত্র Worker রোলধারী ইউজাররা আবেদন করতে পারবেন",
        )

    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="কাজটি পাওয়া যায়নি"
        )

    if job.employer_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="নিজের পোস্ট করা কাজে আবেদন করা সম্ভব নয়",
        )

    if job.status != JobStatus.OPEN:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="এই কাজটিতে আর আবেদন গ্রহণ করা হচ্ছে না",
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
            detail="আপনি ইতিমধ্যে এই কাজটিতে আবেদন করেছেন",
        )

    rate = getattr(app_data, "proposed_rate", None) or getattr(app_data, "proposed_budget", job.budget)
    note = getattr(app_data, "cover_note", None)

    application = JobApplication(
        job_id=job_id,
        worker_id=current_user.id,
        proposed_rate=rate,
        cover_note=note,
        status=ApplicationStatus.PENDING,
    )

    db.add(application)
    db.commit()
    db.refresh(application)
    return application


# ৫. নিয়োগকর্তা কর্তৃক পোস্ট করা কাজের সব আবেদন দেখা
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
            detail="আবেদন দেখার অনুমতি আপনার নেই",
        )

    return (
        db.query(JobApplication)
        .filter(JobApplication.job_id == job_id)
        .all()
    )


# ৬. কর্মীকে কাজ বরাদ্দ করা (Assign Worker)
@router.post("/{job_id}/assign/{worker_id}", response_model=JobResponse)
def assign_worker(
    job_id: int,
    worker_id: int,
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
            detail="কর্মী নির্ধারণের অনুমতি আপনার নেই",
        )

    application = (
        db.query(JobApplication)
        .filter(
            JobApplication.job_id == job_id,
            JobApplication.worker_id == worker_id,
        )
        .first()
    )
    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="কর্মী এই কাজটিতে আবেদন করেননি",
        )

    job.worker_id = worker_id
    job.status = JobStatus.ASSIGNED
    application.status = ApplicationStatus.ACCEPTED

    db.commit()
    db.refresh(job)
    return job


# ৭. কাজ সম্পন্ন ঘোষণা করা (Mark Job Completed)
@router.post("/{job_id}/complete", response_model=JobResponse)
def complete_job(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="কাজটি পাওয়া যায়নি"
        )

    if current_user.id not in [job.employer_id, job.worker_id]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="কাজটি সম্পন্ন ঘোষণা করার অনুমতি আপনার নেই",
        )

    if job.status != JobStatus.ASSIGNED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="কাজটি আগে Assign করা হতে হবে",
        )

    job.status = JobStatus.COMPLETED
    db.commit()
    db.refresh(job)
    return job


# ৮. পেমেন্ট প্রদান সিমুলেশন (Payout / Disbursement)
@router.post("/{job_id}/payout", response_model=TransactionResponse)
def release_payout(
    job_id: int,
    payment_method: str = "bkash",
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
            detail="শুধুমাত্র Employer পেমেন্ট রিলিজ করতে পারবেন",
        )

    if job.status != JobStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="পেমেন্ট রিলিজ করার আগে কাজ সম্পন্ন ঘোষণা করতে হবে",
        )

    transaction = Transaction(
        job_id=job.id,
        receiver_id=job.worker_id,
        amount=job.budget,
        payment_method=payment_method,
        status=TransactionStatus.SUCCESS,
    )

    db.add(transaction)
    db.commit()
    db.refresh(transaction)
    return transaction