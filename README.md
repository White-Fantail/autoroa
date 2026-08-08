# Carfolio

Carfolio is a New Zealand-first mobile fuel companion. A receipt and odometer scan produce a private vehicle record, useful economy/cost metrics, and a separate anonymised station-price observation.

```text
Expo Mobile ── JWT/API ──> FastAPI ──> Supabase Postgres/Storage/Auth
                              │                    │
Google Places ──> Station matching       Fuel-price dataset
                              │
                         OCR provider
Next.js landing/admin ───────> FastAPI
```

## Prerequisites and setup

Install Node 20+, pnpm 9+, Python 3.12+, uv, and Docker. Then:

```bash
cp .env.example .env
pnpm install
uv sync --project services/api
docker compose up -d postgres
uv run --project services/api alembic upgrade head
pnpm dev
```

Web runs at `http://localhost:3000`, API at `http://localhost:8000` (`/docs` for OpenAPI), and Expo prints its development URL. For a no-Docker API, keep the SQLite `DATABASE_URL` and run `uv run --project services/api fastapi dev app/main.py` from `services/api`.

Development authentication accepts `Authorization: Bearer dev:<uuid>[:admin]`; production requires a Supabase JWT. Mock OCR/maps keep the complete path free of paid calls.

## Validation

```bash
pnpm validate
```

See [architecture](docs/architecture.md), [API](docs/api.md), [database](docs/database.md), [product](docs/product.md), and [deployment](docs/deployment.md).
