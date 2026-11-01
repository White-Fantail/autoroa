# Autoroa Development Roadmap

## Current product planning: vehicle-first (2026-11-01)

> **Planning overlay, not a new source-code audit.** The implementation inventory below remains the 2026-10-22 snapshot. The new vision changes **product priorities**, not the claimed DONE/PARTIAL/TODO status of code. No application code, tests, deploy or native build was changed by this planning update. Read [product strategy](vision-2026.md), [mobile vehicle-care specification](vehicle-care.md), [web product boundaries](web-products.md).

**Outcome:** create the easiest NZ vehicle-ownership logbook: one-touch fuel receipt capture, optional odometer and trustworthy economy; equally easy recording of tyres, oil, repairs and compliance dates; then two separately governed web experiences (private owner garage, public trusted automotive information). The product must retain value when a user never contributes a public price.

### Revised product-order decisions

| Product track | Product priority | What ships for a user | Honest state on 2026-11-01 |
| --- | --- | --- | --- |
| **P0: capture reliability** | First | Phone shortcut to locally durable receipt; optional second odometer photo; clear asynchronous status, recoverable review, valid economy | Substantial code exists, but OCR speed/quality and physical-device release gates still unverified |
| **P1: vehicle-care beta** | Next, design alongside P0 | Photo or fast category entry for oil, tyre work, repairs, WoF, rego, RUC; service history, documents, due items and unified vehicle timeline | **PLANNED**, not demonstrated as implemented |
| **P1: private owner web** | After trustworthy personal records | Secure timeline, breakdown, document lookup and export | **PLANNED**; public/admin Next.js presence does not prove a private garage exists |
| **P1: trusted public fuel web** | Parallel quality track | Search by area/grade, verified pump price, freshness, source, correction and coverage transparency | Existing public map/price code; nationwide correctness/coverage still to validate |
| **P2: aggregate vehicle-care web** | Only after privacy/sample gate | Carefully qualified regional repair/maintenance ranges with sample limitations | **RESEARCH/PLANNED**; never publish individual invoices |
| **P2: funded benefits / premium** | After demonstrated retention | Real value or convenience backed by sustainable economics | **HYPOTHESIS**, no claim of cash-value rewards |
| **P3: EV/fleet/marketplace** | Defer | New markets after core habit and trusted data work | Later exploration |

The historical Phase 4 below deferred all maintenance. **That specific prioritisation is superseded**: a *narrow* maintenance-history and reminders beta is now a core next product milestone. Extensive workshop commerce, national repair benchmarks and complex fleet tools remain deferred.

### Product planning backlog with user outcomes

| ID | State | Decision/design deliverable | User-centred acceptance / blocker |
| --- | --- | --- | --- |
| PLAN-01 | DOC DRAFT | Observe 20–30 prospective drivers over real refuelling and servicing tasks; document alternatives and actual motivation | Could users retrieve an old receipt and voluntarily repeat capture at the next event? Replace guesses with measurements |
| PLAN-02 | DOC DRAFT | Finalize one-tap receipt, optional odometer, odometer-only, local/outbox status and zero-form default | Tap to local-save works offline; user never mistakes local save for processed result; device validation remains QC-05–QC-09 |
| PLAN-03 | DOC DRAFT | Define explicit habitual-full preference, partial tank and missing-fill semantics | Never claim L/100 km with unreliable full-to-full evidence or fabricated mileage |
| PLAN-04 | DOC DRAFT | Define vehicle-care events, invoice/photo/manual entry, tyre puncture and oil service flows | A no-photo tyre repair and a multi-line-item invoice both record quickly without double counting |
| PLAN-05 | DOC DRAFT | Define due items and WoF/rego/RUC distinctions, sourced dates and reminders | Correct timezone, missing odometer, edits and new WoF effective rules; existing WoF expiry is respected |
| PLAN-06 | DOC DRAFT | Define private owner web, unified vehicle timeline, documents and exports | Owner-only access, no public indexing, totals match mobile, usable retrieval/export |
| PLAN-07 | DOC DRAFT | Define public fuel evidence, freshness, station matching and opt-in contribution | No private receipt automatically exposed; a stale/unknown station is labelled honestly |
| PLAN-08 | DOC DRAFT | Decide legal/privacy, sample and bias controls for aggregate repair-cost pages | No release until independent vehicles/workshops suffice and suppression/re-identification review passes |
| PLAN-09 | DOC DRAFT | Define onboarding, retention and cost experiments | Measure real repeat-event use, OCR cost per useful private record and moderation per published observation |
| PLAN-10 | DOC DRAFT | Price business hypotheses and test one partner-funded benefit | Demonstrable user saving and sponsor payment; existing gamified points are not cash |

