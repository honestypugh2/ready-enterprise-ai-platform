# Multi-stage build for the API and the worker.
#
# One image serves both: they share the same composition root, so shipping two
# images would mean two dependency sets that can drift apart. The command
# selects the entry point.
#
# Runs as a non-root user with no build toolchain in the final layer, because a
# container that can compile is a container that can be made to compile
# something else.

FROM python:3.14-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

COPY --from=ghcr.io/astral-sh/uv:0.11.3 /uv /usr/local/bin/uv

WORKDIR /build

# Dependencies resolve from the lockfile in their own layer, so a source change
# does not re-resolve the dependency graph.
COPY pyproject.toml uv.lock README.md LICENSE ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

COPY packages/ packages/
COPY apps/ apps/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev


FROM python:3.14-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH" \
    REAP_MODE=local_mock

RUN groupadd --system --gid 10001 reap \
    && useradd --system --uid 10001 --gid reap --no-create-home reap

WORKDIR /app

COPY --from=builder --chown=reap:reap /build/.venv /app/.venv
COPY --from=builder --chown=reap:reap /build/packages /app/packages
COPY --from=builder --chown=reap:reap /build/apps /app/apps
COPY --chown=reap:reap data/ /app/data/

USER reap

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/livez', timeout=2).status == 200 else 1)"

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
