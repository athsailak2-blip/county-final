# Bexar PublicSearch clerk_recordings — Matched Lead Spec (v2)

## 0. Status and scope

- **Date:** 2026-05-17
- **Version:** v2
- **Updated:** 2026-05-17 (architectural alignment — renamed `evidence_record` to
  `matched_lead`, aligned canonical field vocabulary to existing framework conventions
  per `09_output_schemas.md` and `08_evidence_ledger.md`)
- **Operator:** Quentin Flores
- **County:** bexar_tx
- **Source ID:** publicsearch_clerk_recordings

**Scope — strict.** This spec defines how the `publicsearch_clerk_recordings` source
contributes to the framework's **existing Matched lead schema** (record type 4 in
`knowledge_base/architecture/09_output_schemas.md`) — the parcel-grouped, signal-stacked,
suppression-aware lead row stored at `data/leads.json`. It does NOT cover:

- the scraper (`publicsearch_clerk_recordings_scraper_spec.md` — locked v2);
- the translator (`publicsearch_clerk_recordings_translator_spec.md` — locked v1);
- scoring calibration (deferred — separate later phase);
- pipeline wiring or the actual matched-lead-layer Python code;
- format rendering — Excel / GHL CSV / dashboard JSON / SMS export are all deferred to a
  future format-rendering spec;
- LEVEL 3 inference (heirship, property-affecting judgment, MEMO/NOTICE/MOD sub-types);
- scoring weights, bonuses, multipliers, `seller_score` logic, `scoring_overrides`;
- the cross-source dedup *algorithm*.

**This spec does NOT define a new record type.** v1 of this document invented a record
type called `evidence_record`. A grounding pass against the architecture docs found that
the framework already has a parcel-grouped, signal-stacked record — the **Matched lead**
(record type 4 per `09_output_schemas.md`) — and that "evidence" is a reserved term for
the per-field provenance ledger (`08_evidence_ledger.md`). Per operator decision, v2
renames `evidence_record` → `matched_lead` and aligns to the existing schema. The
`matched_lead` referenced throughout this document **IS the framework's Matched lead**,
with field-level extensions documented in §3 and queued for v5.1.2-beta-final.

**This spec must be operator-approved before any matched-lead-layer code is written.**

---

## 1. Matched lead layer purpose

The matched-lead layer is the third pipeline tier, after the scraper and the translator.
Its job: turn the translator's `(signals, parcels, per_signal_meta_by_url)` three-tuple
into operator-actionable, parcel-grouped Matched lead rows.

Pipeline flow:

    PublicSearch portal
        |
        v
    [scraper publicsearch_clerk_recordings]
        |
        v
    data/raw/clerk_recordings.jsonl (wrapped raw_payload per §4.32)
        |
        v
    [translator publicsearch_clerk_recordings]
        |
        v
    (signals, parcels, per_signal_meta_by_url) tuple
        |
        v
    [matched-lead layer]   <-- THIS SPEC
        |
        v
    Matched lead records (record type 4, data/leads.json — one per parcel, signals stacked)
        |
        v
    [downstream: format rendering — Excel, GHL CSV, dashboard JSON, etc.]

**Responsibility.** The matched-lead layer takes ONE OR MORE translator three-tuples —
from one or more sources (`publicsearch_clerk_recordings`, `foreclosure_notices_map`,
`parcel_master`, …) — and produces a **parcel-grouped, signal-stacked,
suppression-aware** Matched lead record. It is the join point where multiple sources'
signals on the same property become a single operator-facing lead row.

This spec describes the **Matched lead record shape** for the
`publicsearch_clerk_recordings` contribution. Format rendering (operator-facing
Excel / GHL CSV / dashboard JSON / SMS export) is downstream and deferred (§9).

### 1.1 The existing Matched lead schema (record type 4)

This spec aligns to — it does NOT replace — the Matched lead record already defined in
`knowledge_base/architecture/09_output_schemas.md` (record type 4, stored at
`data/leads.json`). The framework's existing Matched lead fields, cited verbatim from
that file:

- `lead_id` — `lead_<uuid>`, the record identifier;
- `primary_parcel_id` — the parcel this lead is keyed on;
- `normalized_address` — the normalized property address;
- `owner_entity_id` — resolved owner entity;
- `signals[]` — array of `signal_id` references;
- `patterns[]` — deduplicated lead-pattern list;
- `attributes[]` — parcel-attribute list;
- `score`, `score_reasons[]`, `deal_paths[]`, `deal_path_reasons[]` — scoring /
  classification (out of scope for this spec — scoring is deferred);
- `match_confidence`, `parser_confidence_avg`;
- `doc_type_normalization{raw_doc_types_seen[], normalized_doc_types[],
  doc_type_confidences[], doc_type_review_required}`;
- `lifecycle_states[]` — one entry per active lifecycle on the parcel, each with
  `lifecycle`, `current_stage`, `stage_entered_at`, `lifecycle_status`,
  `active_signals[]`, `suppressed_signals[]`;
- `title_complexity_score`, `title_complexity_tier`, `title_complexity_contributors[]`;
- `document_priority_max`;
- `evidence_ids[]` — references into the per-field evidence ledger
  (`08_evidence_ledger.md`);
- `review_flags[]`;
- `lead_status`, `lead_status_history[]`, `export_status`.

