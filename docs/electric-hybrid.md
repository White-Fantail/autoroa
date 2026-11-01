# Electric and hybrid vehicle experience — BEV / PHEV / HEV

> Product design update: 2026-11-02 (NZ). **PLANNED, not a statement of implemented functionality.**
> The existing source audit remains dated 2026-10-22; existing fuel/receipt flows do not establish usable charging support.
> Read with [product vision](vision-2026.md), [vehicle-care experience](vehicle-care.md), [web products](web-products.md), and [roadmap](roadmap.md).

## 1. Correcting the original product gap

Autoroa must be valuable to the owner **independently of propulsion type and public participation**. Treating EV charging as a distant extension is incompatible with a general vehicle ownership platform. The minimum product must support the *recording, costs and useful insight* of all common powertrains; advanced charger-network integrations and live chargepoint discovery may come later.

The central promise is **"Capture fuel or charging once, understand what the car really costs, and never lose its maintenance history."** "One snap" still fits a fuel or public charging receipt, but home charging may not create a receipt. Requiring users to photograph a home charger each night would destroy the value proposition.

### Correct vehicle classification at onboarding

| Powertrain | Main energy inputs | Default home action | First-use value |
| --- | --- | --- | --- |
| Petrol/diesel ICE | Pump fuel | Scan fuel receipt | Fuel spend, pump history and later measured L/100 km |
| Petrol HEV (non-plug-in) | Pump petrol only, recovered energy is not purchased externally | Scan fuel receipt | Measured petrol economy and cost; no artificial charging sessions |
| Diesel HEV (non-plug-in) | Diesel fuel; RUC may apply | Scan fuel receipt | Cost and actual RUC obligations |
| BEV | Grid/solar/public electricity | **Add charge**: recent public receipt/screenshot OR one-tap home charging method | Charging outlay, home/public split, charging plan comparison, RUC and due items |
| Petrol PHEV | Pump petrol + external electricity | **Fuel** and **Charge** as equal first-class actions | Combined actual energy cost, component breakdown, RUC and realistic blended cost/km |
| Diesel PHEV | Diesel + external electricity | Fuel and Charge | Combined energy expenses and applicable RUC; do not apply petrol PHEV rate |

Selecting a powertrain configures **what the app asks for**, not only how a graph looks. Allow changing classification with explicit review of previous events and RUC rules. No assumed EV battery capacity, efficiency, tariff, home availability, driving mode or vehicle connection. Preserve source values across transitions. Multi-vehicle owners get a stable selected vehicle and safe switching.

## 2. Start-to-finish user flows

### A. BEV owner, public charger — photo-first

1. Home/shortcut **Add charge** → camera/gallery for invoice, email screenshot or charging-app session screenshot. A manual "No receipt" path is always available.
2. Locally save evidence and a private, recoverable charge draft immediately. OCR or extraction can infer provider/site, timestamp, energy delivered (kWh), paid total, unit rate and extra fees only if shown. No Save step for a routine confident capture; user can leave at once.
3. If there are missing or contradictory values, show a compact **Needs review** inbox. A screenshot can contain account IDs or precise times and remains private. Never assert successful server processing merely because a photo is locally stored.
4. Result: **"That charge cost $X and added Y kWh"**; if measured information is absent, show just the known cost/session. Optional odometer and battery SOC do not block recording.
5. Any optional public charger update needs a separate opt-in, eligible station, observed tariff and time. A *personal paid total* is not automatically the public kWh tariff.

### B. BEV owner, home charging — no nightly typing

1. Optional one-time setup: home charger type, electricity plan and **time bands** (peak/off-peak/free hour), GST handling, and energy source. Provide a clear Skip option. These fields are private, versioned and editable.
2. Offer three honest data paths, ranked by effort and reliability:
   - **Observed charge**: import a smart-charger CSV/export, upload screenshot of completed session or enter metered kWh (best evidence, not an assumed existing integration).
   - **Quick charge**: remember Home + applicable tariff; enter **one number** (kWh) if available, or photograph the completed charger screen. Date/time is a suggested default.
   - **Estimated charging budget**: optionally use the owner's *explicitly supplied* typical kWh/100 km or reference assumption and actual odometer difference. Label this **estimate**, not an observed charge or energy efficiency result.
