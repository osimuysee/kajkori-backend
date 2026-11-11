"""Public profile, jobs, reviews, CORS and headers. Fake data only."""
from decimal import Decimal

import pytest

from app.models import Job, JobStatus, Review, User

JOBS = "/api/v1/jobs/"


def _post_job(api, employer, budget=500):
    return api.client.post(JOBS, json={"title": "Fix a tap", "budget": budget}, headers=employer.headers)


def _completed_job(api):
    """employer posts, worker applies, employer assigns and completes."""
    employer = api.login("01711111111", "employer")
    worker = api.login("01722222222", "worker")
    job_id = _post_job(api, employer).json()["id"]
    assert api.client.post(f"{JOBS}{job_id}/apply", json={}, headers=worker.headers).status_code == 200
    assert api.client.post(f"{JOBS}{job_id}/assign/{worker.id}", headers=employer.headers).status_code == 200
    assert api.client.post(f"{JOBS}{job_id}/complete", headers=employer.headers).status_code == 200
    return employer, worker, job_id


# ---- AUDIT #2: public profile -------------------------------------------------
def test_public_profile_needs_no_login_and_hides_private_fields(api):
    user = api.login("01711111111", "employer")
    api.client.put(
        "/api/v1/users/me",
        json={
            "full_name": "Rahim",
            "location_district": "Dhaka",
            "location_upazila": "Savar",
            "location_union": "Ward 5",
            "location_village_area": "House 12, Road 3",
        },
        headers=user.headers,
    )

    r = api.client.get(f"/api/v1/users/{user.id}")

    assert r.status_code == 200
    assert set(r.json()) == {
        "id", "full_name", "role", "is_verified",
        "location_division", "location_district", "location_upazila",
    }
    assert "01711111111" not in r.text
    assert "House 12" not in r.text


def test_own_profile_still_shows_own_phone(api):
    user = api.login("01711111111")
    assert api.client.get("/api/v1/users/me", headers=user.headers).json()["phone"] == "01711111111"


# ---- job posting: money must be positive --------------------------------------
@pytest.mark.parametrize("budget", [0, -1, -1000, "NaN", 10.999, 10 ** 12])
def test_job_budget_must_be_a_positive_amount_with_two_decimals(api, budget):
    employer = api.login("01711111111", "employer")
    r = api.client.post(JOBS, content=f'{{"title": "x", "budget": {budget}}}',
                        headers={**employer.headers, "Content-Type": "application/json"})
    assert r.status_code == 422


def test_job_budget_is_stored_exactly(api):
    employer = api.login("01711111111", "employer")
    job_id = _post_job(api, employer, budget=1250.50).json()["id"]
    with api.Session() as db:
        assert db.get(Job, job_id).budget == Decimal("1250.50")


def test_negative_proposed_rate_is_rejected(api):
    employer = api.login("01711111111", "employer")
    worker = api.login("01722222222", "worker")
    job_id = _post_job(api, employer).json()["id"]
    r = api.client.post(f"{JOBS}{job_id}/apply", json={"proposed_rate": -5}, headers=worker.headers)
    assert r.status_code == 422


# ---- AUDIT #8 (job flow part): assign and complete ----------------------------
def test_only_an_applicant_can_be_assigned(api):
    employer = api.login("01711111111", "employer")
    bystander = api.login("01733333333", "worker")
    job_id = _post_job(api, employer).json()["id"]

    r = api.client.post(f"{JOBS}{job_id}/assign/{bystander.id}", headers=employer.headers)

    assert r.status_code == 400
    with api.Session() as db:
        job = db.get(Job, job_id)
        assert job.worker_id is None and job.status == JobStatus.OPEN


def test_a_job_cannot_be_assigned_twice(api):
    employer = api.login("01711111111", "employer")
    first = api.login("01722222222", "worker")
    second = api.login("01733333333", "worker")
    job_id = _post_job(api, employer).json()["id"]
    for w in (first, second):
        api.client.post(f"{JOBS}{job_id}/apply", json={}, headers=w.headers)

    assert api.client.post(f"{JOBS}{job_id}/assign/{first.id}", headers=employer.headers).status_code == 200
    assert api.client.post(f"{JOBS}{job_id}/assign/{second.id}", headers=employer.headers).status_code == 400
    with api.Session() as db:
        assert db.get(Job, job_id).worker_id == first.id


def test_only_an_assigned_job_can_be_completed_and_only_once(api):
    employer = api.login("01711111111", "employer")
    worker = api.login("01722222222", "worker")
    job_id = _post_job(api, employer).json()["id"]

    # still open: nobody is working on it
    assert api.client.post(f"{JOBS}{job_id}/complete", headers=employer.headers).status_code == 400

    api.client.post(f"{JOBS}{job_id}/apply", json={}, headers=worker.headers)
    api.client.post(f"{JOBS}{job_id}/assign/{worker.id}", headers=employer.headers)
    assert api.client.post(f"{JOBS}{job_id}/complete", headers=employer.headers).status_code == 200
    assert api.client.post(f"{JOBS}{job_id}/complete", headers=employer.headers).status_code == 400


