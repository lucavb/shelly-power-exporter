FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim AS builder

ARG VERSION=0.0.0
ENV SETUPTOOLS_SCM_PRETEND_VERSION_FOR_SHELLY_POWER_EXPORTER=${VERSION}

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev


FROM python:3.11-slim-bookworm

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/main.py /app/main.py
COPY --from=builder /app/config.py /app/config.py
COPY --from=builder /app/metrics.py /app/metrics.py
COPY --from=builder /app/collector.py /app/collector.py
COPY --from=builder /app/version.py /app/version.py

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 9102

CMD ["python", "main.py"]

