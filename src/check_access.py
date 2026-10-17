#!/usr/bin/env python3
"""Uji akses situs sumber dan buat laporan bukti (Markdown + JSON + salinan respons).

Tujuan: mendokumentasikan, secara jujur dan bisa diulang, apa yang terjadi ketika program (bukan manusia)
meminta halaman situs sumber. Skrip ini TIDAK menyamar, tidak memakai proxy, dan tidak mencoba menembus
proteksi apa pun. Ia hanya melakukan sedikit permintaan GET biasa dengan identitas yang jujur, lalu mencatat
hasilnya: kode status, header, apakah halaman tantangan, dan apakah ada data produk.

Yang DAPAT dibuktikan: apa yang dijawab situs terhadap permintaan otomatis dari komputer ini pada waktu ini.
Yang TIDAK dapat dibuktikan: bahwa situs tidak bisa dibuka manusia, atau bahwa penolakan berlaku untuk
semua jaringan dan waktu. Laporan menuliskan batasan ini.

Contoh:
  python src/check_access.py --label wifi-rumah
  python src/check_access.py --label hotspot-hp --attempts 2
  python src/check_access.py --url "Tokopedia=https://www.tokopedia.com/unilever"
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform as pyplatform
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional
from urllib import robotparser
from urllib.parse import urlparse

import yaml

from crawler import FetchResult, detect_block, parse_page

ROOT = Path(__file__).resolve().parent.parent
WIB = timezone(timedelta(hours=7))
HOMEPAGES = {
    "Klik Indomaret": "https://www.klikindomaret.com/",
    "Blibli": "https://www.blibli.com/",
    "Tokopedia": "https://www.tokopedia.com/",
}
KEEP_HEADERS = ("server", "cf-ray", "cf-mitigated", "content-type", "retry-after", "location", "via")
MAX_SAVED_BYTES = 300_000


def load_env_file(path: Path) -> None:
    """Baca .env sederhana (KEY=VALUE); nilai yang sudah ada di environment tidak ditimpa."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def title_of(html: str) -> Optional[str]:
    m = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.I | re.S)
    return " ".join(m.group(1).split())[:200] if m else None


def classify(rec: dict) -> str:
    if rec.get("error_type"):
        return "CONNECTION_ERROR"
    reason = rec.get("block_reason") or ""
    if reason.startswith("challenge_page"):
        return "CHALLENGE_PAGE"
    if reason.startswith("http_"):
        return "REFUSED_" + reason.split("_", 1)[1]
    status = rec.get("status")
    if status == 200 and rec.get("product_cards", 0) > 0:
        return "OPEN_WITH_PRODUCTS"
    if status == 200:
        return "OPEN_NO_PRODUCT_DATA"
    return f"HTTP_{status}"


def probe(session, name: str, url: str, timeout: int, platform_cfg: Optional[dict], save_dir: Path,
          tag: str) -> dict:
    now = datetime.now(timezone.utc)
    rec = {"platform": name, "url": url, "started_at_utc": now.isoformat(timespec="seconds"),
           "started_at_wib": now.astimezone(WIB).isoformat(timespec="seconds")}
    t0 = time.time()
    try:
        r = session.get(url, timeout=timeout, allow_redirects=True)
        rec.update(status=r.status_code, final_url=r.url, redirects=len(r.history),
                   elapsed_ms=round((time.time() - t0) * 1000),
                   headers={k: v for k, v in r.headers.items() if k.lower() in KEEP_HEADERS})
        text = r.text or ""
    except Exception as exc:  # noqa: BLE001 - semua kegagalan jaringan adalah data bukti
        rec.update(status=None, error_type=type(exc).__name__, error_message=str(exc)[:300],
                   elapsed_ms=round((time.time() - t0) * 1000))
        text = ""
    rec["bytes"] = len(text.encode("utf-8", errors="replace"))
    rec["sha256"] = sha256(text) if text else None
    rec["title"] = title_of(text) if text else None
    rec["price_mentions"] = len(re.findall(r"Rp\s?\d", text))
    h = {k.lower(): v for k, v in rec.get("headers", {}).items()}
    rec["cloudflare_headers"] = "cloudflare" in h.get("server", "").lower() or "cf-ray" in h
    block = detect_block(FetchResult(url, rec.get("status") or 0, text))
    rec["block_reason"] = block
    cards = 0
    if text and platform_cfg and not block:
        try:
            _, st = parse_page(text, url, name, platform_cfg)
            cards = st.cards
        except Exception:  # noqa: BLE001
            cards = 0
    rec["product_cards"] = cards
    rec["verdict"] = classify(rec)
    if text:
        fname = f"{tag}.html"
        (save_dir / fname).write_text(text[:MAX_SAVED_BYTES], encoding="utf-8", errors="replace")
        rec["saved_response"] = f"responses/{fname}"
    return rec


