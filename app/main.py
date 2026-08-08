from pathlib import Path
from fastapi import FastAPI, HTTPException
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

# Static Files Path
BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# ১. হোম পেজ রাউট (/ এবং /index.html)
@app.get("/", include_in_schema=False)
@app.get("/index.html", include_in_schema=False)
def read_root():
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {"message": "KajKori API is running!"}

# ২. লগইন পেজ রাউট (/login.html বা /login)
@app.get("/login.html", include_in_schema=False)
@app.get("/login", include_in_schema=False)
def read_login():
    login_file = STATIC_DIR / "login.html"
    if login_file.exists():
        return FileResponse(login_file)
    raise HTTPException(status_code=404, detail="login.html file not found inside static directory")

# ৩. রেজিস্ট্রেশন পেজ রাউট (/register.html বা /register)
@app.get("/register.html", include_in_schema=False)
@app.get("/register", include_in_schema=False)
def read_register():
    register_file = STATIC_DIR / "register.html"
    if register_file.exists():
        return FileResponse(register_file)
    raise HTTPException(status_code=404, detail="register.html file not found inside static directory")

# ৪. এডমিন পেজ রাউট (/admin.html বা /admin)
@app.get("/admin.html", include_in_schema=False)
@app.get("/admin", include_in_schema=False)
def read_admin():
    admin_file = STATIC_DIR / "admin.html"
    if admin_file.exists():
        return FileResponse(admin_file)
    raise HTTPException(status_code=404, detail="admin.html file not found inside static directory")