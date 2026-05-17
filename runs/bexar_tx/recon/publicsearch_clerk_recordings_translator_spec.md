# Bexar PublicSearch clerk_recordings — Translator Spec (v1)

## 0. Status and scope

- **Date:** 2026-05-17
- **Version:** v1
- **Operator:** Quentin Flores
- **County:** bexar_tx
- **Source ID:** publicsearch_clerk_recordings
- **Translator scope level:** LEVEL 2 (locked by operator)

**Scope — strict.** This document specifies ONLY the `publicsearch_clerk_recordings`
translator: the pipeline component that consumes the wrapped raw records produced by the
locked v2 scraper and converts them into the framework's canonical
signals/parcels/metadata output. It does NOT cover, and the reader should infer nothing
about:

- the scraper (`publicsearch_clerk_recordings_scraper_spec.md` — already locked at v2;
  its §3.2 record shape is this spec's input contract);
- evidence-output design (step 6 — separate spec later);
- scoring calibration (deferred — separate phase later);
- pipeline wiring into `build_leads.py` (later);
- the actual Python file
  `scaffold/pipeline/translators/publicsearch_clerk_recordings.py` — written LATER, only
  AFTER the operator approves this spec;
- any framework-canonical changes;
- LEVEL 3 inference — heirship pattern detection, property-affecting judgment detection,
  MEMO/NOTICE/MODIFICATION semantic sub-type inference, or any regex-driven inference
  (all explicitly deferred — see §9).

**This spec must be operator-approved before any translator code is written.**

**Two findings up front** (both grounded by reading the actual framework files; see §15
for full detail):

1. The framework's registered translators do NOT emit a "canonical translated record"
   object with `canonical_record_id` / `canonical_payload` / `field_map_applied` /
   `record_emitted_at`. They return a **three-tuple** `(signals, parcels,
   per_signal_meta_by_url)`. This spec documents that real shape (§3.2), not an invented
   one.
2. `publicsearch_doc_type_map_proposal.json` has **no `canonical_doc_type` field** on its
   entries. The §4 mapping table's canonical column is therefore *proposed by this spec*
   and cross-checked against `knowledge_base/domain/canonical_doc_types.json`, rather
   than read from the proposal.

---

## 1. Translator role in the pipeline

The translator is the boundary component that converts source-specific PublicSearch
knowledge into framework-canonical vocabulary. Pipeline flow:

    PublicSearch portal
        |
        v
    [scraper publicsearch_clerk_recordings]   <-- locked v2 scraper spec
        |
        v
    data/raw/clerk_recordings.jsonl (wrapped raw_payload per §4.32)
        |
        v
    [translator publicsearch_clerk_recordings]   <-- THIS SPEC
        |
        v
    canonical translated records (translator registry contract output)
        |
        v
    [downstream pipeline: matchers, scoring, evidence ledger, lead emission]

The translator is the boundary where source-specific knowledge — PublicSearch doc-type
codes, PublicSearch internal ids, Bexar field names — is converted to framework-canonical
vocabulary (canonical doc types, canonical signal/parcel fields). **After the translator,
no downstream pipeline code should need to know that PublicSearch exists.** Matchers,
scoring, the evidence ledger, and lead emission all consume the canonical shape only.

Per `MASTER_PROMPT.md §4.31` (universality contract) and the registry contract in
`scaffold/pipeline/translators/__init__.py`, the eventual translator *code* must be
county-agnostic — all county-specific data arrives through the `county_config` and
`source_config` arguments at call time. This **spec document** lives under
`runs/bexar_tx/` and may freely reference Bexar; the future Python file may not (see
§10).

---

## 2. Input contract

### 2.1 Input source

- **File:** `data/raw/clerk_recordings.jsonl`, produced by the locked v2 scraper.
- **Format:** one JSON object per line, exactly as defined in scraper spec §3.2.

In practice the pipeline loader reads this file, parses each line, and hands the
translator a `list[dict]` of wrapped raw records (the `raw_records` argument — see §3.1).
The translator does not open the file itself.

### 2.2 Input record shape (verbatim from scraper spec §3.2)

Each input record:

    {
      "raw_record_id": "publicsearch_bexar_<internal_doc_id>",
      "source_id": "publicsearch_clerk_recordings",
      "source_url": "https://bexar.tx.publicsearch.us/doc/<internal_doc_id>",
      "source_fetched_at": "<ISO8601 UTC>",
      "parser_confidence": 95,
      "raw_payload": {
        "internal_doc_id": "<string>",
        "document_number": "<string>",
        "doc_type_code": "<string, e.g. LIS PEN>",
        "doc_type_label": "<string, e.g. LIS PENDENS>",
        "recorded_date": "<YYYY-MM-DD>",
        "grantor": "<string or null>",
        "grantee": "<string or null>",
        "property_address": "<string or null>",
        "legal_description": "<string or null>",
        "book_volume_page": "<string or null>",
        "parcel_grid_identifiers": "<string or null>"
      }
    }

This shape is `MASTER_PROMPT.md §4.32`-compliant. The top-level fields —
`raw_record_id`, `source_id`, `source_url`, `source_fetched_at`, `parser_confidence`,
`raw_payload` — are framework metadata; `raw_payload` is the only source-specific block.
The §4.32 contract is enforced by `scaffold/tests/test_translator_registry.py`, which
feeds wrapped/normalized synthetic records to every registered translator and asserts
correct output.

### 2.3 Input validation

The translator MUST validate every input record before transforming it. Validation
rules:

- `parser_confidence` must be an integer 0–100 — else skip the record, log a warning.
- `raw_payload.internal_doc_id` must be present and non-empty — else skip, log a warning.
- `raw_payload.doc_type_code` must match a known code in
  `publicsearch_doc_type_map_proposal.json` (the 124-code catalog) — else skip, log a
  warning, tag `UNKNOWN_DOC_TYPE`.
- `raw_payload.recorded_date` must parse as `YYYY-MM-DD` — else skip, log a warning.
- All other `raw_payload` fields are nullable per the scraper contract; null is valid.

The translator MUST NOT halt the whole run on individual record failures. Each
validation error is logged with the offending `raw_record_id` and the failing rule;
downstream consumers see only successfully translated records. A run-level summary
records how many records were skipped and why (see §12).

---

## 3. Output contract

### 3.1 Output target

The translator is a registered function invoked by the pipeline orchestrator
(`build_leads.py`) through the framework's translator registry
(`scaffold/pipeline/translators/`). Verified call convention (from
`scaffold/pipeline/translators/__init__.py` and the three built-in translators
`foreclosure_notices.py`, `parcel_master.py`, `csv_static_list.py`):

    translator_fn(raw_records, county_config, source_config)
        -> (signals, parcels, per_signal_meta_by_url)

- `raw_records` — `list[dict]`, the wrapped raw records from §2.
- `county_config` — the full county config (geography, sources, etc.).
- `source_config` — this source's config block (`translator`, `translator_config`,
  `parcel_id_prefix`, `field_map`).
