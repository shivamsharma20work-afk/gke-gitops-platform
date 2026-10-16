"""Catalog service: the product list other services read from."""

import os
import random

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app.metrics import instrument

SERVICE = "catalog"
VERSION = os.getenv("APP_VERSION", "dev")
# Fraction of requests that fail with 500. Lets you trigger the error-rate alert on purpose.
FAULT_RATE = float(os.getenv("FAULT_RATE", "0"))

app = FastAPI(title="catalog", version=VERSION)
instrument(app, SERVICE)


class Product(BaseModel):
    id: int
    name: str
    price_inr: float
    stock: int


PRODUCTS = {
    p.id: p
    for p in [
        Product(id=1, name="Mechanical keyboard", price_inr=3499, stock=25),
        Product(id=2, name="USB-C hub", price_inr=1299, stock=40),
        Product(id=3, name="27-inch monitor", price_inr=15999, stock=8),
        Product(id=4, name="Laptop stand", price_inr=999, stock=0),
    ]
}


def maybe_fail() -> None:
    if FAULT_RATE and random.random() < FAULT_RATE:
        raise HTTPException(500, "injected fault")


@app.get("/healthz", include_in_schema=False)
def healthz() -> dict:
    return {"status": "ok"}


@app.get("/readyz", include_in_schema=False)
def readyz() -> dict:
    return {"status": "ready"}


@app.get("/version")
def version() -> dict:
    return {"service": SERVICE, "version": VERSION}


@app.get("/products")
def list_products() -> list[Product]:
    maybe_fail()
    return list(PRODUCTS.values())


@app.get("/products/{product_id}")
def get_product(product_id: int) -> Product:
    maybe_fail()
    if product_id not in PRODUCTS:
        raise HTTPException(404, "product not found")
    return PRODUCTS[product_id]