def test_somebody_else_cannot_assign_or_complete_my_job(api):
    employer = api.login("01711111111", "employer")
    other = api.login("01744444444", "employer")
    worker = api.login("01722222222", "worker")
    job_id = _post_job(api, employer).json()["id"]
    api.client.post(f"{JOBS}{job_id}/apply", json={}, headers=worker.headers)

    assert api.client.post(f"{JOBS}{job_id}/assign/{worker.id}", headers=other.headers).status_code == 400
    assert api.client.post(f"{JOBS}{job_id}/complete", headers=other.headers).status_code == 400


def test_negative_budget_cannot_be_used_to_pull_money_out_of_another_wallet(api):
    """Reproduced on the old code: budget -1000, assign a user who never applied,
    complete, release -> 1000 moved from the victim to the attacker."""
    attacker = api.login("01711111111", "employer")
    with api.Session() as db:
        victim = User(phone="01755555555", wallet_balance=Decimal("5000.00"))
        db.add(victim)
        db.commit()
        victim_id = victim.id

    assert _post_job(api, attacker, budget=-1000).status_code == 422

    # Even with a normal job the victim cannot be attached without applying.
    job_id = _post_job(api, attacker, budget=1000).json()["id"]
    assert api.client.post(f"{JOBS}{job_id}/assign/{victim_id}", headers=attacker.headers).status_code == 400
    assert api.client.post(f"{JOBS}{job_id}/complete", headers=attacker.headers).status_code == 400
    assert api.client.post(f"/api/v1/wallet/release-escrow/{job_id}", headers=attacker.headers).status_code == 400

    with api.Session() as db:
        assert db.get(User, victim_id).wallet_balance == Decimal("5000.00")
        assert (db.get(User, attacker.id).wallet_balance or 0) == 0


def test_balance_works_when_reserved_balance_is_null(api):
    user = api.login("01711111111")
    with api.Session() as db:
        row = db.get(User, user.id)
        row.wallet_balance = Decimal("120.00")
        row.reserved_balance = None
        db.commit()

    r = api.client.get("/api/v1/wallet/balance", headers=user.headers)
    assert r.status_code == 200
    assert r.json()["available_balance"] == 120.0


# ---- AUDIT #11: reviews ---------------------------------------------------------
def _review(api, who, job_id, target_id, rating=5):
    return api.client.post(
        "/api/v1/users/review",
        json={"job_id": job_id, "target_user_id": target_id, "rating": rating},
        headers=who.headers,
    )


def test_both_parties_can_review_each_other_once(api):
    employer, worker, job_id = _completed_job(api)

    assert _review(api, employer, job_id, worker.id).status_code == 200
    assert _review(api, worker, job_id, employer.id, rating=4).status_code == 200
    # second review of the same job by the same person
    assert _review(api, employer, job_id, worker.id, rating=1).status_code == 400

    with api.Session() as db:
        assert db.query(Review).count() == 2
    summary = api.client.get(f"/api/v1/users/{worker.id}/reviews").json()
    assert summary["total_reviews"] == 1 and summary["average_rating"] == 5.0


def test_review_target_must_be_the_other_party(api):
    employer, worker, job_id = _completed_job(api)
    stranger = api.login("01733333333", "worker")

    assert _review(api, employer, job_id, stranger.id).status_code == 400  # unrelated user
    assert _review(api, employer, job_id, employer.id).status_code == 400  # yourself
    assert _review(api, stranger, job_id, worker.id).status_code == 403  # not part of the job
    with api.Session() as db:
        assert db.query(Review).count() == 0


# ---- AUDIT #12: CORS, plus response headers -----------------------------------
def test_cors_does_not_allow_credentials_for_arbitrary_origins(api):
    r = api.client.get("/api/v1/jobs/", headers={"Origin": "https://evil.example"})
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") == "*"
    assert "access-control-allow-credentials" not in r.headers


def test_cors_origin_list_is_read_from_the_environment(monkeypatch):
    from app.core.config import cors_allowed_origins

    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "https://kajkori.example/, https://www.kajkori.example")
    assert cors_allowed_origins() == ["https://kajkori.example", "https://www.kajkori.example"]
    monkeypatch.delenv("CORS_ALLOWED_ORIGINS")
    assert cors_allowed_origins() == []


def test_security_headers_are_set_on_pages_and_api(api):
    for path in ("/", "/admin", "/api/v1/jobs/"):
        r = api.client.get(path)
        assert r.headers["x-content-type-options"] == "nosniff"
        assert r.headers["x-frame-options"] == "DENY"
        assert r.headers["referrer-policy"] == "strict-origin-when-cross-origin"
