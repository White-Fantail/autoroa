# Carfolio

Carfolio is a New Zealand-first mobile fuel companion. A receipt and odometer scan produce a private vehicle record, useful economy/cost metrics, and a pseudonymous station-price observation with private provenance links that are never exposed publicly.

Migration tests always exercise SQLite zero-to-head and populated `0001` upgrades. CI can additionally set `CARFOLIO_TEST_POSTGRES_URL` to a dedicated disposable PostgreSQL database to run both PostgreSQL migration paths; never point it at a shared or production database.

```text
Expo Mobile ── JWT/API ──> FastAPI ──> Supabase Postgres/Storage/Auth
                              │                    │
Google Places ──> Station matching       Fuel-price dataset
                              │
                         OCR provider
Next.js landing/admin ───────> FastAPI
```

## Prerequisites and setup

Install Docker, then:

```bash
cp .env.example .env
docker compose up --build
```

Web runs at `http://localhost:3000` with live reload, and API runs at `http://localhost:8000` (`/docs` for OpenAPI). PostgreSQL data and the web dependency/build caches are kept in Docker volumes. `NEXT_PUBLIC_API_URL` remains a browser-facing URL, so its local default is `http://localhost:8000/api/v1`, not the Compose service hostname.

For host-based development, install Node 20+, pnpm 9+, Python 3.12+, and uv. Keep the SQLite `DATABASE_URL`, run `uv run --project services/api fastapi dev app/main.py` from `services/api`, and run `pnpm dev` from the repository root. Expo prints its own development URL when run this way.

Development authentication accepts `Authorization: Bearer dev:<uuid>[:admin]`; production requires a Supabase JWT. With `APP_ENV=development` and `OCR_PROVIDER=mock`, receipt and odometer images are uploaded to the API and stored under `services/api/.local-media/`, so the complete scan flow needs neither Supabase Storage nor paid APIs. Local media still receives the same size, MIME, decode, and duplicate checks as production and is removed when its account is deleted. Production always requires private Supabase Storage.

## Validation

```bash
pnpm validate
```

See [architecture](docs/architecture.md), [API](docs/api.md), [database](docs/database.md), [product](docs/product.md), and [deployment](docs/deployment.md).
