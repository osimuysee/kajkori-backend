from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import (
    Job,
    JobStatus,
    Transaction,
    TransactionStatus,
    User,
)

router = APIRouter(prefix="/api/v1/wallet", tags=["Wallet & Escrow Payment"])


# Pydantic Request Schemas
class DepositRequest(BaseModel):
    amount: float
    payment_method: str = "bkash"


class WithdrawRequest(BaseModel):
    amount: float
    payment_method: str = "bkash"
    account_number: str


# ১. ওয়ালেট ব্যালেন্স চেক করা
@router.get("/balance")
def get_wallet_balance(current_user: User = Depends(get_current_user)):
    return {
        "user_id": current_user.id,
        "phone": current_user.phone,
        "wallet_balance": current_user.wallet_balance or 0.0,
        "currency": "BDT",
    }


# ২. ওয়ালেটে টাকা ডিপোজিট / টপ-আপ করা
@router.post("/deposit")
def deposit_funds(
    request: DepositRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if request.amount <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="টাকার পরিমাণ ০ এর বেশি হতে হবে",
        )

    current_user.wallet_balance = (
        current_user.wallet_balance or 0.0
    ) + request.amount

    transaction = Transaction(
        receiver_id=current_user.id,
        amount=request.amount,
        payment_method=request.payment_method,
        status=TransactionStatus.SUCCESS,
    )

    db.add(transaction)
    db.commit()
    db.refresh(current_user)

    return {
        "status": "success",
        "message": f"{request.amount} BDT সফলভাবে ওয়ালেটে যুক্ত হয়েছে",
        "new_balance": current_user.wallet_balance,
    }


# ৩. কাজ শেষে এসক্রো থেকে কর্মীকে পেমেন্ট রিলিজ করা
@router.post("/release-escrow/{job_id}")
def release_escrow_payment(
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
            detail="শুধুমাত্র নিয়োগকর্তা পেমেন্ট রিলিজ করতে পারবেন",
        )

    if job.status != JobStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="পেমেন্ট রিলিজ করার আগে কাজ সম্পন্ন (COMPLETED) হতে হবে",
        )

    if not job.worker_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="এই কাজে কোনো কর্মী এসাইন করা নেই",
        )

    if (current_user.wallet_balance or 0.0) < job.budget:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"পর্যাপ্ত ব্যালেন্স নেই। আপনার ওয়ালেটে অন্তত {job.budget} BDT"
                " থাকতে হবে।"
            ),
        )

    worker = db.query(User).filter(User.id == job.worker_id).first()
    if not worker:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="কর্মী পাওয়া যায়নি"
        )

    # Employer থেকে Worker-এর ওয়ালেটে টাকা পাঠানো
    current_user.wallet_balance -= job.budget
    worker.wallet_balance = (worker.wallet_balance or 0.0) + job.budget

    transaction = Transaction(
        job_id=job.id,
        receiver_id=worker.id,
        amount=job.budget,
        payment_method="wallet_escrow",
        status=TransactionStatus.SUCCESS,
    )

    db.add(transaction)
    db.commit()

    return {
        "status": "success",
        "message": (
            f"কর্মী ({worker.phone})-এর ওয়ালেটে {job.budget} BDT সফলভাবে"
            " পাঠানো হয়েছে"
        ),
        "employer_remaining_balance": current_user.wallet_balance,
    }


# ৪. ওয়ালেট থেকে টাকা উইথড্র / ক্যাশ-আউট করা (bKash/Nagad)
@router.post("/withdraw")
def withdraw_funds(
    request: WithdrawRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if request.amount <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="টাকার পরিমাণ ০ এর বেশি হতে হবে",
        )

    if (current_user.wallet_balance or 0.0) < request.amount:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="পর্যাপ্ত ওয়ালেট ব্যালেন্স নেই",
        )

    current_user.wallet_balance -= request.amount

    transaction = Transaction(
        receiver_id=current_user.id,
        amount=request.amount,
        payment_method=(
            f"withdraw_{request.payment_method}_{request.account_number}"
        ),
        status=TransactionStatus.SUCCESS,
    )

    db.add(transaction)
    db.commit()
    db.refresh(current_user)

    return {
        "status": "success",
        "message": (
            f"{request.amount} BDT {request.payment_method} নম্বর"
            f" ({request.account_number})-এ ক্যাশ-আউট প্রসেস করা হয়েছে"
        ),
        "remaining_balance": current_user.wallet_balance,
    }