def robots_info(session, name: str, url: str, ua: str, timeout: int, save_dir: Path) -> dict:
    p = urlparse(url)
    robots_url = f"{p.scheme}://{p.netloc}/robots.txt"
    info = {"platform": name, "robots_url": robots_url}
    try:
        r = session.get(robots_url, timeout=timeout)
        info.update(status=r.status_code, bytes=len(r.text), block_reason=detect_block(
            FetchResult(robots_url, r.status_code, r.text)))
        if r.status_code == 200 and not info["block_reason"]:
            (save_dir / f"robots_{re.sub(r'[^a-z0-9]+', '_', name.lower())}.txt").write_text(
                r.text[:MAX_SAVED_BYTES], encoding="utf-8", errors="replace")
            rp = robotparser.RobotFileParser()
            rp.parse(r.text.splitlines())
            info["parser"] = rp
        else:
            info["parser"] = None
    except Exception as exc:  # noqa: BLE001
        info.update(status=None, error_type=type(exc).__name__, error_message=str(exc)[:200], parser=None)
    return info


def build_targets(cfg: Optional[dict], extra: list[str]) -> list[tuple[str, str]]:
    targets: list[tuple[str, str]] = [(n, u) for n, u in HOMEPAGES.items()]
    if cfg:
        for n, pc in cfg.get("platforms", {}).items():
            for u in pc.get("start_urls") or []:
                targets.append((n, u))
    for item in extra:
        n, _, u = item.partition("=")
        if n and u:
            targets.append((n.strip(), u.strip()))
    seen, out = set(), []
    for t in targets:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def run_check(targets: list[tuple[str, str]], ua: str, attempts: int, delay: float, timeout: int,
              out_dir: Path, label: str, cfg: Optional[dict] = None,
              sleeper: Callable[[float], None] = time.sleep, session=None) -> dict:
    import requests
    session = session or requests.Session()
    session.headers.update({"User-Agent": ua, "Accept-Language": "id,en;q=0.8"})
    (out_dir / "responses").mkdir(parents=True, exist_ok=True)
    resp_dir = out_dir / "responses"

    robots: dict[str, dict] = {}
    results: list[dict] = []
    skipped: list[dict] = []
    for name, url in targets:
        host = urlparse(url).netloc
        if host not in robots:
            robots[host] = robots_info(session, name, url, ua, timeout, out_dir)
        rp = robots[host].get("parser")
        if rp is not None and not rp.can_fetch(ua, url):
            skipped.append({"platform": name, "url": url, "reason": "dilarang oleh robots.txt"})
            continue
        pcfg = (cfg or {}).get("platforms", {}).get(name)
        for n in range(1, attempts + 1):
            if results or n > 1:
                sleeper(delay)
            tag = f"{re.sub(r'[^a-z0-9]+', '_', name.lower())}_{len(results) + 1:02d}"
            results.append(probe(session, name, url, timeout, pcfg, resp_dir, tag) | {"attempt": n})

    per_platform: dict[str, dict] = {}
    for r in results:
        d = per_platform.setdefault(r["platform"], {"verdicts": [], "cloudflare": False})
        d["verdicts"].append(r["verdict"])
        d["cloudflare"] = d["cloudflare"] or r["cloudflare_headers"]
    for d in per_platform.values():
        uniq = sorted(set(d["verdicts"]))
        d["verdict"] = uniq[0] if len(uniq) == 1 else "MIXED"
        d["distinct"] = uniq

    data = {
        "label": label, "user_agent": ua, "attempts": attempts, "delay_seconds": delay,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "generated_at_wib": datetime.now(WIB).isoformat(timespec="seconds"),
        "environment": {"python": sys.version.split()[0], "os": pyplatform.platform(),
                        "requests": requests.__version__},
        "robots": [{k: v for k, v in info.items() if k != "parser"} for info in robots.values()],
        "skipped": skipped, "results": results, "per_platform": per_platform,
    }
    (out_dir / "results.json").write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    data["results_sha256"] = sha256((out_dir / "results.json").read_text(encoding="utf-8"))
    (out_dir / "report.md").write_text(render_report(data), encoding="utf-8")
    return data


