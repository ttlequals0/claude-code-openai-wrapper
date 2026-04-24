# syntax=docker/dockerfile:1.6

# -----------------------------------------------------------------------------
# Base: install Poetry and app dependencies. Shared by dev and prod stages.
# -----------------------------------------------------------------------------
FROM python:3.12-slim AS base

# Install system deps (curl for Poetry installer).
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry globally.
RUN curl -sSL https://install.python-poetry.org | python3 -
ENV PATH="/root/.local/bin:${PATH}"

# Note: Claude Code CLI is bundled with claude-agent-sdk >= 0.1.8.
# No separate Node.js/npm installation required.

WORKDIR /app

# Copy manifests first so dependency install is cached when source changes.
COPY pyproject.toml poetry.lock* /app/
# --only main excludes the dev group (black, bandit, pytest, mypy, etc.),
# which are only needed in CI and would otherwise ship inside the image and
# expand the vulnerability surface (e.g. CVE-2026-32274 black < 26.3.1).
RUN poetry install --no-root --only main --no-interaction --no-ansi

# Copy the application source.
COPY . /app

# Build-info stamp: record the installed SDK and bundled Claude CLI versions
# so the running container advertises what it actually ships. This turns
# "which SDK shipped in the image?" from guesswork into a one-shot `cat`.
# Must run via `poetry run` because dependencies are installed into the
# Poetry-managed virtualenv, not the system site-packages.
RUN poetry run python -c "\
import importlib.metadata, pathlib, claude_agent_sdk;\
sdk = importlib.metadata.version('claude-agent-sdk');\
cli = pathlib.Path(claude_agent_sdk.__file__).parent / '_bundled' / 'claude';\
open('/app/BUILD_INFO', 'w').write(f'claude-agent-sdk={sdk}\\nbundled_cli_present={cli.exists()}\\nbundled_cli_path={cli}\\n')\
" || echo "BUILD_INFO stamp skipped (non-fatal)"

EXPOSE 8000

# -----------------------------------------------------------------------------
# Dev stage: --reload watches the filesystem for changes. Not suitable for prod
# because it interferes with long-lived streaming connections and adds startup
# cost; keep it strictly for local iteration.
# -----------------------------------------------------------------------------
FROM base AS dev
CMD ["poetry", "run", "uvicorn", "src.main:app", \
     "--host", "0.0.0.0", "--port", "8000", "--reload"]

# -----------------------------------------------------------------------------
# Prod stage: multi-worker, no reload. Default target for deployment images.
# Override worker count via the UVICORN_WORKERS env var at runtime if needed.
# -----------------------------------------------------------------------------
FROM base AS prod
ENV UVICORN_WORKERS=2
CMD ["sh", "-c", "poetry run uvicorn src.main:app \
    --host 0.0.0.0 --port 8000 --workers ${UVICORN_WORKERS} --no-access-log"]
