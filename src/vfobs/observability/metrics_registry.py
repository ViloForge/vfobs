from prometheus_client import CollectorRegistry, Counter, Histogram, make_asgi_app

REGISTRY = CollectorRegistry(auto_describe=True)

REQUESTS = Counter(
    "vfobs_http_requests_total",
    "Total HTTP requests handled",
    ["method", "path", "status"],
    registry=REGISTRY,
)

DURATION = Histogram(
    "vfobs_http_request_duration_seconds",
    "HTTP request duration",
    ["method", "path"],
    registry=REGISTRY,
)


def metrics_asgi_app():
    return make_asgi_app(registry=REGISTRY)
