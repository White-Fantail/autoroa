# Quick Capture — mobile-first operating model

## User contract

A Quick Capture deep link opens the camera without navigating the normal app.
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
vehicle, and uploaded receipt media. The endpoint also accepts the earlier
client_key + receipt_id request so already-installed clients can finish uploads. It atomically creates a private receipt,
capture session, and OCR job. `POST /quick-captures/{id}/odometer` attaches a
separate odometer job, idempotently.

The server worker auto-creates a private FillUp only when the receipt's critical
fuel type, litres, pump price, total and date fields meet the 0.90 confidence
threshold, math is plausible, the transaction date is sensible and the fuel
type matches the selected vehicle. Low-confidence or contradictory scans remain
REVIEW_REQUIRED. Unreviewed station names do not publish fuel prices.

Missing odometers are represented by NULL rather than fabricated numbers.
Such records contribute to fuel costs but not fuel economy. Full-tank status is
not guessed by the no-confirmation camera flow: its default is false until a
user explicitly records full-tank status. Manual review can confirm it. A trustworthy
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
- Implement network backoff, background transfer, and production-grade
  recovery notifications before public release. The outbox and server
  REVIEW_REQUIRED inbox exist but still need physical-device verification.
- Keep staging and production storage separate; never auto-confirm suspicious
  fuel records or publish personal receipt identifiers.
- Test the SDK upgrade on a separate branch before adding native App Intents
  and system widgets. Avoid a simultaneous unvalidated dependency migration.

## Review workflow

A capture that fails core OCR gates appears in Recent captures with Needs review.
The Review screen loads the stored receipt and optional odometer OCR values and
sends corrected values to POST /quick-captures/{id}/confirm. The record is
always personal and never directly publishes a station price. Arithmetic, mismatched fuel types, oversized tank volumes, and
odometer-order anomalies require a second explicit user acknowledgement.

## Migration and compatibility

The main branch's existing Alembic 0016 and 0017 migrations and stricter,
owner-scoped Quick Capture schema remain authoritative. Migration 0018 only
normalizes old statuses (COMPLETED to CONFIRMED, NEEDS_REVIEW to
REVIEW_REQUIRED); it does not drop old sessions, receipts or photos. The new
backend serves both the previous receipt_id/client_key API and the new
media-first client_token API. All raw media remains private.

On the first signed-in foreground sync, the mobile app also migrates the
previous `quick-captures/` manifest format into the new two-slot
`autoroa-captures/` outbox. It copies receipt and odometer images, carries
forward uploaded media/receipt IDs, verifies two usable manifests and then
cleans up the old files. A failed migration retains original files. Captures
belonging to other accounts are left untouched. The migration has isolated
unit coverage for interrupted networks, two-photo captures, and ownership.

This code merge is not a native mobile release: iOS App Intents, home/lock
widgets, persistent native background transfers, and end-to-end device QA are
explicitly outstanding. Do not label a successfully saved *local* photo as an
OCR-completed fuel record.

## iPhone shortcuts: supported today, without a native extension

- Navigate to **Quick Capture shortcuts** from Home.
- Long-press the displayed **Receipt only** URL to copy it.
- Open Apple's **Shortcuts** app, create a new shortcut with a **URL** input
  and the **Open URLs** action, then paste the copied URL.
- Name it `Scan fuel receipt`. Add it to the Home Screen or an Apple
  Shortcuts widget. On supported phones, assign the shortcut to the Action
  Button in iPhone Settings. Use the **Receipt + odometer** URL for the second
  action. This is not a native Autoroa widget or a branded Siri App Intent.
- `shortcuts://create-shortcut` opens Apple's shortcut editor when available.
  The user must finish creating the shortcut; Autoroa does not install it.

This SDK 52 app cannot safely adopt the new alpha `expo-widgets` and
`expo-app-intents` packages without a separate SDK upgrade and iOS native
build. Preserve the current tested camera and URL entry until that work is
validated. An Apple Shortcuts widget already provides the requested
tap-to-camera entry on a configured iPhone.

## Outbox recovery and display

The Home dashboard shows only private, locally saved pending captures
belonging to the current signed-in account, separately from the server's
OCR processing statuses. Upload interruptions remain in the two-slot
manifest, with bounded retry delays (15 seconds doubling to 15 minutes);
uploads are retried when the app next runs in the foreground. **Retry uploads
now** bypasses the delay. Corrupt manifest folders are retained and flagged
rather than removed. Previously saved images can still be migrated using
the legacy capture outbox procedure. Local capture success never means OCR
was completed or a fuel record was confirmed.

## iOS physical-device acceptance checklist

1. Install an EAS iOS internal preview build, using the existing `preview`
   profile. Validate the entitlement, camera permission, and external URL
   opening on a real iPhone; CI cannot establish these.
2. Use the two URLs from the Apple Shortcuts app, both when Autoroa is killed
   and when it is already open. Confirm that receipt mode takes exactly one
   photo and full mode takes a second, optional odometer photo.
3. Capture in airplane mode with a vehicle previously cached by the app.
   Confirm the Home outbox shows the photo as waiting and preserves it across
   force quit, app restart, and device restart.
4. Restore network access and use **Retry uploads now**; verify that the
   backend creates exactly one private fuel record, or opens **Needs review**
   on uncertain recognition. A failed upload must not remove its local photo.
5. Test a malformed photo, rejected permissions, switching accounts,
   receipt-only after abandoning full mode, and a full-storage device.
6. Verify data migrations from a build created before PR #29 using an
   unsynced receipt and odometer photo.
7. Do not release to the App Store until camera/queue UX, migration,
   background termination behavior and network conditions have been tested
   on physical devices. Native background URLSession transfer and a branded
   Autoroa widget remain distinct follow-on work.

**Build configuration:** Android Google Maps secrets are required for Android
EAS builds. iOS EAS builds do not require an Android-only Maps API key.
The dedicated CI job validates the iOS public Expo config without that key;
it does not compile a native iOS binary.
