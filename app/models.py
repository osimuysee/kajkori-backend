import enum
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database import Base


class UserRole(str, enum.Enum):
    EMPLOYER = "employer"
    WORKER = "worker"


class JobStatus(str, enum.Enum):
    OPEN = "open"
    PENDING = "pending"
    ASSIGNED = "assigned"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class ApplicationStatus(str, enum.Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class TransactionStatus(str, enum.Enum):
    SUCCESS = "success"
    PENDING = "pending"
    FAILED = "failed"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    phone = Column(String, unique=True, index=True, nullable=False)
    otp_code = Column(String, nullable=True)
    otp_expires_at = Column(DateTime, nullable=True)
    otp_attempts = Column(Integer, default=0)
    is_verified = Column(Boolean, default=False)
    role = Column(Enum(UserRole), default=UserRole.WORKER)
    full_name = Column(String, nullable=True)
    
    # পূর্ণাঙ্গ ৫-স্তরের লোকেশন
    location_division = Column(String, nullable=True)       # বিভাগ
    location_district = Column(String, nullable=True)       # জেলা
    location_upazila = Column(String, nullable=True)        # উপজেলা / থানা
    location_union = Column(String, nullable=True)          # ইউনিয়ন / ওয়ার্ড
    location_village_area = Column(String, nullable=True)   # গ্রাম / মহল্লা / এলাকা

    wallet_balance = Column(Float, default=0.0)


class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, index=True)
    employer_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    worker_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String, nullable=True)
    budget = Column(Float, nullable=False)

    # পূর্ণাঙ্গ ৫-স্তরের লোকেশন
    location_division = Column(String, nullable=True)       # বিভাগ
    location_district = Column(String, nullable=True)       # জেলা
    location_upazila = Column(String, nullable=True)        # উপজেলা / থানা
    location_union = Column(String, nullable=True)          # ইউনিয়ন / ওয়ার্ড
    location_village_area = Column(String, nullable=True)   # গ্রাম / মহল্লা / এলাকা

    status = Column(Enum(JobStatus), default=JobStatus.OPEN)


class JobApplication(Base):
    __tablename__ = "job_applications"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=False)
    worker_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    proposed_rate = Column(Float, nullable=True)
    cover_note = Column(Text, nullable=True)
    status = Column(Enum(ApplicationStatus), default=ApplicationStatus.PENDING)


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=True)
    receiver_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    amount = Column(Float, nullable=False)
    payment_method = Column(String, nullable=False)
    status = Column(Enum(TransactionStatus), default=TransactionStatus.SUCCESS)


class Review(Base):
    __tablename__ = "reviews"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=False)
    reviewer_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    target_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    rating = Column(Integer, nullable=False)
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
