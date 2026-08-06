from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import Base, engine
from app.routers import jobs, users

# ডাটাবেজ টেবিল তৈরি করা
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="KajKori Backend API",
    description="Backend services for KajKori Platform - Connecting Employers & Workers",
    version="1.0.0",
)

# CORS Middleware (ফ্রন্টএন্ড বা মোবাইল অ্যাপ থেকে এক্সেস দেওয়ার জন্য)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # প্রোডাকশনে সুনির্দিষ্ট ফ্রন্টএন্ড ডোমেইন বসাতে হবে
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# রাউটার যুক্ত করা
app.include_router(users.router)
app.include_router(jobs.router)


@app.get("/")
def root():
    return {
        "message": "Welcome to KajKori Platform API",
        "docs": "Visit /docs for API documentation",
    }