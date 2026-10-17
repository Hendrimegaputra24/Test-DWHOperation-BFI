#!/usr/bin/env python3
"""Pipeline lengkap: skema raw -> muat data -> dbt build -> (freshness) -> rekomendasi harga.

Dipakai oleh `docker compose up` (service `pipeline`) dan bisa dijalankan manual:
    python src/pipeline.py

Setiap langkah dicatat sebagai log JSON (nama, durasi, kode keluar). Langkah wajib yang gagal
menghentikan pipeline dengan kode keluar 1. Aman dijalankan berulang (idempotent).
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class JsonFormatter(logging.Formatter):
    def format(self, record):
        payload = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                   "level": record.levelname, "event": record.getMessage()}
        payload.update(getattr(record, "fields", {}))
        return json.dumps(payload, ensure_ascii=True, default=str)


_h = logging.StreamHandler(sys.stdout)
_h.setFormatter(JsonFormatter())
_log = logging.getLogger("pipeline")
_log.handlers = [_h]
_log.setLevel(logging.INFO)


def emit(level, event, **fields):
    _log.log(level, event, extra={"fields": fields})


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def connect():
    import psycopg
    return psycopg.connect(
        host=os.environ.get("DB_HOST", "localhost"), port=int(os.environ.get("DB_PORT", "5432")),
        dbname=os.environ["POSTGRES_DB"], user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"], connect_timeout=5, autocommit=True)


def wait_for_db(timeout_s: int | None = None) -> bool:
    timeout_s = timeout_s or int(os.environ.get("PIPELINE_DB_WAIT_SECONDS", "90"))
    deadline = time.time() + timeout_s
    attempt = 0
    while time.time() < deadline:
        attempt += 1
        try:
            with connect() as conn:
                conn.execute("select 1")
            emit(logging.INFO, "db_ready", attempts=attempt)
            return True
        except Exception as exc:  # noqa: BLE001
            emit(logging.INFO, "db_waiting", attempt=attempt, error=str(exc)[:120])
            time.sleep(3)
    emit(logging.ERROR, "db_not_ready", timeout_s=timeout_s)
    return False


def ensure_raw_schema() -> int:
    """Terapkan sql/01_raw_schema.sql (idempotent: IF NOT EXISTS)."""
    try:
        sql = (ROOT / "sql" / "01_raw_schema.sql").read_text(encoding="utf-8")
        with connect() as conn:
            conn.execute(sql)
        return 0
    except Exception as exc:  # noqa: BLE001
        emit(logging.ERROR, "ensure_schema_failed", error=str(exc)[:300])
        return 1


def dbt_cmd(*args: str) -> list[str]:
    exe = shutil.which("dbt") or str(Path(sys.executable).parent / "dbt")
    return [exe, *args, "--project-dir", "dbt", "--profiles-dir", "dbt"]


def run_cmd(name: str, cmd: list[str], fatal: bool) -> bool:
    t0 = time.time()
    emit(logging.INFO, "step_start", step=name, cmd=" ".join(cmd))
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    secs = round(time.time() - t0, 1)
    tail = (proc.stdout + proc.stderr).strip().splitlines()[-6:]
    ok = proc.returncode == 0
    emit(logging.INFO if ok else (logging.ERROR if fatal else logging.WARNING), "step_end",
         step=name, ok=ok, returncode=proc.returncode, seconds=secs, output_tail=tail)
    return ok or not fatal


def main() -> int:
    load_env_file(ROOT / ".env")
    t0 = time.time()
    emit(logging.INFO, "pipeline_start", db_host=os.environ.get("DB_HOST", "localhost"))
    if not wait_for_db():
        return 1
    if ensure_raw_schema() != 0:
        return 1
    py = sys.executable
    steps = [
        ("load_raw", [py, "src/load_raw.py"], True),
        ("dbt_build", dbt_cmd("build"), True),
        ("dbt_source_freshness", dbt_cmd("source", "freshness"), False),  # informasi, tidak fatal
        ("recommend", [py, "src/recommend.py", "--days", "7"], True),
    ]
    for name, cmd, fatal in steps:
        if not run_cmd(name, cmd, fatal):
            emit(logging.ERROR, "pipeline_failed", failed_step=name, seconds=round(time.time() - t0, 1))
            return 1
    emit(logging.INFO, "pipeline_done", seconds=round(time.time() - t0, 1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
