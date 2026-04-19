FROM python:3.12-slim AS builder

WORKDIR /build

RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.12-slim AS runtime

LABEL maintainer="RWA Platform Team"
LABEL description="RWA Tokenization Backend — FastAPI + Celery"

RUN apt-get update && \
    apt-get install -y --no-install-recommends libpq5 curl && \
    rm -rf /var/lib/apt/lists/* && \
    groupadd -r rwa && useradd -r -g rwa -d /app -s /sbin/nologin rwa

WORKDIR /app

COPY --from=builder /install /usr/local

COPY backend/ ./backend/
COPY network/ ./network/

RUN chown -R rwa:rwa /app

USER rwa

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
