import httpx
import pytest
from fastapi.testclient import TestClient

from app import main

PRODUCTS = {
    1: {"id": 1, "name": "Mechanical keyboard", "price_inr": 3499, "stock": 25},
    4: {"id": 4, "name": "Laptop stand", "price_inr": 999, "stock": 0},
}


def fake_catalog(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/healthz":
        return httpx.Response(200, json={"status": "ok"})
    pid = int(request.url.path.rsplit("/", 1)[-1])
    if pid in PRODUCTS:
        return httpx.Response(200, json=PRODUCTS[pid])
    return httpx.Response(404)


@pytest.fixture
def client(monkeypatch):
    transport = httpx.MockTransport(fake_catalog)
    monkeypatch.setattr(
        main, "catalog_client", lambda: httpx.Client(base_url="http://catalog", transport=transport)
    )
    return TestClient(main.app)


def test_create_order_prices_from_catalog(client):
    r = client.post("/orders", json={"product_id": 1, "quantity": 2})
    assert r.status_code == 201
    assert r.json()["total_inr"] == 6998
    assert any(o["product_id"] == 1 for o in client.get("/orders").json())


def test_out_of_stock_409(client):
    assert client.post("/orders", json={"product_id": 4, "quantity": 1}).status_code == 409


def test_unknown_product_404(client):
    assert client.post("/orders", json={"product_id": 99, "quantity": 1}).status_code == 404


def test_quantity_validated(client):
    assert client.post("/orders", json={"product_id": 1, "quantity": 0}).status_code == 422


def test_catalog_down_gives_502_and_not_ready(monkeypatch):
    def down(request):
        raise httpx.ConnectError("no route")

    transport = httpx.MockTransport(down)
    monkeypatch.setattr(
        main, "catalog_client", lambda: httpx.Client(base_url="http://catalog", transport=transport)
    )
    c = TestClient(main.app)
    assert c.post("/orders", json={"product_id": 1, "quantity": 1}).status_code == 502
    assert c.get("/readyz").status_code == 503
