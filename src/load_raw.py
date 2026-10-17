#!/usr/bin/env python3
"""Loader raw layer: baca file .jsonl -> validasi (Pydantic) -> raw.crawl_product_price.

Prinsip:
  * Raw layer menyimpan data APA ADANYA. Loader hanya MENOLAK baris yang strukturnya rusak
    (JSON tidak valid, metadata/nama produk kosong). Baris yang isinya mencurigakan
    (harga kosong, diskon aneh, dll.) tetap dimuat tetapi DITANDAI di log.
    Pembersihan dilakukan nanti di silver (dbt).
  * Idempotent: unique key (platform, source_url, crawl_date, payload_hash) +
    INSERT ... ON CONFLICT DO NOTHING. Menjalankan ulang tidak membuat duplikat.
  * Log berformat JSON satu baris per kejadian, mudah dicari saat troubleshooting.
  * Jika tingkat baris valid < ambang (default 95%), exit code 1 (alert).

Contoh:
  python src/load_raw.py --dry-run          # uji tanpa database
  python src/load_raw.py                    # muat ke PostgreSQL
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import sys
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

LOADER_VERSION = "1.0"
ROOT = Path(__file__).resolve().parent.parent
WIB = timezone(timedelta(hours=7))
HASH_KEYS = ["platform", "source_url", "product_name", "price",
             "original_price", "discount", "detail", "breadcrumb"]

INSERT_SQL = """
INSERT INTO raw.crawl_product_price
    (platform, source_url, crawled_at, crawler_version, payload_hash, data_source,
     source_file, product_name, price_text, original_price_text, discount_text,
     detail, breadcrumb, raw_payload)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT ON CONSTRAINT uq_raw_crawl_idempotent DO NOTHING
RETURNING raw_id
"""


# ----------------------------------------------------------------- logging JSON
class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "level": record.levelname,
            "event": record.getMessage(),
        }
        payload.update(getattr(record, "fields", {}))
        return json.dumps(payload, ensure_ascii=True, default=str)


_handler = logging.StreamHandler(sys.stdout)
_handler.setFormatter(JsonFormatter())
_logger = logging.getLogger("loader")
_logger.handlers = [_handler]
_logger.setLevel(logging.INFO)


def emit(level: int, event: str, **fields) -> None:
    _logger.log(level, event, extra={"fields": fields})


# ----------------------------------------------------------------- skema Pydantic
class RawRecord(BaseModel):
    """Bentuk satu baris .jsonl. Field wajib = metadata ingestion + nama produk."""
    model_config = ConfigDict(extra="ignore")

    platform: str = Field(min_length=1)
    source_url: str = Field(min_length=1)
    crawled_at: datetime
    crawler_version: str = Field(min_length=1)
    data_source: Literal["live", "synthetic"]
    payload_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    product_name: str = Field(min_length=1)
    price: Optional[str] = None
    original_price: Optional[str] = None
    discount: Optional[str] = None
    detail: Optional[str] = None
    breadcrumb: Optional[str] = None

    @field_validator("crawled_at")
    @classmethod
    def must_have_timezone(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("crawled_at harus memuat zona waktu")
        return v


def compute_hash(raw: dict) -> str:
    blob = json.dumps({k: raw.get(k) for k in HASH_KEYS}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def suspicious_flags(rec: RawRecord, raw: dict) -> list[str]:
    """Tanda isi yang mencurigakan. Baris tetap dimuat (raw = apa adanya)."""
    flags = []
    if rec.price is None:
        flags.append("price_missing")
    else:
        digits = re.sub(r"\D", "", rec.price)
        if not digits:
            flags.append("price_no_digits")
        elif int(digits) == 0:
            flags.append("price_not_positive")
    if rec.discount:
        m = re.search(r"-?\d+", rec.discount)
        if not m or not (0 <= int(m.group()) <= 100):
            flags.append("discount_out_of_range")
    if compute_hash(raw) != rec.payload_hash:
        flags.append("payload_hash_mismatch")
    return flags


# ----------------------------------------------------------------- konfigurasi
def load_env_file(path: Path) -> None:
    """Baca .env sederhana (KEY=VALUE) tanpa pustaka tambahan."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def connect():
    import psycopg  # diimpor di sini agar --dry-run tidak butuh database
    return psycopg.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        port=int(os.environ.get("DB_PORT", "5432")),
        dbname=os.environ["POSTGRES_DB"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        connect_timeout=10,
    )


