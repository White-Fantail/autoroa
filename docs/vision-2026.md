# Autoroa: vehicle-first product strategy

> Planning baseline: 2026-11-01 (NZ). **Proposal, not a statement of implemented features or release readiness.**
> Product promise: **Capture once, stay in control of your car, and share only what you choose.**
> Decision priority: private user utility first; trusted public information second; commercial products third.
> Related: [current implementation audit](roadmap.md), [Quick Capture contract](quick-capture.md), [vehicle-care specification](vehicle-care.md), [web products and data boundaries](web-products.md), [existing product decisions](product.md).

## 1. The job to be done

For ordinary New Zealand car owners, vehicle administration is fragmented across fuel receipts, the odometer, paper servicing invoices, tyre repairs, WoF/rego/RUC dates, and multiple apps. The user's actual goal is not to submit data to Autoroa. It is to **spend less time keeping a reliable, searchable record**, know what the vehicle costs, and avoid forgetting an important service or deadline.

Autoroa therefore has two connected but distinct products:

1. **Private mobile vehicle companion**: exceptionally fast entry, reliable records, accurate insights, actionable due items, and portability. It works even if nobody else contributes data.
2. **Web information service**: up-to-date, source-labelled fuel-price discovery first, then aggregate maintenance and ownership-cost intelligence when sample quality and privacy permit it. Public pages must stand on their own merits, not merely repeat app screens.

A signed-in **private web garage** may offer the same owner's timeline, documents, charts and exports on a larger screen. It is NOT the same dataset, access model, or product as the public web information service.

North-star question: **Would a driver keep using the app for their own car if public contributions and rewards disappeared?** If not, fix private utility before trying to grow a contributor network.

## 2. Positioning and alternatives

- Gaspy already offers NZ crowdsourced fuel prices and a participation game; duplicating a map plus points is not a defensible sole proposition.
- NZTA's app already displays official vehicle details, WoF/rego dates and RUC information. Autoroa should complement authoritative records, never imply its manual dates replace NZTA records.
- BONNET and Autofy already address vehicle compliance, servicing reminders and/or workshop workflows.
- Our candidate differentiation is **photo-first capture that becomes a trustworthy lifelong vehicle ledger**, bringing fuel costs, real-world economy, repairs, maintenance documents and next actions together with minimal data entry. Aggregate web products follow as a responsibly governed by-product.
- These are competitive positioning hypotheses, not proof of demand. Validate with actual local drivers.

References checked 2026-11-01:
- https://www.gaspy.nz/
- https://nzta.govt.nz/about-us/app
- https://bonnet.co.nz/
- https://www.autofy.co.nz/

## 3. Target users and order of expansion

**Primary beta:** NZ driver of one or two petrol/diesel/hybrid vehicles who saves receipts, is concerned about running costs and periodically pays for servicing/tyres. Use a small Christchurch-area pilot for direct observation; the product should not assume Christchurch-only geography.

**Secondary:** multi-driver household sharing a vehicle; careful owner building resale/service history; small owner-operated business with a few vehicles. Shared permissions and fleet administration should not complicate first-run onboarding.

**Not first:** workshop booking marketplace, official compliance database, insurance underwriting, heavy-fleet management, or EV charging network. EV and RUC support need their own documented rules and can be phased, not misrepresented as complete.

## 4. One consistent capture model

Each capture is stored **immediately as a private, durable local event** and then uploaded/processed asynchronously. It has a clear status: saved on device, waiting to upload, processing, recorded, needs review, or failed with recovery. A photo being saved is not equivalent to a confirmed record. No Save button or form after routine camera capture; the app should be dismissible immediately. Native OS limitations around suspended or force-quit apps are explicit, not hidden.

### Fuel: default path

**Home/lock-screen shortcut or in-app action → camera → receipt photo → done.** Vehicle selection is remembered; if ambiguous, place the entry in a private inbox rather than silently attaching it to the wrong car. Fields extracted when supported: merchant/station candidate, transaction date, fuel grade, litres, pump/unit price, discounts, total paid, and invoice evidence. Values are validated for consistency. Odometer remains optional, never invented.

An explicitly configured **receipt + odometer** shortcut opens a second camera after the first; Skip remains available. A separately configured **odometer-only** capture can supply occasional readings between fill-ups. Do not automatically infer a mileage reading from photo location, time, GPS distance, or the previous reading. Never require an odometer every refuel.

Full-tank correctness is the hidden usability challenge: fuel economy needs valid full-to-full boundaries. During optional one-time setup, offer a plain-language preference such as "I normally fill the tank"; using it as the default requires the driver's explicit choice, with an easy per-fill correction. No selection means unknown, not full. Partial fills, missed visits and inconsistent readings must create honest gaps rather than attractive but false L/100 km values. Distinguish historical spending (available without odometer) from verified economy (not always calculable).

### Maintenance: same muscle memory, different data

