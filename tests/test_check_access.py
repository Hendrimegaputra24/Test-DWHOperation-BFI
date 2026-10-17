"""Tes skrip uji akses memakai server lokal yang meniru berbagai jawaban situs."""
import hashlib
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest
import yaml

import check_access

FIX = Path(__file__).parent / "fixtures"
CFG = yaml.safe_load((Path(__file__).resolve().parent.parent / "config" / "selectors.yml").read_text(encoding="utf-8"))
UA = "TestBot/1.0 (+test@example.com)"
SEEN_UA: list = []


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # diamkan log server uji
        pass

    def _send(self, code, body, headers=None):
        data = body.encode("utf-8")
        self.send_response(code)
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        SEEN_UA.append(self.headers.get("User-Agent"))
        p = self.path
        if p == "/robots.txt":
            return self._send(200, "User-agent: *\nDisallow: /private\n")
        if p == "/products":
            return self._send(200, (FIX / "changed_layout.html").read_text(encoding="utf-8"))
        if p == "/shell":
            return self._send(200, "<html><head><title>App</title></head><body><div id='app'></div></body></html>")
        if p == "/refused":
            return self._send(403, (FIX / "blocked_challenge.html").read_text(encoding="utf-8"),
                              {"Server": "cloudflare", "CF-RAY": "abc123-CGK"})
        if p == "/challenge200":
            return self._send(200, (FIX / "blocked_challenge.html").read_text(encoding="utf-8"))
        if p == "/private":
            return self._send(200, "rahasia")
        self._send(404, "tidak ada")


@pytest.fixture(scope="module")
def server():
    srv = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


@pytest.fixture()
def result(server, tmp_path):
    SEEN_UA.clear()
    targets = [("Tokopedia", server + "/products"), ("Blibli", server + "/shell"),
               ("Klik Indomaret", server + "/refused"), ("Challenge", server + "/challenge200"),
               ("Private", server + "/private"), ("Mati", "http://127.0.0.1:1/")]
    sleeps = []
    data = check_access.run_check(targets, UA, attempts=2, delay=5, timeout=3, out_dir=tmp_path,
                                  label="uji", cfg={"platforms": {"Tokopedia": CFG["platforms"]["Tokopedia"]}},
                                  sleeper=sleeps.append)
    return data, tmp_path, sleeps


def verdicts(data):
    return {r["platform"]: r["verdict"] for r in data["results"]}


def test_each_kind_of_answer_is_classified(result):
    data, _, _ = result
    v = verdicts(data)
    assert v["Tokopedia"] == "OPEN_WITH_PRODUCTS"
    assert v["Blibli"] == "OPEN_NO_PRODUCT_DATA"
    assert v["Klik Indomaret"] == "REFUSED_403"
    assert v["Challenge"] == "CHALLENGE_PAGE"
    assert v["Mati"] == "CONNECTION_ERROR"


def test_cloudflare_headers_are_recorded(result):
    data, _, _ = result
    refused = next(r for r in data["results"] if r["platform"] == "Klik Indomaret")
    assert refused["cloudflare_headers"] is True and refused["status"] == 403
    assert data["per_platform"]["Klik Indomaret"]["cloudflare"] is True


def test_robots_disallowed_url_is_skipped_not_requested(result):
    data, _, _ = result
    assert any(s["url"].endswith("/private") for s in data["skipped"])
    assert "/private" not in [r["url"].split("127.0.0.1:")[-1][5:] for r in data["results"]]
    assert "Private" not in {r["platform"] for r in data["results"]}


def test_identity_is_honest_and_attempts_are_polite(result):
    data, _, sleeps = result
    assert set(u for u in SEEN_UA if u) == {UA}                 # satu identitas, apa adanya
    assert not any("Mozilla" in (u or "") for u in SEEN_UA)    # tidak menyamar sebagai browser
    assert len([r for r in data["results"] if r["platform"] == "Tokopedia"]) == 2   # 2 percobaan
    assert sleeps and all(s == 5 for s in sleeps)               # jeda dipakai


def test_evidence_files_and_hashes_are_consistent(result):
    data, out, _ = result
    results_text = (out / "results.json").read_text(encoding="utf-8")
    assert data["results_sha256"] == hashlib.sha256(results_text.encode("utf-8")).hexdigest()
    report = (out / "report.md").read_text(encoding="utf-8")
    assert data["results_sha256"] in report and "Tidak dibuktikan" in report
    for r in data["results"]:
        if r.get("saved_response"):
            saved = (out / r["saved_response"]).read_text(encoding="utf-8")
            assert hashlib.sha256(saved.encode("utf-8")).hexdigest() == r["sha256"]   # salinan = yang diterima
    assert json.loads(results_text)["label"] == "uji"


def test_report_does_not_overclaim(result):
    _, out, _ = result
    report = (out / "report.md").read_text(encoding="utf-8")
    assert "manusia" in report                                   # menyebut batasan bahwa manusia mungkin bisa membuka
    assert "tidak dapat dibuka" not in report.split("Tidak dibuktikan")[0]


def _without_contact(monkeypatch):
    monkeypatch.setenv("CRAWLER_CONTACT", "x")      # trik: dicatat agar dipulihkan setelah tes
    monkeypatch.delenv("CRAWLER_CONTACT")


def test_contact_required(monkeypatch, tmp_path, capsys):
    _without_contact(monkeypatch)
    monkeypatch.setattr(check_access, "ROOT", tmp_path)       # tanpa .env
    monkeypatch.setattr("sys.argv", ["check_access.py"])
    assert check_access.main() == 1
    assert "CRAWLER_CONTACT" in capsys.readouterr().out


def test_contact_is_read_from_dotenv(monkeypatch, tmp_path):
    _without_contact(monkeypatch)
    (tmp_path / ".env").write_text("CRAWLER_CONTACT=dari-dotenv@example.com\n", encoding="utf-8")
    monkeypatch.setattr(check_access, "ROOT", tmp_path)
    seen = {}

    def fake_run_check(targets, ua, *a, **k):
        seen["ua"] = ua
        return {"per_platform": {}}

    monkeypatch.setattr(check_access, "run_check", fake_run_check)
    monkeypatch.setattr("sys.argv", ["check_access.py", "--output-dir", str(tmp_path / "out")])
    assert check_access.main() == 0
    assert "dari-dotenv@example.com" in seen["ua"]