3. Since many owners plug in daily, **do not require one form/event every night**. If no automated measurement exists, show an honest monthly **estimated** electricity budget from real distance and the owner's assumptions, then invite occasional reconciliation against a charger bill/export. Do not silently fabricate session events.
4. Provide **"Charge cheaper"** insight only where the user has entered a real tariff: compare measured consumption under their actual time bands versus a clearly labelled counterfactual. Show off-peak share and estimated tariff saving with methodology.
5. If a household plan has time bands, solar export opportunity cost, subscription, free-period caps or charging losses, disclose what is and is not included. Do not use a generic universal NZ electricity price for actual personal expenses.

### C. PHEV owner — the first feature is combined running cost

1. Two prominent actions: **Fuel receipt** and **Charge**. Both link to the same vehicle timeline and cost summary. No requirement to decide petrol vs electric mode for every trip.
2. Show **fuel NZD + electricity NZD + distance-based RUC accrued** separately, with a **total cost per 100 km** only when the relevant time window has a trustworthy distance baseline and sufficiently complete costs.
3. Compare periods to help the driver understand whether *their own* charging habits change overall cost. An "EV driving %" is available only if supplied by the car or a credible distance breakdown; **never derive it from the ratio of kWh and litres**.
4. If either energy source is missing or only estimated, a blended cost figure must be marked partial/estimated. Do not declare a PHEV to be "petrol-only" simply because no public charging record exists.

### D. Non-plug-in HEV owner

- Show the same frictionless fuel and odometer history as a conventional petrol/diesel car; make real-world L/100 km, fuel cost/km and servicing useful.
- A regular petrol HEV does **not** need charging logs and should not see charge prompts. Regenerative braking is not purchased electricity.
- A diesel HEV can incur RUC; classify fuel and obligations by the actual legally relevant vehicle type, never by the word "hybrid" alone.
- Do not invent battery SOC or electric-only mileage from fuel receipts. Battery care and replacement/warranty documents remain normal maintenance events.

## 3. An honest measurement system

### Consumption and cost equations

All ratios require a **consistent, credible odometer distance in the same analysis window**; label vehicle display vs charger/wall electricity distinctly.

- **Petrol/diesel fuel economy**: measured litres / valid full-to-full distance × 100, only when the fuel chain is complete. The existing full-to-full integrity rule stays in force.
- **BEV measured energy usage from wall/charger**: observed *grid/charger-delivered* kWh / reliable driven distance × 100 is a **wall-to-distance charging consumption rate**, not necessarily battery-to-wheel efficiency. It can be biased by charge timing, missing sessions, battery SOC changes and charge losses. Only publish a comparable measured window when beginning/end energy balance is known and charging records are sufficiently complete; otherwise use an "energy bought per 100 km" provisional ratio or no efficiency figure.
- **Vehicle-reported battery consumption**: a separate value from a credible in-vehicle trip report, with provenance, window and units. Do not mix into grid energy totals.
- **Energy cost**: sum actual billed electricity amounts, or metered kWh × applicable observed tariff bands plus fees where known. Estimated costs stay separate and do not become bank-spending facts.
- **PHEV blended drive-energy cost/km**: (observed petrol/diesel paid + observed electricity paid) / distance over a matched complete window. RUC, maintenance and other costs can be layered on separately.
- **RUC allocation**: for a qualifying vehicle, rate effective for that vehicle/date × distance in the relevant licence period, with official licence constraints. Show **accrued driving cost** separately from **cash paid when buying a licence**. A paid RUC licence is a prepaid asset/expense transaction; counting both the purchase and accrued RUC in a single total double-counts it.

**Calculation eligibility**: use a confidence/coverage meter (complete / partially observed / estimated / unavailable); validate odometer resets and non-monotonic readings, irregular imports, charger data coverage, price plan changes, fees, currency, time zones, unit conversions and duplicated screenshots. No mysterious precision to two decimal places when the data is only a budget estimate.

