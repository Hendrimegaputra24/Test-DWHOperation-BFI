"""API harga kompetitor dan rekomendasi harga.

Aturan penting:
  * Semua query membaca HANYA schema gold (dijaga oleh tests/test_api_reads_gold_only.py).
  * Kecuali POST /recommendations/run, yang memanggil model batch (src/recommend.py)
    untuk menulis ke gold.fct_price_recommendation. Hanya peran admin yang boleh.
"""
from __future__ import annotations

import json
import logging
import subprocess
import sys
import threading
import time
from contextlib import asynccontextmanager
from datetime import date
from typing import Optional

import psycopg
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Path, Query, Request
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm

from . import db
from .config import ROOT, get_settings
from .schemas import (Page, Platform, PriceRecord, Product, Recommendation,
                      RunRequest, RunResult, Token)
from .security import User, authenticate, create_access_token, require_roles

log = logging.getLogger("api")
logging.basicConfig(level=logging.INFO, format="%(message)s")

KEY_PATTERN = r"^[0-9a-f]{32}$"
READ = require_roles("analyst", "admin")     # analyst dan admin boleh membaca
ADMIN = require_roles("admin")               # hanya admin boleh memicu run


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_settings()          # gagal cepat bila konfigurasi/rahasia belum diisi
    db.open_pool()
    yield
    db.close_pool()


app = FastAPI(
    title="Price Analytics API",
    version="1.0.0",
    description=(
        "Data harga kompetitor dan rekomendasi harga untuk XYZ. Membaca dari layer **gold**.\n\n"
        "Masuk lewat `POST /auth/token`, lalu klik **Authorize** di halaman ini. "
        "Peran **analyst** dapat membaca; peran **admin** juga dapat memicu run rekomendasi.\n\n"
        "Catatan: data pada lingkungan ini bersifat **sintetis**."
    ),
    lifespan=lifespan,
)


