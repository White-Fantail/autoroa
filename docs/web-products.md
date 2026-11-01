# Autoroa web products and evidence-governance plan

> 2026-11-01 proposal, **not evidence that these web experiences are deployed**.
> Source of truth: [vehicle-first vision](vision-2026.md) and [vehicle-care specification](vehicle-care.md).

## Three surfaces, not one public database

| Surface | Audience | Core job | Default visibility |
| --- | --- | --- | --- |
| **Owner web garage** (authenticated) | Vehicle owner and explicitly authorised members | Review fuel/service history, search invoices, filter costs, export records, edit due items | Private per vehicle |
| **Public fuel web** | Any NZ driver, search user or traveller | Find reliable observed pump prices by location, grade and recency; see source quality | Curated and approved station-level observations only |
| **Public ownership/repair insight web** (later) | Drivers researching repair/maintenance costs | See appropriately sampled and qualified cost ranges and care patterns by broad category/vehicle cohort | Carefully aggregated, permission-appropriate and suppressed where unsafe |

Distinct URLs, navigation and API responses can share infrastructure, but must have separate authorization, indexing, disclosure, moderation and analytics policies. An owner-only personal record must never be made indexable just because the public site uses the same application.

## Public fuel: experience contract

1. A visitor can search an area/route and fuel grade without creating an account.
2. Show a station's **observed pump price** when there is trustworthy evidence; distinguish paid-after-loyalty prices or discounts and never rank them as comparable retail pump prices.
3. Display observation timestamp, freshness/stale status and a meaningful source/confidence label. If data is missing, show **unknown**, not a synthetic current price.
4. Support map and list view, source-corrected station identities, filtering, price/distance ranking with clear distance assumptions, and an error-report action.
5. An optional submission flow can request a price-board photograph or explicit receipt-price contribution. Location/station/fuel type/evidence should be checked. An unverified price must not instantly outrank verified evidence.
6. Cache/index only public-safe derived station information. Do not leak registration numbers, plate images, card details, full receipt photos, driver IDs, exact routes, odometers or personal history in public results or metadata.
7. Show regional coverage quality, not just the number of database rows. A concentration of repeated observations at one station does not imply adequate coverage of nearby stations.
8. If estimated savings are shown, expose the comparison baseline and any travel-cost assumptions; if insufficient data, omit the claim.

Data lifecycle: separate eligible observation creation → station verification → quality/moderation → current price resolution → freshness decay/expiration → correction/rollback. An older trustworthy observation may remain visible as historical evidence but must not masquerade as a fresh price. Reward points do not grant data authority.

## Maintenance and repair-cost insights: do not launch from raw invoices

Potential future pages: common service categories; what owners paid for tyres, oil changes or WoF-related work in a broad region; costs grouped by vehicle class/age and broad repair type; seasonal maintenance education with credible sources. **Do not** advertise a national "average repair cost" from an unrepresentative early adopter cohort.

Proposed publication gate for every aggregate result:
- There is a legitimate disclosed purpose and appropriate permission or other vetted privacy basis for secondary public use.
- Sample includes enough independent vehicles and independent workshops/transactions; an owner who uploads many invoices does not dominate.
- Classify comparable services, parts included/excluded, tax, labour, currency, date, geography and work complexity. Incomplete invoices cannot be safely treated as complete repair prices.
- Set a conservative privacy threshold per cell and suppress/filter rare combinations, small cohorts, specific dates, exact odometers, registration identifiers and unusual line items. Threshold is a **design control requiring privacy review**, not a legal guarantee.
- Test for re-identification through intersection of location, date, rare vehicle model and repair type, including repeated query/difference attacks. Review data licensing and evidence permissions.
- Display sample size (appropriately coarsened), geography, date range, scope and uncertainty. Suppress insights when too sparse or biased.
- Provide corrections, removal pathways and provenance tracing; user deletion and consent revocation require a defined derived-data handling policy.
- No access for insurers/credit or individual profiling via supposedly aggregated endpoints.

Only after a documented legal/privacy review and independent quality tests should this public product ship. If the sample cannot pass, keep personal vehicle records private and defer aggregate pages.

## Revenue and trust boundaries

- Free public price discovery is an acquisition possibility, not proof of national coverage.
- Monetization candidates: disclosed sponsoring that never changes the independent cheapest-price sort; provider-funded repair/tyre offers; carefully scoped premium owner reporting/export; optional aggregate B2B research only where safe and permitted.
- Do not sell or expose raw invoices, user activity trails, household vehicle associations, private odometer information, or personally attributable repair histories.
- Never suggest that a currently existing contribution point is redeemable cash or a guaranteed discount.
- Validate sponsor interest, acquisition cost, fraudulent updates, OCR/storage expense and moderation time before building a redemption system.

## Validation and web readiness

**Public fuel beta ready** only when: tested station matching and provenance; mandatory timestamps and freshness; measured correct price/grade samples; error reporting and correction; regional coverage dashboard; moderation response procedure; private/public serialization and search-index privacy tests; cost controls.

**Owner web beta ready** only when: account authorization and vehicle-level isolation; consistent totals with mobile; fast searchable event history; full export and deletion workflow; clear OCR status; no public indexing of user records.

**Aggregate maintenance beta ready** only after: documented privacy and consent assessment, sufficient independent sample, bias review, correct accounting/tax comparability, suppression/reidentification testing, transparent uncertainty and take-down/correction handling.

### Web metrics

- Public: unique stations observed per region, % with sufficiently fresh eligible evidence, median age by grade, source diversity, corrections per published price, useful search result rate, repeat visits.
- Owner: time to find old invoice, consistency of totals across mobile/web, successful exports, unauthorized access tests, users returning to review due items.
- Aggregate: independent sample coverage, withheld-cell rate, repair-type normalization error, documented confidence bands and complaints/corrections.
- Economics: server/OCR/storage/moderation cost per accepted item, partner conversion on explicitly sponsored content, value to users versus ad load.

## Primary sources and follow-up verification

- NZTA vehicle records and current app capability: https://nzta.govt.nz/about-us/app
- NZTA WoF rule transition from 2026-11-01: https://nzta.govt.nz/projects-and-consultations/have-your-say/past-consultations/considering-changes-to-light-vehicle-inspections/changes-to-light-vehicle-inspections
- NZ Privacy Commissioner on disclosure: https://www.privacy.org.nz/resources-and-learning/knowledge-base/view/228/
- NZ Privacy Commissioner on personal information purposes: https://www.privacy.org.nz/privacy-principles/10/

This is a product/privacy design proposal, not legal advice or a claim of privileged NZTA data access.
