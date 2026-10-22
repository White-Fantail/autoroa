# Autoroa Development Roadmap

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

### Phase 4 — Expansion only after the core loop works (P3)

- Maintenance/service history, reminders, garage and repair-cost information.
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

## Maintenance rule for future work

After every merged feature, update the corresponding roadmap **ID/state**, file or PR reference, validation evidence, and release status. Add a dated line to the progress log. New items must have an owner-visible acceptance test; if testing has not happened, keep the item **PARTIAL** or **VERIFY** rather than marking release-complete. Review the product risks (OCR friction, usefulness, and coverage) before promoting new roadmap items.
