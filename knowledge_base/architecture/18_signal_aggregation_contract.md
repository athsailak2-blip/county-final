# 18. Signal Aggregation Contract (v5.3.0+)

The signal aggregation contract defines how multiple raw records about the same property
collapse into the signal chips, signal counts, and stacked-signal totals visible on the
lead dashboard.

This file is the universal contract. The per-county canonical doc-type taxonomy and the
per-county signal-type display labels live in `config/counties/<county_slug>.json`.

---

## 18.0 Status and scope

- **Version:** v5.3.0 (Session A2 — Gap 6).
- **Date:** 2026-05-18.
- **Authoritative for:** every pipeline component that groups raw records into signals
  on a matched lead.
- **Scope:** universal — the aggregation key, the within-group merge contract, the
  cross-source rule, the legitimate-stacking-versus-dedup-failure test, and the
  anti-collapse rule. Per-county taxonomy and display labels live in the county config.

---

## 18.A Purpose

The signal aggregation contract defines how multiple raw records about the same property
collapse into the signal chips, signal counts, and stacked-signal totals visible on the
lead dashboard. Without an explicit contract, aggregation produces duplicate chips,
inflated counts, or signal collapse (multiple distinct signals merging into one).

---

## 18.B The aggregation key

Signals are grouped by the tuple `(parcel_id, canonical_doc_type, signal_type)`:

- **`parcel_id`** — the resolved property identifier, in county-canonical form.
- **`canonical_doc_type`** — the doc type after county taxonomy normalization (e.g.
  `hospital_lien`, `executor_deed`).
- **`signal_type`** — the operator-facing semantic category (e.g. "Hospital Lien",
  "Estate-Titled Property", "Federal Tax Lien").

The aggregation key is the dedup boundary. Multiple raw records that share the full key
collapse into a single signal with a count badge. Records that differ in any tuple
component remain distinct signals.

---

## 18.C What gets merged within a signal group

When N raw records share the aggregation key, the resulting signal carries:

- **`count`** — N.
- **`instrument_numbers`** — array of distinct instrument numbers, one per source record.
- **`source_urls`** — array of distinct source proof URLs.
- **`evidence_ids`** — array of distinct evidence file paths (PDF paths, screenshot
  paths).
- **`earliest_recorded_date`** — the earliest of the N record dates.
- **`latest_recorded_date`** — the latest of the N record dates.
- **`recorded_date_range`** — the pair `(earliest, latest)` for display.

The signal's display label remains the canonical `signal_type`. The count badge displays
N if N > 1. There is no display change for N = 1.

---

## 18.D Cross-source aggregation

When a lead is anchored to a parcel and signals originate from multiple sources
(`clerk_recordings` + `foreclosure_notices`, for example), each source contributes its
own signals to the lead's signal list. Cross-source signals MUST be deduplicated by the
same `(parcel_id, canonical_doc_type, signal_type)` key.

Example: a clerk-recorded foreclosure notice plus a foreclosure-portal foreclosure notice
for the same parcel and same recording date collapse to one signal with `count = 2` and
`source_urls` containing both URLs. If the recording dates differ but parcel and doc type
match, they still collapse — it is the same legal event recorded across two sources.

---

## 18.E Distinguishing legitimate stacking from dedup failures

Legitimate stacking (`count > 1` expected):

- multiple distinct hospital liens against the same patient over time — different
  instrument numbers, different dates;
- multiple state tax liens for sequential filing periods;
- an executor's deed filed N times when an estate filed N separate deeds for N parcels
  under one administrator.

Dedup failure (`count > 1` is a bug):

- the same `instrument_number` appearing N times in the input stream;
- the same source URL appearing N times;
- an identical raw record duplicated across multiple ingest passes.

The aggregator MUST union by `instrument_number` within a group. If the union reduces the
count below the input record count, the difference is dedup; if it does not, the count is
legitimate stacking.

---

## 18.F Anti-collapse rule

Distinct `signal_type` values MUST NOT collapse into one, even when they share
`parcel_id` and source. Example: a parcel with a `hospital_lien` AND an `executor_deed`
AND a `federal_tax_lien` produces THREE signals on the lead, not one. The `signal_type`
component of the aggregation key prevents collapse across types.

---

## 18.G Per-type caps and visual treatment (display contract)

When `count` exceeds a display threshold (e.g. `count > 5`), the signal chip displays
"Signal Type × N" with N visible. The dashboard MUST NOT truncate or hide high-count
signals — operators need to see when stacking is unusually high, which is a signal of
either genuine high engagement with the property OR a dedup failure to investigate.

---

## 18.H Cross-reference to §13 and §17

- **§13** (`13_lead_origination_contract.md`) determines which records originate leads.
- **§17** (`17_debtor_party_rules.md`) determines which party in the record is the
  debtor (`owner_name`).
- **§18** (this contract) determines how multiple records about the same property
  collapse into signals.

---

## 18.I Universal versus county-specific separation

- **Universal** — the aggregation key, the within-group merge contract, and the
  anti-collapse rule. They live in this file.
- **County-specific** — the per-county canonical doc-type taxonomy lives in
  `config/counties/<county_slug>.json`; the per-county signal-type display labels live
  in `config/counties/<county_slug>.json` under `signal_type_labels`.

This file contains no county name, no state name, and no county-specific example. The
county-agnostic regression scanner enforces this.
