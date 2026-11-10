import os
from datetime import timedelta

import jwt
from dotenv import load_dotenv
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import secret_key
from app.core.types import utcnow
from app.database import get_db
from app.models import User

load_dotenv()

# Only HMAC algorithms: the signing key is a shared secret.
_ALLOWED_ALGORITHMS = {"HS256", "HS384", "HS512"}
_configured_algorithm = os.getenv("ALGORITHM", "HS256").strip().upper()
ALGORITHM = _configured_algorithm if _configured_algorithm in _ALLOWED_ALGORITHMS else "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = int(os.getenv("ACCESS_TOKEN_EXPIRE_DAYS", 7))

security = HTTPBearer()


def create_access_token(data: dict):
    # secret_key() has no default in production: a missing SECRET_KEY raises
    # ConfigError here instead of signing with a publicly known string.
    now = utcnow()
    to_encode = data.copy()
    to_encode.update({"iat": now, "exp": now + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)})
    return jwt.encode(to_encode, secret_key(), algorithm=ALGORITHM)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid token or expired session",
        headers={"WWW-Authenticate": "Bearer"},
    )
    # Outside the try block on purpose: a missing key is a server problem
    # (ConfigError -> 503 in app/main.py), not an invalid token.
    key = secret_key()
    try:
        payload = jwt.decode(
            credentials.credentials,
            key,
            algorithms=[ALGORITHM],
            options={"require": ["exp", "sub"]},
        )
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, TypeError, ValueError):
        raise credentials_exception

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise credentials_exception
    return user
