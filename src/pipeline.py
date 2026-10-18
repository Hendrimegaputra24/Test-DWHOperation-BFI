#!/usr/bin/env python3
"""Pipeline lengkap: skema raw -> muat data -> dbt build -> (freshness) -> rekomendasi harga.

Dipakai oleh `docker compose up` (service `pipeline`) dan bisa dijalankan manual:
    python src/pipeline.py                 # semua langkah
    python src/pipeline.py --step ingest   # hanya ambil/muat data (dipakai Airflow)

Setiap langkah dicatat sebagai log JSON (nama, durasi, kode keluar). Langkah wajib yang gagal
menghentikan pipeline dengan kode keluar 1. Aman dijalankan berulang (idempotent).
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
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


def grant_gold_readonly() -> bool:
    """Buat/perbarui akun database khusus-baca (untuk Metabase) yang hanya boleh SELECT di schema gold.
    Dibuat ulang setiap run karena dbt membuat ulang tabel dan dapat menghapus hak akses lama."""
    user = os.environ.get("METABASE_DB_USER")
    password = os.environ.get("METABASE_DB_PASSWORD")
    if not user or not password:
        emit(logging.WARNING, "readonly_role_skipped",
             reason="METABASE_DB_USER / METABASE_DB_PASSWORD belum diisi di .env")
        return True
    from psycopg import sql
    ident = sql.Identifier(user)
    owner = sql.Identifier(os.environ["POSTGRES_USER"])
    try:
        with connect() as conn:
            exists = conn.execute("select 1 from pg_roles where rolname = %s", (user,)).fetchone()
            verb = "alter" if exists else "create"
            conn.execute(sql.SQL(verb + " role {} login password {}").format(ident, sql.Literal(password)))
            conn.execute(sql.SQL("grant connect on database {} to {}").format(
                sql.Identifier(os.environ["POSTGRES_DB"]), ident))
            conn.execute(sql.SQL("grant usage on schema gold to {}").format(ident))
            conn.execute(sql.SQL("grant select on all tables in schema gold to {}").format(ident))
            conn.execute(sql.SQL("alter default privileges for role {} in schema gold "
                                 "grant select on tables to {}").format(owner, ident))
        emit(logging.INFO, "readonly_role_ready", role=user, schema="gold")
        return True
    except Exception as exc:  # noqa: BLE001
        emit(logging.ERROR, "readonly_role_failed", error=str(exc)[:300])
        return False


def dbt_cmd(*args: str) -> list[str]:
    exe = shutil.which("dbt") or str(Path(sys.executable).parent / "dbt")
    return [exe, *args, "--project-dir", "dbt", "--profiles-dir", "dbt"]


def exec_cmd(name: str, cmd: list[str], fatal: bool) -> bool:
    """Jalankan satu perintah dan kembalikan hasil SEBENARNYA (True = sukses)."""
    t0 = time.time()
    emit(logging.INFO, "step_start", step=name, cmd=" ".join(cmd))
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    secs = round(time.time() - t0, 1)
    tail = (proc.stdout + proc.stderr).strip().splitlines()[-6:]
    ok = proc.returncode == 0
    emit(logging.INFO if ok else (logging.ERROR if fatal else logging.WARNING), "step_end",
         step=name, ok=ok, returncode=proc.returncode, seconds=secs, output_tail=tail)
    return ok


def choose_data_source(py: str) -> tuple[str, str] | None:
    """Tentukan sumber data. Kembalikan (folder, pola file) atau None bila mode live gagal.
    sample = data sampel; live = crawl, harus berhasil; auto = coba crawl, bila gagal pakai sampel."""
    mode = os.environ.get("SOURCE_MODE", "sample").strip().lower()
    emit(logging.INFO, "source_mode", mode=mode)
    if mode == "sample":
        return "data/sample", "*.jsonl"
    if mode not in ("live", "auto"):
        emit(logging.ERROR, "bad_source_mode", mode=mode, allowed="sample | live | auto")
        return None
    ok = exec_cmd("crawl_live", [py, "src/crawler.py"], fatal=(mode == "live"))
    today = datetime.now(timezone(timedelta(hours=7))).date().isoformat()
    files = list((ROOT / "data" / "live").glob(f"live_{today}_*.jsonl"))
    if ok and files:
        return "data/live", f"live_{today}_*.jsonl"
    if mode == "live":
        emit(logging.ERROR, "live_crawl_failed", hint="Gunakan SOURCE_MODE=auto atau sample sebagai cadangan")
        return None
    emit(logging.WARNING, "fallback_to_sample", reason="crawl live tidak berhasil penuh; memakai data sampel")
    return "data/sample", "*.jsonl"


def run_cmd(name: str, cmd, fatal: bool) -> bool:
    if callable(cmd):  # langkah berupa fungsi Python
        t0 = time.time()
        ok = cmd()
        emit(logging.INFO if ok else logging.ERROR, "step_end", step=name, ok=ok,
             seconds=round(time.time() - t0, 1))
        return ok or not fatal
    t0 = time.time()
    emit(logging.INFO, "step_start", step=name, cmd=" ".join(cmd))
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    secs = round(time.time() - t0, 1)
    tail = (proc.stdout + proc.stderr).strip().splitlines()[-6:]
    ok = proc.returncode == 0
    emit(logging.INFO if ok else (logging.ERROR if fatal else logging.WARNING), "step_end",
         step=name, ok=ok, returncode=proc.returncode, seconds=secs, output_tail=tail)
    return ok or not fatal


STEP_CHOICES = ("all", "ingest", "transform", "recommend")


def main(argv: list[str] | None = None) -> int:
    """Jalankan pipeline. --step all (bawaan) = semua langkah berurutan, persis seperti sebelumnya.
    ingest = ambil/muat data ke raw; transform = dbt build + akun baca + freshness;
    recommend = hitung rekomendasi harga. Pembagian ini dipakai Airflow (satu langkah = satu task)."""
    ap = argparse.ArgumentParser(description="Pipeline Price Analytics")
    ap.add_argument("--step", choices=STEP_CHOICES, default="all",
                    help="langkah yang dijalankan (bawaan: all)")
    args = ap.parse_args(argv)
    do_ingest = args.step in ("all", "ingest")
    do_transform = args.step in ("all", "transform")
    do_recommend = args.step in ("all", "recommend")

    load_env_file(ROOT / ".env")
    t0 = time.time()
    emit(logging.INFO, "pipeline_start", db_host=os.environ.get("DB_HOST", "localhost"), step=args.step)
    if not wait_for_db():
        return 1
    if ensure_raw_schema() != 0:
        return 1
    py = sys.executable
    steps: list[tuple] = []
    if do_ingest:
        source = choose_data_source(py)
        if source is None:
            emit(logging.ERROR, "pipeline_failed", failed_step="choose_data_source", step=args.step)
            return 1
        data_dir, pattern = source
        steps.append(("load_raw", [py, "src/load_raw.py", "--data-dir", data_dir, "--pattern", pattern], True))
    if do_transform:
        steps += [
            ("dbt_build", dbt_cmd("build"), True),
            ("grant_gold_readonly", grant_gold_readonly, True),
            ("dbt_source_freshness", dbt_cmd("source", "freshness"), False),  # informasi, tidak fatal
        ]
    if do_recommend:
        steps.append(("recommend", [py, "src/recommend.py", "--days", "7"], True))
    for name, cmd, fatal in steps:
        if not run_cmd(name, cmd, fatal):
            emit(logging.ERROR, "pipeline_failed", failed_step=name, step=args.step,
                 seconds=round(time.time() - t0, 1))
            return 1
    emit(logging.INFO, "pipeline_done", step=args.step, seconds=round(time.time() - t0, 1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
