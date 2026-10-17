"""Tes crawler memakai halaman contoh (tanpa menghubungi situs mana pun)."""
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

import crawler
from crawler import FetchResult
from load_raw import RawRecord, suspicious_flags as loader_flags

FIX = Path(__file__).parent / "fixtures"
CFG = yaml.safe_load((Path(__file__).resolve().parent.parent / "config" / "selectors.yml").read_text(encoding="utf-8"))
DEFAULTS = {**CFG["defaults"], "max_pages": 3, "min_delay_seconds": 3}
NOW = datetime(2026, 10, 17, 9, 0, 0, tzinfo=timezone(timedelta(hours=7)))
UA = "TestBot/1.0 (+test@example.com)"
BASE = "https://shop.example"


@pytest.fixture(autouse=True)
def _capture_crawler_logs(caplog):
    caplog.set_level(logging.INFO, logger="crawler")


def page(name):
    return (FIX / name).read_text(encoding="utf-8")


def tokopedia_cfg(urls):
    return {**CFG["platforms"]["Tokopedia"], "start_urls": urls}


class FakeFetcher:
    def __init__(self, pages=None, robots=None):
        self.pages = pages or {}
        self.robots = robots if robots is not None else FetchResult(f"{BASE}/robots.txt", 404, "")
        self.calls = []

    def fetch(self, url):
        self.calls.append(url)
        if url.endswith("/robots.txt"):
            return self.robots
        return self.pages.get(url, FetchResult(url, 404, ""))


def events(caplog):
    return [{"event": r.getMessage(), **getattr(r, "fields", {})}
            for r in caplog.records if r.name == "crawler"]


def run(fetcher, urls, tmp_path, sleeper=lambda s: None, defaults=None):
    return crawler.crawl_platform("Tokopedia", tokopedia_cfg(urls), defaults or DEFAULTS, fetcher,
                                  tmp_path, NOW, UA, sleeper=sleeper)


# ---- ekstraksi dan validasi
def test_primary_selectors_and_missing_price_counts_as_failure():
    prods, st = crawler.parse_page(page("primary_layout.html"), BASE + "/s", "Tokopedia", tokopedia_cfg([]))
    assert (st.cards, st.ok, st.failed) == (4, 3, 1)       # kartu keempat tanpa harga = gagal parse
    assert st.card_selector_index == 0 and not st.fallback_fields
    first = prods[0]
    assert first.price == "Rp14.500" and first.original_price == "Rp16.000" and first.discount == "9%"
    assert first.source_url == BASE + "/p/bango-kecap-520"


def test_fallback_selectors_survive_layout_change():
    prods, st = crawler.parse_page(page("changed_layout.html"), BASE + "/s", "Tokopedia", tokopedia_cfg([]))
    assert (st.cards, st.ok, st.failed) == (4, 4, 0)
    assert st.card_selector_index > 0                        # selector utama gagal, cadangan dipakai
    assert st.fallback_fields["name"] > 0 and st.fallback_fields["price"] > 0


def test_json_ld_fallback_when_no_cards():
    prods, st = crawler.parse_page(page("jsonld_only.html"), BASE + "/s", "Tokopedia", tokopedia_cfg([]))
    assert st.used_json_ld and st.ok == 2
    assert {p.product_name for p in prods} == {"Bango Kecap Manis Refill 520 ml", "Sunsilk Shampoo Black Shine 340 ml"}


def test_suspicious_values_are_flagged():
    p = crawler.ScrapedProduct(platform="X", source_url="u", product_name="n", price="Rp 20.000",
                               original_price="Rp 10.000", discount="150%")
    assert set(crawler.suspicious_flags(p)) == {"price_gt_original", "discount_out_of_range"}
    assert crawler.suspicious_flags(crawler.ScrapedProduct(platform="X", source_url="u", product_name="n")) == ["price_missing"]


# ---- alert, blokir, robots
def test_parse_rate_below_threshold_raises_alert(caplog, tmp_path):
    f = FakeFetcher({BASE + "/s": FetchResult(BASE + "/s", 200, page("broken_layout.html"))})
    res = run(f, [BASE + "/s"], tmp_path)
    assert res.status == "below_threshold" and res.rate == 0.0
    assert any(e["event"] == "ALERT_parse_success_rate_below_threshold" for e in events(caplog))
    assert not list(tmp_path.glob("*.jsonl"))                # tidak menulis file kosong


