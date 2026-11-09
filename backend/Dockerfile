# The translate proxy service. Build from the repository root:
#   docker build -f backend/Dockerfile -t mirror-backend backend
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    BACKEND_CONFIG_DIR=/var/lib/mirror/runtime-config

WORKDIR /srv

COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /usr/local/bin/uv

# Dependencies first, so a code change does not re-resolve them.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

COPY app ./app
COPY config ./config
RUN uv sync --locked --no-dev

RUN mkdir -p "$BACKEND_CONFIG_DIR"

EXPOSE 8000
CMD ["uv", "run", "--no-dev", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
