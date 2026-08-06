from datetime import datetime
from enum import Enum
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    Integer,
    Numeric,
    String,
)
from sqlalchemy.orm import relationship
from app.database import Base


# Enum Definitions
class UserRole(str, Enum):
    EMPLOYER = "employer"
    WORKER = "worker"


class DeviceType(str, Enum):
    SMARTPHONE = "smartphone"
    BUTTON_PHONE = "button_phone"


class JobStatus(str, Enum):
    PENDING = "pending"
    ASSIGNED = "assigned"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class ApplicationStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class TransactionStatus(str, Enum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"


# Database Models
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    phone = Column(String, unique=True, index=True, nullable=False)
    full_name = Column(String, nullable=True)
    role = Column(SQLEnum(UserRole), default=UserRole.WORKER, nullable=False)
    device_type = Column(SQLEnum(DeviceType), default=DeviceType.BUTTON_PHONE)
    location_district = Column(String, index=True, nullable=True)
    location_upazila = Column(String, index=True, nullable=True)
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    otp_code = Column(String, nullable=True)


class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, index=True)
    employer_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    worker_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    title = Column(String, nullable=False)
    budget = Column(Numeric(10, 2), nullable=False)
    status = Column(SQLEnum(JobStatus), default=JobStatus.PENDING)
    location_upazila = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    employer = relationship("User", foreign_keys=[employer_id])
    worker = relationship("User", foreign_keys=[worker_id])
    applications = relationship("JobApplication", back_populates="job")


class JobApplication(Base):
    __tablename__ = "job_applications"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=False)
    worker_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    proposed_budget = Column(Numeric(10, 2), nullable=True)
    status = Column(
        SQLEnum(ApplicationStatus), default=ApplicationStatus.PENDING
    )
    created_at = Column(DateTime, default=datetime.utcnow)

    job = relationship("Job", back_populates="applications")
    worker = relationship("User", foreign_keys=[worker_id])


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=False)
    receiver_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    amount = Column(Numeric(10, 2), nullable=False)
    payment_method = Column(String, default="bkash")  # bkash / nagad
    status = Column(
        SQLEnum(TransactionStatus), default=TransactionStatus.SUCCESS
    )
    created_at = Column(DateTime, default=datetime.utcnow)

    job = relationship("Job")
    receiver = relationship("User", foreign_keys=[receiver_id])