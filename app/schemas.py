from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field
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
    user: "UserResponse"

    class Config:
        from_attributes = True


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


class PublicUserResponse(BaseModel):
    """What anyone may see about a user.

    No phone, no wallet, and no location below upazila: those stay private
    until a booking is accepted (see CLAUDE.md, security rules).
    """

    id: int
    full_name: Optional[str] = None
    role: UserRole
    is_verified: bool
    location_division: Optional[str] = None
    location_district: Optional[str] = None
    location_upazila: Optional[str] = None

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
    comment: Optional[str] = Field(default=None, max_length=2000)


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
    title: str = Field(min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=5000)
    # Decimal, and strictly positive: a zero or negative budget would let the
    # escrow release move money in the wrong direction.
    budget: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
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
    proposed_rate: Optional[Decimal] = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    proposed_budget: Optional[Decimal] = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    cover_note: Optional[str] = Field(default=None, max_length=2000)


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
