from fastapi.testclient import TestClient

from app import main

client = TestClient(main.app)


def test_health_and_ready():
    assert client.get("/healthz").json() == {"status": "ok"}
    assert client.get("/readyz").status_code == 200


def test_list_and_get_product():
    products = client.get("/products").json()
    assert len(products) == 4
    assert client.get("/products/1").json()["name"] == "Mechanical keyboard"


def test_unknown_product_404():
    assert client.get("/products/999").status_code == 404


def test_metrics_use_route_template():
    client.get("/products/2")
    body = client.get("/metrics").text
    assert 'route="/products/{product_id}"' in body
    assert "http_request_duration_seconds_bucket" in body
    assert 'route="/healthz"' not in body


def test_fault_injection(monkeypatch):
    monkeypatch.setattr(main, "FAULT_RATE", 1.0)
    assert client.get("/products").status_code == 500
