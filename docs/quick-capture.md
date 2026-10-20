# Quick Capture — mobile-first operating model

## User contract

One shortcut/widget entry opens a camera without navigating the normal app.
The default mode takes a single receipt photograph. A separately configured
Full Scan mode takes receipt + optional odometer without a form or Save button.

**Captured** means the photo has been copied to durable app document storage and
a local outbox manifest was written. It does **not** claim network upload or OCR
has finished. iOS can suspend JavaScript and network requests after the app
is closed or force-quit. In this first slice, outstanding uploads resume on
the next foreground entry. Native background URLSession transfer should be
added and tested before advertising upload completion after force-quit.

## Data ownership and automated processing

`POST /api/v1/quick-captures` accepts a per-account idempotency token,
vehicle, and uploaded receipt media. It atomically creates a private receipt,
capture session, and OCR job. `POST /quick-captures/{id}/odometer` attaches a
separate odometer job, idempotently.

The server worker auto-creates a private FillUp only when the receipt's critical
fuel type, litres, pump price, total and date fields meet the 0.90 confidence
threshold, math is plausible, the transaction date is sensible and the fuel
type matches the selected vehicle. Low-confidence or contradictory scans remain
REVIEW_REQUIRED. Unreviewed station names do not publish fuel prices.

Missing odometers are represented by NULL rather than fabricated numbers.
Such records contribute to fuel costs but not fuel economy. A trustworthy
odometer may be attached after an auto-created fill-up, with chronological
consistency checked before changing economy metrics.

## Client entry points

- `autoroa://quick-capture?mode=receipt`: one-photo camera.
- `autoroa://quick-capture?mode=full`: receipt then odometer.
- Home screen quick actions call the same routes.
- On iOS these URLs can already be used with the Shortcuts app's **Open URL**
  action; a branded App Intent, system Home/Lock widget and Action Button
  configuration require a compatible Expo SDK update and a real native build.
- Auth routing must preserve incoming Quick Capture deep links.

## Follow-up acceptance criteria

- Verify physical iPhone camera permissions, deep links, switching modes,
  app termination, offline capture, token refresh, and storage exhaustion.
- Implement network backoff, background transfer, and an explicit local queue
  and server REVIEW_REQUIRED inbox before public release.
- Keep staging and production storage separate; never auto-confirm suspicious
  fuel records or publish personal receipt identifiers.
- Test the SDK upgrade on a separate branch before adding native App Intents
  and system widgets. Avoid a simultaneous unvalidated dependency migration.
