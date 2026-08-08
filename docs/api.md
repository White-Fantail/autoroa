# API

The API prefix is `/api/v1`; interactive OpenAPI is `/docs` outside production. Send a Supabase access token as `Authorization: Bearer …`. Local development accepts `dev:<uuid>` and `dev:<uuid>:admin`.

Groups include `/me`, `/vehicles`, `/media`, `/receipts`, `/odometer-readings`, `/fill-ups`, vehicle `/metrics`, `/fuel-stations`, `/fuel-prices/nearby`, and protected `/admin` operations. Fill-up listing supports vehicle/date filters and cursor/limit. Nearby discovery accepts coordinates, radius, fuel type, and price/distance sorting.

Errors use `{"error":{"code":"…","message":"…","details":null}}` for server faults; validation/auth responses use FastAPI's standard status semantics. Media upload preparation validates MIME/size and returns a short-lived owner-scoped target. The mock URL is for local flow only; cloud mode signs a private Supabase upload.
