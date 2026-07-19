# Deterministic build for Railway / any container host.
# Uses uv for reproducible installs from the lockfile, then seeds the ledger
# from the committed snapshot on first boot (same behavior as render_start.sh).
FROM python:3.12-slim

WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

COPY . .
RUN uv sync --frozen

# $PORT is provided by the platform; seed the DB if this instance has no ledger yet.
CMD ["sh", "-c", "test -f vcbrain.db || cp data/vcbrain-seed.sqlite3 vcbrain.db; exec uv run uvicorn vcbrain.app:app --host 0.0.0.0 --port ${PORT:-8000}"]
