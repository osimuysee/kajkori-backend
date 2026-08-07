from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text

from app.database import Base, engine
from app.limiter import limiter
from app.routers.ivr import router as ivr_router
from app.routers.jobs import router as jobs_router
from app.routers.users import router as users_router

# ডাটাবেজ টেবিল আপডেট ও মিসিং কলাম অটো-চেক
try:
    with engine.connect() as conn:
        conn.execute(
            text(
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS wallet_balance"
                " FLOAT DEFAULT 0.0;"
            )
        )
        conn.commit()
    Base.metadata.create_all(bind=engine)
except Exception as e:
    print(f"Database Initialization Error: {e}")

app = FastAPI(
    title="KajKori Backend API",
    description=(
        "Backend services for KajKori Platform - Connecting Employers &"
        " Workers"
    ),
    version="1.0.0",
)

# Rate Limiter কনফিগারেশন
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# রাউটার যুক্ত করা
app.include_router(users_router)
app.include_router(jobs_router)
app.include_router(ivr_router)


@app.get("/")
def root():
    return {
        "message": "Welcome to KajKori Platform API",
        "docs": "Visit /docs for API documentation",
    }