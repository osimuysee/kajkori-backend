# KajKori backend: project guide for Claude Code

## What this is
A marketplace for Bangladesh: users hire verified workers (all trades, all of Bangladesh), pay digitally (bKash/Nagad), and workers get a searchable "worker card". The normal booking flow has no admin; the admin only handles disputes and the review queue. One admin only: the owner.

## Real stack (do not assume anything else)
- Python 3.11/3.12, FastAPI, SQLAlchemy 2 (Column style), Alembic, pydantic 2
- PostgreSQL on Render, SQLite locally. NOT Node, NOT MongoDB.
- Phone OTP login, JWT (PyJWT), slowapi rate limiting, Greenweb SMS
- Static pages in `static/`. The admin page `static/admin.html` talks to Firebase, not to this API (see docs/AUDIT.md #9).

## Run
```
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env            # then fill in SECRET_KEY and NID_HMAC_PEPPER
uvicorn app.main:app --reload
pytest -q                       # SQLite only, never touches a real database
```

## Layout
```
app/
  main.py            app + routers (payments and ivr routers exist but are NOT mounted)
  auth.py database.py limiter.py schemas.py
  models.py          existing: users, jobs, job_applications, transactions, reviews
  models_marketplace.py  NEW: locations, worker_profiles, worker_trades,
                         worker_service_areas, bookings, disputes, audit_logs
  core/config.py     env handling, fails closed (APP_ENV unset = production)
  core/types.py      UTCDateTime (always tz-aware), utcnow(), ensure_utc() for legacy naive columns
  core/phone.py      normalize_bd_phone() (one canonical 01XXXXXXXXX form), mask_phone() for logs
  security/nid.py    normalise + HMAC-hash NID numbers
  security/otp.py    generate / hash / constant-time check of login codes
  routers/ services/ existing code
alembic/versions/    migrations (single head: 20261109_marketplace_tables)
tests/               pytest
docs/AUDIT.md        known problems in the existing code, with priorities.
                     LOCAL ONLY (git-ignored): this repository is public, so the
                     list of unfixed problems is not published. Ask the owner for it.
```

## Rules for every change
1. One small task at a time. Write a short plan first and wait for approval before big changes. Do not rewrite unrelated files.
2. Every schema change needs an Alembic migration AND a passing `tests/test_migrations.py` (it fails if models and migrations drift apart).
3. Rollback command is `alembic downgrade 88e104190a1d`. `downgrade -1` does not work from the merge revision.
4. Never rely on `create_all` in production; it is only a local-dev convenience for now.
5. Time: use `UTCDateTime` columns and `utcnow()`. Never `datetime.utcnow()`, never naive datetimes.
6. Money: `Decimal` / `Numeric(12, 2)`. Never float in new code.
7. Run `pytest -q` before saying anything is done. Add tests with every feature.
8. Fake data only. Never ask for or use real NID numbers, photos, or payment credentials.
9. End-user messages are in Bangla (existing convention); code comments in English.
10. Stop and ask before touching: payments/escrow, KYC/NID rules, anything legal, deleting data.

## Security rules (strict)
- Never store, log or return a raw NID number. Store `hash_nid()` output in `worker_profiles.nid_hash` (UNIQUE). NID images are stored as references to encrypted storage, never public URLs.
- Never log or return OTPs, JWTs, webhook secrets, full phone numbers. Hash OTPs at rest and compare in constant time (`hmac.compare_digest`).
- No secret has a default value in code. Use `require_secret()` from `app/core/config.py`.
- Hide phone numbers and exact addresses until a booking is accepted/paid. Public profile endpoints must not return phone or wallet data.
- Every protected route checks the role. Admin actions and every money movement write an `audit_logs` row (no PII in `details`).
- Payment webhooks: verify the signature with a constant-time compare, make handlers idempotent, take row locks when moving money.
- Do not expose exception text to clients.

## Domain rules (design targets; mostly not implemented yet)
- Booking flow: requested > accepted > paid_hold > started > completed > released. Side states: declined, expired, cancelled, disputed, refunded. Validate every transition.
- User gives the worker a one-time start code (store only its hash; count attempts).
- Not confirmed 24h after completion: auto-confirm. Disputes must be opened within 48h.
- Money is held at booking and released after confirmation. Commission is fixed at release.
- Risk tiers: 1 labour and cleaning, 2 skilled trades, 3 enters homes (domestic help, driver, caregiver, security): needs extra verification.
- Shared payout number across workers is a review-queue signal, not a hard block.
- An area opens for booking only when enough verified workers exist there; otherwise show a waitlist.

## Build order
1. [done] Foundation: this file, `.env.example`, config, test setup
2. [done, needs review] Schemas + migration for the marketplace tables
3. [done except money, needs review] P0 items in docs/AUDIT.md + auth/OTP hardening + static page bugs (see the 11 Nov update in docs/AUDIT.md). The items still waiting for the owner are listed there
4. Worker onboarding (NID + selfie, duplicate check, review queue)
5. Locations seed (needs an official dataset; do not invent data) + search + worker card API
6. Booking flow without money
7. Payment sandbox, escrow, payout
8. Reviews, disputes, admin (decide Firebase vs this API first)
9. Security review and external pentest
10. Go live in one small area first

## Out of scope until asked
IVR/USSD flow, local agent app, B2B, insurance/loans.
