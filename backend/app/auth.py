"""
Authentication: password hashing + JWT session tokens.

Flow:
  1. Signup: hash password with bcrypt, store user row.
  2. Login: verify entered password against stored hash, issue a JWT.
  3. Protected routes: require a valid JWT in the Authorization header,
     decode it to get the current user_id.
"""

import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from dotenv import load_dotenv
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

load_dotenv()  # don't rely on another module having loaded .env first
logger = logging.getLogger(__name__)

SECRET_KEY = os.getenv("JWT_SECRET")
if not SECRET_KEY:
    # Never fall back to a guessable constant. A random per-process secret is
    # secure but invalidates all tokens on restart — set JWT_SECRET to persist them.
    SECRET_KEY = secrets.token_urlsafe(64)
    logger.warning("JWT_SECRET is not set; using a random per-process secret (tokens reset on restart).")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", str(60 * 24)))  # default 1 day

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    return pwd_context.verify(plain_password, password_hash)


def create_access_token(user_id: int, email: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": str(user_id), "email": email, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None


def get_current_user_id(token: str = Depends(oauth2_scheme)) -> int:
    """FastAPI dependency — inject this into any route that requires login."""
    payload = decode_access_token(token)
    if payload is None or "sub" not in payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return int(payload["sub"])