**Fields in §3 that exceed this existing schema are PROPOSED SCHEMA EXTENSIONS**, not new
record types invented by this spec. They are proposals to extend the Matched lead record,
and they are queued in `v5.1.2-beta-final-additions.md` for framework registry update.
§3 marks each field EXISTING or PROPOSED EXTENSION.

**Terminology.** "Evidence" remains reserved for the per-field provenance ledger in
`08_evidence_ledger.md` (`evidence_id`, `field`, `value`, `status`,
`source_reliability_grade` A–E, stored at `data/evidence.jsonl`). This spec does not
reuse "evidence" to mean the lead row. The Matched lead references the ledger through its
existing `evidence_ids[]` field; the ledger concept is unchanged.

---

## 2. Inputs from translator three-tuple

The matched-lead layer consumes the translator output. The three-tuple, exactly as
defined in `publicsearch_clerk_recordings_translator_spec.md` §3.2 and confirmed against
the built-in translators (`foreclosure_notices.py`, `parcel_master.py`,
`csv_static_list.py`):

    (signals, parcels, per_signal_meta_by_url)

- **`signals`** — `list[dict]`. One signal per translated source record. Each carries
  `signal_id`, `raw_record_id`, `source_id`, `source_url`, `doc_type` (the normalized
  doc type — the translator's mapping output), `doc_type_subtype_label` (the verbatim
  source label), `doc_number`, `primary_parcel_id`, `filing_date`, `parser_confidence`,
  and the two LEVEL 2 flags `lifecycle_suppression_flag` and
  `dedup_against_foreclosure_notices_map`.
- **`parcels`** — `list[dict]`. The property side of the join: `parcel_id`, `address`,
  `city`, `zip`, `owner_name`, `parcel_master_status`.
- **`per_signal_meta_by_url`** — `dict[str, dict]`, keyed by `source_url`. Per-signal
  metadata: `preset_review_flags`, `match_confidence`, `match_method`, `address`,
  `city`, `zip`, `primary_parcel_id`, plus the clerk-recording context the translator
  carries through (`grantor`, `grantee`, `legal_description`,
  `parcel_grid_identifiers`).

**Entity-resolution rule.** The matched-lead layer matches signals to parcels via parcel
identification — address normalization, `parcel_grid_identifiers` match, or other
resolution rules. The framework's entity-resolution logic is documented in
`knowledge_base/architecture/12_entity_resolution.md`. **The matched-lead layer consumes
already-resolved matches** — each translator signal already carries a
`primary_parcel_id`. Computing the parcel match is upstream pipeline work; this layer
groups by the `primary_parcel_id` it is given.

**Multiple sources, one parcel.** A single parcel can receive signals from several
sources. The matched-lead layer aggregates ALL contributing sources' signals into one
Matched lead record — not just `publicsearch_clerk_recordings`. A parcel with a
PublicSearch `LIS PEN` and an ArcGIS foreclosure-notice signal produces ONE Matched lead
listing both in `contributing_sources`.

---

## 3. Matched lead record shape

This is the core of the spec. One Matched lead per parcel. The shape below is the
framework Matched lead (record type 4) as it pertains to the
`publicsearch_clerk_recordings` contribution, with PROPOSED EXTENSIONS marked. Shape
(indented block, not a code fence):

    {
      "lead_id": "<string — unique per parcel-keyed Matched lead row>",
      "primary_parcel_id": "<string — canonical parcel identifier>",
      "normalized_address": "<string or null>",
      "parcel_grid_identifiers": "<string or null>",
      "county_slug": "<string — runtime-resolved, e.g. bexar_tx>",
      "signal_count": <integer — count of active, non-suppressed signals>,
      "signal_types": [<normalized_doc_type strings, deduplicated, sorted>],
      "primary_signal": "<string — highest-priority normalized_doc_type, §4 hierarchy>",
      "source_urls": [<source_url strings, one per active signal>],
      "document_numbers": [<document_number strings, parallel order to source_urls>],
      "latest_event_date": "<YYYY-MM-DD — most recent event_date across signals>",
      "earliest_event_date": "<YYYY-MM-DD — oldest event_date across signals>",
      "matched_lead_summary": "<string — short human-readable summary>",
      "source_confidence": "<aggregated label — HIGH / MEDIUM / LOW>",
      "parcel_lifecycle_rollup": "<ACTIVE / RESOLVED / PARTIALLY_RESOLVED>",
      "suppression_status": "<NONE / SUPPRESSED_HIDDEN / SUPPRESSED_VISIBLE_HISTORY>",
      "contributing_sources": [<source_id strings, deduplicated, sorted>],
      "matched_lead_emitted_at": "<ISO8601 UTC>",
      "signal_details": [
        {
          "signal_id": "<string>",
          "normalized_doc_type": "<string>",
          "raw_doc_type": "<string — source-native code, e.g. LIS PEN>",
          "doc_type_label": "<string — source-native label, e.g. LIS PENDENS>",
          "event_date": "<YYYY-MM-DD>",
          "source_id": "<string>",
          "source_url": "<string>",
          "document_number": "<string>",
          "grantor": "<string or null>",
          "grantee": "<string or null>",
          "parser_confidence": <integer 0-100>,
          "is_suppression_record": <boolean>,
          "suppressed_by": "<string or null — signal_id of the signal that suppressed this one>",
          "lifecycle_suppression_flag": <boolean>,
          "dedup_against_foreclosure_notices_map": <boolean>
        }
      ]
    }

