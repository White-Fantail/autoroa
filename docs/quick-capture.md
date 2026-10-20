# Quick Capture entry points

Quick Capture has a single camera flow with two deep links:

- `autoroa://quick-capture?mode=receipt`: receipt only
- `autoroa://quick-capture?mode=full`: receipt and optional odometer

These URLs can be used with a manually configured iOS Shortcuts "Open URLs" action. Native Siri App Intents, Home/Lock Screen widgets, and Action Button registration are **not yet implemented**; the iOS build and entitlements must be validated on device before enabling them.

The camera stores each captured image in the app's private documents directory before upload. The per-capture JSON record survives app restarts. Upload is resumed when the signed-in app becomes active; iOS is not guaranteed to finish network work after the app is suspended or killed. The server completes high-confidence OCR captures and keeps uncertain work in review status. Do not remove local source photos until the entire capture is verified and safely stored by the backend.

Note: crash recovery after a server request succeeds but before its returned identifier is persisted is not yet fully idempotent at every upload step. This remains a release blocker until tested and addressed. The current Quick Capture flow is development-only.