- Return — a three-tuple, type `tuple[list[dict], list[dict], dict[str, dict]]`.

The translator does NOT write files. The orchestrator owns all I/O; the translator is a
pure in-memory transformation.

### 3.2 Output record shape (grounded in the framework's actual translators)

**Important.** The framework's registered translators do NOT emit a flat "canonical
translated record" with `canonical_record_id` / `canonical_payload` / `field_map_applied`
/ `record_emitted_at`. Reading `__init__.py` and `foreclosure_notices.py` directly, every
built-in translator returns the three-tuple `(signals, parcels,
per_signal_meta_by_url)`. This spec documents that real shape. The divergence from the
output shape assumed in the step-5 instructions is recorded as open question 1 in §15.

**signals** — `list[dict]`. One signal per successfully translated input record. Shape
modeled on `foreclosure_notices.py`, with the two LEVEL 2 flags added:

    {
      "signal_id": "sig_<16-hex>",
      "raw_record_id": "publicsearch_bexar_<internal_doc_id>",
      "source_id": "publicsearch_clerk_recordings",
      "source_url": "https://bexar.tx.publicsearch.us/doc/<internal_doc_id>",
      "doc_type": "<canonical_doc_type — see §4>",
      "doc_type_subtype_label": "<PublicSearch doc_type_label, e.g. LIS PENDENS>",
      "doc_number": "<raw_payload.document_number>",
      "primary_parcel_id": "<parcel_id_prefix + hash — see parcels below>",
      "filing_date": "<raw_payload.recorded_date, YYYY-MM-DD>",
      "parser_confidence": 95,
      "lifecycle_suppression_flag": <bool — §5.1>,
      "dedup_against_foreclosure_notices_map": <bool — §5.2>
    }

- `signal_id` is a stable hash, e.g. `"sig_" + sha1(f"{source_id}|{document_number}|
  {internal_doc_id}").hexdigest()[:16]` — matching the `foreclosure_notices.py`
  convention.
- `doc_type` carries the **canonical doc type** (the translator's primary mapping
  output); `doc_type_subtype_label` carries the verbatim PublicSearch label for audit.
- `lifecycle_suppression_flag` and `dedup_against_foreclosure_notices_map` are new keys
  beyond the `foreclosure_notices.py` signal shape. Whether the framework prefers
  dedicated signal keys or routing these through `per_signal_meta_by_url`'s
  `preset_review_flags` list is open question 2 in §15.

**parcels** — `list[dict]`. Placeholder parcels, deduplicated within the run. Shape from
`foreclosure_notices.py`:

    {
      "parcel_id": "<parcel_id_prefix + sha1(address)[:12]>",
      "address": "<raw_payload.property_address or null>",
      "city": null,
      "zip": null,
      "owner_name": "<grantor or grantee — see field_map §6, currently TBD>",
      "parcel_master_status": "placeholder_pending_enrichment"
    }

- `parcel_id_prefix` is `BX-PS-` per the scraper spec / source config.
- `city` and `zip` are `null` in v1 — the v2 scraper does not capture city (it was
  dropped as a detail-only field). Downstream parcel-master enrichment fills them.
- **Address-less records:** many clerk recordings have `property_address = null`/`N/A`
  (probe-confirmed — non-conveyance doc types frequently have no address). The
  `foreclosure_notices.py` parcel-id helper hashes the address, which fails when the
  address is null. For such records the translator falls back to hashing
  `internal_doc_id` so a stable `parcel_id` still exists. This fallback is flagged as
  open question 5 in §15.

**per_signal_meta_by_url** — `dict[str, dict]`, keyed by `source_url`. Shape from
`foreclosure_notices.py`, extended with clerk-recording context:

    {
      "<source_url>": {
        "preset_review_flags": [<strings>],
        "match_confidence": 0,
        "match_method": "placeholder",
        "address": "<property_address or null>",
        "city": null,
        "zip": null,
        "primary_parcel_id": "<parcel_id>",
        "grantor": "<raw_payload.grantor or null>",
        "grantee": "<raw_payload.grantee or null>",
        "legal_description": "<raw_payload.legal_description or null>",
        "parcel_grid_identifiers": "<raw_payload.parcel_grid_identifiers or null>"
      }
    }

