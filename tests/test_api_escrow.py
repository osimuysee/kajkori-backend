"""Escrow release (AUDIT #8, money half). Fake data only.

Scope: SQLite. The row locks (SELECT ... FOR UPDATE) only take effect on
PostgreSQL, so two truly simultaneous releases are NOT exercised here; the
last test only checks that the lock is part of the PostgreSQL statement.
"""
from decimal import Decimal

from sqlalchemy.dialects import postgresql

from app.models import Job, JobStatus, Transaction, TransactionStatus, TransactionType, User
from app.models_marketplace import AuditLog

JOBS = "/api/v1/jobs/"
EMPLOYER_PHONE = "01711111111"
WORKER_PHONE = "01722222222"


def _release(api, who, job_id):
    return api.client.post(f"/api/v1/wallet/release-escrow/{job_id}", headers=who.headers)


def _set_wallet(api, user_id, balance, reserved="0.00"):
    with api.Session() as db:
        row = db.get(User, user_id)
        row.wallet_balance = Decimal(balance)
        row.reserved_balance = Decimal(reserved)
        db.commit()


def _balances(api, *user_ids):
    with api.Session() as db:
        return [db.get(User, uid).wallet_balance or Decimal("0.00") for uid in user_ids]


def _completed_job(api, budget=500, employer_balance="1200.00"):
    employer = api.login(EMPLOYER_PHONE, "employer")
    worker = api.login(WORKER_PHONE, "worker")
    job_id = api.client.post(JOBS, json={"title": "Fix a tap", "budget": budget}, headers=employer.headers).json()["id"]
    assert api.client.post(f"{JOBS}{job_id}/apply", json={}, headers=worker.headers).status_code == 200
    assert api.client.post(f"{JOBS}{job_id}/assign/{worker.id}", headers=employer.headers).status_code == 200
    assert api.client.post(f"{JOBS}{job_id}/complete", headers=employer.headers).status_code == 200
    _set_wallet(api, employer.id, employer_balance)
    return employer, worker, job_id


def test_release_moves_the_budget_from_employer_to_worker(api):
    employer, worker, job_id = _completed_job(api)

    r = _release(api, employer, job_id)

    assert r.status_code == 200
    assert _balances(api, employer.id, worker.id) == [Decimal("700.00"), Decimal("500.00")]
    with api.Session() as db:
        trx = db.query(Transaction).one()
        assert (trx.job_id, trx.receiver_id, trx.amount) == (job_id, worker.id, Decimal("500.00"))
        assert trx.type == TransactionType.ESCROW
        assert trx.status == TransactionStatus.SUCCESS
        assert trx.is_released is True


def test_a_job_is_paid_only_once(api):
    """Old code: every extra call paid the worker again while the balance lasted."""
    employer, worker, job_id = _completed_job(api)

    assert _release(api, employer, job_id).status_code == 200
    second = _release(api, employer, job_id)
    third = _release(api, employer, job_id)

    assert second.status_code == 400 and third.status_code == 400
    assert _balances(api, employer.id, worker.id) == [Decimal("700.00"), Decimal("500.00")]
    with api.Session() as db:
        assert db.query(Transaction).count() == 1


def test_release_writes_one_audit_row_without_personal_data(api):
    employer, worker, job_id = _completed_job(api)
    _release(api, employer, job_id)
    _release(api, employer, job_id)  # refused: must not add a second row

    with api.Session() as db:
        entry = db.query(AuditLog).one()
        trx = db.query(Transaction).one()
        assert entry.action == "escrow.released"
        assert entry.actor_user_id == employer.id
        assert (entry.target_type, entry.target_id) == ("job", str(job_id))
        assert entry.details == {
            "amount": "500.00",
            "worker_user_id": worker.id,
            "transaction_id": trx.id,
        }
        assert entry.created_at.tzinfo is not None
    assert EMPLOYER_PHONE not in str(entry.details) and WORKER_PHONE not in str(entry.details)