**19 top-level fields** (the last being `signal_details`, a list of objects with **15
sub-fields** each).

**Universality note — `county_slug` is runtime-resolved.** The matched-lead-layer Python
code MUST NOT hardcode `county_slug`. It reads the value from run context or source
config at call time, per the `MASTER_PROMPT.md §4.31` universality contract. This spec
lives under `runs/bexar_tx/` and uses `bexar_tx` as the *example* value only.

### 3.1 Top-level field reference (EXISTING vs PROPOSED EXTENSION)

Each field is marked **EXISTING** (already in the Matched lead schema, record type 4) or
**PROPOSED EXTENSION** (a proposed addition queued in `v5.1.2-beta-final-additions.md`).

- **`lead_id`** — **EXISTING.** The Matched lead record identifier (`lead_<uuid>`).
  Required. Derived as a stable id keyed on `county_slug + primary_parcel_id`. (v1
  called this `evidence_record_id`; v2 uses the framework's actual field name.)
- **`primary_parcel_id`** — **EXISTING.** Canonical parcel identifier and the grouping
  key. Required. Derived from the translator signals' `primary_parcel_id`. (v1 called
  this `parcel_id`.)
- **`normalized_address`** — **EXISTING.** The normalized property address. Optional
  (null when no address — many non-conveyance clerk recordings have none). (v1 called
  this `situs_address`, the Parcel-record field name; v2 uses the Matched-lead field
  name.)
- **`parcel_grid_identifiers`** — **PROPOSED EXTENSION.** The Bexar grid string
  (Lot/Block/NCB/County Block) as a single raw string. Optional. No framework canonical
  exists — backlog item B in `v5.1.2-beta-final-additions.md`. Carried verbatim for v1.
  **Still TBD** (§13).
- **`county_slug`** — **PROPOSED EXTENSION.** The county this record belongs to.
  Required, runtime-resolved. The Matched lead schema has no county field (it is
  implicitly single-county per build); the run manifest uses `county_id`. **Still TBD**
  whether to adopt `county_id` for consistency (§13).
- **`signal_count`** — **PROPOSED EXTENSION.** Integer count of active, non-suppressed
  signals. Derivable from the existing `signals[]`; surfaced as a convenience rollup.
  Required. Derived per §5.
- **`signal_types`** — **EXISTING (aligns).** Deduplicated, sorted list of
  `normalized_doc_type` values from active signals. Aligns to the Matched lead's
  existing `doc_type_normalization.normalized_doc_types[]`. Required. Derived per §5.
- **`primary_signal`** — **PROPOSED EXTENSION.** The single highest-priority
  `normalized_doc_type` per the §4 hierarchy. Required. Derived per §4 / §5.
- **`source_urls`** — **PROPOSED EXTENSION.** List of `source_url` strings, one per
  active signal, in `source_id` then `event_date` order. Required. The framework keeps
  source URLs per-evidence in the ledger; this aggregated list is a convenience rollup.
- **`document_numbers`** — **PROPOSED EXTENSION.** List of `document_number` strings,
  parallel order to `source_urls` (§6). Required.
- **`latest_event_date`** / **`earliest_event_date`** — **PROPOSED EXTENSION.** Max / min
  `event_date` across active signals, `YYYY-MM-DD`. Required. (v1 called the per-signal
  date `recorded_date`; v2 uses the framework Normalized-signal field name `event_date`.)
- **`matched_lead_summary`** — **PROPOSED EXTENSION.** A short human-readable summary
  string, e.g. `"LIS PENDENS + MECHANICS LIEN active; FEDERAL TAX LIEN pending review"`.
  Required. (v1 called this `evidence_summary`, which collides with the structured
  counts object of the same name in `08_evidence_ledger.md`; v2 renames it.)
- **`source_confidence`** — **PROPOSED EXTENSION.** Aggregated confidence label, `HIGH` /
  `MEDIUM` / `LOW`. Required. Its aggregation rule and its relationship to the
  framework's `source_reliability_grade` (A–E) are unresolved — **still TBD** (§5, §13).
- **`parcel_lifecycle_rollup`** — **PROPOSED EXTENSION.** `ACTIVE` / `RESOLVED` /
  `PARTIALLY_RESOLVED`. Required. (v1 called this `lifecycle_status`, which collides with
  the per-signal `lifecycle_status` enum in `09_output_schemas.md`; v2 renames it. The
  Matched lead's richer per-lifecycle detail lives in the existing `lifecycle_states[]`;
  this field is a parcel-level summary rollup.)
- **`suppression_status`** — **PROPOSED EXTENSION.** `NONE` / `SUPPRESSED_HIDDEN` /
  `SUPPRESSED_VISIBLE_HISTORY`. Required. Derived per §5 / §7.
- **`contributing_sources`** — **PROPOSED EXTENSION.** Deduplicated, sorted list of
  `source_id` strings. Required. Relates to the `08_evidence_ledger.md` rollup field
  `primary_sources`.
- **`matched_lead_emitted_at`** — **PROPOSED EXTENSION.** ISO8601 UTC timestamp the
  record was produced. Required. (v1 called this `evidence_emitted_at`.)
- **`signal_details`** — **PROPOSED EXTENSION.** Full per-signal breakdown for operator
  drill-down. Required (may be a single-element list). The Matched lead's existing
  `signals[]` holds `signal_id` *references*; `signal_details` inlines the per-signal
  detail (the framework otherwise keeps it in `data/signals.jsonl`). See §3.2.

