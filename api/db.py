"""Koneksi database (pool). API hanya membaca tabel di schema gold."""
from __future__ import annotations

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .config import get_settings

_pool: ConnectionPool | None = None


def open_pool() -> None:
    global _pool
    _pool = ConnectionPool(get_settings().conninfo, min_size=1, max_size=5,
                           kwargs={"row_factory": dict_row}, open=False)
    _pool.open(wait=True, timeout=15)


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


def get_conn():
    """Dependency FastAPI: satu koneksi dari pool per permintaan."""
    if _pool is None:
        raise RuntimeError("Pool database belum dibuka")
    with _pool.connection() as conn:
        yield conn
