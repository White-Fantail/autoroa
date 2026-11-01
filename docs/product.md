# Product decisions

Autoroa's primary value exchange is **private vehicle usefulness first**: capture fuel receipts and optional odometers with almost no input, preserve reliable spending/economy records, and increasingly capture maintenance/tyre/repair/WoF/rego history and reminders. Verified public fuel-price contributions are a separate, explicit opt-in path; private receipts do not silently become public price reports. Any aggregate maintenance-cost web product is a later, privacy-gated proposal. Private provenance remains internally linked for audit and deletion but is never included in public price responses. High-confidence OCR results (≥.90) are applied automatically only when their destination is already known; medium (.70–.899), attention-required (<.70), and unassigned station price-board results require explicit confirmation.

Admin station pricing offers two independent actions: upload a photo into the background OCR queue, or enter prices manually for immediate application. Admins may also upload a price-board photo without selecting a station. The queue then requires station selection and price review before applying it.

**Fuel-only L/100 km** economy is only computed between valid full tanks. Partial-fill litres/cost are accumulated; missed fills, non-increasing odometers, or unreliable chains yield `null`. Pump price is the comparable public value; loyalty paid price remains separate. Freshness states are Very fresh (<1h), Fresh (1–6h), Recent (6–24h), Old (1–3d), and Stale (>3d).

The implementation audit dated 2026-10-22 covers account/vehicle/fill-up workflows, discovery, personal metrics, and operational review. The 2026-11-01 **product-plan update** promotes vehicle maintenance history and basic sourced reminders to the next staged product-design track, while they remain **not established as implemented**. **BEV and PHEV charging-cost recording, honest estimates, petrol/diesel hybrid classification and multi-energy vehicle views are promoted into the core staged vehicle-companion product**. Advanced live charger networks, smart-car/charger integrations, financial rewards, marketplace, subscriptions, navigation, and fleet functionality remain later extensions. The existing Quick Capture API and OCR status do not prove those EV features are implemented.


## Powertrain and electricity product decisions (2026-11-02; design only)

- Owners select the actual powertrain: combustion, non-plug-in petrol/diesel HEV, BEV, or petrol/diesel PHEV. A non-plug-in petrol HEV should see fuel recording without a spurious charging action; BEV should not have to complete a petrol receipt.
- BEV charging sessions are first-class private events. A public charging screenshot can be stored immediately and analysed later; at home, owner-entered tariff, metered kWh, occasional receipts/imports, or a clearly labelled monthly estimate should avoid mandatory nightly data entry.
- PHEVs need one private vehicle timeline with two energy streams and a cost breakdown, not guessed electric driving shares. Full-cost/km needs aligned mileage and adequately complete fuel/charging records. Petrol/diesel HEVs use the applicable fuel and RUC rules.
- NZ RUC classification is fuel- and vehicle-specific. As checked against NZTA on 2026-11-02, typical light BEV/eligible diesel-hybrid rate is NZD 76 / 1,000 km, petrol PHEV NZD 38 / 1,000 km, while non-plug-in petrol HEVs do not pay RUC solely for being hybrids. Source- and date-version rates; exemptions and future legal changes remain relevant. **RUC licence purchases and accrued RUC must not be double counted.**
- Keep *actual paid*, *observed electricity*, *vehicle-reported consumption*, *estimated* and *hypothetical savings* visibly distinct. A battery SOC photo is neither an energy meter nor battery-health diagnosis. Home address, charge times, electricity plan and invoices remain private; public charging intelligence follows separately reviewed opt-in and licensing controls.
- [Detailed electric and hybrid product specification](electric-hybrid.md) includes low-friction flows, costing rules, acceptance cases and data-source review. It **does not mean charger support is coded or released**.

## Planning direction (2026-11-01; not implemented status)

- [Vehicle-first vision and three-pass product review](vision-2026.md): private utility, photo-first capture, credible insights, public web, sustainability, experiments, and open decisions.
- [Electric and hybrid vehicle experience](electric-hybrid.md): BEV charge receipts/home costs, HEV fuel-first flows, PHEV combined costs, RUC, verified versus estimated efficiency, charging data boundaries.
- [Vehicle-care mobile journeys and acceptance criteria](vehicle-care.md): fuel, tyres, oil, repairs, WoF/rego/RUC, honest economy, unified timeline, due items, and edge cases.
- [Three web surfaces and sharing boundaries](web-products.md): authenticated owner garage, independently trusted public fuel information, and privacy-gated aggregate repair-cost insights.
- [Existing Quick Capture technical contract](quick-capture.md) remains the source for verified implementation limitations and real-device gates. Product aspirations do not override its local-save versus OCR-complete distinction.

**Decision hierarchy:** field-tested evidence > safety/privacy and accounting invariants > user outcome > feature wish list. Existing public price confidence, explicit consent, and private provenance protections must not be weakened to grow contribution volume. The maintenance/web specification is proposed future scope, not a claim of current API support.