EXPLAIN = {
    "OPEN_WITH_PRODUCTS": "Halaman terbuka dan memuat data produk. Crawling mungkin dilakukan.",
    "OPEN_NO_PRODUCT_DATA": "Halaman terbuka (200) tetapi tidak berisi data produk yang dapat dibaca. Biasanya halaman kerangka yang mengisi produk lewat JavaScript atau API terpisah.",
    "CHALLENGE_PAGE": "Situs menjawab halaman tantangan (mis. verifikasi manusia) alih-alih konten.",
    "CONNECTION_ERROR": "Koneksi gagal sebelum ada jawaban HTTP (galat jaringan, TLS, atau koneksi ditutup).",
    "MIXED": "Hasil berbeda antar percobaan; lihat tabel per percobaan.",
}


def explain(verdict: str) -> str:
    if verdict.startswith("REFUSED_"):
        return f"Server menolak permintaan otomatis dengan kode HTTP {verdict.split('_', 1)[1]}."
    return EXPLAIN.get(verdict, "Lihat rincian.")


def render_report(d: dict) -> str:
    L = []
    L.append(f"# Laporan Uji Akses Situs Sumber\n")
    L.append(f"- Label pengujian: **{d['label'] or '(tanpa label)'}**")
    L.append(f"- Waktu pembuatan: {d['generated_at_wib']} (WIB) / {d['generated_at_utc']} (UTC)")
    L.append(f"- Identitas (User-Agent): `{d['user_agent']}`")
    L.append(f"- Percobaan per URL: {d['attempts']}, jeda {d['delay_seconds']} detik")
    e = d["environment"]
    L.append(f"- Lingkungan: Python {e['python']}, {e['os']}, requests {e['requests']}")
    L.append(f"- SHA-256 `results.json`: `{d['results_sha256']}`\n")
    L.append("## Cara pengujian\n")
    L.append("Skrip `src/check_access.py` mengirim sedikit permintaan GET biasa ke URL di bawah dengan identitas yang "
             "jujur (tanpa penyamaran, tanpa proxy, tanpa upaya menembus proteksi), memeriksa `robots.txt`, memberi jeda "
             "antar permintaan, dan mencatat apa yang dijawab situs. Respons disimpan di folder `responses/`.\n")
    L.append("## Kesimpulan per platform\n")
    L.append("| Platform | Hasil | Header Cloudflare terlihat | Penjelasan |\n|---|---|---|---|")
    for name, p in d["per_platform"].items():
        L.append(f"| {name} | `{p['verdict']}` | {'ya' if p['cloudflare'] else 'tidak'} | {explain(p['verdict'])} |")
    L.append("")
    L.append("## Rincian setiap percobaan\n")
    L.append("| Platform | URL | Ke- | Status | Hasil | Judul halaman | Kartu produk | Ukuran (byte) | ms |\n|---|---|---|---|---|---|---|---|---|")
    for r in d["results"]:
        status = r.get("status") if r.get("status") is not None else f"galat: {r.get('error_type')}"
        L.append(f"| {r['platform']} | {r['url']} | {r['attempt']} | {status} | `{r['verdict']}` | "
                 f"{(r.get('title') or '-').replace('|', '/')} | {r['product_cards']} | {r['bytes']} | {r['elapsed_ms']} |")
    L.append("")
    L.append("## robots.txt\n")
    L.append("| Platform | Status | Catatan |\n|---|---|---|")
    for rb in d["robots"]:
        note = rb.get("block_reason") or rb.get("error_type") or ("dibaca" if rb.get("status") == 200 else "tidak tersedia")
        L.append(f"| {rb['platform']} | {rb.get('status', '-')} | {note} |")
    if d["skipped"]:
        L.append("\nURL yang dilewati karena `robots.txt`:")
        for s in d["skipped"]:
            L.append(f"- {s['platform']}: {s['url']}")
    L.append("\n## Yang dibuktikan dan yang tidak\n")
    L.append("**Dibuktikan:** pada waktu dan jaringan di atas, permintaan otomatis dari komputer ini dijawab seperti "
             "tertulis pada tabel (kode status, header, dan salinan respons tersimpan, lengkap dengan hash).\n")
    L.append("**Tidak dibuktikan:**\n"
             "- bahwa situs tidak dapat dibuka oleh manusia di browser (halaman yang sama bisa terbuka normal);\n"
             "- bahwa penolakan berlaku di semua jaringan, perangkat, dan waktu;\n"
             "- penyebab pastinya (proteksi anti-bot, aturan jaringan, atau gangguan sementara).\n")
    L.append("Untuk memperkuat bukti, jalankan ulang dari jaringan lain dengan `--label` berbeda dan bandingkan.\n")
    L.append("## Cara mengulang\n")
    L.append("```\npython src/check_access.py --label nama-jaringan\n```\n")
    return "\n".join(L)