### State-of-charge, range and battery health

SOC (%) and the instrument-cluster range estimate are **snapshots**, not measured purchased energy, actual battery degradation or universal health. Never compute battery State of Health (SoH) from a few SOC changes, advertised battery capacity or charging speed. Store genuine manufacturer/diagnostic battery-health documents with source, date and caveats; do not issue battery-fault or safety diagnoses from app heuristics.

### Sample illustrative comparison (not NZ market price)

If a driver records 30 kWh charged at a genuinely applicable off-peak price of NZD 0.15/kWh, the energy-only cost is NZD 4.50 **before any separate fees**. If the same 30 kWh were billed at an actual public rate of NZD 0.65/kWh, the energy-only amount would be NZD 19.50. That **NZD 15 difference is a hypothetical tariff comparison**, not automatically "money saved": charging losses, available capacity, idle/session fees, time, location and electricity-plan restrictions can change the result. Actual user savings need actual usage/tariff evidence, a plausible baseline and honest assumption labels.

## 4. NZ compliance and cost reporting — dated sources

As of the 2026-11-02 review, NZTA identifies RUC obligations and *typical current rates* for light vehicles (up to 3,500 kg in the applicable categories):
- Most BEVs and relevant diesel hybrids: **NZD 76 per 1,000 km**.
- Plug-in **petrol** hybrids: **NZD 38 per 1,000 km**.
- Non-plug-in **petrol** hybrids: do **not** buy RUC solely because they are hybrids; petrol excise duty is paid in fuel.
- Plug-in **diesel** hybrid classification differs from petrol PHEV: do not assign the petrol PHEV discount.
- RUC administration fees exist and depend on purchase channel. Actual legal obligation depends on vehicle type, weight, licence class, effective dates and exemptions. Rates may change; store a dated official source and rule version, and allow reviewing an actual purchased licence. A mileage-based **remaining RUC distance** needs a known licence end and current odometer, and should warn before running out.
- Official RUC purchases must go via NZTA/approved services; Autoroa only records/reminds unless separately authorised.
- The proposed wider transition from petrol excise to electronic RUC is not treated as already in effect. Legal-rule refresh is a release and ongoing maintenance requirement.

Official sources:
- https://www.nzta.govt.nz/vehicles/road-user-charges/about-ruc
- https://nzta.govt.nz/vehicles/road-user-charges/ruc-rates-and-transaction-fees
- https://nzta.govt.nz/vehicles/road-user-charges/replacing-fuel-tax-with-road-user-charges
- https://www.eeca.govt.nz/for-homes/vehicles/charging-your-ev/
- https://www.eeca.govt.nz/for-homes/vehicles/smart-ev-chargers/

**Cost presentation rule:** "energy-only", "energy + RUC", and "total vehicle running cost" are distinct measures; maintenance, tyres, rego, insurance and depreciation (if modeled at all) should not silently appear/disappear. Depreciation, battery replacement, environmental savings and purchase-versus-ICE comparisons require explicit assumptions; never imply an actual financial saving from a fabricated baseline.

## 5. EV/PHEV service value and reminders

BEVs still need tyres (including pressure, rotation and replacement), brake service and fluid checks where relevant, cabin filters, WoF, rego, insurance and RUC. PHEVs also need combustion-engine oil/filter and other model-specific engine maintenance. HEVs share normal fuel/engine-related service needs. Make service suggestions configurable or linked to *verified manufacturer instructions*, not generic uniform intervals.

Vehicle home panel examples:
- "RUC licence distance remaining: 850 km" **only if** an actual licence end and reliable current odometer are known.
- "The last 5 observed public charges cost NZD X; home sessions are not yet fully measured."
- "Your oil service is due by date X" only with user-entered or sourced schedule.
- "Tyres last replaced at Y km" from a dated owner record.
- An optional warranty record can track battery, drivetrain and tyre warranty terms with sourced documents; **not** a battery-health prediction.

## 6. Public web: EV usefulness with a defensible scope