`grantor`, `grantee`, `legal_description`, and `parcel_grid_identifiers` are carried in
the metadata so downstream matchers and the evidence ledger can use them without the
translator interpreting them (interpretation is LEVEL 3 — §9).

### 3.3 Per-record canonical_doc_type mapping

The translator's primary job is to map each input `doc_type_code` to a canonical doc
type, emitted as the signal's `doc_type` field. The mapping table is §4. The dispatch is
config-driven: the translator reads a `doc_type_code_map` from
`source_config.translator_config` (analogous to the `layer_doc_type_map` that
`foreclosure_notices.py` uses for layer dispatch). The translator code contains no
hardcoded code→canonical pairs (universality, §10).

---

## 4. Doc-type → canonical mapping table

This table covers the 20 daily-refresh codes (8 CORE + 12 EXPANDED). The canonical column
is **proposed by this spec** — `publicsearch_doc_type_map_proposal.json` carries no
`canonical_doc_type` field (see §0 / §15). Each proposed canonical is cross-checked
against the 74 entries in `knowledge_base/domain/canonical_doc_types.json`
(`canonical_types`):

- **MATCH** — the canonical already exists in `canonical_doc_types.json`; wire directly.
- **GAP** — the canonical does not yet exist; it must be added to
  `canonical_doc_types.json` in v5.1.2-beta-final. The translator MAY emit a GAP
  canonical now; framework promotion of the vocabulary is a separate, deferred work item.

### 4.1 CORE tier (8 codes)

- `LIS PEN` — label `LIS PENDENS` — canonical **`LIS_PENDENS`** — **MATCH**.
- `MECHLN` — label `MECHANICS LIEN` — canonical **`MECHANICS_LIEN`** — **MATCH**.
- `FTL` — label `FEDERAL TAX LIEN` — canonical **`FEDERAL_TAX_LIEN`** — **MATCH**.
- `STL` — label `STATE TAX LIEN` — canonical **`STATE_TAX_LIEN`** — **MATCH**.
- `PROBATE` — label `PROBATE` — canonical **`PROBATE_RECORDING`** — **GAP**. No generic
  probate canonical exists (`canonical_doc_types.json` has `LETTERS_TESTAMENTARY`,
  `LETTERS_OF_ADMINISTRATION`, `DETERMINATION_OF_HEIRSHIP`, `AFFIDAVIT_OF_HEIRSHIP`,
  `MUNIMENT_OF_TITLE` — but no umbrella `PROBATE_RECORDING`).
- `LETTERS` — label `LETTERS` — canonical **`PROBATE_LETTERS`** — **GAP**. The PublicSearch
  `LETTERS` code is an umbrella; the registry splits this into `LETTERS_TESTAMENTARY` and
  `LETTERS_OF_ADMINISTRATION` (both MATCH individually) but has no umbrella covering
  both. Distinguishing the two is a content read the v1 translator does not do; an
  umbrella `PROBATE_LETTERS` is proposed.
- `WILL` — label `WILL & TESTAMENT` — canonical **`WILL_RECORDING`** — **GAP**. No `WILL`
  canonical exists (`MUNIMENT_OF_TITLE` is will-adjacent but semantically distinct).
- `DECREE` — label `DECREE` — canonical **`COURT_DECREE`** — **GAP**. The registry has
  `FINAL_DECREE_OF_DIVORCE` and `FINAL_JUDGMENT_OF_FORECLOSURE` but no generic
  `COURT_DECREE`; PublicSearch `DECREE` is a broad umbrella.

### 4.2 EXPANDED tier (12 codes)

- `HOSP LN` — label `HOSPITAL LIEN` — canonical **`HOSPITAL_LIEN`** — **MATCH**.
- `AFFIDAV` — label `AFFIDAVIT` — canonical **`GENERIC_AFFIDAVIT`** — **GAP**.
  `AFFIDAVIT_OF_HEIRSHIP` exists, but `AFFIDAV` is the umbrella for all affidavits;
  mapping it to `AFFIDAVIT_OF_HEIRSHIP` would be wrong (heirship is a minority subset, and
  heirship detection is LEVEL 3 — §9). An umbrella `GENERIC_AFFIDAVIT` is proposed.
- `CSUP LN` — label `CHILD SUPPORT LN` — canonical **`CHILD_SUPPORT_LIEN`** — **GAP**.
- `JUDG` — label `JUDGMENT` — canonical **`COURT_JUDGMENT`** — **GAP**. `JUDGMENT_LIEN`
  and `VACATED_JUDGMENT` exist, but `JUDG` is the umbrella and not every judgment is a
  property lien (operator strict rule). A generic `COURT_JUDGMENT` is proposed; isolating
  property-affecting judgments is LEVEL 3 (§9).
- `SJ` — label `State-Judgment` — canonical **`STATE_JUDGMENT`** — **GAP**.
- `LIEN` — label `LIEN` — canonical **`GENERIC_LIEN`** — **GAP**. Many specific lien
  canonicals exist (`CONSTRUCTION_LIEN`, `HOA_LIEN`, `MUNICIPAL_LIEN`, `JUDGMENT_LIEN`,
  `WATER_LIEN`, …) but no generic umbrella; `LIEN` is the broad PublicSearch umbrella.
- `LNLD LN` — label `LANDLORD LIEN` — canonical **`LANDLORD_LIEN`** — **GAP**.
- `PA` — label `POWER OF ATTORNEY` — canonical **`POWER_OF_ATTORNEY`** — **GAP**.
- `MEMO` — label `MEMORANDUM` — canonical **`GENERIC_MEMORANDUM`** — **GAP**. Broad
  umbrella; sub-type inference is LEVEL 3 (§9).
