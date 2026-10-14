# API and MCP server image. The model runs elsewhere (vLLM on a GPU host); this image needs no GPU.
FROM python:3.12-slim AS base
COPY --from=ghcr.io/astral-sh/uv:0.12.15 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
COPY data ./data
COPY evals/cassettes ./evals/cassettes
RUN uv sync --frozen --no-dev && useradd --uid 10001 app && mkdir /state && chown app /state
USER app
ENV LEDGER_DB=/state/ledger.db CHECKPOINT_DB=/state/checkpoints.db PATH="/app/.venv/bin:$PATH"
EXPOSE 8000 8765
CMD ["uvicorn", "loan_draw.api:app", "--host", "0.0.0.0", "--port", "8000"]
