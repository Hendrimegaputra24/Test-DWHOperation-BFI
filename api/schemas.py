"""Model data (validasi masukan dan bentuk keluaran) untuk OpenAPI."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Generic, Literal, Optional, TypeVar

from pydantic import BaseModel, Field

Platform = Literal["Klik Indomaret", "Blibli", "Tokopedia"]
T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    total: int = Field(description="Jumlah seluruh baris yang cocok dengan filter")
    limit: int
    offset: int
    items: list[T]


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Masa berlaku token dalam detik")
    role: str


class Product(BaseModel):
    product_key: str
    product_name: str
    brand: str
    category: str
    pack_size: str
    n_platforms: int
    first_seen_date: date


class PriceRecord(BaseModel):
    price_date: date
    product_key: str
    product_name: str
    brand: str
    category: str
    platform: str
    price_idr: float
    original_price_idr: float
    discount_pct: float
    is_discounted: bool
    data_source: str
    last_crawled_at: datetime


class Recommendation(BaseModel):
    recommendation_date: date
    product_key: str
    product_name: str
    competitor_count: int
    competitor_median_price_idr: float
    competitor_min_price_idr: float
    price_floor_idr: float
    recommended_price_idr: float
    rule_applied: str
    model_version: str
    run_id: str
    run_ts: datetime
    parameters: Optional[dict[str, Any]] = None


class RunRequest(BaseModel):
    days: int = Field(1, ge=1, le=31, description="Jumlah tanggal terakhir yang diproses")
    undercut: float = Field(0.02, ge=0, le=0.5, description="Potongan dari median kompetitor (0,02 = 2%)")
    cost_ratio: float = Field(0.80, gt=0, le=1.5, description="ASUMSI biaya sebagai bagian dari harga tercatat")
    min_margin: float = Field(0.10, ge=0, le=1, description="Margin minimum di atas biaya")


class RunResult(BaseModel):
    run_id: str
    model_version: str
    dates: int
    recommendations: int
    margin_floor_applied: int
    skipped: int
    triggered_by: str
