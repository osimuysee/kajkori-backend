from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import Base, engine

# সরাসরি ফাইল থেকে রাউটার ইম্পোর্ট করা হচ্ছে (ইনইট ফাইলের ঝামেলা এড়াতে)
from app.routers.ivr import router as ivr_router
from app.routers.jobs import router as jobs_router
from app.routers.users import router as users_router
from app.routers.wallet import router as wallet_router

# ডাটাবেজ টেবিল তৈরি করা
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="KajKori Backend API",
    description="Backend services for KajKori Platform - Connecting Employers & Workers",
    version="1.0.0",
)

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
app.include_router(wallet_router)


@app.get("/")
def root():
    return {
        "message": "Welcome to KajKori Platform API",
        "docs": "Visit /docs for API documentation",
    }