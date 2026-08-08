# Architecture

Expo Router provides the primary iOS/Android experience. It authenticates with Supabase, retains its token in Secure Store, and calls the versioned FastAPI API. Next.js serves the public site and a deliberately operational admin surface.

FastAPI is authoritative for ownership, fuel economy, observation generation, anomaly checks, station matching, and current-price resolution. PostgreSQL holds private vehicle records separately from anonymised public observations. Supabase Auth owns identity; private Storage contains original media. Google Places supplies station identity/location only. OCR and maps are provider protocols with no-cost mocks; OpenAI and Google implementations can replace them without changing domain services.

The fill-up flow is media upload → OCR → editable confirmation → station match → fill-up → economy recalculation → eligible observation → current-price resolution. A future job queue can call the isolated processing service without changing the HTTP contract. Analytics is an interface/no-op by default.

Threat boundaries: user identity always comes from the JWT, object queries include the profile owner, service credentials remain server-only, uploads use generated owner-prefixed paths, and public endpoints never join profiles, vehicles, media, receipts, or odometers.
