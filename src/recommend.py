#!/usr/bin/env python3
"""Model batch rekomendasi harga (versi sederhana / dummy) -> gold.fct_price_recommendation.

Aturan (rule-v1.0), dihitung per produk untuk satu tanggal:
  1. harga_acuan  = median harga jual kompetitor pada tanggal itu
  2. harga_undercut = harga_acuan * (1 - undercut)                  (default undercut = 2%)
  3. batas_bawah  = median harga tercatat * cost_ratio * (1 + min_margin)
                    (cost_ratio = ASUMSI biaya sebagai bagian dari harga tercatat; XYZ belum
                    punya data biaya, jadi 0,80 hanyalah asumsi contoh)
  4. rekomendasi  = max(harga_undercut, batas_bawah), dibulatkan ke Rp 100

Sifat:
  * Hanya MEMBACA tabel gold (fct_product_price_daily) dan MENULIS gold.fct_price_recommendation.
  * Batch: semua produk diproses dalam satu run.
  * Idempotent per (produk, tanggal, model_version): menjalankan ulang menimpa baris yang sama.
  * Jejak: setiap baris menyimpan model_version, run_id, run_ts, dan parameter yang dipakai.

Contoh:
  python src/recommend.py --dry-run         # hitung dan tampilkan, tanpa menulis
  python src/recommend.py                   # tanggal terbaru
  python src/recommend.py --days 7          # 7 tanggal terakhir
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import math
import os
import sys
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

MODEL_VERSION = "rule-v1.0"
ROOT = Path(__file__).resolve().parent.parent


# ----------------------------------------------------------------- logging JSON
class JsonFormatter(logging.Formatter):
    def format(self, record):
        payload = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                   "level": record.levelname, "event": record.getMessage()}
        payload.update(getattr(record, "fields", {}))
        return json.dumps(payload, ensure_ascii=True, default=str)


_h = logging.StreamHandler(sys.stdout)
_h.setFormatter(JsonFormatter())
_log = logging.getLogger("recommend")
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


# ----------------------------------------------------------------- aturan harga
def round100(x: float) -> int:
    return int(round(x / 100.0)) * 100


def ceil100(x: float) -> int:
    return int(math.ceil(x / 100.0)) * 100


def recommend(median_price, median_list, undercut, cost_ratio, min_margin):
    """Kembalikan (harga_rekomendasi, batas_bawah, aturan_yang_dipakai)."""
    undercut_price = round100(float(median_price) * (1 - undercut))
    floor_price = ceil100(float(median_list) * cost_ratio * (1 + min_margin))
    if floor_price > undercut_price:
        return floor_price, floor_price, "margin_floor"
    return undercut_price, floor_price, "undercut_median"


SQL_DATES = """
select distinct price_date, date_key from gold.fct_product_price_daily
where price_date <= %s order by price_date desc limit %s
"""

SQL_COMPETITORS = """
select product_key,
       count(*)                                                       as competitor_count,
       percentile_cont(0.5) within group (order by price_idr)         as median_price,
       min(price_idr)                                                 as min_price,
       percentile_cont(0.5) within group (order by original_price_idr) as median_list
from gold.fct_product_price_daily
where date_key = %s
group by product_key
"""

SQL_DELETE = """
delete from gold.fct_price_recommendation
where date_key = %s and model_version = %s
"""

SQL_INSERT = """
insert into gold.fct_price_recommendation
    (recommendation_key, date_key, product_key, competitor_median_price_idr, competitor_min_price_idr,
     competitor_count, price_floor_idr, recommended_price_idr, rule_applied,
     model_version, run_id, run_ts, parameters)
values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""


def main() -> int:
    ap = argparse.ArgumentParser(description="Model batch rekomendasi harga")
    ap.add_argument("--date", help="tanggal akhir YYYY-MM-DD (default: tanggal terbaru di fakta)")
    ap.add_argument("--days", type=int, default=1, help="jumlah tanggal terakhir yang diproses")
    ap.add_argument("--undercut", type=float, default=0.02)
    ap.add_argument("--cost-ratio", type=float, default=0.80)
    ap.add_argument("--min-margin", type=float, default=0.10)
    ap.add_argument("--min-competitors", type=int, default=2)
    ap.add_argument("--dry-run", action="store_true", help="hitung saja, tanpa menulis ke database")
    args = ap.parse_args()

    import psycopg
    from psycopg.types.json import Jsonb

    load_env_file(ROOT / ".env")
    run_id = uuid.uuid4().hex[:12]
    run_ts = datetime.now(timezone.utc)
    params = {"undercut_pct": args.undercut, "cost_ratio_assumed": args.cost_ratio,
              "min_margin_pct": args.min_margin, "min_competitors": args.min_competitors}
    emit(logging.INFO, "run_start", run_id=run_id, model_version=MODEL_VERSION,
         parameters=params, dry_run=args.dry_run)

    try:
        conn = psycopg.connect(
            host=os.environ.get("DB_HOST", "localhost"), port=int(os.environ.get("DB_PORT", "5432")),
            dbname=os.environ["POSTGRES_DB"], user=os.environ["POSTGRES_USER"],
            password=os.environ["POSTGRES_PASSWORD"], connect_timeout=10)
    except Exception as exc:  # noqa: BLE001
        emit(logging.ERROR, "db_connection_failed", error=str(exc))
        return 1

    total_rows = total_floor = total_skipped = 0
    with conn:
        end = date.fromisoformat(args.date) if args.date else date.max
        with conn.cursor() as cur:
            cur.execute(SQL_DATES, (end, args.days))
            dates = cur.fetchall()
        if not dates:
            emit(logging.ERROR, "no_price_data", hint="Jalankan dbt build dulu")
            return 1

        for price_date, date_key in sorted(dates):
            with conn.cursor() as cur:
                cur.execute(SQL_COMPETITORS, (date_key,))
                comp = cur.fetchall()
            rows, skipped, floor_hits = [], 0, 0
            for product_key, n, med, mn, med_list in comp:
                if n < args.min_competitors:
                    skipped += 1
                    emit(logging.WARNING, "product_skipped", reason="insufficient_competitors",
                         product_key=product_key, competitor_count=n, date=price_date)
                    continue
                rec, floor_p, rule = recommend(med, med_list, args.undercut, args.cost_ratio, args.min_margin)
                floor_hits += rule == "margin_floor"
                key = hashlib.md5(f"{product_key}|{date_key}|{MODEL_VERSION}".encode()).hexdigest()
                rows.append((key, date_key, product_key, round(float(med), 2), float(mn), n,
                             floor_p, rec, rule, MODEL_VERSION, run_id, run_ts, Jsonb(params)))
            if not args.dry_run:
                with conn.transaction():  # hapus + isi ulang satu tanggal = idempotent
                    with conn.cursor() as cur:
                        cur.execute(SQL_DELETE, (date_key, MODEL_VERSION))
                        cur.executemany(SQL_INSERT, rows)
            emit(logging.INFO, "date_done", date=price_date, products=len(rows),
                 skipped=skipped, margin_floor_applied=floor_hits, written=not args.dry_run)
            total_rows += len(rows); total_floor += floor_hits; total_skipped += skipped

    emit(logging.INFO, "run_summary", run_id=run_id, model_version=MODEL_VERSION, dates=len(dates),
         recommendations=total_rows, margin_floor_applied=total_floor, skipped=total_skipped,
         dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
