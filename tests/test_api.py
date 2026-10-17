"""Tes integrasi API. Dilewati otomatis bila database/konfigurasi tidak tersedia."""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    try:
        from api.main import app
        ctx = TestClient(app)
        c = ctx.__enter__()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"API atau database tidak tersedia: {exc}")
    yield c
    ctx.__exit__(None, None, None)


def _login(client, username):
    from api.config import get_settings
    pwd = get_settings().users[username][0]
    r = client.post("/auth/token", data={"username": username, "password": pwd})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_health_is_public(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_login_wrong_password_is_401(client):
    r = client.post("/auth/token", data={"username": "admin", "password": "salah"})
    assert r.status_code == 401


def test_endpoints_require_token(client):
    for path in ("/products", "/prices", "/recommendations"):
        assert client.get(path).status_code == 401


def test_invalid_token_is_401(client):
    r = client.get("/products", headers={"Authorization": "Bearer abc.def.ghi"})
    assert r.status_code == 401


def test_products_pagination_and_total(client):
    h = _login(client, "analyst")
    r = client.get("/products", params={"limit": 5, "offset": 0}, headers=h).json()
    assert r["total"] == 40 and len(r["items"]) == 5 and r["limit"] == 5
    page2 = client.get("/products", params={"limit": 5, "offset": 5}, headers=h).json()
    assert {p["product_key"] for p in r["items"]}.isdisjoint({p["product_key"] for p in page2["items"]})


def test_products_filters(client):
    h = _login(client, "analyst")
    r = client.get("/products", params={"category": "Perawatan Mulut", "limit": 200}, headers=h).json()
    assert r["total"] > 0 and all(p["category"] == "Perawatan Mulut" for p in r["items"])
    r = client.get("/products", params={"q": "bango"}, headers=h).json()
    assert r["total"] == 3
    assert client.get("/products", params={"q": "%%"}, headers=h).json()["total"] == 0  # wildcard di-escape


def test_input_validation(client):
    h = _login(client, "analyst")
    assert client.get("/products", params={"limit": 1000}, headers=h).status_code == 422
    assert client.get("/products", params={"offset": -1}, headers=h).status_code == 422
    assert client.get("/prices", params={"platform": "Shopee"}, headers=h).status_code == 422
    assert client.get("/prices", params={"date_from": "2026-10-10", "date_to": "2026-10-01"},
                      headers=h).status_code == 422
    assert client.get("/products/bukan-hash", headers=h).status_code == 422


def test_product_detail_and_404(client):
    h = _login(client, "analyst")
    key = client.get("/products", params={"limit": 1}, headers=h).json()["items"][0]["product_key"]
    assert client.get(f"/products/{key}", headers=h).json()["product_key"] == key
    assert client.get("/products/" + "0" * 32, headers=h).status_code == 404


def test_prices_filters(client):
    h = _login(client, "analyst")
    r = client.get("/prices", params={"platform": "Blibli", "date_from": "2026-10-10",
                                      "date_to": "2026-10-12", "limit": 200}, headers=h).json()
    assert r["total"] > 0
    assert all(p["platform"] == "Blibli" and "2026-10-10" <= p["price_date"] <= "2026-10-12" for p in r["items"])
    d = client.get("/prices", params={"only_discounted": True, "limit": 50}, headers=h).json()
    assert d["total"] > 0 and all(p["is_discounted"] and p["discount_pct"] > 0 for p in d["items"])


def test_analyst_cannot_run_but_admin_can(client):
    assert client.post("/recommendations/run", json={}).status_code == 401
    analyst = _login(client, "analyst")
    assert client.post("/recommendations/run", json={}, headers=analyst).status_code == 403
    admin = _login(client, "admin")
    assert client.post("/recommendations/run", json={"days": 99}, headers=admin).status_code == 422
    r = client.post("/recommendations/run", json={"days": 2}, headers=admin)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["triggered_by"] == "admin" and body["recommendations"] > 0 and body["run_id"]


def test_recommendations_by_product_and_date(client):
    h = _login(client, "analyst")
    lst = client.get("/recommendations", params={"limit": 3}, headers=h).json()
    assert lst["total"] > 0
    first = lst["items"][0]
    one = client.get(f"/recommendations/{first['product_key']}",
                     params={"date": first["recommendation_date"]}, headers=h)
    assert one.status_code == 200
    body = one.json()
    assert body["recommended_price_idr"] >= body["price_floor_idr"] > 0
    assert body["model_version"] and body["run_id"] and body["run_ts"]
    missing = client.get(f"/recommendations/{first['product_key']}", params={"date": "2020-01-01"}, headers=h)
    assert missing.status_code == 404
    assert client.get(f"/recommendations/{first['product_key']}", headers=h).status_code == 422


def test_openapi_documents_security(client):
    spec = client.get("/openapi.json").json()
    assert "OAuth2PasswordBearer" in spec["components"]["securitySchemes"]
    assert "/recommendations/run" in spec["paths"]
