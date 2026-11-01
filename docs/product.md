# Product decisions

Autoroa's primary value exchange is **private vehicle usefulness first**: capture fuel receipts and optional odometers with almost no input, preserve reliable spending/economy records, and increasingly capture maintenance/tyre/repair/WoF/rego history and reminders. Verified public fuel-price contributions are a separate, explicit opt-in path; private receipts do not silently become public price reports. Any aggregate maintenance-cost web product is a later, privacy-gated proposal. Private provenance remains internally linked for audit and deletion but is never included in public price responses. High-confidence OCR results (≥.90) are applied automatically only when their destination is already known; medium (.70–.899), attention-required (<.70), and unassigned station price-board results require explicit confirmation.

Admin station pricing offers two independent actions: upload a photo into the background OCR queue, or enter prices manually for immediate application. Admins may also upload a price-board photo without selecting a station. The queue then requires station selection and price review before applying it.

Economy is only computed between valid full tanks. Partial-fill litres/cost are accumulated; missed fills, non-increasing odometers, or unreliable chains yield `null`. Pump price is the comparable public value; loyalty paid price remains separate. Freshness states are Very fresh (<1h), Fresh (1–6h), Recent (6–24h), Old (1–3d), and Stale (>3d).

The implementation audit dated 2026-10-22 covers account/vehicle/fill-up workflows, discovery, personal metrics, and operational review. The 2026-11-01 **product-plan update** promotes vehicle maintenance history and basic sourced reminders to the next staged product-design track, while they remain **not established as implemented**. EV charging, financial rewards, marketplace, subscriptions, navigation, and fleet functionality remain later extensions.


## Planning direction (2026-11-01; not implemented status)

- [Vehicle-first vision and three-pass product review](vision-2026.md): private utility, photo-first capture, credible insights, public web, sustainability, experiments, and open decisions.
- [Vehicle-care mobile journeys and acceptance criteria](vehicle-care.md): fuel, tyres, oil, repairs, WoF/rego/RUC, honest economy, unified timeline, due items, and edge cases.
- [Three web surfaces and sharing boundaries](web-products.md): authenticated owner garage, independently trusted public fuel information, and privacy-gated aggregate repair-cost insights.
- [Existing Quick Capture technical contract](quick-capture.md) remains the source for verified implementation limitations and real-device gates. Product aspirations do not override its local-save versus OCR-complete distinction.

**Decision hierarchy:** field-tested evidence > safety/privacy and accounting invariants > user outcome > feature wish list. Existing public price confidence, explicit consent, and private provenance protections must not be weakened to grow contribution volume. The maintenance/web specification is proposed future scope, not a claim of current API support.