### 3.2 signal_details sub-field reference (EXISTING vs PROPOSED EXTENSION)

Each entry in `signal_details` describes one underlying signal. Marked against the
framework Normalized-signal schema (record type 2):

- **`signal_id`** — **EXISTING** (Normalized signal).
- **`normalized_doc_type`** — **EXISTING** (Normalized signal). The canonical doc type.
  (v1 called this `canonical_doc_type`; v2 uses the framework field name. The translator
  emits it as `doc_type`.)
- **`raw_doc_type`** — **EXISTING** (Normalized signal). The source-native code (e.g.
  `LIS PEN`). (v1 called this `doc_type_code`; v2 uses the framework field name.)
- **`doc_type_label`** — **PROPOSED EXTENSION.** The source-native human label (e.g.
  `LIS PENDENS`); maps to the translator's `doc_type_subtype_label`. No framework
  Normalized-signal field holds the verbatim label.
- **`event_date`** — **EXISTING** (Normalized signal). The recording date, `YYYY-MM-DD`.
  (v1 called this `recorded_date`; v2 uses the framework field name.)
- **`source_id`** — **EXISTING.**
- **`source_url`** — **EXISTING** (evidence object / translator signal).
- **`document_number`** — **EXISTING (aligns).** Aligns to the evidence object's
  `source_document_id`; name retained as `document_number` for source-native clarity —
  flagged in §13.
- **`grantor`** / **`grantee`** — **TBD.** The framework Normalized-signal schema models
  parties as `party_names[]` + `party_roles{}`, not two flat fields. The canonical
  two-party model is unresolved (translator spec §6 / `v5.1.2-beta-final` item B).
  **Still TBD** (§13).
- **`parser_confidence`** — **EXISTING.** Integer 0–100, passthrough.
- **`is_suppression_record`** — **PROPOSED EXTENSION.** Boolean: true if this signal's
  `raw_doc_type` is in the `LIFECYCLE_SUPPRESSION_DOC_TYPE` class. Required, never null.
- **`suppressed_by`** — **EXISTING** (Normalized signal). The `signal_id` of the signal
  that suppressed THIS signal, or null. (v1 had `suppresses_signal_id` pointing the
  opposite way — suppressor → suppressed. v2 flips to the framework convention: the
  *suppressed* signal carries `suppressed_by` pointing to its suppressor.)
- **`lifecycle_suppression_flag`** / **`dedup_against_foreclosure_notices_map`** —
  **PROPOSED EXTENSION.** Booleans, passthrough from the translator's LEVEL 2 flags.
  Required, never null. Whether these belong at signal level or top level is **a new TBD
  surfaced by the v2 alignment** (§13).

Whether `signal_details` carries only active signals or also suppressed ones is an open
question (§13); §7 assumes suppressed signals MAY remain in `signal_details` (flagged)
so the rendering layer can build the operator history view.

---

## 4. One row per parcel — stacking strategy

**Rule: one Matched lead record per parcel, regardless of how many signals stack on it.**
A parcel with five signals appears once, with the signal data stacked — never five
duplicate rows. This is exactly the framework Matched-lead model (record type 4), which
is parcel-keyed with a `signals[]` array.

Stacking logic:

- All signals — from ANY contributing source — that resolve to the same
  `primary_parcel_id` are aggregated into one Matched lead record.
- `signal_count` = the number of **active, non-suppressed** signals.
- `signal_types` = the deduplicated, alphabetically sorted list of `normalized_doc_type`
  values across the active signals.
- `primary_signal` = the highest-priority `normalized_doc_type` per the hierarchy below.
- `signal_details` = the full per-signal breakdown for operator drill-down.

### 4.1 primary_signal priority hierarchy (TBD-PROPOSED)

The proposed ordering, highest priority first:

    1.  LIS_PENDENS            pending litigation against the property
    2.  FORECLOSURE_RECORDING  foreclosure event
    3.  MECHANICS_LIEN         unpaid-contractor lien
    4.  FEDERAL_TAX_LIEN       IRS lien
    5.  STATE_TAX_LIEN         state tax lien
    6.  PROBATE_RECORDING      estate proceeding
    7.  COURT_DECREE           court order affecting the property
    8.  PROBATE_LETTERS        estate authority (letters)
    9.  WILL_RECORDING         recorded will
    10. CHILD_SUPPORT_LIEN     child-support enforcement lien
    11. HOSPITAL_LIEN          medical-debt lien
    12. LANDLORD_LIEN          landlord / commercial lien
    13. lower-priority + umbrella categories, ranked below the above:
        GENERIC_AFFIDAVIT, GENERIC_LIEN, GENERIC_MEMORANDUM, GENERIC_NOTICE,
        GENERIC_MODIFICATION, POWER_OF_ATTORNEY, COURT_JUDGMENT, STATE_JUDGMENT

**This hierarchy is for ORDERING ONLY** — it decides which stacked signal is labelled
`primary_signal`. It is NOT scoring. There are no numeric weights, bonuses, or
`scoring_overrides` anywhere in this spec; scoring is a separate deferred phase.

The hierarchy is **operator-revisable** and is marked **TBD-PROPOSED** in §13. It is
mostly built from the 15 GAP canonicals (`v5.1.2-beta-final-additions.md` item A), so the
names are provisional until that vocabulary lands.

---

## 5. Signal aggregation rules

