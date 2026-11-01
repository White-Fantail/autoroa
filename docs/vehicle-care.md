# Vehicle care: low-friction mobile experience and data specification

> 2026-11-01 product specification, **not implemented status**. Read with [vehicle-first strategy](vision-2026.md) and [existing Quick Capture contract](quick-capture.md).

## User journeys

| Situation | Fastest entry | What is saved | Optional detail later |
| --- | --- | --- | --- |
| Fuel at a station | Receipt shortcut → one photo → leave | Private capture/outbox, fuel transaction if validated | Odometer, full/partial, wrong field correction, public price opt-in |
| Need economy accuracy | Dedicated receipt + odometer shortcut or separate odometer photo | Timestamped odometer, tied to the right vehicle and optionally fuel event | Correct misread digits; choose full/partial setting |
| Tyre puncture | Vehicle → Tyre repair → optional invoice/photo | Service event with repair type/date/cost if known | Tyre position, workshop, tread/warranty, linked invoice |
| Tyres changed | Vehicle → Tyres → replacement/invoice | Replacement event + cost | Tyre set/positions, brand, size, install km, expected follow-up |
| Oil/filter service | Service → invoice photo OR quick "Oil service" action | Date, event, expense, evidence | Oil spec, workshop, current km and next due date/km |
| WoF completed | WoF → photograph label/report OR date entry | Observed expiry, pass/fail if provided, document | Follow-up repairs, inspector notes, reminder timing |
| Rego/insurance/RUC | Relevant date/odometer or document entry | Status, due date, expense/evidence when known | RUC end reading; renewal reminders; relevant official links |
| Unknown expense/repair | "Other work" → amount or photo | Unclassified private event, still recoverable | Category, related components and next action |

**Two fast paths, not one universal camera:** A known repetitive operation such as refuelling should go straight to camera. An event without a photograph (for example, noticing a puncture) must remain quick to record from a category action. Any photo path auto-saves locally first and may enrich the event later; it does not require completion of OCR before the driver leaves.

## Suggested information model (conceptual only)

- **Vehicle**: owned identity, nickname, fuel type, registration identifier kept private, odometer unit, optional user-configured default fill status, user timezone, optional household permissions in later phase.
- **Capture and source**: photo/document reference, capture timestamp, account/vehicle scope, local/network/OCR status, evidence type, extracted values, confidence/provenance, review corrections, duplicate grouping, deletion state.
- **Fuel event**: date, service station candidate, grade, litres, observed pump price (if present), actual amount paid/discount, full/partial/unknown, verified odometer link, source and confidence. Pump price and paid price are never interchangeable.
- **Odometer observation**: reading, unit, observed date, source and correction history; do not backfill or override with GPS guesses.
- **Service event**: category and subtype, performed date, garage (if known), cost/currency (optional), odometer at service (optional), parts/notes, work status, attachments, invoice total and optional component line items.
- **Component lifecycle** (later, not required for MVP): tyres by position/set; brake parts; battery; install/repair/rotation/replacement events. A single event can refer to multiple components.
- **Due item**: WoF, rego, RUC, insurance, service, tyre recheck, etc.; source of due date/km, confidence, recurrence rule and version, sent/snoozed/completed history.
- **Expense classification**: fuel vs tyres vs servicing vs repair vs compliance vs insurance vs other. Use one primary payable total with component allocations; never sum an invoice total and its line items twice.
- **Contribution**: separate optional event linking *eligible* evidence to a moderated public fuel-price observation, independent of private ownership identity in public output.

Identifiers, exact location, plate, VIN, raw invoice, attachments, odometer and driver notes are private by default. Source lineage must support correction, revocation and deletion. A record saved locally but not uploaded is clearly distinguishable from a server-confirmed event.

## Screen priorities

1. **Home**: one obvious Fuel camera action; optional receipt+odometer shortcut, selected vehicle, concise "saved/processing/needs review", next due action, recent spend. Do not make price reporting a mandatory blocking step.
2. **Vehicle timeline**: fuel and maintenance events chronologically, filterable/searchable; thumbnail evidence and edit/delete action; explicit missing fields without shaming.
3. **Care**: next due WoF/rego/service/RUC/tyres, simple "Add work" categories, reminders with source. Urgent items should be factual, not artificial alarms.
4. **Insights**: actual spend, fuel and non-fuel costs, properly qualified economy and cost/km, completeness indicator. No invented figures where insufficient records exist.
5. **Capture inbox**: quick correction for exception cases with a small actionable field set, local retry and OCR status; old unresolved events remain accessible.
6. **Settings/exports**: vehicle selector, explicit sharing controls, notification cadence, record export and account deletion.