- `NOTICE` — label `NOTICE` — canonical **`GENERIC_NOTICE`** — **GAP**. Specific notice
  canonicals exist (`NOTICE_OF_DEFAULT`, `NOTICE_OF_SALE`,
  `NOTICE_OF_SUBSTITUTE_TRUSTEE_SALE`, `CODE_VIOLATION_NOTICE`, `CONDEMNATION_NOTICE`,
  `TAX_FORECLOSURE_NOTICE`) but no generic umbrella; sub-type inference is LEVEL 3.
- `MOD` — label `MODIFICATION` — canonical **`GENERIC_MODIFICATION`** — **GAP**.
  `MORTGAGE_MODIFICATION` exists but `MOD` is broader (loan mod, trust mod, restrictive
  covenant mod); mapping the umbrella to the mortgage-specific canonical would be wrong.
- `FC` — label `FORECLOSURE` — canonical **`FORECLOSURE_RECORDING`** — **GAP**.
  Foreclosure-stage canonicals exist (`NOTICE_OF_SUBSTITUTE_TRUSTEE_SALE`,
  `FINAL_JUDGMENT_OF_FORECLOSURE`, `TAX_FORECLOSURE_NOTICE`) but no generic
  `FORECLOSURE_RECORDING`.

### 4.3 Mapping summary

- **MATCH (5):** `LIS_PENDENS`, `MECHANICS_LIEN`, `FEDERAL_TAX_LIEN`, `STATE_TAX_LIEN`,
  `HOSPITAL_LIEN`.
- **GAP (15):** `PROBATE_RECORDING`, `PROBATE_LETTERS`, `WILL_RECORDING`, `COURT_DECREE`,
  `GENERIC_AFFIDAVIT`, `CHILD_SUPPORT_LIEN`, `COURT_JUDGMENT`, `STATE_JUDGMENT`,
  `GENERIC_LIEN`, `LANDLORD_LIEN`, `POWER_OF_ATTORNEY`, `GENERIC_MEMORANDUM`,
  `GENERIC_NOTICE`, `GENERIC_MODIFICATION`, `FORECLOSURE_RECORDING`.

Total 20: 5 MATCH + 15 GAP. The 5 MATCH canonicals are wired directly. The 15 GAP
canonicals are listed in §15 as a canonical-vocabulary addition needed in
v5.1.2-beta-final; until then the translator emits them as new canonical strings and the
`canonical_doc_types.json` promotion is a deferred, separate work item.

### 4.4 Behavior for codes NOT in the daily-refresh list (the other 104 codes)

The v1 scraper pulls only the 20 daily-refresh codes, so in normal operation no other
codes reach the translator. The translator is nonetheless defensive:

- **`LIFECYCLE_SUPPRESSION_DOC_TYPE` codes (28 — see §5.1).** If the scraper somehow
  emits one, the translator STILL translates it and sets `lifecycle_suppression_flag =
  true`. The `doc_type` canonical for these can be a best-effort GAP canonical or
  `UNKNOWN_DOC_TYPE`; the suppression flag is the load-bearing output. This is defense in
  depth.
- **`NOISY_SKIP`, `FORECLOSURE_DUPLICATE_SKIP`, `CONTEXT_SIGNAL`,
  `NEEDS_OPERATOR_REVIEW` codes.** The translator logs a warning
  (`UNKNOWN_DOC_TYPE_FOR_DAILY_REFRESH`) and skips the record. These should never appear
  in v1 daily input; if they do, it is an upstream scraper bug and the warning surfaces
  it.

---

## 5. Level 2 flags (lifecycle and FC dedup)

LEVEL 2 is the locked v1 scope: LEVEL 1 (code→canonical mapping + field_map application +
contract-compliant output) plus the two flags below. The flags only TAG records; the
joins they enable are downstream pipeline work.

### 5.1 lifecycle_suppression_flag

For input records whose `doc_type_code` is classified `LIFECYCLE_SUPPRESSION_DOC_TYPE` in
`publicsearch_doc_type_map_proposal.json`:

- the translator sets `lifecycle_suppression_flag = true` on the emitted signal;
- translation continues normally — the record is NOT rejected;
- downstream, the pipeline uses this flag to age-out earlier leads whose underlying
  signal (e.g. a lis pendens) has since been released. **The v1 translator only TAGS;
  the age-out join is pipeline work and is deferred.**

For all other records the flag is `false` (never null).

The 28 lifecycle codes the translator recognizes (resolved at runtime from source
config, not hardcoded — §11):

    VOID UCCRP, PART RL STL, RL STL, VOID STL, CANC J, CANCEL, DISMISS, P RL J,
    PART RL, RECONV, REINST, REL H LN, RELEASE, REMOVAL, RESCISS, REVOCTN, RL H LN,
    RL J, SAT, SAT J, SUBORD, TERMIN, VOID OPR, WAIVER, SR, PART RL FTL, RL FTL,
    VOID FTL

None of these 28 are in the 20-code daily-refresh list, so in normal v1 operation every
emitted signal has `lifecycle_suppression_flag = false`. The flag exists for defense in
depth (§4.4) and for the day the EXPANDED list or scraper scope changes.

### 5.2 dedup_against_foreclosure_notices_map

For input records whose `doc_type_code` is `FC`:

- the translator sets `dedup_against_foreclosure_notices_map = true` on the emitted
  signal;
