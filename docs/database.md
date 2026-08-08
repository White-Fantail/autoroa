# Database

Alembic is the authoritative schema workflow. UUID entities include profiles, vehicles, brands/stations, media assets, receipts, odometer readings, fill-ups, and observations. `fuel_station_current_prices` is a replaceable derived cache; observations remain immutable history except moderation flags.

Money uses `NUMERIC`/Python `Decimal`; fuel quantities use three decimal places and pump prices four. Times are UTC and clients display Pacific/Auckland where appropriate. Fill-ups reference their owner and vehicle; observations intentionally contain no user or odometer fields.

Latitude/longitude with a composite index and Haversine filtering are sufficient for the MVP. Migrate to PostGIS `geography(Point,4326)` and GiST indexing as coverage grows. Supabase Storage policies restrict object paths to the authenticated user's UUID.

Account deletion removes storage objects and private records, detaches retained verified observations from private provenance, and deactivates user-confirmed observations. Retained evidence is pseudonymous before detachment and contains no public identity fields.
