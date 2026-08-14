# API

The API prefix is `/api/v1`; interactive OpenAPI is `/docs` outside production. Send a Supabase access token as `Authorization: Bearer …`. Local development accepts `dev:<uuid>` and `dev:<uuid>:admin`.

Groups include `/me`, `/vehicles`, `/media`, `/receipts`, `/odometer-readings`, `/fill-ups`, vehicle `/metrics`, `/fuel-stations`, `/fuel-prices/nearby`, and protected `/admin` operations. Fill-up listing supports vehicle/date filters and cursor/limit. Nearby discovery accepts coordinates, radius, fuel type, and price/distance sorting.

`POST /ocr-jobs` queues receipt, odometer, or price-board recognition and returns `202` with a durable job. `GET /ocr-jobs` lists the caller's recent work and `GET /ocr-jobs/{id}` reports queue status, extracted results, confidence, whether confirmation is required, and when an automatic or confirmed result was applied.

Errors use `{"error":{"code":"…","message":"…","details":null}}` for server faults; validation/auth responses use FastAPI's standard status semantics. Media upload preparation validates MIME/size and returns a short-lived owner-scoped target. Development and test environments without Supabase Storage return an authenticated local upload target; cloud mode signs a private Supabase upload. Local upload intents expire after 15 minutes, are single-use, and persist validated image bytes in the ignored `services/api/.local-media/` runtime directory. This fallback is unavailable outside development and test.

For finite vehicle metric periods, `distance_km` is the latest in-period odometer minus the latest odometer at or before the period cutoff. If no cutoff baseline exists, it uses the earliest and latest in-period odometers. For `all`, it uses the earliest and latest recorded odometers. A negative result is returned as zero rather than a misleading negative distance.
