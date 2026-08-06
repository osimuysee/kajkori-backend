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
)
from app.schemas import (
    ApplicationCreate,
    ApplicationResponse,
    JobCreate,
    JobResponse,
    TransactionResponse,
)

router = APIRouter(prefix="/api/v1/jobs", tags=["Jobs Management"])


# ১. নতুন কাজের পোস্ট তৈরি করা
@router.post(
    "/", response_model=JobResponse, status_code=status.HTTP_201_CREATED
)
def create_job(
    job_data: JobCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    new_job = Job(
        employer_id=current_user.id,
        title=job_data.title,
        budget=job_data.budget,
        location_upazila=job_data.location_upazila,
        status=JobStatus.PENDING,
    )
    db.add(new_job)
    db.commit()
    db.refresh(new_job)
    return new_job


# ২. উন্মুক্ত কাজের তালিকা দেখা
@router.get("/", response_model=List[JobResponse])
def get_all_jobs(db: Session = Depends(get_db)):
    return db.query(Job).filter(Job.status == JobStatus.PENDING).all()


# ৩. কাজের জন্য কর্মী কর্তৃক আবেদন করা
@router.post(
    "/{job_id}/apply",
    response_model=ApplicationResponse,
    status_code=status.HTTP_201_CREATED,
)
def apply_for_job(
    job_id: int,
    app_data: ApplicationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Job not found"
        )

    if job.employer_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot apply to your own job",
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
            detail="Already applied to this job",
        )

    application = JobApplication(
        job_id=job_id,
        worker_id=current_user.id,
        proposed_budget=app_data.proposed_budget or job.budget,
        status=ApplicationStatus.PENDING,
    )
    db.add(application)
    db.commit()
    db.refresh(application)
    return application


# ৪. নিয়োগকর্তা তার পোস্ট করা নির্দিষ্ট কাজের সব আবেদন দেখা
@router.get(
    "/{job_id}/applications", response_model=List[ApplicationResponse]
)
def get_job_applications(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Job not found"
        )

    if job.employer_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to view applications for this job",
        )

    return (
        db.query(JobApplication)
        .filter(JobApplication.job_id == job_id)
        .all()
    )


# ৫. নিয়োগকর্তা কর্তৃক কর্মী নির্ধারণ (Assign Worker)
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
            status_code=status.HTTP_404_NOT_FOUND, detail="Job not found"
        )

    if job.employer_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to assign worker for this job",
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
            detail="Worker has not applied for this job",
        )

    job.worker_id = worker_id
    job.status = JobStatus.ASSIGNED
    application.status = ApplicationStatus.ACCEPTED

    db.commit()
    db.refresh(job)
    return job


# ৬. কাজ সম্পন্ন ঘোষণা করা (Mark Job Completed)
@router.post("/{job_id}/complete", response_model=JobResponse)
def complete_job(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Job not found"
        )

    if current_user.id not in [job.employer_id, job.worker_id]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to complete this job",
        )

    if job.status != JobStatus.ASSIGNED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Job must be assigned before marking as completed",
        )

    job.status = JobStatus.COMPLETED
    db.commit()
    db.refresh(job)
    return job


# ৭. কর্মীকে পেমেন্ট প্রদান সিমুলেশন (Payout/Disbursement)
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
            status_code=status.HTTP_404_NOT_FOUND, detail="Job not found"
        )

    if job.employer_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the employer can release payment",
        )

    if job.status != JobStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Job must be marked completed before payout",
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