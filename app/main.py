import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.database import Base, engine
from app.routers.users import router as users_router
from app.routers.jobs import router as jobs_router
from app.routers.wallet import router as wallet_router
from app.routers.dashboard import router as dashboard_router

# ডাটাবেজ টেবিল তৈরি
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="KajKori API",
    description="A local service marketplace platform for Bangladesh",
    version="1.0.0",
)

# ১. CORS Middleware (HTML/JavaScript থেকে ব্যাকএন্ডের API কলের অনুমতি দেওয়ার জন্য)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ২. সকল রাউটার যুক্ত করা
app.include_router(users_router)
app.include_router(jobs_router)
app.include_router(wallet_router)
app.include_router(dashboard_router)


# ৩. HTML/CSS/JS সরাসরি সার্ভ করার ব্যবস্থা
if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

    @app.get("/", include_in_schema=False)
    def read_root():
        index_path = os.path.join("static", "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)
        return {"message": "KajKori API is running successfully!"}
else:
    @app.get("/", include_in_schema=False)
    def read_root():
        return {"message": "KajKori API is running successfully!"}