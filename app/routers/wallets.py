from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.auth import get_current_user
from app.database import get_db
from app.models import User, Transaction
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/wallet", tags=["Wallet & Payments"])


class DepositRequest(BaseModel):
    amount: float
    payment_method: str  # e.g. "bkash", "nagad", "sandbox"


# ১. ওয়ালেট ব্যালেন্স চেক করা
@router.get("/balance")
def get_balance(current_user: User = Depends(get_current_user)):
    return {
        "user_id": current_user.id,
        "balance": getattr(current_user, "wallet_balance", 0.0),
    }


# ২. ওয়ালেটে টাকা রিচার্জ/ডিপোজিট করা (Sandbox Mode)
@router.post("/deposit")
def deposit_money(
    request: DepositRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if request.amount <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="টাকার পরিমাণ অবশ্যই ০-এর বেশি হতে হবে",
        )

    # ইউজার অবজেক্টে ব্যালেন্স আপডেট
    current_user.wallet_balance = (
        getattr(current_user, "wallet_balance", 0.0) + request.amount
    )

    # লেনদেনের হিস্ট্রি রেকর্ড তৈরি
    new_transaction = Transaction(
        receiver_id=current_user.id,
        amount=request.amount,
        type="deposit",
        status="completed",
    )

    db.add(new_transaction)
    db.commit()
    db.refresh(current_user)

    return {
        "message": f"সফলভাবে ৳{request.amount} আপনার ওয়ালেটে জমা হয়েছে",
        "new_balance": current_user.wallet_balance,
    }