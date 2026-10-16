"""Prometheus RED metrics (Rate, Errors, Duration) for every HTTP request.

The alert rules and Grafana dashboard in /monitoring query these exact names.
"""

import time

from fastapi import FastAPI, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

REQUESTS = Counter("http_requests_total", "HTTP requests", ["service", "method", "route", "status"])
LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency",
    ["service", "method", "route"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5),
)
SKIP = {"/metrics", "/healthz", "/readyz"}


def instrument(app: FastAPI, service: str) -> None:
    @app.middleware("http")
    async def record(request: Request, call_next):
        start = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        finally:
            # Use the route template (/products/{id}), not the raw path, to keep label cardinality low
            route = getattr(request.scope.get("route"), "path", "unmatched")
            if route not in SKIP:
                REQUESTS.labels(service, request.method, route, str(status)).inc()
                LATENCY.labels(service, request.method, route).observe(time.perf_counter() - start)

    @app.get("/metrics", include_in_schema=False)
    def metrics() -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
