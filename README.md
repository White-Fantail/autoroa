# Autoroa

Autoroa is a New Zealand-first vehicle ownership and automotive information platform. Its current foundation combines personal vehicle and fuel-economy tracking with receipt and odometer scanning, nearby fuel discovery, crowdsourced fuel pricing, and aggregated statistics. Vehicle servicing, maintenance history, garage information, and repair-cost insights are planned extensions.

## Product direction (planning update, 2026-11-01)

**Capture once, manage your vehicle, share only what you choose.** The long-term offering is a photo-first **private mobile vehicle companion** (fuel receipts, optional odometer, real fuel economy where evidence supports it, oil/tyres/repairs/WoF/rego/RUC and due items) plus a **separate public web information service** (trusted, source-labelled fuel prices first; aggregated maintenance insights only after privacy and sample-quality gates). A signed-in owner's web garage is private, not part of the public dataset.

The vehicle-care and aggregate-web features described here are **planning proposals**, not implemented features. The October 2026 code audit and existing Quick Capture release limitations remain recorded in the roadmap. See [product vision](docs/vision-2026.md), [vehicle-care journeys](docs/vehicle-care.md), [web and privacy boundaries](docs/web-products.md), [product decisions](docs/product.md), and [development roadmap](docs/roadmap.md).

Migration tests always exercise SQLite zero-to-head and populated `0001` upgrades. CI can additionally set `AUTOROA_TEST_POSTGRES_URL` to a dedicated disposable PostgreSQL database to run both PostgreSQL migration paths; never point it at a shared or production database.

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

See the [development roadmap and progress tracker](docs/roadmap.md) for implementation status, outstanding work, release gates, and next priorities. For the one-tap camera flow, see [Quick Capture](docs/quick-capture.md).

See [architecture](docs/architecture.md), [API](docs/api.md), [database](docs/database.md), [product](docs/product.md), and [deployment](docs/deployment.md).
