from pathlib import Path
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

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# সকল রাউটার
app.include_router(users_router)
app.include_router(jobs_router)
app.include_router(wallet_router)
app.include_router(dashboard_router)

# Static Files Path (Absolute Path Resolution)
BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
INDEX_FILE = STATIC_DIR / "index.html"

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.get("/", include_in_schema=False)
def read_root():
    if INDEX_FILE.exists():
        return FileResponse(INDEX_FILE)
    return {
        "message": "KajKori API is running, but static/index.html was not found!",
        "checked_path": str(INDEX_FILE)
    }