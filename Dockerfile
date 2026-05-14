FROM python:3.12-slim AS builder

WORKDIR /build

COPY pyproject.toml /build/pyproject.toml
COPY src /build/src
COPY alembic /build/alembic
COPY alembic.ini /build/alembic.ini

RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
 && pip install --no-cache-dir --target=/install .


FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/lib

WORKDIR /app

COPY --from=builder /install /app/lib
COPY --from=builder /build/alembic /app/alembic
COPY --from=builder /build/alembic.ini /app/alembic.ini
COPY src /app/src

ENV PYTHONPATH=/app/src:/app/lib

EXPOSE 8080

CMD ["python", "-m", "uvicorn", "vfobs.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8080"]
