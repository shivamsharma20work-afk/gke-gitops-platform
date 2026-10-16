"""Orders service: validates the product against catalog, then records the order."""

import itertools
import os
from datetime import UTC, datetime

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.metrics import instrument

SERVICE = "orders"
VERSION = os.getenv("APP_VERSION", "dev")
# In-cluster DNS name of the catalog Service
CATALOG_URL = os.getenv("CATALOG_URL", "http://catalog.shop.svc.cluster.local")

app = FastAPI(title="orders", version=VERSION)
instrument(app, SERVICE)

_ids = itertools.count(1)
ORDERS: dict[int, dict] = {}


class OrderIn(BaseModel):
    product_id: int
    quantity: int = Field(ge=1, le=10)


class Order(BaseModel):
    id: int
    product_id: int
    product_name: str
    quantity: int
    total_inr: float
    created_at: datetime


def catalog_client() -> httpx.Client:
    return httpx.Client(base_url=CATALOG_URL, timeout=2.0)


@app.get("/healthz", include_in_schema=False)
def healthz() -> dict:
    return {"status": "ok"}


@app.get("/readyz", include_in_schema=False)
def readyz() -> dict:
    # Ready only if the dependency is reachable, so Kubernetes stops routing to us otherwise
    try:
        with catalog_client() as c:
            c.get("/healthz").raise_for_status()
    except httpx.HTTPError:
        raise HTTPException(503, "catalog unreachable") from None
    return {"status": "ready"}


@app.get("/version")
def version() -> dict:
    return {"service": SERVICE, "version": VERSION}


@app.post("/orders", status_code=201)
def create_order(body: OrderIn) -> Order:
    try:
        with catalog_client() as c:
            r = c.get(f"/products/{body.product_id}")
    except httpx.HTTPError:
        raise HTTPException(502, "catalog unavailable") from None
    if r.status_code == 404:
        raise HTTPException(404, "product not found")
    if r.status_code != 200:
        raise HTTPException(502, "catalog error")

    product = r.json()
    if product["stock"] < body.quantity:
        raise HTTPException(409, "not enough stock")

    order = Order(
        id=next(_ids),
        product_id=product["id"],
        product_name=product["name"],
        quantity=body.quantity,
        total_inr=product["price_inr"] * body.quantity,
        created_at=datetime.now(UTC),
    )
    ORDERS[order.id] = order.model_dump()
    return order


@app.get("/orders")
def list_orders() -> list[Order]:
    return [Order(**o) for o in ORDERS.values()]