**Proposed design-review gate:** For each PLAN item check (1) immediate driver benefit; (2) minimum taps and safe offline failures; (3) trustworthy math and source provenance; (4) private/public boundary; (5) costs and competition; (6) measurable acceptance. Keep status DOC DRAFT until user research and review validate assumptions. Implementation work should only begin on separate authorization.

### What is deliberately not assumed

- A screenshot, source-code presence or merged PR proves a native release.
- Every fuel receipt has a valid public pump price or a usable odometer.
- Full tank is the default without a deliberate owner preference.
- User-uploaded garage invoices are safe to publish as individual repair prices.
- A WoF issue frequency can be calculated from one simple annual rule: **NZTA's staged changes start 2026-11-01, with additional phase 2027-11-01**, and previously issued expiry remains unchanged. Source: https://nzta.govt.nz/projects-and-consultations/have-your-say/past-consultations/considering-changes-to-light-vehicle-inspections/changes-to-light-vehicle-inspections
- Rewards, aggregate data and workshop leads generate revenue absent sponsor/user validation.

### Product review history

| Date | Lens | Finding / revision | Evidence level |
| --- | --- | --- | --- |
| 2026-11-01 | Usefulness | Fuel price map alone does not sufficiently motivate repeated captures; individual savings history and a service-document vault make the record useful before community scale | Planning hypothesis, to test |
| 2026-11-01 | Accuracy | One photo cannot guarantee economy, station pump price or maintenance benchmarking; treat missing data as missing and condition public output on verified eligibility | Product safety rule |
| 2026-11-01 | Feasibility | Do not chase all NZTA/Gaspy/workshop features; ship narrow private utility and truthful public discovery before commercial expansion | Competitive review and proposed scope |

---

## Historical implementation audit: 2026-10-22

The following source-level inventory and delivery gates are preserved as an engineering snapshot. Historical phase labels are not the current product prioritisation when they conflict with the 2026-11-01 overlay.


> Last audited: **2026-10-22** (NZ time)  
> Repository baseline: **`main` at `67ac548f29b7cfa8b5139c2b61c29c5d9f4ee5d5`**, before this documentation change.  
> Product direction: **One tap. One snap. Done.** A receipt is the default; an odometer photo is optional. Camera capture must not require typing or pressing Save.  
> Scope of audit: source files, existing product/architecture/API/deployment/Quick Capture documentation, and merged PR descriptions. This is a **source-level audit, not a production smoke test**.

## How to read this roadmap

- **DONE (code)**: implementation was located on `main`; **does not** mean deployed or physically tested.
- **PARTIAL**: meaningful code exists, but acceptance criteria, integration, or evidence remain incomplete.
- **TODO**: no complete implementation established by this audit.
- **BLOCKED / VERIFY**: technical or release dependency must be resolved or objectively tested.
- Priority: **P0** = next reliable mobile release, **P1** = user value and price coverage, **P2** = scale/monetization, **P3** = later extensions.
- When closing an item, record the **PR/commit, test or device evidence, release environment, and date**. Do not turn a source-level check into a claim of production readiness.

## Executive snapshot

