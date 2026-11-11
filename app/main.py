import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded

from app.core.config import ConfigError, cors_allowed_origins, secret_key
from app.database import Base, engine
from app.limiter import limiter
import app.models_marketplace  # noqa: F401  (registers the marketplace tables with Base)
from app.routers.users import router as users_router
from app.routers.jobs import router as jobs_router
from app.routers.wallet import router as wallet_router
from app.routers.dashboard import router as dashboard_router

logger = logging.getLogger("kajkori")

# ডাটাবেজ টেবিল তৈরি
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="KajKori API",
    description="A local service marketplace platform for Bangladesh",
    version="1.0.0",
)

# Rate limiting (slowapi needs the limiter on app.state and a 429 handler).
app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"detail": "অনেক বেশি অনুরোধ করা হয়েছে। কিছুক্ষণ পর আবার চেষ্টা করুন।"},
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    # Same shape as FastAPI's default 422, minus the echoed "input". The
    # default handler crashed with HTTP 500 when the rejected value was NaN or
    # Infinity (not valid JSON), and there is no reason to send input back.
    errors = [
        {"loc": list(err.get("loc", ())), "msg": err.get("msg", ""), "type": err.get("type", "")}
        for err in exc.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": errors})


@app.exception_handler(ConfigError)
async def config_error_handler(request: Request, exc: ConfigError):
    # A required secret is missing or too weak. Say so in the server log only;
    # never send configuration details to the client.
    logger.critical("Server misconfigured (%s). Check SECRET_KEY / NID_HMAC_PEPPER.", type(exc).__name__)
    return JSONResponse(
        status_code=503,
        content={"detail": "সার্ভার কনফিগারেশনে সমস্যা আছে। কিছুক্ষণ পর আবার চেষ্টা করুন।"},
    )


# Make a missing SECRET_KEY visible in the deploy log straight away. The static
# pages keep working; login and every protected route answer 503 until it is set.
try:
    secret_key()
except ConfigError:
    logger.critical(
        "SECRET_KEY is missing or shorter than 32 characters: login is DISABLED. "
        "Set a long random SECRET_KEY in the environment."
    )

# CORS Middleware
# The API authenticates with a Bearer token in a header, not with cookies, so
# browsers never need credentialed CORS. "Any origin + credentials" is unsafe,
# so credentials are only allowed for an explicit CORS_ALLOWED_ORIGINS list.
_cors_origins = cors_allowed_origins()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins or ["*"],
    allow_credentials=bool(_cors_origins),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    # Stop MIME sniffing, stop other sites from framing our pages (clickjacking
    # on /admin), and do not leak full URLs to other sites.
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    return response


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