**Add work → choose a common category or photograph invoice → recorded privately → adjust only if necessary.** Let users start with a category-first manual quick entry even if they have no receipt. Suggested categories include oil/filter service, tyre puncture/repair, tyre replacement/rotation, brakes, battery, other repair, periodic service, WoF, rego, RUC, insurance, and other expenses. Keep them extensible, not a giant form.

A maintenance capture can propose category, service date, garage, amount, odometer, parts, next due date/km and attachments; it must distinguish extracted fact from suggested interpretation. A service invoice may contain multiple line items: retain the original invoice and enable a single service event with optional line items, rather than inventing duplicate expenses. If OCR is uncertain, save a private draft and make correction easy.

Use a unified **vehicle timeline** (fuel + repairs + inspections + expenses), next-actions view, document vault and cost breakdown. Search and export are core trust features, not an optional afterthought.

### Reminder contract

User-entered or verified expiry/due dates drive reminders. Unknown does not mean overdue. WoF and rego dates are distinct from a booked inspection or service date. A combined date/odometer threshold is satisfied when **either** configured trigger is reached; if no reliable current odometer exists, show the km trigger as unknown and keep date reminder active. Reminders should be cancellable, snoozable and explain their source. Safety-critical advice cannot be replaced with a generic "safe until WoF" implication.

**New Zealand policy alert:** WoF inspection rules begin changing on **1 November 2026**, phased again on **1 November 2027**. Existing issued WoF expiry dates remain unchanged; new frequency matters at the next inspection. Do not derive a legally authoritative expiry from a hard-coded annual interval. Prefer an observed expiry date; if prediction is ever provided, label it provisional and date/version its rule source. Verify the current official guidance before release:
- https://nzta.govt.nz/projects-and-consultations/have-your-say/past-consultations/considering-changes-to-light-vehicle-inspections/changes-to-light-vehicle-inspections
- https://vehicleinspection.nzta.govt.nz/news/1-november-virm-changes-are-now-available-to-preview

## 5. Value immediately after the first capture

A single receipt already shows **fuel spend, litres, price paid, transaction history and an organised digital receipt**. A repair invoice yields **what was done, by whom, when, for how much, and where to find the evidence**. Even with no odometer and no community data, a user has gained something.

After a few events, explain fuel-price change versus user discounts, rolling cash outlay, annualised trends only when the time horizon is meaningful, and a timeline of servicing work. After enough **valid** full-tank boundaries and odometers, show measured L/100 km and cost/km; otherwise explicitly explain why economy is unavailable and offer the least burdensome next action.

Keep fuel, servicing, tyres, inspection/rego, insurance and RUC as separate cost categories; avoid double counting invoice totals and line items. Separate observed values, calculations and estimates. Don't imply that an isolated expensive repair is a vehicle-wide market benchmark.

## 6. The public contribution flywheel is optional

The private record is created first. A subsequent, lightweight and **explicitly opt-in** action can contribute an eligible fuel price observation, subject to station identity, evidence freshness, fuel grade, pump-price versus paid-price classification, anti-fraud checks and moderation. The default is private. A generic private receipt must never silently become a published station price. Showing the driver the contribution outcome, including rejection or expiry, makes the loop credible.

Price discovery should be honest about coverage. Each displayed result needs station, grade, unit, observation time, source/confidence and a visible stale/unknown state. Do not show an invented "current price" for unobserved stations. Distance-adjusted savings estimates must disclose assumptions and should not overpromise.

Maintenance invoices are **not published** as individual events. Any future public repair-cost or maintenance-frequency insight requires a separate purpose notice/permission where applicable, an adequately sized and representative cohort, coarse grouping, suppression of rare cells, anti-reidentification analysis and visible sample limitations. "Anonymous" labels alone are insufficient.

Before promising nationwide fuel coverage, build a region-by-region dashboard tracking coverage, independent contributors, accepted observations, freshness, staleness, corrections and cost of moderation. Fill sparsely covered areas through targeted incentives or partnerships only after economics and trust are verified.

## 7. Sustainable business choices, not speculative rewards

**First revenue hypothesis:** useful, clearly labelled business-to-consumer or partner-funded offers (service/tyre shops, roadside assistance, fuel partners) only where drivers save real money and sponsors cover the benefit. Sponsored placements must never alter independent price ranking without conspicuous disclosure.

**Second hypothesis:** premium convenience for engaged owners (multiple vehicles, household permissions, extended history/export, advanced ownership insights), with the basic capture and records remaining genuinely useful for free.

**Third hypothesis:** separately licensed, privacy-safe aggregate reporting or workshop products if data coverage, sampling bias, user permissions and customer willingness to pay are demonstrated. No sale of personal trip histories, registration numbers, invoices or raw receipt photos.

Do not promise real-value points while existing rewards are only gamified scores. Before any financial reward, model OCR/storage/notification/support costs, fraud, redemption, sponsor reconciliation, complaints and NZ consumer/privacy rules. Revenue is not assumed merely because data exists.

## 8. Release sequence and experiment gates

