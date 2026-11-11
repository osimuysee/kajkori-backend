from decimal import Decimal
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import (
    Job,
    JobStatus,
    Transaction,
    TransactionStatus,
    TransactionType,
    User,
)
from app.models_marketplace import AuditLog

router = APIRouter(prefix="/api/v1/wallet", tags=["Wallet & Escrow Payment"])


# Helpers
def format_bdt(amount: Decimal) -> str:
    return f"{amount:,.2f} BDT"


# Pydantic Request Schemas
class DepositRequest(BaseModel):
    amount: float
    payment_method: str = "bkash"
    idempotency_key: Optional[str] = None


class WithdrawRequest(BaseModel):
    amount: float
    payment_method: str = "bkash"
    account_number: str
    idempotency_key: Optional[str] = None


# ১. ওয়ালেট ব্যালেন্স চেক করা
@router.get("/balance")
def get_wallet_balance(current_user: User = Depends(get_current_user)):
    # wallet_balance and reserved_balance are Decimal/Numeric in the model
    balance = current_user.wallet_balance or Decimal("0.00")
    # "or 0": reserved_balance is NULL for rows created before the column
    # existed, and Decimal - None raised TypeError (HTTP 500).
    reserved = getattr(current_user, "reserved_balance", None) or Decimal("0.00")
    available = balance - reserved
    return {
        "user_id": current_user.id,
        "phone": current_user.phone,
        "wallet_balance": float(balance),
        "reserved_balance": float(reserved),
        "available_balance": float(available),
        "amount_formatted": format_bdt(balance),
        "available_formatted": format_bdt(available),
        "currency": "BDT",
    }


# ২. ওয়ালেটে টাকা ডিপোজিট / টপ-আপ করা (starts a PENDING transaction — wait for gateway callback)
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

    # create a pending Transaction; actual credit will happen on gateway callback
    idempotency_key = request.idempotency_key or str(uuid4())

    # Check for existing transaction with same idempotency
    existing = (
        db.query(Transaction)
        .filter(Transaction.idempotency_key == idempotency_key, Transaction.receiver_id == current_user.id)
        .first()
    )
    if existing:
        return {
            "status": "exists",
            "transaction_id": existing.id,
            "message": "A transaction with this idempotency key already exists",
        }

    trx = Transaction(
        receiver_id=current_user.id,
        amount=Decimal(str(request.amount)),
        type=TransactionType.DEPOSIT,
        payment_provider=request.payment_method,
        idempotency_key=idempotency_key,
        status=TransactionStatus.PENDING,
    )

    db.add(trx)
    db.commit()
    db.refresh(trx)

    # In real integration: return gateway redirect/checkout info. For now return transaction record.
    return {
        "status": "pending",
        "transaction_id": trx.id,
        "amount": float(trx.amount),
        "amount_formatted": format_bdt(trx.amount),
        "currency": "BDT",
        "message": "Transaction created in PENDING state. Await gateway callback to confirm and credit wallet.",
    }


# ---- Row locks for money movement ---------------------------------------------
# SELECT ... FOR UPDATE: on PostgreSQL a second request for the same rows waits
# until the first one has committed or rolled back. SQLite ignores it (local
# development only, single writer).
def _locked_job_query(db: Session, job_id: int):
    return db.query(Job).filter(Job.id == job_id).with_for_update()


def _locked_wallets_query(db: Session, user_ids):
    # Always lock in id order: two releases between the same two users in
    # opposite directions then wait for each other instead of deadlocking.
    # populate_existing(): the logged-in user is already loaded in this session,
    # and without it SQLAlchemy would keep the balance it read BEFORE the lock.
    return (
        db.query(User)
        .filter(User.id.in_(set(user_ids)))
        .order_by(User.id)
        .with_for_update()
        .populate_existing()
    )