def main() -> int:
    load_env_file(ROOT / ".env")
    ap = argparse.ArgumentParser(description="Uji akses situs sumber dan buat laporan bukti")
    ap.add_argument("--label", default="", help="catatan jaringan, mis. wifi-rumah atau hotspot-hp")
    ap.add_argument("--attempts", type=int, default=2, help="jumlah percobaan per URL (bawaan 2)")
    ap.add_argument("--delay", type=float, default=5.0, help="jeda antar permintaan, detik (bawaan 5)")
    ap.add_argument("--timeout", type=int, default=20)
    ap.add_argument("--url", action="append", default=[], metavar="PLATFORM=URL", help="URL tambahan")
    ap.add_argument("--config", default=os.environ.get("CRAWLER_CONFIG") or str(ROOT / "config" / "selectors.yml"))
    ap.add_argument("--output-dir", default=None)
    args = ap.parse_args()

    contact = os.environ.get("CRAWLER_CONTACT", "").strip()
    if not contact:
        print("CRAWLER_CONTACT belum diisi (email atau URL). Isi di .env agar identitas pengujian jujur.")
        return 1
    ua = os.environ.get("CRAWLER_USER_AGENT") or f"PriceResearchBot/1.0 (+{contact})"
    cfg = yaml.safe_load(Path(args.config).read_text(encoding="utf-8")) if Path(args.config).exists() else None
    stamp = datetime.now(WIB).strftime("%Y%m%d_%H%M%S")
    suffix = re.sub(r"[^A-Za-z0-9_-]+", "-", args.label).strip("-")
    out_dir = Path(args.output_dir) if args.output_dir else (
        ROOT / "docs" / "crawl_evidence" / f"access_check_{stamp}{('_' + suffix) if suffix else ''}")
    out_dir.mkdir(parents=True, exist_ok=True)

    targets = build_targets(cfg, args.url)
    print(f"Menguji {len(targets)} URL, {args.attempts} percobaan masing-masing, jeda {args.delay} detik...")
    data = run_check(targets, ua, args.attempts, args.delay, args.timeout, out_dir, args.label, cfg)
    for name, p in data["per_platform"].items():
        print(f"  {name:16s} {p['verdict']}")
    print(f"Laporan: {out_dir / 'report.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
