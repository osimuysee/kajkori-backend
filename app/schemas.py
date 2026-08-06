from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel


# User & Auth Schemas
class OTPRequest(BaseModel):
    phone: str
    role: Optional[str] = "worker"


class OTPVerify(BaseModel):
    phone: str
    otp_code: str


class UserResponse(BaseModel):
    id: int
    phone: str
    role: str
    is_verified: bool

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str
    user: UserResponse


# Application Schemas
class ApplicationCreate(BaseModel):
    proposed_budget: Optional[Decimal] = None


class ApplicationResponse(BaseModel):
    id: int
    job_id: int
    worker_id: int
    proposed_budget: Optional[Decimal]
    status: str

    class Config:
        from_attributes = True


# Job Schemas
class JobCreate(BaseModel):
    title: str
    budget: Decimal
    location_upazila: str


class JobResponse(BaseModel):
    id: int
    employer_id: int
    worker_id: Optional[int] = None
    title: str
    budget: Decimal
    status: str
    location_upazila: str
class TransactionResponse(BaseModel):
    id: int
    job_id: int
    receiver_id: int
    amount: Decimal
    payment_method: str
    status: str

    class Config:
        from_attributes = True