Every aggregated field is derived **deterministically** — given the same translator
three-tuple input, the Matched lead record is byte-identical across runs. Sorting and
ordering rules below exist precisely to guarantee that. (Field names are updated per the
v2 framework-vocabulary alignment; the aggregation logic is unchanged from v1.)

- **`signal_count`** — integer count of active (non-suppressed) signals on the parcel.
- **`signal_types`** — list of distinct `normalized_doc_type` values from active
  signals, deduplicated, sorted alphabetically.
- **`primary_signal`** — the active signal whose `normalized_doc_type` ranks highest in
  the §4.1 hierarchy. Tie-break (same canonical type, or two types of equal rank): the
  signal with the most recent `event_date`, then the lowest `signal_id`
  lexicographically, for determinism.
- **`source_urls`** — list of `source_url` strings, one per active signal, ordered by
  `source_id` ascending, then `event_date` ascending.
- **`document_numbers`** — list of `document_number` strings in the SAME order as
  `source_urls` (parallel arrays — see §6).
- **`latest_event_date`** — the maximum `event_date` across active signals.
- **`earliest_event_date`** — the minimum `event_date` across active signals.
- **`matched_lead_summary`** — a human-readable string built deterministically from the
  active `signal_types` plus status notes, e.g.
  `"LIS PENDENS + MECHANICS LIEN active; 1 resolved"`. The exact template is TBD (§13);
  it must be a pure function of the record's other fields so it stays deterministic.
- **`source_confidence`** — an aggregated `HIGH` / `MEDIUM` / `LOW` label. **TBD —
  aggregation rule unresolved (§13).** Candidate rules: (a) take the MAX per-signal
  confidence; (b) take the most conservative (MIN); (c) weight by the source's
  `source_reliability_grade` (A–E, per `08_evidence_ledger.md`). This spec does not lock
  the rule — it must be picked in operator review and must remain deterministic. Note
  this is a *confidence* label, not a score.
- **`contributing_sources`** — list of distinct `source_id` values across ALL signals
  (active and suppressed), deduplicated, sorted alphabetically.
- **`parcel_lifecycle_rollup`** (per-parcel rollup; distinct from the per-signal
  `lifecycle_status` enum and the per-lifecycle `lifecycle_states[]`):
  - `ACTIVE` — at least one signal is active and not suppressed.
  - `RESOLVED` — every signal on the parcel is suppressed. (Such a parcel likely should
    not produce an active Matched lead at all — see §7 — but the value is defined for
    defensive completeness.)
  - `PARTIALLY_RESOLVED` — some signals suppressed, at least one still active.
- **`suppression_status`**:
  - `NONE` — no suppression records touch this parcel.
  - `SUPPRESSED_HIDDEN` — suppression records exist and the resolved signals are hidden
    from active output (the default behavior — §7).
  - `SUPPRESSED_VISIBLE_HISTORY` — operator config `show_resolved_history = true`;
    resolved signals are retained for the operator view only.

**Determinism is mandatory.** Every list is sorted by an explicit key; every scalar is a
pure function of the input. No timestamps other than `matched_lead_emitted_at` enter a
derived value, and `matched_lead_emitted_at` itself is metadata, never an input to
another field.

---

## 6. Source proof and click-through fields