## Detailed acceptance cases

### A. Receipt-only

- In an already configured vehicle, one shortcut opens receipt camera with no intermediate form.
- After shutter and storage success, app may close without user Save/Submit. UI accurately says **saved on device**, not "fully processed."
- No odometer → spend and litres can be shown; calculated fuel economy remains unavailable until valid readings and tank boundaries exist.
- Low-confidence or contradictory receipt → needs-review private inbox, not a silently guessed record or publicly posted pump price.
- Wrong vehicle / mixed household → never auto-assign based solely on last session when an explicit ambiguity is detected.

### B. Economy integrity

- Two credible full-tank events with ordered odometers and no missing intervening fills permit a measured segment.
- Explicitly marked partial fills can be included inside a bounded full-to-full segment when the chain is complete; unknown/missing stops break reliability.
- Reset/rollover, odometer decrease, imported historical readings, calendar date changes, different units and impossible consumption create an anomaly requiring review.
- A per-vehicle habitual-full default needs prior explicit owner selection and easy exception correction; unknown does not silently become full.
- Show sample distance, included litres, missing evidence and reason unavailable rather than a fake decimal.

### C. Maintenance, tyres and reminders

- A driver may log a tyre puncture without invoice, cost or odometer; record is still useful.
- An invoice with oil + filter + brake work is a **single paid service event** with optional categories, not three duplicated paid records.
- Warrant fail → can create follow-up action without marking the vehicle safe or creating an issued expiry.
- A service performed today with no stated next interval does not automatically create an authoritative due date. A user may set a schedule.
- Date/km trigger, source, timezone and notifications are testable; lacking a current odometer never hides a calendar due reminder.
- Attachments remain searchable through service history and exports even after OCR correction.
- A household member sees only explicitly shared vehicles, never all account documents by default.

### D. Failure/recovery

- Offline capture, killed app, denied camera/photo permission, expired auth, storage full, duplicate upload, same invoice photographed twice, device clock drift and account switch all have defined states and safe recovery.
- Duplicate detection should suggest a merge/review, not erase a legitimate separate repair on the same day.
- Declined notifications do not disable due-item display.
- Private originals are never exposed in public pages or station-price APIs.

## NZ-specific policies and boundaries

**WoF:** The inspection frequency began changing on 2026-11-01 and has a further phase from 2027-11-01; current issued expiry remains valid. An exact printed/officially obtained expiry is the preferred field. Rule-derived suggestions must be marked estimated and tied to the correct vehicle category, age, registration timeline and effective rule version. Refer to:
https://nzta.govt.nz/projects-and-consultations/have-your-say/past-consultations/considering-changes-to-light-vehicle-inspections/changes-to-light-vehicle-inspections

**Rego / RUC:** do not treat registration expiry, fuel purchase, insurance or a distance licence as equivalent. RUC remaining distance needs an actual reading. The official NZTA app is a user-facing reference, not an assumed API access entitlement:
https://nzta.govt.nz/about-us/app

**Safety:** A WoF is a periodic legal inspection, not a guarantee of current safety or a comprehensive mechanical service. Repair/maintenance information is not a substitute for professional inspection:
https://www.consumerprotection.govt.nz/help-product-service/cars/fixing-your-car

## Scope cut for a usable first vehicle-care beta

**Must:** named vehicle, basic category actions, photo optional, private record with date/amount/optional mileage, one chronological timeline, attachment retrieval, basic sourced due items, honest totals, robust review/outbox, deletion/export design.

**Should:** OCR enrichment of repair invoices, editable invoice itemisation, tyre position metadata, conditional km reminders, multiple vehicles and phone notifications.

**Later:** parts price benchmarking, automatic NZTA synchronization if legitimately accessible, complex component inventory, family sharing with permissions, external garage integrations, booking marketplace, resale certification, safety prediction and fleet management.

## User research and decision checkpoints

Observe at least these tasks without explaining the app first: "Photograph a fuel receipt", "Log that a puncture was repaired without a receipt", "Find what you paid for your last oil service", "Check when WoF is due", "Why is this fuel economy blank?". Record taps, time, errors, correction burden, confidence in the answer and whether a driver would use it again at their next real event.

A feature only passes product review when: it saves real user effort, accurately labels unknowns, makes evidence retrievable, respects privacy and has a testable benefit. More screens and more captured fields are not themselves success.