**Private owner web garage**: fuel and charging sessions on one timeline; home/public/solar/unknown energy source; observed versus estimated running costs; period costs; charge receipts; RUC licence/reminders; vehicle-specific maintenance; editable tariff history and export.

**Public EV information** should progressively include:
1. **Initial**: clear independent explainers for charging cost and RUC calculations; tariff-comparison calculator with user-entered settings, no claim of live charging prices.
2. **Next**: public charger map/list sourced from licensed data with connector, power, operator, source timestamp and when legitimate availability feeds exist their actual live status. Unknown/offline must be distinguished from available. Show source date and access restrictions.
3. **Later**: verified charging tariffs by location/connector/time/session fees and user reports with independent moderation. Avoid comparing "$/kWh" alone when charging sessions have idle, connection, time-of-use or parking fees. Make payment/provider terms clear.
4. **Only after representative data/privacy review**: aggregated real-world kWh/100 km and running-cost distributions, with model/region/cohort limits, no individual home addresses, charging times or identifiable journeys.

Potential sources to assess before integration:
- **EECA EVRoam**: live charging infrastructure data; information is distributed via apps/websites, but developer access, attribution, allowed reuse, currency and API rights must be independently confirmed, not assumed.
  https://www.nzta.govt.nz/partners/planning-and-investment/planning/transport-planning/planning-for-electric-vehicles/evroam
  https://evroam.co.nz/explore-evroam/
- **EECA charger dataset**: quarterly infrastructure snapshot, not automatically a current tariff or live-availability feed.
  https://www.eeca.govt.nz/insights/data-tools/public-ev-charger-dashboard/
- **Open Charge Map**: API with access key, mixed data-provider licenses, attribution and rate limits.
  https://www.openchargemap.org/develop/api

Charging networks such as ChargeNet already publish maps/status; Autoroa should not pretend that a new charger map alone is a competitive moat. Its advantage should be **the individual's actual multi-energy cost picture, then trustworthy comparison**, not an unverified live-data mirror.

**Sharing contract**: home location, provider-account IDs, private electricity plan/tariff, session times, SOC, trip history, invoices and odometers are private. A public charger-price submission is separate, specific and opt-in, with known provenance and rejection/correction rules.

## 7. Buildable, staged MVP and UX design choices

### Minimum usable EV / hybrid product (P1, parallel with narrow vehicle care)

- [ ] Vehicle energy profile: ICE / petrol HEV / diesel HEV / BEV / petrol PHEV / diesel PHEV. Appropriate actions and unit labels; can be changed safely.
- [ ] BEV **Add charge**: manual kWh + amount with Home/Public/Work and optional date, or photo of receipt/screenshot; local capture/outbox/review contract reused where possible.
- [ ] Home charging profile: optional reusable *actual* flat/off-peak tariff and optional manual charge kWh; permit "no readings available" without repeated prompts.
- [ ] PHEV combined ledger: Fuel + Charge actions, separated but visibly totalled without double counting.
- [ ] HEV fuel-only flow, with legal fuel/RUC classification.
- [ ] Odometer-only capture usable across all vehicles; cost/km only with reliable distance and cost coverage.
- [ ] Charging, maintenance and RUC records on the owner timeline; correct running-cost labels, private export and correction.
- [ ] An immediately useful "energy/cost summary": measured costs so far and/or clearly marked estimated monthly budget; no empty dashboard because public charge network coverage is missing.

### Next, after observed demand and data quality

- [ ] Time-band schedules, revised tariffs, receipts with session/idle/parking fees, reconciliation, useful off-peak comparison.
- [ ] Calendar/km RUC reminders and official-link handoff, license photo/receipt OCR.
- [ ] Smart-charger CSV import and selective provider APIs after permitted access and testable reconciliation; **no assumed Tesla or utility account access**.
- [ ] EVRoam / licensed live charger discovery after coverage, attribution, access and freshness are tested.
- [ ] Manufacturer-specific battery health / warranty document ingestion, vehicle trip energy where permitted.
- [ ] Solar charging allocation and home-utility bill attribution with actual meter inputs, consent and defensible accounting.

