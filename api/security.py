"""Autentikasi JWT dan otorisasi berbasis peran (analyst, admin)."""
from __future__ import annotations

import hmac
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel

from .config import get_settings

ALGORITHM = "HS256"
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")


class User(BaseModel):
    username: str
    role: str


def authenticate(username: str, password: str) -> User | None:
    entry = get_settings().users.get(username)
    # compare_digest dipakai agar waktu pembandingan tidak membocorkan isi kata sandi
    expected = entry[0] if entry else ""
    ok = hmac.compare_digest(password.encode(), expected.encode())
    return User(username=username, role=entry[1]) if (entry and ok) else None


def create_access_token(user: User) -> tuple[str, int]:
    s = get_settings()
    ttl = s.token_ttl_minutes * 60
    now = datetime.now(timezone.utc)
    payload = {"sub": user.username, "role": user.role, "iat": now, "exp": now + timedelta(seconds=ttl)}
    return jwt.encode(payload, s.jwt_secret, algorithm=ALGORITHM), ttl


def current_user(token: str = Depends(oauth2_scheme)) -> User:
    err = HTTPException(status.HTTP_401_UNAUTHORIZED, "Token tidak valid atau kedaluwarsa",
                        headers={"WWW-Authenticate": "Bearer"})
    try:
        data = jwt.decode(token, get_settings().jwt_secret, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        raise err
    if data.get("role") not in ("analyst", "admin") or not data.get("sub"):
        raise err
    return User(username=data["sub"], role=data["role"])


def require_roles(*roles: str):
    """Dependency pembatas peran. Contoh: Depends(require_roles('admin'))."""
    def checker(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN,
                                f"Peran '{user.role}' tidak diizinkan; dibutuhkan: {', '.join(roles)}")
        return user
    return checker