The matched-lead layer MUST preserve click-through so operators can independently verify
every signal. This is non-negotiable for v1 and is the same principle the framework
evidence ledger enforces ("every CSV row the operator's client can trace back to a
county source", `08_evidence_ledger.md`).

For each signal in `signal_details`:

- **`source_url`** — the direct deep link to the source document, e.g.
  `https://bexar.tx.publicsearch.us/doc/314427553`. Verbatim from the translator signal;
  never templated or reconstructed.
- **`document_number`** — the publicly-searchable recorded instrument number, e.g.
  `20260010220`. Operators can use it to look the record up independently even if the
  deep link rots.
- **`source_id`** — identifies which source produced the signal
  (`publicsearch_clerk_recordings` vs `foreclosure_notices_map` vs `parcel_master`).

**Operator workflow (v1, non-negotiable):** click `source_url` → arrive at the source
portal record → verify. The Matched lead exists to make every claim auditable.

**Parallel ordering.** The top-level `source_urls` and `document_numbers` lists are
parallel arrays — index N of one corresponds to index N of the other (§5 fixes the
shared ordering: `source_id` then `event_date`). An operator reading the rendered output
can correlate URL N with document-number N without ambiguity. The per-signal
`signal_details` entries carry the same pairing intrinsically.

---

## 7. Suppression handling

This section restates design decision E3 with implementation specifics. The 28
`LIFECYCLE_SUPPRESSION_DOC_TYPE` codes (RELEASE, SATISFACTION, CANCELLATION, VOID,
DISMISSAL, SUBORDINATION, …) are the suppression universe; the translator already tags
each such record with `lifecycle_suppression_flag = true`.

**E3.a — A lone suppression record does not create an active Matched lead row.** A
RELEASE / SATISFACTION / CANCELLATION / VOID / DISMISSAL / SUBORDINATION signal that
arrives with no prior signal on the same parcel MUST NOT produce an active Matched lead.
It is logged (so the run summary still counts it) and discarded from active output. There
is nothing for it to suppress.

**E3.b — A suppression record that matches a prior signal on the same parcel.** Default
behavior: HIDE the prior signal from active output.

- `signal_count` for the parcel decreases (it counts only active, non-suppressed
  signals). If the suppressed signal was the only one, the parcel drops out of active
  output entirely.
- `signal_details` MAY still include the suppression signal record, marked
  `is_suppression_record = true`; the *suppressed* signal carries `suppressed_by`
  pointing at the suppressing signal's `signal_id`.
- `suppression_status = SUPPRESSED_HIDDEN`.
- `parcel_lifecycle_rollup` reflects the new active count — `ACTIVE`,
  `PARTIALLY_RESOLVED`, or `RESOLVED`.

**Optional operator config: `show_resolved_history = true`.** When enabled:

- resolved (suppressed) signals appear in the **OPERATOR VIEW only** (a separate
  rendering target — §8);
- resolved signals NEVER appear in the **CLIENT VIEW** or any active GHL export, under
  any circumstances;
- `suppression_status = SUPPRESSED_VISIBLE_HISTORY`.

This config is a **claim of the spec**: the Matched lead record carries enough
information (`is_suppression_record`, `suppressed_by`, `suppression_status`,
`parcel_lifecycle_rollup`, the suppressed entries retained in `signal_details`) that the
*rendering* layer can enforce the client/operator split. The actual filtering happens at
the rendering layer (a later spec); this spec only guarantees the record is rich enough
to support it.

**Matching rule.** A suppression record matches a prior signal "on the same parcel" via
`primary_parcel_id` resolution — both signals carry the same resolved
`primary_parcel_id`. **Stronger cross-document matching** — e.g. matching a RELEASE's
`document_number` reference to the exact prior LIS PENDENS instrument it releases — is
downstream pipeline work, not matched-lead-layer work. The matched-lead layer consumes
already-matched signal triplets; it groups and stacks, it does not perform the
document-to-document join. (This bounds the v1 layer to parcel-level suppression;
instrument-level suppression precision is future work — §11.)

---

## 8. Client View vs Operator View considerations

Two conceptual consumers of the Matched lead record (full rendering details deferred —
§9):

- **CLIENT VIEW** — the customer-facing output. **Active leads only.** Suppressed /
  resolved history NEVER appears. The GHL CSV export, SMS templates, and customer
  dashboards consume this view.
- **OPERATOR VIEW** — the internal operator interface. MAY optionally include suppressed
  history when `show_resolved_history = true`. Always includes the full `signal_details`
  for verification. The operator sees both what is active and what has been resolved.

The **Matched lead record shape carries enough information to support BOTH views** —
`suppression_status`, `parcel_lifecycle_rollup`, `is_suppression_record`,
`suppressed_by`, and the retained-but-flagged suppressed entries in `signal_details` are
exactly what a renderer needs to project either view. The actual filtering logic that
produces each view is downstream rendering work, defined in a later spec.

This spec does NOT define which **format** (Excel, CSV, JSON, dashboard, SMS export)
renders each view. That is deferred (§9).

---

## 9. Format rendering deferred (explicit)

- This spec defines the **Matched lead record shape only**.
- Format rendering — Excel, GHL CSV, dashboard JSON, SMS export — is downstream of the
  record shape and is **intentionally deferred**.
- A future **format-rendering spec** will define which fields appear in each rendering
  target: the Excel column set, the GHL CSV column set, the dashboard JSON projection,
  the SMS-export template. None of those column lists or schemas appears in this
  document.
- The Matched lead record shape (§3) deliberately includes **all fields any future
  rendering may need** — adding a field later is more disruptive than including it now.
  The record is intentionally a superset; each renderer projects the subset it needs.

(For reference, the framework already defines downstream projection record types in
`09_output_schemas.md` — the Dashboard record (type 6) and the CRM export record
(type 7). The future format-rendering spec should reconcile against those existing types
rather than inventing parallel ones.)

---

## 10. Test fixture requirements

Fixtures are created when the matched-lead-layer code is written, NOT now. This section
locks the fixture *plan*. Fixtures will be saved under
`scaffold/tests/fixtures/matched_lead/`.

- **Single-source, single-signal** — a parcel with one `LIS PEN` signal from
  `publicsearch_clerk_recordings` → one Matched lead record, `signal_count = 1`,
  `primary_signal = LIS_PENDENS`, `parcel_lifecycle_rollup = ACTIVE`,
  `suppression_status = NONE`.
- **Single-source, multi-signal** — a parcel with three signals from
  `publicsearch_clerk_recordings` (`PROBATE` + `LETTERS` + `WILL`) → one Matched lead
  record, `signal_count = 3`, `primary_signal = PROBATE_RECORDING`, `signal_types`
  sorted.
- **Multi-source** — a parcel with signals from BOTH `publicsearch_clerk_recordings` AND
  `foreclosure_notices_map` → one Matched lead record,
  `contributing_sources = [foreclosure_notices_map, publicsearch_clerk_recordings]`
  (sorted).
- **FC dedup** — a parcel with a `FORECLOSURE_RECORDING` from
  `publicsearch_clerk_recordings` (carrying `dedup_against_foreclosure_notices_map =
  true`) AND a foreclosure signal from `foreclosure_notices_map` → the Matched lead
  stacks the `foreclosure_notices_map` signal as `primary_signal`; the clerk-recordings
  `FC` is retained in `signal_details` but does NOT double-count toward `signal_count`.
- **Suppression match** — a parcel with a prior `LIS PEN` signal, then a `RELEASE` on the
  same parcel → `parcel_lifecycle_rollup = RESOLVED`,
  `suppression_status = SUPPRESSED_HIDDEN`, `signal_count = 0` (or the parcel drops out
  of active output entirely).
- **Suppression visible history** — the same setup with `show_resolved_history = true` →
  a Matched lead record exists with `suppression_status = SUPPRESSED_VISIBLE_HISTORY`,
  carrying the resolved signal in `signal_details` for the OPERATOR VIEW only.

Each fixture asserts the aggregation is deterministic (§5) — re-running the matched-lead
layer on the same input yields a byte-identical record.

---

## 11. Out of scope items

Explicitly NOT in the v1 matched-lead spec:

- **Format rendering** — Excel, GHL CSV, dashboard JSON, SMS export — deferred to a
  future format-rendering spec (§9).
- **Scoring** — weights, `seller_score`, bonuses, multipliers, `scoring_overrides`. The
  `primary_signal` hierarchy (§4) is ordering only, not scoring.
- **The cross-source dedup algorithm** — the matched-lead layer consumes already-resolved
  entity matches and already-deduped inputs; the dedup join (FC vs
  `foreclosure_notices_map`) is pipeline-layer work.
- **The address-normalization / entity-resolution algorithm** — handled upstream
  (`12_entity_resolution.md`); the matched-lead layer groups by the `primary_parcel_id`
  it is given.
- **LEVEL 3 inference** — heirship pattern detection, property-affecting judgment
  detection, MEMO/NOTICE/MODIFICATION sub-type inference — deferred per the translator
  spec.
- **Multi-county Matched lead records** — this spec is `bexar_tx`-scoped; cross-county
  aggregation is future scope.
- **Historical-lookup-mode output** — historical mode is disabled for v1 per the scraper
  spec.
- **Instrument-level / temporal-join lifecycle inference** — lifecycle conclusions that
  require matching documents with no shared identifier are downstream pipeline work; v1
  matched-lead-layer suppression is parcel-level only (§7).

---

## 12. Operator approval gate

This spec is not final until the operator checks every box below.

- [ ] Spec scope confirmed — `matched_lead` schema extension; not a new record type.
- [ ] Renamed `evidence_record` → `matched_lead` throughout.
- [ ] Renamed `evidence_summary` → `matched_lead_summary`.
- [ ] Field names aligned to framework vocabulary (`canonical_doc_type` →
      `normalized_doc_type`, `doc_type_code` → `raw_doc_type`, `recorded_date` →
      `event_date`, `suppresses_signal_id` → `suppressed_by`, etc.).
- [ ] Matched lead schema extensions documented (§3) and queued in
      `v5.1.2-beta-final-additions.md`.
- [ ] Evidence ledger terminology preserved for per-field provenance
      (`08_evidence_ledger.md`).
- [ ] One-row-per-parcel stacking still in effect (§4).
- [ ] Suppression handling still in effect (§7).
- [ ] Client View vs Operator View distinction still in effect (§8).
- [ ] Format rendering still deferred (§9).
- [ ] No scoring, no weights, no bonuses, no multipliers, no `seller_score`, no
      `scoring_overrides`.
- [ ] `county_slug` remains runtime-resolved per the §3 universality note.
- [ ] Lesson-learned section added (§14).
- [ ] All open questions in §13 updated with the v1 → v2 alignment trail.
- [ ] Ready to proceed to actual matched-lead-layer code (deferred to post-Phase 5).

---

## 13. Open questions for operator review

### 13.1 v1 → v2 alignment trail

v1 of this document invented an `evidence_record` record type with a 19-field shape. A
grounding pass against `09_output_schemas.md` and `08_evidence_ledger.md` found two
collisions, and the operator directed the v2 alignment:

- **`evidence_record` → `matched_lead`.** The framework already has a parcel-grouped,
  signal-stacked record — the **Matched lead** (record type 4 in `09_output_schemas.md`,
  stored at `data/leads.json`). v2 renames the artifact and aligns to that schema; §1.1
  cites the existing Matched lead fields, and §3 marks each field EXISTING or PROPOSED
  EXTENSION.
- **"evidence" terminology collision.** "Evidence" is reserved for the per-field
  provenance ledger (`08_evidence_ledger.md`). v2 stopped using it for the lead row:
  `evidence_record` → `matched_lead`, `evidence_summary` → `matched_lead_summary`,
  `evidence_emitted_at` → `matched_lead_emitted_at`, "evidence layer" → "matched-lead
  layer". The ledger concept (`evidence_id`, `evidence_ids[]`, the evidence object) is
  preserved unchanged.

### 13.2 The 12 v1 TBD fields — v2 resolution

    v1 field name          v2 resolution
    ---------------------  --------------------------------------------------
    evidence_record_id     -> renamed to lead_id (framework Matched-lead id)
    parcel_id              -> renamed to primary_parcel_id (framework field)
    county_slug            -> kept; STILL TBD (no Matched-lead county field;
                              manifest uses county_id — adopt for consistency?)
    parcel_grid_identifiers-> kept; STILL TBD (no framework canonical; backlog
                              item B in v5.1.2-beta-final-additions.md)
    evidence_summary       -> renamed to matched_lead_summary
    source_confidence      -> kept; STILL TBD (aggregation rule unresolved;
                              relationship to source_reliability_grade A-E)
    lifecycle_status       -> renamed to parcel_lifecycle_rollup (avoids the
                              per-signal lifecycle_status enum collision)
    canonical_doc_type     -> renamed to normalized_doc_type (framework field)
    doc_type_code          -> renamed to raw_doc_type (framework field)
    recorded_date          -> renamed to event_date (framework field)
    grantor / grantee      -> kept; STILL TBD (framework models parties as
                              party_names[] + party_roles{})
    suppresses_signal_id   -> renamed to suppressed_by AND direction flipped
                              (the suppressed signal points to its suppressor,
                              per the Normalized-signal convention)

**8 of the 12 v1 TBDs were renamed to a framework-canonical name; 4 remain TBD**
(`county_slug`, `parcel_grid_identifiers`, `source_confidence`, `grantor`/`grantee`).

### 13.3 New TBDs surfaced by the v2 alignment

1. **Flag placement.** `lifecycle_suppression_flag` and
   `dedup_against_foreclosure_notices_map` are translator LEVEL 2 flags. v2 places them
   in `signal_details` (signal level). The framework convention for non-standard signal
   flags is unsettled — the translator spec's §15 open question 2 raises the same point.
   Confirm whether they belong at signal level, top level, or in `review_flags[]`.
2. **`signal_details` vs the existing `signals[]`.** The Matched lead's existing
   `signals[]` holds `signal_id` references; `signal_details` inlines per-signal detail.
   Confirm whether the matched-lead layer should populate the existing `signals[]`
   (refs) AND `signal_details` (inline), or whether `signal_details` replaces `signals[]`
   for this source.
3. **`document_number` vs `source_document_id`.** The evidence object uses
   `source_document_id`; this spec keeps `document_number` for source-native clarity.
   Confirm the canonical name.
4. **Several PROPOSED EXTENSION fields need framework registry entries** —
   `signal_count`, `primary_signal`, `source_urls`, `document_numbers`,
   `latest_event_date`, `earliest_event_date`, `matched_lead_summary`,
   `source_confidence`, `parcel_lifecycle_rollup`, `suppression_status`,
   `contributing_sources`, `matched_lead_emitted_at`, `signal_details`,
   `is_suppression_record`, `doc_type_label`. These are queued for v5.1.2-beta-final via
   `v5.1.2-beta-final-additions.md` (the canonical-record-fields registry, item B, plus
   a Matched-lead schema-extension entry).

### 13.4 Decisions still pending

5. **Relationship to the existing Matched lead — full reconciliation.** §1.1 + §3 align
   field-by-field, but the framework owner should confirm the matched-lead layer emits
   genuine record-type-4 `Matched lead` rows (extended), not a parallel artifact.
6. **`primary_signal` priority hierarchy (§4.1)** — TBD-PROPOSED; operator may reorder.
7. **`source_confidence` aggregation rule** — MAX vs most-conservative vs grade-weighted
   (§5).
8. **`parcel_lifecycle_rollup` vs `lifecycle_states[]`** — confirm the rollup is an
   acceptable summary alongside the framework's richer per-lifecycle `lifecycle_states[]`,
   rather than a competing representation.
9. **`signal_details` — all signals or active only?** Confirm suppressed entries are
   retained-but-flagged (the §7 / §8 assumption).
10. **`matched_lead_summary` template** — lock the exact deterministic summary-string
    template (§5).

---

## 14. Lesson learned — framework alignment

Before defining any output artifact in future specs, Claude Code MUST inspect existing
architecture docs first — `knowledge_base/architecture/08_evidence_ledger.md`,
`09_output_schemas.md`, `12_entity_resolution.md`, `MASTER_PROMPT.md` — and align with
existing schemas before inventing new record types or canonical field names.

This v1 → v2 alignment cycle revealed that the v1 spec invented an `evidence_record` type
that overlapped the existing **Matched lead** schema (record type 4 in
`09_output_schemas.md`), and used canonical field names that collided with framework
vocabulary — including the reserved term "evidence" (`08_evidence_ledger.md`) and the
per-signal `lifecycle_status` enum. The v2 edit renamed the artifact to `matched_lead`,
aligned the field names to the framework's existing canonical vocabulary, and reframed
the spec as a documented extension of an existing schema rather than a new record type.

Future spec prompts should EXPLICITLY require: "read `09_output_schemas.md` and
`08_evidence_ledger.md` first; verify no existing schema covers what this spec is
defining; align field names to the existing canonical vocabulary before introducing new
names." Inventing first and reconciling later costs a full revision cycle.

---

## 15. Document end marker

Spec scope was honored. This step edited exactly one file —
`runs/bexar_tx/recon/publicsearch_clerk_recordings_evidence_output_spec.md` — applying
the operator's 10 alignment decisions. No Python file was written; no matched-lead-layer
code exists. No `scaffold/`, `scrapers/`, pipeline, framework, or `knowledge_base/` file
was modified — `MASTER_PROMPT.md`, `09_output_schemas.md`, `08_evidence_ledger.md`,
`12_entity_resolution.md`, the translator registry, the three existing translators, the
`v5.1.2-beta-final-additions.md` backlog, and all prior recon artifacts were read only.
No format rendering (Excel / CSV / dashboard JSON / SMS export) was defined. No scoring
weights, scores, bonuses, multipliers, `seller_score` logic, or `scoring_overrides`
appear anywhere. Nothing was committed.

PUBLICSEARCH MATCHED LEAD SPEC v2 — AWAITING OPERATOR REVIEW