# ----------------------------------------------------------------- proses file
def process_file(path: Path, cur, seen: set, totals: Counter) -> Counter:
    """Proses satu file. cur=None berarti dry-run (tanpa database)."""
    Jsonb = None
    if cur is not None:  # impor hanya saat benar-benar memuat ke database
        from psycopg.types.json import Jsonb

    c = Counter()
    with path.open(encoding="utf-8-sig") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            c["lines"] += 1
            try:
                raw = json.loads(line)
                if not isinstance(raw, dict):
                    raise ValueError("baris bukan objek JSON")
                rec = RawRecord.model_validate(raw)
            except (json.JSONDecodeError, ValueError, ValidationError) as exc:
                c["rejected"] += 1
                msg = ([f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()]
                       if isinstance(exc, ValidationError) else [str(exc)])
                emit(logging.ERROR, "row_rejected", file=path.name, line=line_no, errors=msg)
                continue

            c["valid"] += 1
            flags = suspicious_flags(rec, raw)
            for fl in flags:
                c[f"flag:{fl}"] += 1
            if flags:
                emit(logging.WARNING, "row_flagged", file=path.name, line=line_no,
                     platform=rec.platform, source_url=rec.source_url, flags=flags)

            if cur is None:  # dry-run: tiru aturan unique key di memori
                key = (rec.platform, rec.source_url,
                       rec.crawled_at.astimezone(WIB).date(), rec.payload_hash)
                if key in seen:
                    c["duplicate_skipped"] += 1
                else:
                    seen.add(key)
                    c["inserted"] += 1
                continue

            cur.execute(INSERT_SQL, (
                rec.platform, rec.source_url, rec.crawled_at, rec.crawler_version,
                rec.payload_hash, rec.data_source, path.name, rec.product_name,
                rec.price, rec.original_price, rec.discount, rec.detail,
                rec.breadcrumb, Jsonb(raw)))
            if cur.fetchone() is None:
                c["duplicate_skipped"] += 1
            else:
                c["inserted"] += 1
    return c


def main() -> int:
    ap = argparse.ArgumentParser(description="Muat file .jsonl ke raw layer")
    ap.add_argument("--data-dir", default=str(ROOT / "data" / "sample"))
    ap.add_argument("--pattern", default="*.jsonl")
    ap.add_argument("--threshold", type=float, default=0.95,
                    help="batas minimal rasio baris valid (default 0.95)")
    ap.add_argument("--dry-run", action="store_true", help="validasi saja, tanpa database")
    args = ap.parse_args()

    load_env_file(ROOT / ".env")
    files = sorted(Path(args.data_dir).glob(args.pattern))
    if not files:
        emit(logging.ERROR, "no_input_files", data_dir=args.data_dir, pattern=args.pattern)
        return 1

    run_id = datetime.now(WIB).strftime("%Y%m%d-%H%M%S")
    emit(logging.INFO, "run_start", run_id=run_id, loader_version=LOADER_VERSION,
         files=len(files), dry_run=args.dry_run, threshold=args.threshold)
    t0 = time.time()
    totals: Counter = Counter()
    failed_files: list[str] = []
    seen: set = set()

    conn = None
    try:
        if not args.dry_run:
            try:
                conn = connect()
            except Exception as exc:  # noqa: BLE001 - tampilkan penyebab apa pun
                emit(logging.ERROR, "db_connection_failed", error=str(exc),
                     hint="Pastikan 'docker compose up -d' berjalan dan .env benar")
                return 1

        for path in files:
            try:
                if conn is None:
                    c = process_file(path, None, seen, totals)
                else:
                    with conn.transaction():  # satu file = satu transaksi
                        with conn.cursor() as cur:
                            c = process_file(path, cur, seen, totals)
            except Exception as exc:  # noqa: BLE001
                failed_files.append(path.name)
                emit(logging.ERROR, "file_failed", file=path.name, error=str(exc))
                continue
            totals.update(c)
            emit(logging.INFO, "file_done", file=path.name,
                 **{k.replace(":", "_"): v for k, v in c.items()})
    finally:
        if conn is not None:
            conn.close()

    lines = totals["lines"]
    rate = (totals["valid"] / lines) if lines else 0.0
    flags = {k[5:]: v for k, v in totals.items() if k.startswith("flag:")}
    emit(logging.INFO, "run_summary", run_id=run_id, lines=lines, valid=totals["valid"],
         rejected=totals["rejected"], parse_success_rate=round(rate, 4),
         inserted=totals["inserted"], duplicate_skipped=totals["duplicate_skipped"],
         flags=flags, failed_files=failed_files, seconds=round(time.time() - t0, 2),
         dry_run=args.dry_run)

    if failed_files:
        emit(logging.ERROR, "run_failed_files", files=failed_files)
        return 1
    if rate < args.threshold:
        emit(logging.ERROR, "ALERT_parse_success_rate_below_threshold",
             rate=round(rate, 4), threshold=args.threshold)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