@app.middleware("http")
async def access_log(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    log.info(json.dumps({"event": "request", "method": request.method, "path": request.url.path,
                         "status": response.status_code,
                         "ms": round((time.perf_counter() - start) * 1000, 1)}))
    return response


@app.exception_handler(psycopg.Error)
async def db_error_handler(request: Request, exc: psycopg.Error):
    log.error(json.dumps({"event": "db_error", "path": request.url.path, "error": str(exc)[:300]}))
    return JSONResponse(status_code=503, content={"detail": "Database tidak tersedia atau query gagal"})


# --------------------------------------------------------------------- util
def pagination(limit: int = Query(50, ge=1, le=200, description="Jumlah baris per halaman"),
               offset: int = Query(0, ge=0, description="Lewati sekian baris pertama")):
    return {"limit": limit, "offset": offset}


def check_range(date_from: Optional[date], date_to: Optional[date]) -> None:
    if date_from and date_to and date_from > date_to:
        raise HTTPException(422, "date_from tidak boleh lebih besar dari date_to")


def escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def page_of(conn, base_from: str, where: list[str], params: dict, select: str, order: str, pg: dict) -> dict:
    """Jalankan hitungan total dan satu halaman data. Fragmen SQL statis; nilai selalu lewat parameter."""
    clause = ("where " + " and ".join(where)) if where else ""
    total = conn.execute(f"select count(*) as n from {base_from} {clause}", params).fetchone()["n"]
    rows = conn.execute(f"select {select} from {base_from} {clause} order by {order} "
                        f"limit %(_limit)s offset %(_offset)s",
                        {**params, "_limit": pg["limit"], "_offset": pg["offset"]}).fetchall()
    return {"total": total, "limit": pg["limit"], "offset": pg["offset"], "items": rows}


# --------------------------------------------------------------------- umum
@app.get("/health", tags=["Umum"], summary="Cek status layanan dan database")
def health(conn=Depends(db.get_conn)):
    conn.execute("select 1")
    return {"status": "ok"}


auth = APIRouter(prefix="/auth", tags=["Autentikasi"])


@auth.post("/token", response_model=Token, summary="Login dan dapatkan token JWT")
def login(form: OAuth2PasswordRequestForm = Depends()):
    user = authenticate(form.username, form.password)
    if user is None:
        raise HTTPException(401, "Username atau password salah", headers={"WWW-Authenticate": "Bearer"})
    token, ttl = create_access_token(user)
    return Token(access_token=token, expires_in=ttl, role=user.role)


# --------------------------------------------------------------------- produk dan harga
catalog = APIRouter(tags=["Produk dan harga"], dependencies=[Depends(READ)])


@catalog.get("/products", response_model=Page[Product], summary="Daftar produk kanonik")
def list_products(
    category: Optional[str] = Query(None, description="Persis sama dengan nama kategori"),
    brand: Optional[str] = Query(None),
    q: Optional[str] = Query(None, min_length=2, max_length=60, description="Cari di nama produk"),
    pg: dict = Depends(pagination), conn=Depends(db.get_conn),
):
    where, params = [], {}
    if category:
        where.append("m.category = %(category)s"); params["category"] = category
    if brand:
        where.append("m.brand = %(brand)s"); params["brand"] = brand
    if q:
        where.append("m.product_name ilike %(q)s"); params["q"] = f"%{escape_like(q)}%"
    return page_of(conn, "gold.dim_product_master m", where, params,
                   "m.product_key, m.product_name, m.brand, m.category, m.pack_size, "
                   "m.n_platforms, m.first_seen_date",
                   "m.product_name", pg)


@catalog.get("/products/{product_key}", response_model=Product, summary="Detail satu produk")
def get_product(product_key: str = Path(pattern=KEY_PATTERN), conn=Depends(db.get_conn)):
    row = conn.execute(
        "select product_key, product_name, brand, category, pack_size, n_platforms, first_seen_date "
        "from gold.dim_product_master where product_key = %(k)s", {"k": product_key}).fetchone()
    if row is None:
        raise HTTPException(404, "Produk tidak ditemukan")
    return row


@catalog.get("/prices", response_model=Page[PriceRecord], summary="Harga harian per produk dan platform")
def list_prices(
    product_key: Optional[str] = Query(None, pattern=KEY_PATTERN),
    platform: Optional[Platform] = None,
    category: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    only_discounted: bool = Query(False, description="Hanya baris yang sedang diskon"),
    pg: dict = Depends(pagination), conn=Depends(db.get_conn),
):
    check_range(date_from, date_to)
    where, params = [], {}
    if product_key:
        where.append("f.product_key = %(product_key)s"); params["product_key"] = product_key
    if platform:
        where.append("p.platform_name = %(platform)s"); params["platform"] = platform
    if category:
        where.append("m.category = %(category)s"); params["category"] = category
    if date_from:
        where.append("f.price_date >= %(date_from)s"); params["date_from"] = date_from
    if date_to:
        where.append("f.price_date <= %(date_to)s"); params["date_to"] = date_to
    if only_discounted:
        where.append("f.is_discounted")
    base = ("gold.fct_product_price_daily f "
            "join gold.dim_product_master m on m.product_key = f.product_key "
            "join gold.dim_platform p on p.platform_key = f.platform_key")
    return page_of(conn, base, where, params,
                   "f.price_date, f.product_key, m.product_name, m.brand, m.category, "
                   "p.platform_name as platform, f.price_idr, f.original_price_idr, f.discount_pct, "
                   "f.is_discounted, f.data_source, f.last_crawled_at",
                   "f.price_date desc, m.product_name, p.platform_name", pg)


# --------------------------------------------------------------------- rekomendasi
recs = APIRouter(prefix="/recommendations", tags=["Rekomendasi harga"])

REC_FROM = ("(select distinct on (r.product_key, r.date_key) r.* from gold.fct_price_recommendation r "
            "{mv} order by r.product_key, r.date_key, r.run_ts desc) r "
            "join gold.dim_product_master m on m.product_key = r.product_key "
            "join gold.dim_date d on d.date_key = r.date_key")
REC_SELECT = ("d.date as recommendation_date, r.product_key, m.product_name, r.competitor_count, "
              "r.competitor_median_price_idr, r.competitor_min_price_idr, r.price_floor_idr, "
              "r.recommended_price_idr, r.rule_applied, r.model_version, r.run_id, r.run_ts, r.parameters")


def rec_from(model_version: Optional[str]) -> str:
    return REC_FROM.format(mv="where r.model_version = %(model_version)s" if model_version else "")


@recs.get("", response_model=Page[Recommendation], dependencies=[Depends(READ)],
          summary="Daftar rekomendasi (run terbaru untuk tiap produk dan tanggal)")
def list_recommendations(
    product_key: Optional[str] = Query(None, pattern=KEY_PATTERN),
    category: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    model_version: Optional[str] = Query(None, max_length=50),
    pg: dict = Depends(pagination), conn=Depends(db.get_conn),
):
    check_range(date_from, date_to)
    where, params = [], {}
    if model_version:
        params["model_version"] = model_version
    if product_key:
        where.append("r.product_key = %(product_key)s"); params["product_key"] = product_key
    if category:
        where.append("m.category = %(category)s"); params["category"] = category
    if date_from:
        where.append("d.date >= %(date_from)s"); params["date_from"] = date_from
    if date_to:
        where.append("d.date <= %(date_to)s"); params["date_to"] = date_to
    return page_of(conn, rec_from(model_version), where, params, REC_SELECT,
                   "d.date desc, m.product_name", pg)


@recs.get("/{product_key}", response_model=Recommendation, dependencies=[Depends(READ)],
          summary="Rekomendasi satu produk pada satu tanggal")
def get_recommendation(
    product_key: str = Path(pattern=KEY_PATTERN),
    on: date = Query(..., alias="date", description="Tanggal rekomendasi (YYYY-MM-DD)"),
    model_version: Optional[str] = Query(None, max_length=50),
    conn=Depends(db.get_conn),
):
    params = {"product_key": product_key, "on": on}
    if model_version:
        params["model_version"] = model_version
    row = conn.execute(f"select {REC_SELECT} from {rec_from(model_version)} "
                       "where r.product_key = %(product_key)s and d.date = %(on)s", params).fetchone()
    if row is None:
        raise HTTPException(404, "Belum ada rekomendasi untuk produk dan tanggal tersebut")
    return row


_run_lock = threading.Lock()


@recs.post("/run", response_model=RunResult, summary="Jalankan model rekomendasi (khusus admin)")
def run_recommendations(body: RunRequest, user: User = Depends(ADMIN)):
    """Menjalankan model batch untuk semua produk pada `days` tanggal terakhir.
    Menjalankan ulang dengan versi model yang sama akan menimpa baris yang sama."""
    if not _run_lock.acquire(blocking=False):
        raise HTTPException(409, "Run rekomendasi lain masih berjalan")
    try:
        cmd = [sys.executable, str(ROOT / "src" / "recommend.py"), "--days", str(body.days),
               "--undercut", str(body.undercut), "--cost-ratio", str(body.cost_ratio),
               "--min-margin", str(body.min_margin)]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300, cwd=ROOT)
        summary = None
        for line in proc.stdout.splitlines():
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            if obj.get("event") == "run_summary":
                summary = obj
        if proc.returncode != 0 or summary is None:
            log.error(json.dumps({"event": "recommend_run_failed", "code": proc.returncode,
                                  "stdout_tail": proc.stdout[-500:], "stderr_tail": proc.stderr[-500:]}))
            raise HTTPException(502, "Model rekomendasi gagal dijalankan; lihat log server")
        log.info(json.dumps({"event": "recommend_run_triggered", "by": user.username,
                             "run_id": summary["run_id"]}))
        return RunResult(run_id=summary["run_id"], model_version=summary["model_version"],
                         dates=summary["dates"], recommendations=summary["recommendations"],
                         margin_floor_applied=summary["margin_floor_applied"],
                         skipped=summary["skipped"], triggered_by=user.username)
    finally:
        _run_lock.release()


app.include_router(auth)
app.include_router(catalog)
app.include_router(recs)
