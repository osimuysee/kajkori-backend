from typing import List, Optional
from pydantic import BaseModel
from app.models import ApplicationStatus, JobStatus, TransactionStatus, UserRole


class OTPRequest(BaseModel):
    phone: str
    role: Optional[str] = "worker"


class OTPVerify(BaseModel):
    phone: str
    otp_code: str


class Token(BaseModel):
    access_token: str
    token_type: str
    user: dict


class UserResponse(BaseModel):
    id: int
    phone: str
    is_verified: bool
    role: UserRole
    full_name: Optional[str] = None
    location_division: Optional[str] = None
    location_district: Optional[str] = None
    location_upazila: Optional[str] = None
    location_union: Optional[str] = None
    location_village_area: Optional[str] = None
    wallet_balance: Optional[float] = 0.0

    class Config:
        from_attributes = True


class ProfileUpdate(BaseModel):
    full_name: Optional[str] = None
    location_division: Optional[str] = None
    location_district: Optional[str] = None
    location_upazila: Optional[str] = None
    location_union: Optional[str] = None
    location_village_area: Optional[str] = None


class ReviewCreate(BaseModel):
    job_id: int
    target_user_id: int
    rating: int
    comment: Optional[str] = None


class ReviewResponse(BaseModel):
    id: int
    job_id: int
    reviewer_id: int
    target_user_id: int
    rating: int
    comment: Optional[str] = None

    class Config:
        from_attributes = True


class JobCreate(BaseModel):
    title: str
    description: Optional[str] = None
    budget: float
    category: Optional[str] = None
    location_division: Optional[str] = None
    location_district: Optional[str] = None
    location_upazila: Optional[str] = None
    location_union: Optional[str] = None
    location_village_area: Optional[str] = None


class JobResponse(BaseModel):
    id: int
    employer_id: int
    worker_id: Optional[int] = None
    title: str
    description: Optional[str] = None
    budget: float
    category: Optional[str] = None
    location_division: Optional[str] = None
    location_district: Optional[str] = None
    location_upazila: Optional[str] = None
    location_union: Optional[str] = None
    location_village_area: Optional[str] = None
    status: JobStatus

    class Config:
        from_attributes = True


class ApplicationCreate(BaseModel):
    proposed_rate: Optional[float] = None
    proposed_budget: Optional[float] = None
    cover_note: Optional[str] = None


class ApplicationResponse(BaseModel):
    id: int
    job_id: int
    worker_id: int
    proposed_rate: Optional[float] = None
    cover_note: Optional[str] = None
    status: ApplicationStatus

    class Config:
        from_attributes = True


class TransactionResponse(BaseModel):
    id: int
    job_id: Optional[int] = None
    receiver_id: int
    amount: float
    payment_method: str
    status: TransactionStatus

    class Config:
        from_attributes = True