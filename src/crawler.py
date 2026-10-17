#!/usr/bin/env python3
"""Crawler harga produk -> file JSONL berformat sama dengan data sampel (siap dimuat oleh load_raw.py).

Prinsip:
  * Sopan dan jujur: baca robots.txt, jeda antar permintaan, identitas (User-Agent) apa adanya
    beserta kontak. Tidak ada proxy berputar, penyamaran, atau upaya menembus proteksi.
  * Bila situs menolak (403/429/halaman tantangan), crawler MENCATAT lalu berhenti untuk platform itu.
  * Tahan perubahan tampilan: selector ada di config/selectors.yml, tiap field punya selector cadangan,
    ada cadangan JSON-LD, validasi Pydantic menandai field hilang/mencurigakan, dan ada ALERT bila
    tingkat keberhasilan parse di bawah ambang.
  * Idempotent: isi baris menentukan payload_hash; menjalankan ulang pada hari yang sama menghasilkan
    file yang sama dan loader membuang duplikatnya.

Kode keluar: 0 = semua platform berhasil, 1 = ada alert/kegagalan, 3 = tidak ada data sama sekali
(semua diblokir/dilarang/tanpa URL).

Contoh:
  python src/crawler.py                                   # semua platform aktif
  python src/crawler.py --platform Tokopedia
  python src/crawler.py --from-html Tokopedia=halaman.html   # uji selector pada halaman yang disimpan
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional
from urllib import robotparser
from urllib.parse import urljoin, urlparse

import yaml
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field, ValidationError

from load_raw import compute_hash  # satu definisi hash untuk crawler dan loader

CRAWLER_VERSION = "crawler-1.0"
ROOT = Path(__file__).resolve().parent.parent
WIB = timezone(timedelta(hours=7))
BLOCK_STATUSES = {403, 429, 503}
BLOCK_MARKERS = ("just a moment", "cf-chl", "captcha", "verify you are human", "access denied",
                 "attention required")


# ----------------------------------------------------------------- logging JSON
class JsonFormatter(logging.Formatter):
    def format(self, record):
        payload = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                   "level": record.levelname, "event": record.getMessage()}
        payload.update(getattr(record, "fields", {}))
        return json.dumps(payload, ensure_ascii=True, default=str)


_h = logging.StreamHandler(sys.stdout)
_h.setFormatter(JsonFormatter())
_log = logging.getLogger("crawler")
_log.handlers = [_h]
_log.setLevel(logging.INFO)


def emit(level, event, **fields):
    _log.log(level, event, extra={"fields": fields})


# ----------------------------------------------------------------- pengambil halaman
@dataclass
class FetchResult:
    url: str
    status: int
    text: str = ""
    error: Optional[str] = None


class RequestsFetcher:
    """HTTP biasa dengan identitas yang jujur."""

    def __init__(self, user_agent: str, timeout: int = 20):
        import requests
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent, "Accept-Language": "id,en;q=0.8"})
        self.timeout = timeout

    def fetch(self, url: str) -> FetchResult:
        try:
            r = self.session.get(url, timeout=self.timeout)
            return FetchResult(url, r.status_code, r.text)
        except Exception as exc:  # noqa: BLE001
            return FetchResult(url, 0, "", error=str(exc)[:200])


class PlaywrightFetcher:
    """Browser asli (Chromium) untuk halaman yang dirender JavaScript. Tanpa plugin stealth.
    BELUM DIUJI di lingkungan pengembangan ini (butuh `playwright install chromium`)."""

    def __init__(self, user_agent: str, timeout: int = 20):
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=True)
        self._ctx = self._browser.new_context(user_agent=user_agent)
        self.timeout = timeout * 1000

    def fetch(self, url: str) -> FetchResult:
        try:
            page = self._ctx.new_page()
            resp = page.goto(url, timeout=self.timeout, wait_until="networkidle")
            html = page.content()
            status = resp.status if resp else 0
            page.close()
            return FetchResult(url, status, html)
        except Exception as exc:  # noqa: BLE001
            return FetchResult(url, 0, "", error=str(exc)[:200])

    def close(self):
        self._browser.close()
        self._pw.stop()


class FileFetcher:
    """Membaca halaman yang sudah disimpan di disk (untuk menguji selector tanpa menghubungi situs)."""

    def __init__(self, path: Path):
        self.path = Path(path)

    def fetch(self, url: str) -> FetchResult:
        return FetchResult(url, 200, self.path.read_text(encoding="utf-8", errors="replace"))


# ----------------------------------------------------------------- deteksi blokir dan robots
def detect_block(res: FetchResult) -> Optional[str]:
    if res.status in BLOCK_STATUSES:
        return f"http_{res.status}"
    low = res.text[:6000].lower()
    for marker in BLOCK_MARKERS:
        if marker in low and len(res.text) < 120_000:
            return f"challenge_page:{marker}"
    return None


def robots_decision(fetcher, url: str, user_agent: str) -> tuple[str, Optional[float]]:
    """Kembalikan (keputusan, crawl_delay). keputusan: allowed | disallowed | unverifiable."""
    p = urlparse(url)
    robots_url = f"{p.scheme}://{p.netloc}/robots.txt"
    res = fetcher.fetch(robots_url)
    if res.status == 404:
        return "allowed", None                    # tidak ada robots.txt = tidak ada larangan
    if res.status != 200 or detect_block(res):
        return "unverifiable", None               # tidak bisa memastikan -> jangan crawl
    rp = robotparser.RobotFileParser()
    rp.parse(res.text.splitlines())
    if not rp.can_fetch(user_agent, url):
        return "disallowed", None
    return "allowed", rp.crawl_delay(user_agent)


# ----------------------------------------------------------------- ekstraksi
class ScrapedProduct(BaseModel):
    """Skema hasil crawl. Nama wajib; harga boleh kosong tetapi akan dihitung sebagai kegagalan parse."""
    platform: str
    source_url: str
    product_name: str = Field(min_length=1)
    price: Optional[str] = None
    original_price: Optional[str] = None
    discount: Optional[str] = None
    detail: Optional[str] = None
    breadcrumb: Optional[str] = None


def clean(text: Optional[str]) -> Optional[str]:
    if text is None:
        return None
    t = " ".join(text.split())
    return t or None


def first_text(node, selectors: list[str]) -> tuple[Optional[str], Optional[int]]:
    for i, sel in enumerate(selectors):
        try:
            el = node.select_one(sel)
        except Exception:  # noqa: BLE001 - selector tidak valid: lewati
            continue
        if el:
            t = clean(el.get_text(" ", strip=True))
            if t:
                return t, i
    return None, None


def first_href(node, selectors: list[str]) -> Optional[str]:
    for sel in selectors:
        try:
            el = node.select_one(sel)
        except Exception:  # noqa: BLE001
            continue
        if el and el.get("href"):
            return el["href"]
    return None


def digits(text: Optional[str]) -> Optional[int]:
    d = re.sub(r"\D", "", text or "")
    return int(d) if d else None


def extract_json_ld(soup: BeautifulSoup, page_url: str) -> list[dict]:
    items = []
    for tag in soup.find_all("script", {"type": "application/ld+json"}):
        try:
            data = json.loads(tag.string or "")
        except ValueError:
            continue
        stack = data if isinstance(data, list) else [data]
        while stack:
            d = stack.pop()
            if isinstance(d, dict):
                if "@graph" in d:
                    stack.extend(d["@graph"])
                if d.get("@type") == "Product" and d.get("name"):
                    offers = d.get("offers") or {}
                    if isinstance(offers, list):
                        offers = offers[0] if offers else {}
                    price = offers.get("price") if isinstance(offers, dict) else None
                    items.append({"name": clean(str(d["name"])),
                                  "price": clean(str(price)) if price is not None else None,
                                  "url": urljoin(page_url, d.get("url") or ""),
                                  "detail": clean(d.get("description"))})
    return items


@dataclass
class PageStats:
    cards: int = 0
    ok: int = 0
    failed: int = 0
    card_selector_index: Optional[int] = None
    fallback_fields: dict = field(default_factory=dict)
    flags: dict = field(default_factory=dict)
    used_json_ld: bool = False


def suspicious_flags(p: ScrapedProduct) -> list[str]:
    flags = []
    price, orig = digits(p.price), digits(p.original_price)
    if price is None:
        flags.append("price_missing")
    elif price == 0:
        flags.append("price_not_positive")
    if orig is not None and price is not None and price > orig:
        flags.append("price_gt_original")
    if p.discount:
        m = re.search(r"-?\d+", p.discount)
        if not m or not (0 <= int(m.group()) <= 100):
            flags.append("discount_out_of_range")
    return flags


def parse_page(html: str, page_url: str, platform: str, cfg: dict) -> tuple[list[ScrapedProduct], PageStats]:
    soup = BeautifulSoup(html, "html.parser")
    sel = cfg["selectors"]
    stats = PageStats()
    products: list[ScrapedProduct] = []

    cards, idx = [], None
    for i, s in enumerate(sel["card"]):
        try:
            cards = soup.select(s)
        except Exception:  # noqa: BLE001
            cards = []
        if cards:
            idx = i
            break
    stats.card_selector_index = idx
    stats.cards = len(cards)

    for n, card in enumerate(cards):
        name, ni = first_text(card, sel["name"])
        price, pi = first_text(card, sel["price"])
        orig, _ = first_text(card, sel["original_price"])
        disc, _ = first_text(card, sel["discount"])
        detail, _ = first_text(card, sel.get("detail", []))
        crumb, _ = first_text(card, sel.get("breadcrumb", []))
        href = first_href(card, sel["link"])
        for fname, i in (("name", ni), ("price", pi)):
            if i is not None and i > 0:
                stats.fallback_fields[fname] = max(stats.fallback_fields.get(fname, 0), i)
        url = urljoin(page_url, href) if href else f"{page_url}#item-{n}"
        try:
            p = ScrapedProduct(platform=platform, source_url=url, product_name=name or "",
                               price=price, original_price=orig, discount=disc,
                               detail=detail, breadcrumb=crumb)
        except ValidationError:
            stats.failed += 1
            continue
        for fl in suspicious_flags(p):
            stats.flags[fl] = stats.flags.get(fl, 0) + 1
        if digits(p.price) is None:
            stats.failed += 1          # tanpa harga = gagal parse
            continue
        stats.ok += 1
        products.append(p)

    if not cards and cfg.get("json_ld_fallback"):
        for item in extract_json_ld(soup, page_url):
            stats.cards += 1
            try:
                p = ScrapedProduct(platform=platform, source_url=item["url"] or f"{page_url}#ld-{stats.cards}",
                                   product_name=item["name"] or "", price=item["price"], detail=item["detail"])
            except ValidationError:
                stats.failed += 1
                continue
            if digits(p.price) is None:
                stats.failed += 1
                continue
            stats.used_json_ld = True
            stats.ok += 1
            products.append(p)
    return products, stats


def to_record(p: ScrapedProduct, now: datetime) -> dict:
    rec = {"platform": p.platform, "source_url": p.source_url, "crawled_at": now.isoformat(),
           "crawler_version": CRAWLER_VERSION, "data_source": "live", "product_name": p.product_name,
           "price": p.price, "original_price": p.original_price, "discount": p.discount,
           "detail": p.detail, "breadcrumb": p.breadcrumb}
    rec["payload_hash"] = compute_hash(rec)
    return rec


# ----------------------------------------------------------------- crawl satu platform
@dataclass
class PlatformResult:
    platform: str
    status: str            # ok | below_threshold | blocked | robots_disallowed | robots_unverifiable | no_start_urls | error
    cards: int = 0
    ok: int = 0
    rate: float = 0.0
    rows: int = 0
    detail: str = ""


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def crawl_platform(name: str, cfg: dict, defaults: dict, fetcher, out_dir: Path, now: datetime,
                   user_agent: str, sleeper: Callable[[float], None] = time.sleep,
                   check_robots: bool = True) -> PlatformResult:
    urls = cfg.get("start_urls") or []
    if not urls:
        emit(logging.WARNING, "no_start_urls", platform=name,
             hint="Isi start_urls di config/selectors.yml dari dokumen soal")
        return PlatformResult(name, "no_start_urls")

    delay = float(defaults.get("min_delay_seconds", 3))
    max_pages = int(defaults.get("max_pages", 3))
    threshold = float(defaults.get("parse_success_threshold", 0.90))

    if check_robots:
        decision, crawl_delay = robots_decision(fetcher, urls[0], user_agent)
        emit(logging.INFO, "robots_checked", platform=name, decision=decision, crawl_delay=crawl_delay)
        if decision != "allowed":
            status = "robots_disallowed" if decision == "disallowed" else "robots_unverifiable"
            return PlatformResult(name, status, detail="robots.txt")
        if crawl_delay:
            delay = max(delay, float(crawl_delay))

    records: dict[str, dict] = {}
    tot_cards = tot_ok = 0
    for n, url in enumerate(urls[:max_pages]):
        if n > 0:
            sleeper(delay)
        t0 = time.time()
        res = fetcher.fetch(url)
        emit(logging.INFO, "fetch", platform=name, url=url, status=res.status,
             ms=round((time.time() - t0) * 1000), error=res.error)
        reason = detect_block(res)
        if res.status == 0 or reason:
            if reason:
                emit(logging.ERROR, "site_blocked", platform=name, url=url, reason=reason,
                     action="berhenti untuk platform ini; tidak ada upaya menyiasati")
                return PlatformResult(name, "blocked", tot_cards, tot_ok, detail=reason)
            return PlatformResult(name, "error", tot_cards, tot_ok, detail=res.error or "fetch gagal")
        products, st = parse_page(res.text, url, name, cfg)
        emit(logging.INFO, "page_parsed", platform=name, url=url, cards=st.cards, ok=st.ok, failed=st.failed,
             card_selector_index=st.card_selector_index, json_ld=st.used_json_ld, flags=st.flags)
        for fname, i in st.fallback_fields.items():
            emit(logging.WARNING, "selector_fallback_used", platform=name, field=fname, selector_index=i,
                 hint="Selector utama tidak cocok; periksa config/selectors.yml")
        if st.card_selector_index and st.card_selector_index > 0:
            emit(logging.WARNING, "selector_fallback_used", platform=name, field="card",
                 selector_index=st.card_selector_index)
        tot_cards += st.cards
        tot_ok += st.ok
        for p in products:
            rec = to_record(p, now)
            records.setdefault(rec["source_url"], rec)

    rate = (tot_ok / tot_cards) if tot_cards else 0.0
    path = out_dir / f"live_{now.date().isoformat()}_{slug(name)}.jsonl"
    if records:  # jangan menulis file kosong yang bisa menimpa hasil baik sebelumnya
        out_dir.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            for rec in records.values():
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    status = "ok"
    if rate < threshold:
        status = "below_threshold"
        emit(logging.ERROR, "ALERT_parse_success_rate_below_threshold", platform=name,
             rate=round(rate, 4), threshold=threshold, cards=tot_cards, parsed_ok=tot_ok,
             hint="Kemungkinan tampilan situs berubah atau diblokir; periksa selector")
    emit(logging.INFO, "platform_done", platform=name, status=status, cards=tot_cards, parsed_ok=tot_ok,
         rate=round(rate, 4), rows=len(records), file=str(path))
    return PlatformResult(name, status, tot_cards, tot_ok, rate, len(records))


def exit_code(results: list[PlatformResult]) -> int:
    if not any(r.rows > 0 for r in results):
        return 3
    return 0 if all(r.status == "ok" for r in results) else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="Crawler harga (sopan, tanpa menyiasati proteksi)")
    ap.add_argument("--config", default=os.environ.get("CRAWLER_CONFIG") or str(ROOT / "config" / "selectors.yml"))
    ap.add_argument("--platform", action="append", help="batasi ke platform tertentu (boleh diulang)")
    ap.add_argument("--output-dir", default=str(ROOT / "data" / "live"))
    ap.add_argument("--from-html", action="append", metavar="PLATFORM=FILE",
                    help="parse halaman yang disimpan di disk, tanpa menghubungi situs")
    args = ap.parse_args()

    cfg = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    defaults, platforms = cfg.get("defaults", {}), cfg["platforms"]
    now = datetime.now(WIB).replace(microsecond=0)
    out_dir = Path(args.output_dir)
    results: list[PlatformResult] = []
    emit(logging.INFO, "crawl_start", crawler_version=CRAWLER_VERSION, offline=bool(args.from_html))

    if args.from_html:  # mode offline: uji selector pada halaman tersimpan
        for item in args.from_html:
            pname, _, file = item.partition("=")
            if pname not in platforms or not file:
                emit(logging.ERROR, "bad_from_html", item=item)
                return 1
            pc = {**platforms[pname], "start_urls": [f"file://{file}"]}
            results.append(crawl_platform(pname, pc, defaults, FileFetcher(Path(file)), out_dir, now,
                                          "offline", check_robots=False))
    else:
        contact = os.environ.get("CRAWLER_CONTACT", "").strip()
        if not contact:
            emit(logging.ERROR, "contact_required",
                 hint="Isi CRAWLER_CONTACT (email atau URL) di .env agar identitas crawler jujur")
            return 1
        ua = os.environ.get("CRAWLER_USER_AGENT") or f"PriceResearchBot/1.0 (+{contact})"
        fetchers: dict = {}
        for pname, pcfg in platforms.items():
            if not pcfg.get("enabled", True) or (args.platform and pname not in args.platform):
                continue
            kind = pcfg.get("renderer", "requests")
            if kind not in fetchers:
                try:
                    fetchers[kind] = (PlaywrightFetcher if kind == "playwright" else RequestsFetcher)(
                        ua, int(defaults.get("request_timeout_seconds", 20)))
                except Exception as exc:  # noqa: BLE001
                    emit(logging.ERROR, "fetcher_unavailable", renderer=kind, error=str(exc)[:200])
                    results.append(PlatformResult(pname, "error", detail=f"renderer {kind} tidak tersedia"))
                    continue
            results.append(crawl_platform(pname, pcfg, defaults, fetchers[kind], out_dir, now, ua))
        for f in fetchers.values():
            if hasattr(f, "close"):
                f.close()

    code = exit_code(results)
    emit(logging.INFO, "crawl_summary", exit_code=code,
         platforms={r.platform: {"status": r.status, "rows": r.rows, "rate": round(r.rate, 4)} for r in results})
    return code


if __name__ == "__main__":
    sys.exit(main())
