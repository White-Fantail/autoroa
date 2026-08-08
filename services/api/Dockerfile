FROM python:3.12-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:0.6.14 /uv /bin/uv
WORKDIR /app
COPY pyproject.toml ./
RUN uv sync --no-dev
FROM python:3.12-slim
RUN useradd --create-home app
WORKDIR /app
COPY --from=builder /app/.venv .venv
COPY app app
USER app
ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
HEALTHCHECK CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000","--workers","2"]
