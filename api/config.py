"""Pengaturan API, dibaca dari environment (dan file .env di root proyek)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLACEHOLDER = "change-me"


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


@dataclass(frozen=True)
class Settings:
    db_host: str
    db_port: int
    db_name: str
    db_user: str
    db_password: str
    jwt_secret: str
    token_ttl_minutes: int
    users: dict  # username -> (password, role)

    @property
    def conninfo(self) -> str:
        return (f"host={self.db_host} port={self.db_port} dbname={self.db_name} "
                f"user={self.db_user} password={self.db_password} connect_timeout=10")


def _require(name: str) -> str:
    value = os.environ.get(name, "")
    if not value or value == PLACEHOLDER:
        raise RuntimeError(f"Environment variable {name} belum diisi (nilai '{PLACEHOLDER}' tidak diterima).")
    return value


@lru_cache
def get_settings() -> Settings:
    load_env_file(ROOT / ".env")
    secret = _require("API_JWT_SECRET")
    if len(secret) < 32:
        raise RuntimeError("API_JWT_SECRET minimal 32 karakter.")
    return Settings(
        db_host=os.environ.get("DB_HOST", "localhost"),
        db_port=int(os.environ.get("DB_PORT", "5432")),
        db_name=_require("POSTGRES_DB"),
        db_user=_require("POSTGRES_USER"),
        db_password=_require("POSTGRES_PASSWORD"),
        jwt_secret=secret,
        token_ttl_minutes=int(os.environ.get("API_TOKEN_TTL_MINUTES", "60")),
        users={
            "analyst": (_require("API_ANALYST_PASSWORD"), "analyst"),
            "admin": (_require("API_ADMIN_PASSWORD"), "admin"),
        },
    )
