FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim@sha256:7cf77f594be8042dab6daa9fe326f90962252268b4f120a7f5dccce4d947e6c1 AS uv

FROM python:3.15-slim-bookworm@sha256:4e03260adeeebafccd084f3584e6b84823aba5651cfb53ef8a078ed441ddf9cd AS builder

COPY --from=uv /usr/local/bin/uv /usr/local/bin/uv

RUN apt-get update && apt-get install -y --no-install-recommends build-essential ca-certificates curl \
    && rm -rf /var/lib/apt/lists/* \
    && curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \
       | sh -s -- -y --profile minimal --default-toolchain 1.95.0

ARG VERSION=0.0.0
ENV SETUPTOOLS_SCM_PRETEND_VERSION_FOR_SHELLY_POWER_EXPORTER=${VERSION}

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
ENV UV_PYTHON_DOWNLOADS=never
ENV REQUIRE_CYTHON=1
ENV PATH="/root/.cargo/bin:$PATH"

COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev


FROM python:3.15-slim-bookworm@sha256:4e03260adeeebafccd084f3584e6b84823aba5651cfb53ef8a078ed441ddf9cd

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
