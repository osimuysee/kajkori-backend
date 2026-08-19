from decimal import Decimal
import os
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Transaction, TransactionStatus, TransactionType, User

router = APIRouter(prefix="/api/v1/payments", tags=["Payments"])


@router.post("/webhook")
def payment_webhook(payload: dict, request: Request, db: Session = Depends(get_db)):
    """Generic payment gateway webhook finalizer.

    Expected payload keys (any of):
      - idempotency_key
      - external_trx_id
      - transaction_id
      - status: 'success' or 'failed'

    The gateway should include a header 'X-WEBHOOK-SECRET' whose value matches
    PAYMENT_WEBHOOK_SECRET env var. If PAYMENT_WEBHOOK_SECRET is not set, the
    webhook will accept requests (useful for local/dev only).
    """
    # Basic signature/secret check
    secret = os.getenv("PAYMENT_WEBHOOK_SECRET", "")
    header_secret = request.headers.get("X-WEBHOOK-SECRET") or request.headers.get("X-SIGNATURE")
    if secret:
        if not header_secret or header_secret != secret:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid webhook signature")

    idempotency_key = payload.get("idempotency_key")
    external_trx_id = payload.get("external_trx_id")
    trx_id = payload.get("transaction_id")
    status_str = (payload.get("status") or "").lower()

    if status_str not in ("success", "failed", "pending"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid status")

    trx = None
    if idempotency_key:
        trx = db.query(Transaction).filter(Transaction.idempotency_key == idempotency_key).first()
    if not trx and external_trx_id:
        trx = db.query(Transaction).filter(Transaction.external_trx_id == external_trx_id).first()
    if not trx and trx_id:
        trx = db.query(Transaction).filter(Transaction.id == trx_id).first()

    if not trx:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")

    # Idempotency: if already processed
    if trx.status == TransactionStatus.SUCCESS:
        return {"status": "already_processed", "transaction_id": trx.id}

    # Finalize based on incoming status
    if status_str == "pending":
        return {"status": "pending", "transaction_id": trx.id}

    if status_str == "failed":
        trx.status = TransactionStatus.FAILED
        if external_trx_id:
            trx.external_trx_id = external_trx_id
        db.commit()
        return {"status": "failed", "transaction_id": trx.id}

    # status_str == 'success'
    # Apply money movements inside a DB transaction
    try:
        # Reload relevant user row and apply a FOR UPDATE lock where supported
        user = db.query(User).filter(User.id == trx.receiver_id).with_for_update().first()
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        # Deposit -> credit user's wallet
        if trx.type == TransactionType.DEPOSIT:
            user.wallet_balance = (user.wallet_balance or Decimal("0.00")) + (trx.amount or Decimal("0.00"))
        elif trx.type == TransactionType.WITHDRAW:
            # For withdraw, we expect amount was reserved previously (reserved_balance).
            # On success, subtract from reserved_balance and wallet_balance.
            user.reserved_balance = (user.reserved_balance or Decimal("0.00")) - (trx.amount or Decimal("0.00"))
            user.wallet_balance = (user.wallet_balance or Decimal("0.00")) - (trx.amount or Decimal("0.00"))
        elif trx.type == TransactionType.ESCROW:
            # Escrow success typically means credit to receiver
            user.wallet_balance = (user.wallet_balance or Decimal("0.00")) + (trx.amount or Decimal("0.00"))

        trx.status = TransactionStatus.SUCCESS
        if external_trx_id:
            trx.external_trx_id = external_trx_id

        db.commit()
    except Exception:
        db.rollback()
        raise

    return {"status": "ok", "transaction_id": trx.id}