| Gate | User-visible outcome | Minimum validation before promotion |
| --- | --- | --- |
| A. Trustworthy fuel capture beta | One tap/one photo; optional odometer; private record; understandable queue/review; recover offline data | Real iOS/Android devices and edge cases in the existing QC roadmap; baseline timing and critical-field accuracy on representative NZ receipts |
| B. Vehicle care alpha | Fast oil/tyre/repair/WoF/rego event entry, documents, due items and unified timeline | Observe real owners adding a repair without instruction; date/km reminder correctness and no duplicate cost |
| C. Private owner web | Secure, readable record/timeline and export across devices | Owner-only access tests, deletion/export accuracy, consistent totals versus app |
| D. Useful public fuel web | Trusted prices, freshness, geographic coverage and meaningful correction paths | Publish only eligible evidence; monitor stale percentage, correction rate, contributor diversity and per-region coverage |
| E. Aggregated maintenance insights | Limited regional/category ranges with sample counts and uncertainty | Privacy/consent review, suppression tests, minimum sample and bias assessment; otherwise remain unpublished |
| F. Paid/partner experiments | A real, measurable benefit to both driver and payer | Documented unit economics and a small genuine pilot, not assumed revenue |

A and B may be designed together; A should be dependable before broadly launching B. Web technical infrastructure exists in part, but product-level delivery gates still require verification.

### Proposed pilot, not established targets

Recruit around 20–30 drivers with different fuel brands and at least a few historical servicing records; measure over multiple refuelling cycles rather than 7-day logins alone. Record initial baselines before locking targets. Candidate success thresholds **to test and revise**, not claims of current performance: most routine captures end without typed correction; the user can retrieve an invoice within seconds; most pilot users voluntarily use capture again on their next eligible fuel event; no accepted fuel/maintenance record is lost in offline/restart testing; no private event appears publicly without the required contribution pathway. If these fail, simplify before adding features.

Track: median and p95 time from tap to local save; no-form completion rate; OCR critical-field accuracy, false accept/review percentages; capture-to-record resolution; offline recovery; full-to-full valid economy coverage; real upkeep events per owner; next-event reuse; public eligible price observations, unique sources, age and geographic spread; export/deletion outcomes; OCR cost per useful record and moderation cost per public observation.

## 9. Explicit trade-offs and open decisions

| Decision | Current planning default | Evidence that could change it |
| --- | --- | --- |
| Single-purpose fuel app vs broad vehicle management | Broad **value proposition**, staged implementation; do not ship an empty feature menu | Pilot owners do not use maintenance entry or reminder functions |
| Manual entry vs OCR on every event | Camera primary where a document exists; 2–3-tap structured event when none does | OCR misses key repair details or costs too much |
| Automatic full tank | Never assume; optional explicit per-vehicle preference with correction | Too many partial fills or missed fills invalidate the metric |
| Manual dates vs NZTA sync | Start with user-entered/verified dates, source-labelled | Approved, sustainable and privacy-safe access to authoritative data |
| Public maintenance prices | Withhold until sufficient consent, sample quality and de-identification | Re-identification and sampling concerns resolved |
| Geographic launch | Direct-observation Christchurch pilot, national-readiness architecture | A larger region has better partners/representative cohort |
| Incentives | Actual user utility, then optional funded offers | Price coverage requires affordable, quality-controlled incentives |

## 10. Iterative product-review record

### Review 1: usefulness and retention

**Failure mode:** recording is still work with no payoff. **Correction:** the first photo must immediately become a useful private receipt and cost event; no request to contribute to a map during camera capture. Offer reminders and document retrieval before points. **Remaining uncertainty:** how much of this behaviour owners will repeat; validate in observed sessions.

### Review 2: mathematical and evidentiary honesty

**Failure mode:** attractive but false fuel economy, stale fuel prices, or unreliable repair benchmarks. **Correction:** unknown odometers/full-tank states stay unknown; public pump prices require explicit verified evidence; maintenance market data is withheld until representative enough. **Remaining uncertainty:** what share of receipt formats can be auto-accepted safely; benchmark first.

### Review 3: scope, competition, privacy and cash flow

**Failure mode:** rebuild Gaspy, NZTA, BONNET and an entire workshop marketplace at once, with no unique adoption loop or viable cost structure. **Correction:** prioritise one-photo private ownership ledger, then routine vehicle care and trusted optional public web data; defer complex marketplace/fleet/rewards, separate public/private data and prove partner economics. **Remaining uncertainty:** which task makes users return; measure the next real refuel/service event, not vanity signups.

## 11. Working rules for future planning

1. Product assumptions, source-verified facts, implemented code, field-tested releases and commercial hypotheses must remain separately labelled.
2. Any proposed feature needs a user job, a minimum-entry flow, failure path, privacy classification, and observable acceptance test.
3. Review the hypothesis against **usefulness → trust → effort → viability**. If weaker after each review, narrow or defer.
4. Document technical work in the existing roadmap with evidence; updating this proposal is not implementation.
5. Do not silently broaden user data sharing or weaken the Quick Capture safety contract in pursuit of growth.
