import contextvars
import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from vfobs.observability.metrics_registry import DURATION, REQUESTS

request_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id", default="-"
)

logger = logging.getLogger("vfobs.request")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        rid = str(uuid.uuid4())
        request_id_ctx.set(rid)
        start = time.perf_counter()
        response = await call_next(request)
        duration = time.perf_counter() - start
        path = request.url.path
        method = request.method
        REQUESTS.labels(method=method, path=path, status=response.status_code).inc()
        DURATION.labels(method=method, path=path).observe(duration)
        logger.info(
            "request",
            extra={
                "method": method,
                "path": path,
                "status": response.status_code,
                "duration_ms": int(duration * 1000),
                "request_id": rid,
            },
        )
        return response