# ৩. কাজ শেষে এসক্রো থেকে কর্মীকে পেমেন্ট রিলিজ করা
@router.post("/release-escrow/{job_id}")
def release_escrow_payment(
    job_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Lock the job first. Everything below (including the "already paid" check)
    # runs while this job is locked, so two releases of one job cannot both pay.
    job = _locked_job_query(db, job_id).first()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="কাজটি পাওয়া যায়নি"
        )

    if job.employer_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="শুধুমাত্র নিয়োগকর্তা পেমেন্ট রিলিজ করতে পারবেন",
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

    if job.worker_id == job.employer_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="নিজের কাজের পেমেন্ট নিজেকে রিলিজ করা যাবে না",
        )

    # A job is paid exactly once. (Before this check every extra call paid the
    # worker again for as long as the employer had balance.)
    already_paid = (
        db.query(Transaction.id)
        .filter(
            Transaction.job_id == job.id,
            Transaction.type == TransactionType.ESCROW,
            Transaction.status == TransactionStatus.SUCCESS,
        )
        .first()
    )
    if already_paid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="এই কাজের পেমেন্ট ইতিমধ্যে রিলিজ করা হয়েছে",
        )

    # New jobs cannot be saved with such a budget, but an old row could have one,
    # and a negative amount would move money from the worker to the employer.
    budget = job.budget
    if budget is None or budget <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="এই কাজের বাজেট সঠিক নয়, তাই পেমেন্ট রিলিজ করা যাবে না",
        )

    try:
        wallets = {u.id: u for u in _locked_wallets_query(db, [job.employer_id, job.worker_id]).all()}
        employer = wallets.get(job.employer_id)
        worker = wallets.get(job.worker_id)
        if not employer or not worker:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="কর্মী পাওয়া যায়নি"
            )

        # Balance is read AFTER the lock, so a withdrawal or another release
        # that finished a moment ago is already counted.
        available = (employer.wallet_balance or Decimal("0.00")) - (employer.reserved_balance or Decimal("0.00"))
        if available < budget:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"পর্যাপ্ত ব্যালেন্স নেই। আপনার ওয়ালেটে অন্তত {format_bdt(budget)} থাকতে হবে।"
                ),
            )

        # Move funds: decrease employer's wallet_balance, increase worker's wallet_balance
        employer.wallet_balance = (employer.wallet_balance or Decimal("0.00")) - budget
        worker.wallet_balance = (worker.wallet_balance or Decimal("0.00")) + budget

        trx = Transaction(
            job_id=job.id,
            receiver_id=worker.id,
            amount=budget,
            type=TransactionType.ESCROW,
            payment_provider="wallet_escrow",
            status=TransactionStatus.SUCCESS,
            is_released=True,
        )
        db.add(trx)
        db.flush()  # gives trx.id for the audit row, still inside the same transaction

        # Every money movement leaves an audit row. IDs and the amount only:
        # no phone numbers or names in `details`.
        db.add(AuditLog(
            actor_user_id=employer.id,
            actor_role=getattr(employer.role, "value", None),
            action="escrow.released",
            target_type="job",
            target_id=str(job.id),
            ip_address=request.client.host if request.client else None,
            user_agent=(request.headers.get("user-agent") or "")[:255] or None,
            details={
                "amount": f"{budget:.2f}",
                "worker_user_id": worker.id,
                "transaction_id": trx.id,
            },
        ))

        # Wallets, transaction and audit row are saved together or not at all.
        db.commit()
    except Exception:
        db.rollback()
        raise

    return {
        "status": "success",
        "message": f"কর্মীর ওয়ালেটে {format_bdt(budget)} সফলভাবে পাঠানো হয়েছে",
        "transaction_id": trx.id,
        "employer_remaining_balance": float(employer.wallet_balance),
        "employer_remaining_balance_formatted": format_bdt(employer.wallet_balance),
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

    amount = Decimal(str(request.amount))

    # Reload user row and check available balance (wallet_balance - reserved_balance)
    user_row = db.query(User).filter(User.id == current_user.id).first()
    reserved = getattr(user_row, "reserved_balance", Decimal("0.00")) or Decimal("0.00")
    available = (user_row.wallet_balance or Decimal("0.00")) - reserved

    if available < amount:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="পর্যাপ্ত ওয়ালেট ব্যালেন্স নেই",
        )

    # Reserve the amount (move to reserved_balance)
    user_row.reserved_balance = (reserved + amount)

    trx = Transaction(
        receiver_id=user_row.id,
        amount=amount,
        type=TransactionType.WITHDRAW,
        payment_provider=request.payment_method,
        account_number=request.account_number,
        status=TransactionStatus.PENDING,
        idempotency_key=request.idempotency_key or str(uuid4()),
    )

    db.add(trx)
    db.commit()
    db.refresh(trx)

    # In a real integration we'd call payout API here and wait for callback to finalize.
    return {
        "status": "pending",
        "transaction_id": trx.id,
        "amount": float(trx.amount),
        "amount_formatted": format_bdt(trx.amount),
        "currency": "BDT",
        "message": "Withdrawal reserved and pending. Await payout confirmation callback to complete.",
    }