def test_release_response_does_not_contain_the_worker_phone(api):
    employer, _worker, job_id = _completed_job(api)
    r = _release(api, employer, job_id)
    assert r.status_code == 200
    assert WORKER_PHONE not in r.text


def test_not_enough_money_moves_nothing(api):
    employer, worker, job_id = _completed_job(api, employer_balance="499.99")

    assert _release(api, employer, job_id).status_code == 400
    assert _balances(api, employer.id, worker.id) == [Decimal("499.99"), Decimal("0.00")]
    with api.Session() as db:
        assert db.query(Transaction).count() == 0
        assert db.query(AuditLog).count() == 0


def test_money_reserved_for_a_withdrawal_cannot_be_released(api):
    employer, worker, job_id = _completed_job(api, employer_balance="600.00")
    _set_wallet(api, employer.id, "600.00", reserved="200.00")  # only 400 is free

    assert _release(api, employer, job_id).status_code == 400
    assert _balances(api, employer.id, worker.id) == [Decimal("600.00"), Decimal("0.00")]


def test_only_the_employer_can_release(api):
    employer, worker, job_id = _completed_job(api)
    outsider = api.login("01733333333", "employer")

    assert _release(api, worker, job_id).status_code == 403
    assert _release(api, outsider, job_id).status_code == 403
    assert _balances(api, employer.id, worker.id) == [Decimal("1200.00"), Decimal("0.00")]


def test_job_must_be_completed_first(api):
    employer = api.login(EMPLOYER_PHONE, "employer")
    worker = api.login(WORKER_PHONE, "worker")
    job_id = api.client.post(JOBS, json={"title": "x", "budget": 500}, headers=employer.headers).json()["id"]
    api.client.post(f"{JOBS}{job_id}/apply", json={}, headers=worker.headers)
    api.client.post(f"{JOBS}{job_id}/assign/{worker.id}", headers=employer.headers)
    _set_wallet(api, employer.id, "1200.00")

    assert _release(api, employer, job_id).status_code == 400  # assigned, not completed
    assert _balances(api, employer.id, worker.id) == [Decimal("1200.00"), Decimal("0.00")]


def test_old_job_with_a_negative_budget_cannot_pull_money_from_the_worker(api):
    """New jobs cannot have such a budget any more, but a row saved before the
    fix could. Releasing it used to move money from the worker to the employer."""
    employer = api.login(EMPLOYER_PHONE, "employer")
    worker = api.login(WORKER_PHONE, "worker")
    _set_wallet(api, worker.id, "5000.00")
    with api.Session() as db:
        job = Job(employer_id=employer.id, worker_id=worker.id, title="legacy",
                  budget=Decimal("-1000.00"), status=JobStatus.COMPLETED)
        db.add(job)
        db.commit()
        job_id = job.id

    assert _release(api, employer, job_id).status_code == 400
    assert _balances(api, employer.id, worker.id) == [Decimal("0.00"), Decimal("5000.00")]


def test_old_job_where_employer_and_worker_are_the_same_user_is_refused(api):
    employer = api.login(EMPLOYER_PHONE, "employer")
    _set_wallet(api, employer.id, "1200.00")
    with api.Session() as db:
        job = Job(employer_id=employer.id, worker_id=employer.id, title="legacy",
                  budget=Decimal("500.00"), status=JobStatus.COMPLETED)
        db.add(job)
        db.commit()
        job_id = job.id

    assert _release(api, employer, job_id).status_code == 400
    assert _balances(api, employer.id) == [Decimal("1200.00")]
    with api.Session() as db:
        assert db.query(Transaction).count() == 0


def test_release_takes_row_locks_on_postgresql(api):
    from app.routers import wallet

    with api.Session() as db:
        statements = [
            str(q.statement.compile(dialect=postgresql.dialect()))
            for q in (wallet._locked_job_query(db, 1), wallet._locked_wallets_query(db, [2, 1]))
        ]
    assert all("FOR UPDATE" in sql for sql in statements)
    # Wallet rows are always locked in id order, so two releases between the
    # same two users in opposite directions cannot deadlock each other.
    assert "ORDER BY users.id" in statements[1]