- downstream, the pipeline uses this flag when counting distinct foreclosure leads, to
  avoid double-counting between PublicSearch `FC` records and the Bexar County
  Foreclosure Notices ArcGIS source (the `foreclosure_notices` translator's output).

For all other records the flag is `false` (never null). The flag carries **no sample
data** needed to perform the dedup — it is purely a tag for downstream logic. The dedup
join algorithm (matching on parcel, address, recording date, party) is downstream
pipeline work and is deferred; a backlog item to quantify FC vs. ArcGIS overlap with a
30-day comparison sample already exists in the doc-type-map summary.

---

## 6. field_map application

LEVEL 1 includes renaming the scraper's normalized `raw_payload` field names to
framework-canonical names. The translator does NOT define the rename map — it reads a
`field_map` from `source_config` and applies it, exactly as `foreclosure_notices.py`
does (`_resolve(canonical_name)` returns `field_map.get(canonical_name, canonical_name)`
— identity mapping when a key is absent).

`field_map` keys are the canonical names the translator expects; values are the actual
`raw_payload` field names the scraper writes. `field_map` is config, not translator
logic — the translator just applies what is there.

**Canonical-name vocabulary — partially TBD.** Reading `MASTER_PROMPT.md §4.32` and
`foreclosure_notices.py`, the confirmed framework-canonical `raw_payload` field names
are `address`, `doc_number`, `recording_year`, `recording_month`, `city`, `zip`,
`owner_name`, `layer_id`. There is no published `canonical_record_fields.json` yet
(§4.32 lists it as a v5.1.2-beta-final backlog item). Mappings the Bexar `field_map`
will need:

- `raw_payload.document_number` → canonical **`doc_number`** — confirmed (matches
  `foreclosure_notices.py`).
- `raw_payload.property_address` → canonical **`address`** — confirmed.
- `raw_payload.recorded_date` → **TBD.** The framework canonical convention is split
  integer fields `recording_year` + `recording_month`, not a single `YYYY-MM-DD`
  `recording_date`. The scraper emits a single `recorded_date`. Either the Bexar
  `field_map` plus a small translator-side split is needed, or a `recording_date`
  canonical must be confirmed. Open question 3 (§15).
- `raw_payload.grantor` → **TBD.** `foreclosure_notices.py` uses a single `owner_name`;
  clerk recordings have two parties (grantor and grantee). The canonical convention for
  two-party records is unclear (`party_roles` has 16 entries in
  `canonical_doc_types.json`, suggesting a role-tagged model). Open question 3 (§15).
- `raw_payload.grantee` → **TBD** — same as grantor.
- `raw_payload.legal_description` → canonical **`legal_description`** — assumed identity;
  to be confirmed.
- `raw_payload.parcel_grid_identifiers` → **TBD.** No canonical equivalent is visible in
  the framework files. Carried in `per_signal_meta_by_url` verbatim for v1; canonical
  naming deferred. Open question 3 (§15).
- `raw_payload.internal_doc_id`, `raw_payload.doc_type_code`, `raw_payload.doc_type_label`
  — these are not renamed; they are consumed directly by the translator to build
  `signal_id`, `source_url`, `doc_type`, and `doc_type_subtype_label`.

The full Bexar `field_map` block is to be authored alongside the v5.1.2-beta-final
canonical-field-name registry. This spec deliberately does NOT invent canonical names;
every uncertain rename is marked TBD and listed in §15.

---

## 7. Validation rules

The translator MUST verify all of the following per record. Failed records are NOT
emitted; each failure is logged with `raw_record_id`, the failing rule, and the reason.

1. **Input shape** — the record is §4.32-compliant: top-level `raw_record_id`,
   `source_id`, `source_url`, `source_fetched_at`, `parser_confidence`, `raw_payload`
   present; `raw_payload` is a dict. (Restates §2.3.)
2. **Known doc-type code** — `raw_payload.doc_type_code` is in
   `publicsearch_doc_type_map_proposal.json`'s 124-code catalog.
3. **Canonical resolved** — the mapped `canonical_doc_type` is non-null and, if it is NOT
   one of the 15 known GAP canonicals (§4.3), exists in `canonical_doc_types.json`.
4. **Output completeness** — every emitted signal carries all fields the framework signal
   contract requires (`signal_id`, `raw_record_id`, `source_id`, `source_url`,
   `doc_type`, `doc_number`, `primary_parcel_id`, `filing_date`, `parser_confidence` — per
   `foreclosure_notices.py`), and every emitted parcel carries `parcel_id`,
   `parcel_master_status`.
5. **Flags are booleans** — `lifecycle_suppression_flag` and
   `dedup_against_foreclosure_notices_map` are always `true`/`false`, never null or
   absent.

A framework-contract violation that the translator cannot localize to one record (e.g. a
malformed `county_config`/`source_config`) is a hard error: the translator raises and the
run halts with an explicit message. Per-record problems never halt the run.

---

## 8. Test fixtures (required before code writing)

Fixtures are created during the translator code-writing step, NOT now. This section
locks the fixture *plan* so the eventual code is testable.

### 8.1 Sample wrapped raw_payload records

At least 3 sample input records, covering:

- **A CORE-tier code** — `LIS PEN`. A real-shaped example derived from probe output:

      {
        "raw_record_id": "publicsearch_bexar_314427553",
        "source_id": "publicsearch_clerk_recordings",
        "source_url": "https://bexar.tx.publicsearch.us/doc/314427553",
        "source_fetched_at": "2026-05-17T12:00:00Z",
        "parser_confidence": 95,
        "raw_payload": {
          "internal_doc_id": "314427553",
          "document_number": "20260070780",
          "doc_type_code": "LIS PEN",
          "doc_type_label": "LIS PENDENS",
          "recorded_date": "2026-05-10",
          "grantor": "DOE JOHN",
          "grantee": "ACME BANK NA",
          "property_address": "123 EXAMPLE ST, SAN ANTONIO, TEXAS, 78201",
          "legal_description": "Subdivision - Name: EXAMPLE PLACE Lot: 12 Block: 3",
          "book_volume_page": "--/--/--",
          "parcel_grid_identifiers": "Lot 12, Block 3, NCB N/A, County Block N/A"
        }
      }

- **An EXPANDED-tier code with `operator_confidence_label = LOW`** — `NOTICE` (broad
  umbrella; same wrapped shape, `doc_type_code` = `NOTICE`, `doc_type_label` = `NOTICE`).
- **A LIFECYCLE_SUPPRESSION code** — `RELEASE` (`doc_type_code` = `RELEASE`,
  `doc_type_label` = `RELEASE`). The v1 scraper will not emit this, but the translator
  must handle the defensive case (§4.4 / §5.1).

Sample records may be derived from the real probe capture `raw_html/02_result_list.html`.
Fixtures will be saved under `scaffold/tests/fixtures/publicsearch_clerk_recordings/` when
the translator code is written — not now.

### 8.2 Expected output records

For each sample input, the expected canonical output:

- **`LIS PEN`** → one signal with `doc_type = LIS_PENDENS` (MATCH),
  `doc_type_subtype_label = LIS PENDENS`, `lifecycle_suppression_flag = false`,
  `dedup_against_foreclosure_notices_map = false`; one placeholder parcel; one
  `per_signal_meta_by_url` entry.
- **`NOTICE`** → one signal with `doc_type = GENERIC_NOTICE` (GAP),
  `lifecycle_suppression_flag = false`, `dedup_against_foreclosure_notices_map = false`.
  Confirms an EXPANDED LOW-confidence umbrella code translates without any LEVEL 3
  inference.
- **`RELEASE`** → one signal with `lifecycle_suppression_flag = true` (RELEASE is a
  LIFECYCLE_SUPPRESSION code), `dedup_against_foreclosure_notices_map = false`. Confirms
  the defensive lifecycle path.
- **An `FC` record** (add as a 4th fixture) → one signal with
  `dedup_against_foreclosure_notices_map = true`, `doc_type = FORECLOSURE_RECORDING`
  (GAP).
- Every emitted signal/parcel passes the §4.32-derived output contract checks.

### 8.3 Test invariants

`scaffold/tests/test_translator_registry.py` feeds wrapped/normalized synthetic records
to every registered translator and asserts correct output. For
`publicsearch_clerk_recordings` the invariants it will enforce (per the registry
contract in `__init__.py` and the §4.32 contract):

- the translator is registered under the name `publicsearch_clerk_recordings` and
  resolvable via `lookup()`;
- it accepts the three-argument call `(raw_records, county_config, source_config)` and
  returns a three-tuple `(signals, parcels, per_signal_meta_by_url)` of the correct
  types;
- it reads only `raw_payload` (never top-level fields) for source data;
- it does not assume vendor-protocol field names — all source-field access goes through
  `field_map`;
- every emitted signal has the required signal fields (§7 rule 4);
- the translator code contains no county-specific literal (universality, §10).

The exact assertion set of `test_translator_registry.py` should be re-read when the
translator code is written; this list is the expected shape, recorded as open question 1
in §15 where the contract was not fully explicit.

---

## 9. Out of scope for v1 translator (Level 3 deferred)

LEVEL 3 is explicitly NOT in v1. Each item below is deferred, with the reason:

- **Heirship pattern detection on `AFFIDAV` records** — regex on grantor/grantee/
  legal_description for `ESTATE OF`, `HEIRS OF`, `DECEASED`, etc. Deferred: needs sample
  data and evidence-based pattern design; the v1 translator maps `AFFIDAV` to the
  umbrella `GENERIC_AFFIDAVIT` and stops.
- **Property-affecting judgment detection on `JUDG`, `SJ`, `LIEN`, `TRSCR J`** — deferred:
  needs a corpus of property-affecting vs. non-property-affecting judgments to design the
  classifier, plus operator feedback. v1 maps to the umbrella canonical and stops.
- **`MEMO` / `NOTICE` / `MODIFICATION` semantic sub-type detection** — deferred: each
  umbrella spans dozens of sub-types; sub-type detection needs NLP, document images, or
  an external mapping, none in v1 scope. v1 maps to `GENERIC_MEMORANDUM` /
  `GENERIC_NOTICE` / `GENERIC_MODIFICATION` and stops.
- **Property-address parsing/normalization beyond passthrough** — deferred: address
  parsing is a separate engineering concern; v1 emits the raw address. A v2 may add a
  USPS/USA-style normalizer.
- **Parcel grid identifier splitting** (Lot/Block/NCB/County Block parsing) — deferred:
  the scraper concatenates these into one raw string; the v1 translator passes it
  through verbatim. A v2 may split it into structured sub-fields.
- **Lead-readiness scoring** — deferred: scoring is its own phase. The translator emits
  records; the scoring engine consumes and ranks them.
- **Cross-source dedup beyond the `FC` flag** — deferred: dedup is a pipeline join
  concern. The translator only sets the `dedup_against_foreclosure_notices_map` tag.

The v1 translator stays deterministic, contract-aligned, and free of regex-driven
inference. LEVEL 3 needs sample records, test fixtures, and evidence-based pattern design
before it can be specified safely.

---

## 10. Pipeline integration interface

- The translator will be registered in `scaffold/pipeline/translators/__init__.py` (when
  code is written) under the name **`publicsearch_clerk_recordings`**, via the
  `@register("publicsearch_clerk_recordings")` decorator. Per the registry contract it
  may instead be registered late from county-side adapter code; the framework supports
  both.
- The orchestrator (`build_leads.py`) reads the Bexar county config, finds the
  `publicsearch_clerk_recordings` source block, looks up the translator by its
  `translator` name, and calls
  `translator_fn(raw_records, county_config, source_config)`.
- The translator receives wrapped raw records from the loader and returns the
  `(signals, parcels, per_signal_meta_by_url)` three-tuple. It does NOT write files; the
  orchestrator owns I/O.

**Universality (`MASTER_PROMPT.md §4.31`).** The FUTURE translator code at
`scaffold/pipeline/translators/publicsearch_clerk_recordings.py` MUST be county-agnostic.
All county-specific knowledge arrives through `county_config` and `source_config` at call
time. Specifically it lives in:

- `bexar_tx.json` source config — `field_map`, the `translator_config.doc_type_code_map`
  (code → canonical + classification + flags), `parcel_id_prefix`, the daily-refresh code
  list;
- `publicsearch_doc_type_map_proposal.json` — the recon artifact that the doc-type code
  map is derived from; it is eventually folded into the Bexar source config.

The translator Python file MUST NOT contain any Bexar-specific literal: no `"Bexar"`, no
`"BEXAR"`, no `"San Antonio"`, no `78xxx` ZIP literals, no specific street names. This
restriction applies to the future Python file only — NOT to this spec document, which
lives under `runs/bexar_tx/` and references Bexar throughout by design.

---

## 11. Configuration parameters (lockable values)

All configurable values are read from source/framework config — never hardcoded in the
translator:

- `doc_type_code_map` — in `source_config.translator_config`; maps each PublicSearch
  `doc_type_code` to `{canonical, subtype_label, classification, lifecycle_suppression,
  requires_fc_dedup}`. This is the §4 table in config form.
- `lifecycle_suppression_codes_list` — resolved at runtime from the `doc_type_code_map` /
  the doc-type classification: every code with
  `classification = LIFECYCLE_SUPPRESSION_DOC_TYPE` (the 28 codes in §5.1).
- `foreclosure_dedup_codes_list` — resolved at runtime: every code with
  `requires_dedup_against_foreclosure_notices_map = true`. For v1 this is exactly `FC`.
- `unknown_doc_type_handling` — `"skip_with_warning"` (default) OR
  `"include_with_canonical_unknown"` (alternate; emit the record with
  `doc_type = UNKNOWN_DOC_TYPE`). Operator preference — open question 4 (§15).
- `default_parser_confidence_threshold` — `95`. Records whose `parser_confidence` is
  below this still translate, but trigger a warning log.

No numeric scoring values appear in this configuration. The translator has no weights,
scores, bonuses, multipliers, or `scoring_overrides`.

---

## 12. Performance and operational notes

- The translator is a deterministic, in-memory transformation. Expected throughput is
  thousands of records per second per process.
- The translator is **stateless across records** — a pure function per record, with no
  shared mutable state between input records (the only run-scoped state is the
  within-run `seen_parcel_ids` set used to deduplicate placeholder parcels, matching
  `foreclosure_notices.py`).
- Failure modes: invalid input record → log + skip; unmapped/missing canonical → log +
  either skip or emit `doc_type = UNKNOWN_DOC_TYPE` per `unknown_doc_type_handling`;
  framework-contract violation not localizable to one record → halt the run with an
  explicit error.
- The translator is invoked once per pipeline run; it is not a long-running service.
- Each run logs a summary: records in, signals out, parcels out, records skipped (by
  reason), count of `lifecycle_suppression_flag = true`, count of
  `dedup_against_foreclosure_notices_map = true`.

---

## 13. Out of scope for v1 (explicit recap)

LEVEL 3 inference — deferred (full detail in §9):

- [ ] Heirship pattern detection on `AFFIDAV`.
- [ ] Property-affecting judgment detection on `JUDG` / `SJ` / `LIEN` / `TRSCR J`.
- [ ] `MEMO` / `NOTICE` / `MODIFICATION` semantic sub-type detection.
- [ ] Property-address parsing/normalization beyond passthrough.
- [ ] Parcel grid identifier splitting.
- [ ] Lead-readiness scoring.
- [ ] Cross-source dedup beyond the `FC` flag.

Also out of scope for v1:

- [ ] **Detail-page enrichment** — the translator cannot enrich fields the v2 scraper
      does not capture (`instrument_date`, `city`, `num_pages`, `consideration`).
      Deferred to a future scraper spec.
- [ ] **Cross-county translation** — this translator is `bexar_tx`-specific via its
      `field_map` and `doc_type_code_map`; other counties supply their own config blocks.
      (The translator *code* is county-agnostic; the *configuration* is per-county.)
- [ ] **Doc-type vocabulary growth beyond the v1 20 codes** — when the EXPANDED list
      grows, this spec is revised.

---

## 14. Operator approval gate

This spec is not final until the operator checks every box below.

- [ ] Spec scope confirmed — translator only, LEVEL 2.
- [ ] Input contract confirmed — §4.32 wrapped `raw_payload` from scraper spec §3.2.
- [ ] Output contract confirmed — the real framework three-tuple `(signals, parcels,
      per_signal_meta_by_url)`, NOT the `canonical_record_id`/`canonical_payload` shape
      assumed in the step-5 instructions (see §3.2 and §15 open question 1).
- [ ] Doc-type → canonical mapping table reviewed — 20 codes, 5 MATCH, 15 GAP.
- [ ] LEVEL 2 flags confirmed — `lifecycle_suppression_flag`,
      `dedup_against_foreclosure_notices_map`.
- [ ] LEVEL 3 deferral confirmed — no heirship, no property-affecting judgment, no
      MEMO/NOTICE/MOD inference.
- [ ] `field_map` application boundary confirmed — config-driven, not in-code; TBD
      canonical names accepted as open questions.
- [ ] No scoring, no bonuses, no multipliers anywhere in the translator.
- [ ] Test fixture plan confirmed — 3+ sample records (LIS PEN, NOTICE, RELEASE, plus
      FC).
- [ ] Universality contract compliance confirmed — the future translator code carries no
      county-specific literal; this spec under `runs/bexar_tx/` may reference Bexar.
- [ ] Ready to proceed to step 6 (evidence output design).

---

## 15. Open questions for operator review

1. **Output record shape — the framework does not match the step-5 assumption.** The
   step-5 instructions assumed a translator output of flat canonical records with
   `canonical_record_id`, `canonical_payload`, `field_map_applied`, `record_emitted_at`.
   Reading `scaffold/pipeline/translators/__init__.py` and all three built-in translators
   (`foreclosure_notices.py`, `parcel_master.py`, `csv_static_list.py`), the **actual**
   output is the three-tuple `(signals, parcels, per_signal_meta_by_url)` typed
   `tuple[list[dict], list[dict], dict[str, dict]]`. This spec documents the real shape
   (§3.2). Operator must confirm the translator follows the established three-tuple
   convention (recommended — consistency with every other translator) rather than
   inventing a new output shape.

2. **Where do the LEVEL 2 flags attach?** `lifecycle_suppression_flag` and
   `dedup_against_foreclosure_notices_map` are not part of the `foreclosure_notices.py`
   signal shape. This spec places them as dedicated keys on the signal dict. The
   alternative is routing them through `per_signal_meta_by_url`'s `preset_review_flags`
   list (e.g. flag strings `"lifecycle_suppression"`, `"fc_dedup_required"`). Operator /
   framework owner must confirm which the downstream pipeline expects before code is
   written.

3. **Bexar `field_map` canonical names — several TBD.** (a) `recorded_date`: the
   framework canonical convention is split `recording_year` + `recording_month` integers
   (per `foreclosure_notices.py`), not a single `YYYY-MM-DD` `recording_date` — confirm
   whether to add a `recording_date` canonical or split in the translator. (b)
   `grantor`/`grantee`: `foreclosure_notices.py` uses a single `owner_name`; clerk
   recordings have two parties — confirm the canonical two-party model (the
   `party_roles` list in `canonical_doc_types.json` suggests role-tagging). (c)
   `parcel_grid_identifiers`: no canonical equivalent exists — confirm a canonical name
   or keep it metadata-only. These resolve with the Bexar `field_map` proposal and the
   v5.1.2-beta-final canonical-field-name registry.

4. **`unknown_doc_type_handling` default.** This spec defaults to `"skip_with_warning"`.
   The alternative is `"include_with_canonical_unknown"` (emit with
   `doc_type = UNKNOWN_DOC_TYPE`). Operator preference needed.

5. **Address-less parcel placeholders.** Many clerk recordings have a null/`N/A`
   `property_address`, but the `foreclosure_notices.py` parcel-id helper hashes the
   address. This spec proposes falling back to hashing `internal_doc_id` when the address
   is absent, so a stable `parcel_id` always exists. Operator/framework owner to confirm
   this fallback, or specify an alternative (e.g. emit no parcel for address-less
   records).

6. **15 GAP canonical doc types need adding to `canonical_doc_types.json`.** The 15
   listed in §4.3 — `PROBATE_RECORDING`, `PROBATE_LETTERS`, `WILL_RECORDING`,
   `COURT_DECREE`, `GENERIC_AFFIDAVIT`, `CHILD_SUPPORT_LIEN`, `COURT_JUDGMENT`,
   `STATE_JUDGMENT`, `GENERIC_LIEN`, `LANDLORD_LIEN`, `POWER_OF_ATTORNEY`,
   `GENERIC_MEMORANDUM`, `GENERIC_NOTICE`, `GENERIC_MODIFICATION`,
   `FORECLOSURE_RECORDING` — are not in the current 74-entry `canonical_types` registry.
   They are a v5.1.2-beta-final canonical-vocabulary addition. Operator must confirm the
   exact names (this spec proposes them) before the translator emits them, since
   downstream matchers key on canonical doc types.

7. **`publicsearch_doc_type_map_proposal.json` has no `canonical_doc_type` field.** The
   step-5 instructions said to read each code's canonical from the proposal; that field
   does not exist on the proposal entries. The §4 canonical column is therefore proposed
   by this spec. Operator should confirm whether the proposal JSON should be amended to
   carry a `canonical_doc_type` field (a separate edit, not done here), or whether the
   canonical map lives only in the Bexar source config's `doc_type_code_map`.

---

## 16. Document end marker

Spec scope was honored: this step produced exactly one new file —
`runs/bexar_tx/recon/publicsearch_clerk_recordings_translator_spec.md`. No Python file was
written; `scaffold/pipeline/translators/publicsearch_clerk_recordings.py` does not exist
and was not created. No `scaffold/`, `scrapers/`, pipeline, or framework file was
modified. `MASTER_PROMPT.md`, `canonical_doc_types.json`, the three existing translators,
`bexar_tx.json`, and all prior recon artifacts were read only. Nothing was committed.

PUBLICSEARCH TRANSLATOR SPEC READY — AWAITING OPERATOR REVIEW