Avoid mandatory integration or expensive API reliance as a beta prerequisite. The driver with no home smart charger and no public-session screenshot still needs a useful and truthful experience.

## 8. Acceptance tests and failure scenarios (product-level)

| ID | Scenario | Accept only if... |
| --- | --- | --- |
| EHV-01 | BEV owner who never buys petrol | Onboarding and home never demand fuel litres, pump grades or a fuel receipt; charging and RUC have clear paths |
| EHV-02 | No home charger integration | Owner can enter a single kWh number, skip it, or hold a **clearly labelled** estimate; no phantom charging records |
| EHV-03 | Public charging screenshot | Private evidence retained; extracted paid cost, kWh and session fees have independent confidence/review; exact location not automatically published |
| EHV-04 | Home off-peak plan | Cost uses time-band and effective-date settings; overnight band boundaries, tariff revision and missing schedule are handled, not averaged deceptively |
| EHV-05 | PHEV alternating petrol/electric | Both streams recorded and shown together; incomplete source prevents a falsely precise blended efficiency; RUC treatment follows petrol/diesel classification |
| EHV-06 | Non-plug-in petrol HEV | No charge prompts and no BEV/PHEV RUC warning; valid petrol full-to-full computation continues |
| EHV-07 | BEV RUC expiry | Actual licence end + credible odometer → distance remaining; missing licence data → unknown; no exact future obligation based on outdated rate |
| EHV-08 | Cost report with licence purchase | A $76 licence purchase and an equivalent $76 accrued RUC period do not become $152 of operating costs |
| EHV-09 | Battery SOC photo | SOC / advertised range do not become measured kWh, health score or guaranteed driving range |
| EHV-10 | Multi-vehicle household | A charge belongs to the correct vehicle; private plan, screenshots, locations and invoices never cross account/vehicle or public boundaries |
| EHV-11 | Offline duplicate/import | Source images retained through restart; duplicate screenshot is reviewable, not billed twice or silently discarded |
| EHV-12 | Web charger status/tariff | Only licensed, sufficiently fresh status is labelled live; unknown is not "available"; price excludes/notes fees clearly |

## 9. Second-pass review: what could make EV owners quit?

**Failure: manual nightly charging is more work than a spreadsheet.**
Correction: optional home-plan setup and recurring *estimated budget*, occasional reading/screenshot/CSV; do not invent a charge history. Validate repeat usage through owner tasks without prompting.

**Failure: users celebrate "EV savings" built on missing fees and RUC.**
Correction: separate actual paid cost, estimated energy, RUC accrued vs licence cash purchase, and hypothetical comparisons. Only issue an actual user-specific savings statement when the baseline is user-provided and coverage is adequate.

**Failure: PHEV is treated as a small battery EV or an ICE.**
Correction: one vehicle, two energy ledgers, one coherent but coverage-aware running-cost view. Never infer electric driving fraction solely from energy purchases.

**Failure: the public charging map becomes a bad imitation of mature apps.**
Correction: personal multi-energy management is P1; trusted chargepoint discovery and tariff intelligence is a licensed, later web data track.

**Failure: regulations or technical vehicle APIs are assumed static.**
Correction: dated official rules, real-device/real-data QA, no undocumented vehicle login or scraping, no assumption of tariff API, consent and reversible integrations.

## 10. Validation cohort and decision gate

Recruit BEV owners with and without smart chargers, PHEV owners who charge daily/rarely, petrol HEV owners and at least one diesel hybrid owner. Observe: (1) recording a public charging receipt, (2) recording one home charge or setting a monthly estimation baseline, (3) reconciling a charging bill, (4) viewing a PHEV's combined cost, (5) correctly finding RUC remaining distance, (6) logging a tyre replacement. Track: time/taps to a useful record, manual-entry frequency, estimated-to-observed share, owner comprehension of RUC, true retained/next-event usage and correction burden.

**Decision gate:** do not declare Autoroa ready for all powertrains merely because there is an "EV" vehicle picker. A BEV needs a meaningful charging cost flow; a PHEV needs combined fuel + electricity; a HEV needs a no-charge streamlined experience; all need honest and relevant maintenance/RUC.