**Implemented foundation:** Expo mobile vehicle/fill-up tracking, mileage/cost/economy views, map-based fuel discovery; Next.js public fuel map and admin operations; FastAPI/Supabase-backed vehicle, media, OCR, station, price, and moderation workflows. The user-submitted price-board pipeline includes validation, contributions, points/achievements, and leaderboards on the API side.

**Latest merged focus:** Quick Capture foundations and iPhone Shortcuts guidance are on `main` (PRs [#28](https://github.com/White-Fantail/autoroa/pull/28), [#29](https://github.com/White-Fantail/autoroa/pull/29), [#30](https://github.com/White-Fantail/autoroa/pull/30)). The alternative PR [#27](https://github.com/White-Fantail/autoroa/pull/27) was closed **without a direct merge**; its work was integrated through #29. Do not count #27 as a separate missing deployment.

**Important limitation:** The October Quick Capture changes were merged as **code**, not as a verified native iOS/Android release. A real-device EAS build, native background transfer, first-party iOS widgets/App Intents, end-to-end field QA, and deployment evidence are still outstanding.

**Product risks reported by the operator (not yet resolved by code evidence):** OCR feels too slow and inaccurate; background recognition is not clearly communicated; users have little reason to submit a photo; price reports are geographically concentrated. Improving the mobile capture/recovery experience and measuring OCR quality takes precedence over adding more standalone features.

## Implementation inventory

| Area | State | Evidence on `main` | Scope still missing / not verified |
| --- | --- | --- | --- |
| Identity, vehicles and private records | DONE (code) | `services/api/app/routes.py` (`/me`, `/vehicles`); mobile onboarding/profile | Production auth and account deletion rehearsal |
| Manual fill-ups, odometer, economy and spend | DONE (code) | `/fill-ups`, `/vehicles/{id}/metrics`; `apps/mobile/app/(tabs)/car.tsx` | Real historical data QA; edge cases on actual devices |
| Nearby station and price discovery | DONE (code) | API `/fuel-stations/nearby`, `/fuel-prices/nearby`; `apps/mobile/app/(tabs)/fuel.tsx`; `apps/web/app/fuel-map/FuelMapExplorer.tsx` | Freshness, nationwide practical coverage and field accuracy measurement |
| NZ station catalog, matching, duplicates | DONE (code) | `station_catalog.py`, `station_inference.py`, `station_admin_tools.py`; PR [#21](https://github.com/White-Fantail/autoroa/pull/21) | Scheduled sync operation, duplicate review and nationwide completeness monitoring |
| OCR queue and human review | DONE (code) | `services/api/app/routes.py`, `services/api/app/services.py`; `docs/architecture.md` | Real receipt benchmark, time-to-result telemetry, queue recovery at production load |
| Quick Capture: receipt-only camera | DONE (code) | `apps/mobile/app/quick-capture.tsx`; `services/api/app/quick_capture.py` | Physical camera/deep-link tests; deployed binary |
| Quick Capture: receipt then optional odometer | DONE (code) | Two modes `?mode=receipt` / `?mode=full`, Skip; nullable odometer | Physical two-photo interruption and restart QA |
| Automatic private fill-up and manual correction | DONE (code) | `quick_capture.py` `_trusted_receipt`, `_finalize`, `/confirm`; `apps/mobile/app/capture-review/[id].tsx` | Accuracy measurement on real-world receipts; review completion usability |
| Private durable local photo outbox | DONE (code) | `apps/mobile/lib/capture-queue.ts`, `CaptureOutboxCard.tsx`, tests; `docs/quick-capture.md` | Real-device storage-full, upgrade and crash/recovery verification |
| Foreground retry, exponential backoff, manual retry | DONE (code) | PR #30; bounded 15s-to-15m backoff and Retry uploads now | Background/force-quit transfer and production recovery notification |
| iPhone shortcuts / one-tap entry | PARTIAL | `apps/mobile/app/quick-actions.tsx`; `autoroa://quick-capture` links; Apple Shortcuts Open URL workflow | Setup remains user-created; native WidgetKit / Siri App Intents / Action Button integration not implemented |
| Anonymous/community price-board submissions | DONE (code) | `community_price_boards.py`, `user_price_boards.py`; web Fuel Map upload | Broad contributor adoption; moderation throughput, fraud/abuse and photo quality |
| Contribution scores, badges, leaderboards | PARTIAL | `contribution_rewards.py`, `contribution_views.py`, achievements API | Verify end-to-end presentation and uptake; points are **not** redeemable financial value |
| Admin portal and operations | DONE (code) | `apps/web/app/admin/**`; admin routing PR #25; reporting/moderation/OCR queue | Admin production build, direct-route parity and operational observability |
| Real financial rewards / partner offers | TODO | No coupon redemption, cash value, sponsor settlement or partner-funded rewards established | Business model, economics, compliance and small pilot |
| Native background transfers and widgets | TODO | Explicitly excluded from PRs #27-#30; Expo SDK 52 is in use | Separate compatible SDK/native upgrade, iOS URLSession and native extension |
| Public release validation and monitoring | BLOCKED / VERIFY | Dedicated Quick Capture CI exists; deployment docs exist | Full pipeline remediation, actual EAS builds, mobile QA, staging/production release evidence |

**Safety contract:** OCR should auto-save a private fill-up only when required fields confidently agree (currently **0.90+** plus sanity checks). Ambiguous results require review. Missing odometer stays NULL; fuel-economy data must not be fabricated. A private receipt must **not** silently publish a public station price. See [Quick Capture](quick-capture.md) and [Product decisions](product.md).

## Prioritized delivery plan

### Phase 0 — Stable, measurable mobile capture (P0, next)

| ID | State | Deliverable | Acceptance / evidence to record |
| --- | --- | --- | --- |
| QC-01 | DONE (code) | One-photo receipt camera and optional second odometer camera, with no Save/form step | Code in `quick-capture.tsx`; confirm both real-device flows under QC-05 |
| QC-02 | DONE (code) | Account-scoped two-slot photo manifests, offline save, app-foreground recovery, bounded retry and explicit manual retry | Existing unit tests; device recovery scenarios remain QC-05 |
| QC-03 | DONE (code) | Idempotent server ingestion, OCR worker, auto-private-fill-up rules, needs-review correction | API code/tests + migrations 0016–0018; end-to-end evidence remains QC-05 |
| QC-04 | DONE (code) | Stable deep-link URLs and Apple Shortcuts setup instructions | PR #30; a user still configures Apple's shortcut manually |
| QC-05 | TODO — release gate | Test signed EAS iOS preview on physical iPhone; Android smoke test | Cold/warm links; offline and airplane mode; permission denial; receipt/full/skip; termination/restart; damaged photo; storage exhaustion; app upgrade with old outbox; token refresh; account switch; duplicate-free upload. Record build ID, device, results and defects |
| QC-06 | TODO | Clear capture progress and exceptional-state UX | User always understands **saved on device → uploaded → processing → saved / needs review**; no fake success; actionable error/retry/review; no unnecessary waiting on OCR |
| QC-07 | TODO | Native persistent background uploads and recovery notification | Resume after app suspension and ordinary termination with OS-compliant URLSession; test iOS restrictions/force quit explicitly; never promise guaranteed completion under force quit |
| QC-08 | TODO | SDK compatibility investigation and native Shortcuts/App Intents + Home/Lock widgets | Isolated upgrade branch and EAS native build; preserve working URL-based fallback; no unvalidated SDK 52→new SDK migration |
| QC-09 | TODO — release gate | Security, privacy, migration and production-readiness review | Private media, deletion, rate limits, data separation, DB migrations on disposable staging, rollback, monitoring, verified app release |

**Order:** Finish QC-05 and QC-06 first, then decide whether QC-07/QC-08 block a limited beta or only the broader release. Shortcut entry already provides a practical interim one-tap path on a configured iPhone.

### Phase 1 — OCR speed, quality and trust (P0)

| ID | State | Deliverable | Acceptance / evidence to record |
| --- | --- | --- | --- |
| OCR-01 | TODO | Instrument the full scan lifecycle: local save, upload, queue wait, OCR call, parse, auto-apply/review, final status | Structured request/job/capture correlation IDs; p50/p95 by stage; error categories; no receipt contents or secrets in logs |
| OCR-02 | TODO | Curated, consented NZ receipt and odometer benchmark | Representative vendors, lighting, crumpled/torn receipts, discounts and different fuel labels; per-field precision and auto-save/review rates |
| OCR-03 | TODO | Improve preprocessing, extraction and validation from benchmark evidence | Evaluate crop/orientation/rotation and prompt/model/provider alternatives; track latency, cost, correctness; preserve conservative auto-save gates |
| OCR-04 | TODO | Recovery and queue operations | Stuck-job detection, bounded retries, dead-letter/repair path and admin observability; avoid duplicate charges and records |
| OCR-05 | TODO | User-facing quality feedback loop | Fast correction for uncertain fields and explicit reporting of wrong OCR; analyze errors without exposing private receipt images |

**Success is measured, not assumed:** establish baseline before choosing numerical latency or accuracy targets. Optimize perceived performance by completing camera capture immediately while recognition is asynchronous and clearly traceable.

### Phase 2 — Daily usefulness and community coverage (P1)

| ID | State | Deliverable | Acceptance / evidence to record |
| --- | --- | --- | --- |
| VALUE-01 | PARTIAL | Personal value from fuel records: costs, history and economy | Already implemented basic metrics; improve trend insights, true savings comparison and repeat-use utility |
| VALUE-02 | PARTIAL | Price discovery and community photo reporting | Existing endpoints and public map; shorten submission UX and make review outcome obvious |
| VALUE-03 | TODO | Regional freshness/coverage dashboard | Instrument unique active contributors, stations updated in 24h/7d, fuel-type coverage, stale percentage by city and region |
| VALUE-04 | TODO | Contribution quality and anti-abuse loop | Confidence/source ranking, duplicate/photo replay protection, anomaly review, meaningful moderation SLAs |
| VALUE-05 | TODO | Acquisition and retention experiments | Track one-tap capture completion, successful OCR, reviews, 7/30-day return, and the percentage contributing price evidence |
| VALUE-06 | PARTIAL | Non-monetary participation incentives | Points, achievements and leaderboard APIs exist; validate a coherent mobile/web presentation and whether they motivate users |

**Do not conflate receipt capture with fresh public price reporting.** Receipt flow prioritizes private recording and safety; any opt-in community price contribution needs explicit station/price provenance and trust checks.

### Phase 3 — Funded user benefits and a sustainable model (P2)

| ID | State | Deliverable | Acceptance / evidence to record |
| --- | --- | --- | --- |
| BIZ-01 | TODO | Compare partner-funded discounts, referral offers, sponsored listings and paid tools | Unit economics including OCR/storage/support/fraud costs, advertiser value, and NZ privacy/advertising obligations |
| BIZ-02 | TODO | Design reward units and fraud-resistant eligibility | Document whether a point has **zero**, fixed or variable monetary value; expiry, reversal, caps and clear terms; do not imply current points are cash |
| BIZ-03 | TODO | Limited regional pilot with real partners | At least one verifiable benefit, simple redemption/reconciliation, measurable contribution lift and funded cost |
| BIZ-04 | TODO | Decide expansion based on observed economics | Repeat contribution, incremental regional price freshness, cost per accepted record and sponsor retention |

### Phase 4 — Expansion under the historical 2026-10-22 plan (P3, superseded for narrow vehicle care)

- Maintenance/service history, reminders, garage and repair-cost information. **As of the 2026-11-01 product plan, basic vehicle-care history and reminders are promoted to the next narrow product track; public repair-cost benchmarking remains a later, privacy-gated extension.**
- EV charging, navigation, fleet, subscriptions and marketplace.
- Nationwide scale improvements such as PostGIS/GiST if Haversine/composite-index query performance becomes a demonstrated problem.

These are **not** part of the next Quick Capture beta. Avoid prioritizing broad feature inventory over high-confidence, nearly effortless fuel tracking.

## Technical and deployment gates

| Gate | State as of audit | Next action |
| --- | --- | --- |
| Quick Capture focused tests | HISTORICALLY PASSING | PR #30 reports a passing dedicated workflow (run `39472854753`); verify the current `main` and newly changed code, not just the PR head |
| Full `pnpm validate` and API migration suite | NOT VERIFIED GREEN | PRs #27–#30 describe pre-existing full CI failures. Triage web, achievement/admin, API migration and sporadic concurrency failures; rerun clean |
| iOS native binary on a device | NOT VERIFIED | Run EAS internal preview build, execute QC-05 and attach evidence |
| Android native build/device | NOT VERIFIED | Build and smoke test physical-device capture, camera, permissions, queue and map |
| Staging migration/data retention | NOT VERIFIED | Test 0016–0018 upgrade with old Quick Capture data + orphaned outbox, independent disposable DB and private storage |
| Production deployment / App Store | NOT VERIFIED | Do not interpret merged PRs as released binaries; record deployment URLs/build versions only when confirmed |
| OCR performance in the field | NOT BASELINED | Implement OCR-01/OCR-02 before claiming acceptable speed or recognition accuracy |
| Privacy and security review | OPEN | Document storage lifecycle, account deletion, moderation and abuse controls before wider rollout |

Commands documented in `package.json`: `pnpm validate` (lint, typecheck, JS/API tests, build, Ruff and Alembic); focused CI: `.github/workflows/quick-capture.yml`. Runtime tests were **not executed by this documentation audit**.

## Suggested next implementation sequence

1. **QC-05:** build and test on a physical iPhone; record a reproducible blocker list.
2. **QC-06 + OCR-01:** improve observable foreground/background statuses and add end-to-end timing/error instrumentation.
3. **OCR-02 → OCR-03:** quantify slow/inaccurate recognition; optimize from actual failure patterns.
4. **OCR-04 + QC-09:** recovery, regression CI, migrations, privacy and operational release readiness.
5. **VALUE-03 → VALUE-05:** identify coverage gaps, measure contribution quality and retention.
6. **BIZ-01 → BIZ-03:** validate one funded benefit before building a general financial rewards system.
7. **QC-07/QC-08:** ship native background/first-party widget integration after safe SDK/native validation; reconsider timing based on beta evidence.

## Progress log (append only)

| Date | Change | Evidence | Release confidence |
| --- | --- | --- | --- |
| 2026-08-20 | Admin App Router migration and related build fixes merged | PRs #25–#26 | Code merged; no current deployment proof |
| 2026-10-20 | Quick Capture camera, optional odometer, private ingestion and recovery integrated | PRs #28–#29; #27 superseded by #29 integration | Code merged; not a native release |
| 2026-10-20 | Apple Shortcuts entry guidance, local outbox card and bounded retries merged | PR #30 | Dedicated PR CI passed; EAS/physical devices unverified |
| 2026-10-22 | Baseline audited; implementation inventory, gaps, acceptance criteria and priorities documented | `main` baseline `67ac548f`; source/doc review | Documentation only |

| 2026-11-01 | Vehicle-first strategy, mobile care flows and distinct private/public web surfaces planned; existing implementation audit preserved | [strategy](vision-2026.md), [vehicle care](vehicle-care.md), [web products](web-products.md) | **Documentation only**; no code or real-device verification |

## Maintenance rule for future work

After every merged feature, update the corresponding roadmap **ID/state**, file or PR reference, validation evidence, and release status. Add a dated line to the progress log. New items must have an owner-visible acceptance test; if testing has not happened, keep the item **PARTIAL** or **VERIFY** rather than marking release-complete. Review the product risks (OCR friction, usefulness, and coverage) before promoting new roadmap items.