def test_partial_failure_also_alerts(caplog, tmp_path):
    f = FakeFetcher({BASE + "/s": FetchResult(BASE + "/s", 200, page("primary_layout.html"))})
    res = run(f, [BASE + "/s"], tmp_path)                    # 3 dari 4 = 75% < 90%
    assert res.status == "below_threshold" and res.rows == 3
    assert any(e["event"] == "ALERT_parse_success_rate_below_threshold" for e in events(caplog))


def test_blocked_site_stops_without_retry(caplog, tmp_path):
    f = FakeFetcher({BASE + "/s": FetchResult(BASE + "/s", 403, page("blocked_challenge.html"))})
    res = run(f, [BASE + "/s", BASE + "/s2"], tmp_path)
    assert res.status == "blocked"
    assert f.calls == [BASE + "/robots.txt", BASE + "/s"]    # satu permintaan halaman, tanpa percobaan ulang
    assert any(e["event"] == "site_blocked" for e in events(caplog))
    assert not list(tmp_path.glob("*.jsonl"))


def test_challenge_page_detected_even_with_status_200():
    assert crawler.detect_block(FetchResult("u", 200, page("blocked_challenge.html"))).startswith("challenge_page")
    assert crawler.detect_block(FetchResult("u", 200, page("changed_layout.html"))) is None
    assert crawler.detect_block(FetchResult("u", 429, "")) == "http_429"


def test_robots_disallow_means_no_page_request(tmp_path):
    f = FakeFetcher(robots=FetchResult(f"{BASE}/robots.txt", 200, "User-agent: *\nDisallow: /"))
    res = run(f, [BASE + "/s"], tmp_path)
    assert res.status == "robots_disallowed" and f.calls == [BASE + "/robots.txt"]


def test_unverifiable_robots_means_no_crawl(tmp_path):
    f = FakeFetcher(robots=FetchResult(f"{BASE}/robots.txt", 403, "denied"))
    res = run(f, [BASE + "/s"], tmp_path)
    assert res.status == "robots_unverifiable" and f.calls == [BASE + "/robots.txt"]


def test_no_start_urls(tmp_path):
    assert run(FakeFetcher(), [], tmp_path).status == "no_start_urls"


# ---- kesopanan dan idempotency
def test_delay_between_pages_and_page_cap(tmp_path):
    urls = [f"{BASE}/p{i}" for i in range(5)]
    f = FakeFetcher({u: FetchResult(u, 200, page("changed_layout.html")) for u in urls})
    sleeps = []
    run(f, urls, tmp_path, sleeper=sleeps.append)
    assert len([c for c in f.calls if not c.endswith("robots.txt")]) == 3     # max_pages = 3
    assert sleeps == [3.0, 3.0]                                                # jeda antar halaman


def test_output_is_idempotent_and_compatible_with_loader(tmp_path):
    f = FakeFetcher({BASE + "/s": FetchResult(BASE + "/s", 200, page("changed_layout.html"))})
    run(f, [BASE + "/s"], tmp_path)
    file = next(tmp_path.glob("*.jsonl"))
    first = file.read_text(encoding="utf-8")
    run(f, [BASE + "/s"], tmp_path)
    assert file.read_text(encoding="utf-8") == first                           # jalankan ulang = isi sama
    for line in first.splitlines():
        raw = json.loads(line)
        rec = RawRecord.model_validate(raw)                                    # lolos skema loader
        assert rec.data_source == "live"
        assert "payload_hash_mismatch" not in loader_flags(rec, raw)           # hash cocok dengan loader


def test_exit_codes():
    R = crawler.PlatformResult
    assert crawler.exit_code([R("a", "ok", rows=3), R("b", "ok", rows=2)]) == 0
    assert crawler.exit_code([R("a", "ok", rows=3), R("b", "blocked")]) == 1
    assert crawler.exit_code([R("a", "blocked"), R("b", "robots_disallowed")]) == 3


# ---- jalur CLI
def test_contact_required_for_live_mode(monkeypatch, caplog):
    monkeypatch.delenv("CRAWLER_CONTACT", raising=False)
    monkeypatch.setattr("sys.argv", ["crawler.py"])
    assert crawler.main() == 1
    assert any(e["event"] == "contact_required" for e in events(caplog))


def test_offline_from_html_mode(monkeypatch, tmp_path, caplog):
    monkeypatch.setattr("sys.argv", ["crawler.py", "--from-html", f"Tokopedia={FIX / 'changed_layout.html'}",
                                     "--output-dir", str(tmp_path)])
    assert crawler.main() == 0
    out = next(tmp_path.glob("*.jsonl")).read_text(encoding="utf-8").splitlines()
    assert len(out) == 4
