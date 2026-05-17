# Bexar PublicSearch clerk_recordings — Scraper Spec (v2)

## 0. Status and scope

- **Date:** 2026-05-17
- **Version:** v2
- **Updated:** 2026-05-17 (operator decisions applied on 5 open questions from v1)
- **Operator:** Quentin Flores
- **County:** bexar_tx
- **Source ID:** publicsearch_clerk_recordings
- **Department:** RP / Land Records
- **Portal:** bexar.tx.publicsearch.us (PublicSearch React SPA)

**Scope — strict.** This document specifies ONLY the `publicsearch_clerk_recordings`
scraper: how it fetches county-recorded documents from the PublicSearch portal and
writes normalized wrapped records to `data/raw/clerk_recordings.jsonl`. It does NOT
cover, and the reader should not infer anything about:

- the `publicsearch_clerk_recordings` translator (step 5 — separate spec later);
- evidence-output design (step 6 — separate spec later);
- scoring calibration (deferred — separate phase later);
- pipeline wiring into `build_leads.py` (later);
- any framework-canonical changes;
- the actual Python file `scrapers/clerk_recordings.py` — this is written LATER,
  only AFTER the operator approves this spec.

**This spec must be operator-approved before any scraper code is written.** It exists
to lock the contract — inputs, outputs, URL shapes, extraction selectors, politeness,
failure handling, cursor behavior — so that the eventual code review is a check against
an agreed contract rather than a design conversation.

**Evidence base.** Every concrete claim below is grounded in recon artifacts already in
`runs/bexar_tx/recon/`:

- `doctype_dropdown.json` — the 124-code RP doc-type catalog (5 groups).
- `publicsearch_doc_type_map_proposal.json` — classification + the 20-code daily-refresh
  list (third revision).
- `publicsearch_doc_type_map_summary.md` — operator-facing classification summary.
- `_probe_findings.json` — Playwright probe: advanced search loads, no login wall,
  results URL shape, `tbody tr` row selector, sample rows.
- `follow_up_findings.md` — verified the `docTypes` URL parameter filters results, the
  `recordedDateRange` date format, and the `/doc/<internal_doc_id>` detail URL pattern.
- `raw_html/02_result_list.html` — a captured rendered result-list DOM, used to derive
  the field-to-column extraction map in §5.3.

**Framework contract references.** The output shape in §3.2 is built against
`MASTER_PROMPT.md §4.32` (the scraper-to-translator wrapped raw-record contract) and
respects `MASTER_PROMPT.md §4.31` (the universality contract — all portal-specific
knowledge stays in the county-side scraper, never in `scaffold/pipeline/`). One
deviation between the operator-supplied record shape and §4.32 as written is flagged in
§3.2 and raised as an open question in §15.

---

## 1. Product priority

**This product is DAILY REFRESH FIRST.** The scraper is designed to catch fresh county
recordings shortly after they are filed, every day. It is NOT a historical-mining tool.

- `daily_refresh` is the **primary product mode.** It is the mode that runs in
  production on a schedule, and every design decision in this spec optimizes for it.
- `first_run_backfill` is used **only** at new-client setup or first-county launch — a
  one-time priming pull so the lead set is not empty on day one.
- `historical_lookup` is **disabled for v1.** It is not part of the daily product. The
  scraper must explicitly reject it (see §2.2).
- The scraper is not designed for, and must not be optimized for, deep historical
  back-filling. Its job is fresh leads, pulled daily, with a small overlap window so no
  same-day filing is missed at a cursor boundary.

If a future phase wants historical mining, that is a separate mode with its own spec.
Nothing in v1 should be built to make historical mining easier at the expense of the
daily product.

---

## 2. Inputs

### 2.1 Source config

The scraper reads the following from the county source config (`bexar_tx.json` or its
equivalent block; values shown are the v1 intended values, locked here for review and
moved into config at wiring time):

- `department` — `RP`
- `daily_refresh` doc-type code list — the 20 codes where
  `daily_refresh_enabled = true` in `publicsearch_doc_type_map_proposal.json`. Listed in
  full in §10.
- `first_run_backfill` doc-type code list — mirrors the `daily_refresh` list exactly in
  v1 (same 20 codes).
- `pipeline_modes` block:
  - `daily_refresh.overlap_days` = 3
  - `first_run_backfill.default_days` = 30
  - `first_run_backfill.allowed_days` = [1, 7, 14, 30]
  - `historical_lookup.enabled` = false
- `base_url` — `https://bexar.tx.publicsearch.us`
- `results_path` — `/results`
- `detail_path_pattern` — `/doc/<internal_doc_id>`
- `results_page_size` — 50
- `date_format` — `YYYYMMDD`
- `url_date_separator` — `,` (comma; URL-encoded as `%2C` when the param is encoded)
- `parcel_id_prefix` — `BX-PS-`

The scraper must NOT hardcode county name, portal hostname, or doc-type codes in any
universal module. Per §4.31 these enter only through county config. This scraper lives
county-side (`scrapers/`, not `scaffold/pipeline/`), so it may know the portal protocol
— but the *values* above still come from config so the scraper file itself stays a thin
protocol driver.

### 2.2 Mode selection

The scraper picks a mode from a command-line argument at invocation:

- `--mode daily_refresh` — **default** when `--mode` is omitted.
- `--mode first_run_backfill --backfill-days <1|7|14|30>` — one-time priming pull.
  `--backfill-days` is required in this mode; if omitted, default to 30.
- `--mode historical_lookup` — **REJECT.** The scraper must exit immediately with a
  non-zero code and an explicit error message, for example:
  `ERROR: historical_lookup mode is not supported in v1. Use daily_refresh or
  first_run_backfill.` No records are written, no state is touched.

Any unrecognized `--mode` value is likewise rejected with a non-zero exit and a clear
message.

### 2.3 Cursor and overlap (daily_refresh mode only)

In `daily_refresh` mode the scraper determines its date window as follows:

1. Read `last_successful_recorded_date` from the state file (see §3.4 / §8).
2. `start_date = last_successful_recorded_date − overlap_days` (overlap_days = 3).
3. `end_date = today`.
4. **First-run fallback:** if the state file is absent or has no
   `last_successful_recorded_date`, the scraper falls back to the
   `first_run_backfill` default window (30 days): `start_date = today − 30`,
   `end_date = today`. It logs that it took the fallback path, and it still writes
   output to the same `clerk_recordings.jsonl` (the fallback is a window choice, not a
   mode change — the run is still recorded as `daily_refresh` with a
   `first_run_fallback: true` flag in run metadata).

The 3-day overlap means each daily run re-pulls the last 3 days of recordings. This is
deliberate: county recording back-dates and late indexing mean a document recorded on
day N may not appear in portal results until day N+1 or N+2. Overlap guarantees those
late-appearing records are caught. The cost is duplicate records, which downstream
dedup absorbs (see §9).

### 2.4 Date window (first_run_backfill mode only)

In `first_run_backfill` mode:

- `end_date = today`
- `start_date = today − <--backfill-days>`
- Allowed `--backfill-days` values: 1, 7, 14, 30. Any other value is rejected with a
  non-zero exit.

`first_run_backfill` does not read or require the state file for its window. It MAY
write the state file on success (see §8) so that the first subsequent `daily_refresh`
run has a cursor anchor.

---

## 3. Outputs

### 3.1 Primary output file

- **Path:** `data/raw/clerk_recordings.jsonl`
- **Write mode:** APPEND.

Per operator directive the scraper appends; it never truncates or rewrites the file.
The 3-day overlap window guarantees duplicate records across runs by design, and the
same record also appears once per run it falls inside. Deduplication is a downstream
pipeline responsibility (see §9), not the scraper's. Append-only also means the file is
an auditable, ordered log of everything the scraper ever observed.

### 3.2 Record format (wrapped raw_payload per §4.32)

v2 record shape is §4.32-compliant. The framework's `test_translator_registry.py`
enforces §4.32; any scraper output that deviates will fail the gate.

Every line written to `clerk_recordings.jsonl` is one JSON object of this shape:

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

Notes on the contract:

- **§4.32 compliance.** The top-level fields — `raw_record_id`, `source_id`,
  `source_url`, `source_fetched_at`, `parser_confidence`, `raw_payload` — exactly match
  the `MASTER_PROMPT.md §4.32` wrapped raw-record shape (verified by reading §4.32
  directly). `parser_confidence` is the integer 0–100 confidence field §4.32 specifies;
  the scraper emits the §4.32 default of **95** because result-list extraction is
  header-driven and unambiguous (it may emit a lower value for a specific record if a
  header-map fallback or a malformed cell forced a degraded parse). The v1 draft's
  `first_seen_at` field has been **removed** — it was an over-engineering invention not
  part of §4.32.
- **Detail-only fields excluded.** `instrument_date`, `city`, `num_pages`, and
  `consideration` are NOT captured in v1 because they do not appear in the result-list
  DOM. They appear only on the detail page (`/doc/<internal_doc_id>`). Detail-page
  fetches are explicitly future enhancement scope (see §13). v1 raw_payload captures
  only fields visible in the result list.
- The `raw_payload` field names are the **scraper's normalized names**, chosen to
  describe PublicSearch recordings clearly. They are intentionally NOT all
  framework-canonical. The translator (step 5) bridges them to canonical names using a
  per-source `field_map` per `MASTER_PROMPT.md §4.32` (v5.1.2-beta-r3+ `field_map`
  support). For example the translator's `field_map` will likely bridge
  `property_address → address`, `recorded_date → recording_date` (or
  `recording_year`/`recording_month`), and so on. Defining that `field_map` is the
  translator spec's job, not this one.
- **No translator interpretation happens at the scraper layer.** The scraper writes what
  the portal shows, normalized to types (dates as `YYYY-MM-DD`) but not interpreted.
- The scraper does **NOT** compute a `canonical_doc_type`. Mapping
  `doc_type_label`/`doc_type_code` to a framework-canonical doc type is the translator's
  job, driven by `doctype_dropdown.json` plus config synonyms.
- `raw_record_id` is `publicsearch_bexar_<internal_doc_id>` — stable and globally unique
  within this source because `internal_doc_id` is PublicSearch's own primary key.
- `source_url` is the constructed `/doc/<internal_doc_id>` deep link (see §4.2). It is
  constructed, not visited.
- `source_fetched_at` is the UTC timestamp when the result page carrying this row was
  fetched.
- **`parcel_grid_identifiers` is captured as a single raw string** concatenating the
  Bexar-specific grid columns (Lot, Block, NCB, County Block). Translator-side
  normalization may split these into structured sub-fields later; for v1 the raw string
  preserves all source-of-truth detail.

### 3.3 Run metadata output

- **Path:** `data/raw/clerk_recordings_runs/<YYYYMMDD>T<HHMMSS>_<mode>.json`
  (one file per scraper run; timestamp is the run start in UTC).

Each run-metadata file records:

- `run_id` — a unique id for the run (recommend `<YYYYMMDD>T<HHMMSS>_<mode>`, matching
  the filename stem).
- `mode` — `daily_refresh` or `first_run_backfill`.
- `invocation_args` — the raw command-line arguments the scraper was called with.
- `first_run_fallback` — boolean; true if `daily_refresh` took the 30-day first-run
  fallback because no state file existed.
- `start_date` and `end_date` — the actual date window used (`YYYY-MM-DD`).
- `per_doc_type` — an array, one entry per doc-type attempted, each with:
  - `code`, `label`
  - `tier` — `CORE` or `EXPANDED`
  - `records_fetched`
  - `pages_fetched`
  - `retries` — number of retry attempts consumed
  - `status` — `success`, `partial`, or `failed`
- `total_records_appended` — total lines appended to `clerk_recordings.jsonl` this run.
- `run_started_at`, `run_finished_at`, `run_duration_seconds`.
- `status` — overall run status: `success`, `partial`, or `halted`.
- `halt_reason` — present only when `status = halted`.
- `new_last_successful_recorded_date` — the value written to the state file, present
  only if the run advanced the cursor (see §8 for the conservative advance rule). Absent
  or null if the cursor was not advanced.

### 3.4 State file

- **Path:** `data/raw/clerk_recordings_state.json`
- A single small JSON object:

      {
        "last_successful_recorded_date": "<YYYY-MM-DD>",
        "last_successful_run_id": "<run_id>",
        "last_successful_run_finished_at": "<ISO8601 UTC>"
      }

This file is the cursor anchor for `daily_refresh` mode (§2.3). It is written ONLY when
a run is allowed to advance the cursor per the conservative rule in §8. It is never
written on a halted run. If the file is absent, `daily_refresh` takes the first-run
fallback.

### 3.5 Raw HTML audit persistence

- **Path:**

      data/raw/clerk_recordings_html/<YYYYMMDD>/<doc_type_code_slug>_offset_<int>.html

Behavior:

- For every successful results-page fetch, the scraper writes the full rendered
  `page.content()` to disk as an audit artifact.
- **File naming:** a date directory, then the doc-type code slugified (spaces replaced
  with underscores, e.g. `LIS PEN` → `LIS_PEN`), then the offset — e.g.
  `data/raw/clerk_recordings_html/20260517/LIS_PEN_offset_0.html`.
- **Purpose:** re-parse capability if selector logic changes, and an audit trail for
  debugging extraction.
- **Rotation:** at the start of every `daily_refresh` run, the scraper deletes any HTML
  files older than 30 days from `data/raw/clerk_recordings_html/`. Retention keeps
  storage bounded. Worst-case high-volume estimate is roughly 15 GB (≈500 KB per page ×
  50 pages per doc-type × 20 doc-types × 30 days); realistic `daily_refresh` storage is
  expected to be far lower — likely 100–500 MB depending on actual result volume.
- **Failure handling:** if an HTML write fails (disk full, permission error), the
  scraper logs a warning and continues — an audit-write failure must NOT halt the
  scraper run.

---

## 4. URL construction

### 4.1 Results URL template

The scraper requests result pages from this URL shape:

    https://bexar.tx.publicsearch.us/results
      ?department=RP
      &searchType=advancedSearch
      &docTypes=<URL-encoded code>
      &recordedDateRange=<YYYYMMDD>,<YYYYMMDD>
      &limit=50
      &offset=<int>

Locked facts about this URL (all verified in `follow_up_findings.md` and
`_probe_findings.json`):

- **`docTypes` accepts ONE code per request.** The `docTypes` parameter was verified to
  filter results (a `docTypes=AFFIDAV` request returned 1,145 records, all `AFFIDAVIT`,
  vs. 20,928 unfiltered). The scraper iterates the 20 daily-refresh codes sequentially,
  one request series per code. Multi-value `docTypes` was not verified and v1 does not
  rely on it.
- **Codes with spaces must be URL-encoded.** Several daily-refresh codes contain a
  space — `LIS PEN`, `CSUP LN`, `LNLD LN`. These become `LIS%20PEN`, `CSUP%20LN`,
  `LNLD%20LN`. The scraper URL-encodes the code unconditionally; codes without spaces
  encode to themselves.
- **Date format is `YYYYMMDD`.** This is confirmed and load-bearing:
  `follow_up_findings.md` documents that the `MMDDYYYY` format returns HTTP 500
  "Internal Server Error". The scraper formats both window dates as `YYYYMMDD` joined by
  a comma.
- **`limit=50`** is the chosen page size — probe-verified as a working value.
- **Pagination is via `offset`.** `offset` increments by `limit` (0, 50, 100, ...) until
  an empty result table is returned. See §6.

The recorded-date range filter uses the run's computed `start_date`/`end_date` (§2.3 /
§2.4), reformatted from `YYYY-MM-DD` to `YYYYMMDD`.

### 4.2 Detail URL template

    https://bexar.tx.publicsearch.us/doc/<internal_doc_id>

Locked facts (verified in `follow_up_findings.md`):

- **The scraper does NOT fetch detail pages in v1.** The detail URL is constructed and
  stored, never visited. See §13.
- The detail URL path is `/doc/<internal_doc_id>` where `<internal_doc_id>` is
  PublicSearch's internal numeric document id — **not** the recorded `document_number`.
  Confirmed: clicking a result row navigated to `…/doc/314427553` while that row's
  recorded document number was `20260070780`.
- `internal_doc_id` is extracted directly from the result-row DOM — specifically the
  row's checkbox `<input>` element, whose `id` attribute has the form
  `table-checkbox-<internal_doc_id>` (and whose `aria-label` is
  `Document <internal_doc_id>, …`). No detail-page click and no navigation is required
  to obtain it.
- The scraper CONSTRUCTS the detail URL from `internal_doc_id` and stores it in
  `raw_record_id` and `source_url` so a downstream operator can click through to the
  source document during review.

**Coverage note.** The result-list DOM carries every field in the v2 `raw_payload` shape
(§3.2) — all 11 are extracted without visiting any detail page. The four fields that
appeared in the v1 draft (`instrument_date`, `city`, `num_pages`, `consideration`) are
not result-list columns; they exist only on the detail page and were dropped from v2
scope. The detail URL is constructed and stored in `raw_record_id` and `source_url` for
downstream operator click-through, but the scraper DOES NOT visit it in v1/v2. A future
scraper spec may add an optional detail-page fetch for fields not in the list view (see
§13).

---

## 5. Page fetch and DOM extraction strategy

### 5.1 Engine

**Playwright (Python sync API), headless Chromium.**

Justification: the probe confirmed the portal is a React single-page application. A raw
HTTP GET of `/results` returns an empty application shell with no result rows — the rows
are rendered client-side after the SPA's own data fetch. Playwright drives a real
browser, so the rendered DOM is available. The probe ran headless Chromium successfully
with no login wall and no bot challenge. This is the proven path.

v1 deliberately does NOT attempt to reverse-engineer the SPA's internal data XHR into a
direct API call. That optimization may be revisited later, but for v1 the Playwright
rendered-DOM path is chosen for reliability over speed.

### 5.2 Per-page fetch sequence

For each `(doc_type_code, offset)` combination the scraper:

1. `page.goto(url, wait_until="networkidle", timeout=60000)` — load the results URL.
2. Wait for the results table row selector to be present: `tbody tr[role="row"]`.
   (If, after `networkidle`, no such selector appears AND the result count summary
   indicates zero results, treat the page as a legitimate empty page — end of
   pagination for this code, not a failure. If the selector is absent AND the result
   summary is also absent or errored, treat it as a selector miss / failure — see §8.)
3. Polite delay: sleep a random `2–5` seconds (see §7).
4. `page.content()` — capture the full rendered HTML.
5. Parse the captured HTML with BeautifulSoup (or an equivalent HTML parser).

The scraper uses a single browser, single page object, navigated sequentially. No
concurrency (§7).

### 5.3 Field extraction selectors (column-class-based, probe-verified)

The result table renders one document per `tbody tr[role="row"]`. Each data cell is a
`<td>` with a stable class `col-<N>`. The column meaning was verified against
`raw_html/02_result_list.html` — both the `<th>` `aria-label` values and the row cell
contents were inspected. The verified header order is:

- `col-0` — row checkbox (carries `internal_doc_id`)
- `col-1` — Actions dropdown (ignored)
- `col-2` — Document status icons (ignored)
- `col-3` — Grantor
- `col-4` — Grantee
- `col-5` — Doc Type
- `col-6` — Recorded Date
- `col-7` — Doc Number
- `col-8` — Book/Volume/Page
- `col-9` — Legal Description
- `col-10` — Lot
- `col-11` — Block
- `col-12` — NCB
- `col-13` — County Block
- `col-14` — Property Address

Field-to-source map for the v2 `raw_payload` fields (all 11 DETERMINED):

- **`internal_doc_id`** — DETERMINED. In the row's `col-0` cell, the `<input>` element
  has `id="table-checkbox-<internal_doc_id>"`. Parse the numeric suffix after
  `table-checkbox-`. (The same id appears in the input's `aria-label` as
  `Document <internal_doc_id>, …` — usable as a cross-check.)
- **`document_number`** — DETERMINED. `td.col-7` text content.
- **`doc_type_label`** — DETERMINED. `td.col-5` text content (e.g. `LIS PENDENS`).
- **`doc_type_code`** — DETERMINED (source: not the DOM). The result list has no
  doc-type *code* cell — only the human label in `col-5`. The scraper supplies
  `doc_type_code` from the `docTypes` URL parameter it used for the request (see §5.4).
  The code is authoritative; `doc_type_label` from `col-5` is the verification value.
- **`recorded_date`** — DETERMINED. `td.col-6` text content; normalize to `YYYY-MM-DD`
  (the portal renders e.g. `1/20/2026`).
- **`grantor`** — DETERMINED. `td.col-3` text content.
- **`grantee`** — DETERMINED. `td.col-4` text content.
- **`property_address`** — DETERMINED. `td.col-14` text content. Frequently renders as
  `N/A` (probe observed many `N/A` values, especially on non-conveyance doc types) —
  capture it verbatim even when blank or `N/A`; normalize a literal `N/A` to `null`.
- **`legal_description`** — DETERMINED. `td.col-9` text content (e.g.
  `Subdivision - Name: CENTERO AT STONE OAK CONDOMINIUMS Lot: 709`).
- **`book_volume_page`** — DETERMINED. `td.col-8` text content. Often renders `--/--/--`
  for recent records that have no book/volume/page; normalize that placeholder to
  `null`.
- **`parcel_grid_identifiers`** — DETERMINED. A single raw string formed by
  concatenating the result row's Lot (`col-10`), Block (`col-11`), NCB (`col-12`), and
  County Block (`col-13`) cells, using the same header-driven column identification as
  every other field. Rendered example: `Lot 709, Block N/A, NCB N/A, County Block N/A`.
  Captured as one raw string; the translator may split it into structured sub-fields
  later. Empty / `N/A` sub-values are kept verbatim inside the string so no source
  detail is lost.

**Summary: all 11 v2 `raw_payload` fields are DETERMINED from the result-list DOM.** The
four v1-draft fields not in the result list — `instrument_date`, `city`, `num_pages`,
`consideration` — were dropped from v2 scope (see §3.2 and §13); recovering them would
require a detail-page fetch, which is future enhancement scope.

**Fallback rule — identify columns by header, not by raw index.** PublicSearch may
vary column order or column set between doc types or over time. The scraper must NOT
trust the bare integer in `col-<N>`. At the start of processing each result page it
must read the `<thead>` row, map each column's `aria-label` (or visible header text) to
a field, and build a per-page header→column index. Extraction then uses that map. The
`col-<N>` values listed above are the *expected* layout from the probe capture; the
header-driven map is the *authority*. If a header the scraper needs is missing on a
page, that field is emitted `null` for rows on that page and the condition is logged.

### 5.4 Doc-type code emission

For every record the scraper writes BOTH:

- `raw_payload.doc_type_code` — the doc-type code used in the `docTypes` URL parameter
  for the request that produced this row (e.g. `LIS PEN`).
- `raw_payload.doc_type_label` — the rendered label extracted from `td.col-5` (e.g.
  `LIS PENDENS`).

Both are useful downstream. The **code is authoritative** (the scraper queried by it,
so it is exact). The **label is verification** — if a row's `col-5` label is
inconsistent with the queried code's expected label from `doctype_dropdown.json`, that
is a data-quality signal the translator or an audit step can flag.

---

## 6. Pagination strategy

For each doc-type, the scraper paginates by incrementing `offset` by `limit` (50):
`offset=0`, then `50`, `100`, `150`, … It stops paginating that doc-type when EITHER:

- an empty result table is returned (no `tbody tr[role="row"]` rows, with the result
  summary confirming zero/`end` — a legitimate empty page, not an error), OR
- the scraper reaches `max_pages_per_doc_type` — a configured safety circuit breaker,
  recommended at **200 pages** (200 × 50 = 10,000 records). Hitting this limit is
  abnormal: it means a doc type returned a runaway result set, which almost certainly
  indicates a wrong/too-wide date window or a stuck pagination loop. The scraper stops
  that doc type, records `status = partial` for it, and logs the circuit-breaker trip.

Volume expectations (from probe-scale observation, to set reviewer intuition):

- Narrow, high-signal codes (e.g. `LIS PEN`, `MECHLN`, `FTL`, `STL`) typically return
  well under 100 records in a 30-day window — 1–2 pages.
- Broad umbrella codes (`AFFIDAV`, `MEMO`, `NOTICE`) are volume-heavy. A 30-day
  `first_run_backfill` for one of these may run dozens of pages. A 3-day
  `daily_refresh` window keeps even these to a handful of pages.

**The scraper does NOT scroll-to-load.** It uses URL `offset` pagination only. The
portal supports both an infinite-scroll interaction and explicit `offset` paging; URL
`offset` paging is deterministic, restart-friendly, and far simpler to reason about, so
it is the only paging method v1 uses.

---

## 7. Rate limiting and politeness

**Mode: POLITE** (operator directive). The scraper is a courteous, single-threaded
visitor. It must never look like a load test.

Specific behavior:

- **2–5 second random delay** between successive `page.goto` calls within the same
  doc-type (i.e. between result pages).
- **15 second delay** between doc-types — a deliberate longer pause that gives the
  portal breathing room between query series.
- **No concurrency.** No parallel browsers, no parallel tabs, no parallel pages. One
  Playwright browser instance for the whole run, one `page` object, navigated strictly
  sequentially.
- **User-agent:** a realistic, current Chrome desktop UA string. The scraper must NOT
  spoof Googlebot, must NOT impersonate any monitoring or system identity, and must NOT
  otherwise misrepresent itself.
- **Endpoint discipline:** the scraper requests only `/results` pages. It must NOT call
  `/search/image`, `/fetch-document-images`, or any PDF/document-image endpoint — those
  serve document images and are out of scope (§13).

**Run-time estimate** (for operator planning, not a hard guarantee):

- `daily_refresh` (3-day overlap window): 20 doc types × roughly 1–3 pages each, plus
  per-page 2–5s delays and 15s inter-doc-type delays ≈ **15–30 minutes** per run.
- `first_run_backfill` (30-day window): dominated by the broad umbrellas (`AFFIDAV`,
  `MEMO`, `NOTICE`) which page much deeper ≈ **60–120 minutes**, volume-dependent.

---

## 8. Failure handling and retries

**Operator directive: retry with backoff, then skip.**

### Per-doc-type retry sequence

When a fetch for a `(doc_type, offset)` fails, the scraper retries the *current page
fetch*:

- Attempt 1 — normal fetch.
- Attempt 2 — after a 5-second delay.
- Attempt 3 — after a 30-second delay.
- Attempt 4 — after a 2-minute delay.
- After 3 retry attempts are exhausted (i.e. attempt 4 also failed) → the doc-type is
  marked `FAILED`, recorded as such in run metadata, and the scraper SKIPS to the next
  doc-type. Records already collected for that doc-type from earlier successful pages
  are kept (already appended to the JSONL); the doc-type's run-metadata `status` is
  `partial` if it had at least one successful page before failing, `failed` if it never
  succeeded.

### Failure-triggering conditions (per attempt)

An attempt counts as failed if any of:

- the loaded page returns an HTTP 5xx status;
- a Playwright timeout is exceeded (`per_page_timeout_seconds`, default 60);
- the page renders empty when results were expected (i.e. zero rows AND no valid
  zero-result summary — distinguished from a legitimate end-of-pagination empty page,
  see §5.2 / §6);
- the results table selector (`tbody tr[role="row"]`) is absent after `networkidle` and
  no valid empty-result summary is present (selector miss).

### Hard-halt conditions (whole-run failure)

If any of the following occur, the scraper HALTS the entire run immediately:

- a login wall / authentication-required page appears;
- a CAPTCHA or bot challenge is presented;
- the portal returns a global 503 or a maintenance page;
- the browser fails to launch;
- the state file or an output directory is not writable.

On a hard halt the scraper:

- does **NOT** advance `last_successful_recorded_date` (the state file is left
  untouched);
- writes a run-metadata file with `status = halted`, a `halt_reason`, and the list of
  doc-types completed before the halt;
- exits with a non-zero code.

Records appended to `clerk_recordings.jsonl` before the halt remain on disk (append-only
log); they will be re-pulled and deduplicated on the next successful run because the
cursor did not advance.

### Partial-success cursor rule (conservative)

When some doc-types failed but the run did not hard-halt, cursor advancement is
deliberately conservative — **the cursor must never advance past a date for which the
data is known to be incomplete:**

- The scraper **DOES** advance `last_successful_recorded_date` to the run's `end_date`
  IF **every CORE-tier code (all 8) succeeded** AND **fewer than 3 EXPANDED-tier codes
  failed**. Run `status = partial` (or `success` if nothing failed at all).
- The scraper **DOES NOT** advance the cursor if **any CORE-tier code failed** OR **3 or
  more EXPANDED-tier codes failed**. This is treated as an effective halt for cursor
  purposes even though partial output was written: run `status = partial`, the state
  file is left untouched, and the next `daily_refresh` run re-covers the same window.

The threshold `3` is the configurable `hard_halt_partial_threshold` (§12).

The run-metadata file always records the per-doc-type breakdown so an operator can see
exactly what succeeded, what failed, and whether the cursor moved.

---

## 9. Dedup expectations (downstream, not scraper-side)

**The scraper performs NO deduplication.** It appends every record it extracts to
`clerk_recordings.jsonl`. Deduplication happens downstream in the pipeline.

This is by design. The 3-day overlap window (§2.3) means the same physical recording is
re-pulled on roughly 3 consecutive daily runs before it ages out of the cursor window —
so each record is appended about 3 times. `first_run_backfill` followed by daily runs
also produces overlap. The append-only log is intentional; the pipeline is responsible
for collapsing duplicates.

**Dedup keys (downstream consumer responsibility):**

- `internal_doc_id` — the **primary key.** PublicSearch's own internal document id;
  globally unique within the portal. Downstream dedup should key on this first.
- `document_number` — Bexar's recorded instrument number; a secondary cross-check.
- `doc_type_code` — included in the key in case the same physical document is indexed
  under more than one doc type (it would then legitimately appear once per type).
- `recorded_date` — included in case a record is re-indexed under the same
  `internal_doc_id` with a corrected date (rare, but it would otherwise be silently
  collapsed).

The scraper guarantees `internal_doc_id` is populated for every record (it is extracted
from a structural element — the row checkbox — that is always present). Downstream dedup
can rely on it as the canonical primary key.

---

## 10. Doc-type iteration strategy

The scraper iterates the 20 daily-refresh doc types in **tier order: CORE first, then
EXPANDED.** Within each tier the order is **alphabetical by code**, for deterministic,
reproducible runs.

**CORE tier — 8 codes** (processed first), alphabetical by code:

1. `DECREE` — DECREE
2. `FTL` — FEDERAL TAX LIEN
3. `LETTERS` — LETTERS
4. `LIS PEN` — LIS PENDENS
5. `MECHLN` — MECHANICS LIEN
6. `PROBATE` — PROBATE
7. `STL` — STATE TAX LIEN
8. `WILL` — WILL & TESTAMENT

**EXPANDED tier — 12 codes** (processed second), alphabetical by code:

1. `AFFIDAV` — AFFIDAVIT
2. `CSUP LN` — CHILD SUPPORT LN
3. `FC` — FORECLOSURE
4. `HOSP LN` — HOSPITAL LIEN
5. `JUDG` — JUDGMENT
6. `LIEN` — LIEN
7. `LNLD LN` — LANDLORD LIEN
8. `MEMO` — MEMORANDUM
9. `MOD` — MODIFICATION
10. `NOTICE` — NOTICE
11. `PA` — POWER OF ATTORNEY
12. `SJ` — State-Judgment

**Rationale.** CORE codes are higher-signal and lower-volume. Running them first means
that if a run is interrupted (hard halt, crash, operator stop), the most valuable data
is already captured and on disk. The EXPANDED tier — especially the broad umbrellas
`AFFIDAV`, `MEMO`, `NOTICE` — is the volume-heavy, noisier set; losing it mid-run is
less costly than losing CORE. This ordering also dovetails with the cursor rule in §8:
a CORE failure freezes the cursor, so running CORE first surfaces a CORE problem early.

---

## 11. FC dedup against foreclosure_notices_map (called out separately)

`FC` (FORECLOSURE) is an EXPANDED-tier daily-refresh code, and in
`publicsearch_doc_type_map_proposal.json` it carries
`requires_dedup_against_foreclosure_notices_map = true`.

**The scraper does NOT perform this dedup.** Comparing PublicSearch `FC` records against
the county's `foreclosure_notices_map` records is a pipeline responsibility, downstream
of the scraper.

The scraper's only responsibility regarding FC:

- pull `FC` records exactly like any other EXPANDED code and append them to
  `clerk_recordings.jsonl`;
- ensure the records are attributable to this source via `source_id`
  (`publicsearch_clerk_recordings`) so the pipeline knows these are PublicSearch FC
  records that must be reconciled against `foreclosure_notices_map` before lead
  emission.

The dedup logic, the overlap-quantification, and any decision to deprecate the FC pull
belong to the pipeline/translator phase. A backlog item already exists for it (§15 /
the proposal's backlog): run a 30-day comparison sample of PublicSearch `FC` vs
`foreclosure_notices_map` once both pipelines are live, to quantify overlap and decide
whether to keep the FC pull (with dedup) or drop it.

---

## 12. Configuration parameters (lockable values)

All tunable values are surfaced as configuration, not hardcoded in the scraper. At
wiring time they move into the `bexar_tx.json` source config block. v1 defaults,
documented here for review:

- `polite_min_delay_seconds` — 2
- `polite_max_delay_seconds` — 5
- `inter_doc_type_delay_seconds` — 15
- `max_pages_per_doc_type` — 200 (circuit breaker; 200 × 50 = 10,000 records)
- `per_page_timeout_seconds` — 60
- `retry_attempts` — 3
- `retry_backoff_seconds` — [5, 30, 120]
- `hard_halt_partial_threshold` — 3 (EXPANDED-tier failures before the cursor is frozen
  per §8)
- `raw_html_audit_enabled` — true
- `raw_html_audit_retention_days` — 30

Additional config already covered in §2.1 (`department`, the code lists,
`pipeline_modes`, `base_url`, `results_path`, `detail_path_pattern`,
`results_page_size`, `date_format`, `url_date_separator`, `parcel_id_prefix`) is part of
the same source-config block.

No numeric scoring values appear anywhere in this configuration. The scraper has no
weights, scores, bonuses, multipliers, or `scoring_overrides`.

---

## 13. Out of scope for v1 scraper

The v1 scraper explicitly does NOT:

- fetch detail pages — the `/doc/<internal_doc_id>` URL is constructed and stored, but
  never visited;
- download PDFs or any document images;
- log in, authenticate, or maintain a session (the portal needs none for search);
- solve CAPTCHAs (encountering one is a hard halt, §8);
- handle `historical_lookup` mode (rejected at invocation, §2.2);
- perform deduplication (downstream pipeline job, §9);
- map `doc_type_label`/`doc_type_code` to a framework `canonical_doc_type` (translator
  job);
- compute scoring, lead attributes, patterns, or any derived lead signal
  (translator/scoring job);
- iterate any department other than `RP`;
- pull from the other 17 PublicSearch departments (ASN, BR, CASE, CCM, DC, FC*, IO, MB,
  MC, MISC, NT, PL, PN, PP, SA, UCC, WIL). (*Note: "FC" as a department code is distinct
  from the `FC` doc-type code inside the RP department; v1 pulls only the RP
  department.)

**Detail-page fetch — future enhancement.** Detail-page fetch (`/doc/<internal_doc_id>`)
is explicitly FUTURE enhancement scope, not part of this v2 spec. This v2 spec captures
only result-list-visible fields. If the operator decides `instrument_date`, `city`,
`num_pages`, or `consideration` become must-have fields later, a future v3 spec may add
optional detail-page fetches with appropriate rate limiting and politeness.

---

## 14. Operator approval gate

This spec is not final until the operator checks every box below.

- [ ] Spec v2 reviewed.
- [ ] §4.32 contract compliance confirmed — `parser_confidence` present, `first_seen_at`
      removed (§3.2).
- [ ] 4 detail-only fields confirmed dropped from v1 — `instrument_date`, `city`,
      `num_pages`, `consideration`.
- [ ] `parcel_grid_identifiers` single-string approach confirmed (§3.2, §5.3).
- [ ] `inter_doc_type_delay` = 15s confirmed (§7, §12).
- [ ] Raw HTML audit + 30-day rotation confirmed (§3.5).
- [ ] Detail-page fetch deferred to future spec confirmed (§13).
- [ ] Ready to proceed to step 5 (translator design).

---

## 15. Open questions for operator review

All five v1 open questions were resolved by operator decisions on 2026-05-17:

- **Q1** — drop the 4 detail-only fields (`instrument_date`, `city`, `num_pages`,
  `consideration`) from v1 `raw_payload`.
- **Q2** — match the `MASTER_PROMPT.md §4.32` record shape exactly (add
  `parser_confidence`, remove `first_seen_at`).
- **Q3** — capture the parcel-grid columns as a single `parcel_grid_identifiers` string.
- **Q4** — fix `inter_doc_type_delay_seconds` at 15 seconds.
- **Q5** — persist raw HTML for audit, with a 30-day retention/rotation policy.

See §16 for the change summary. No new open questions surfaced during the v2 edit — the
§4.32 contract was read directly from `MASTER_PROMPT.md` and applied without ambiguity.

---

## 16. v2 change summary

Updated 2026-05-17 (v2 — operator decisions on 5 open questions applied).

Changes from v1 to v2:

- Record shape is now `MASTER_PROMPT.md §4.32`-compliant — added the top-level
  `parser_confidence` field (integer 0–100, default 95) and removed the non-§4.32
  `first_seen_at` field.
- Dropped `instrument_date`, `city`, `num_pages`, and `consideration` from the v1
  `raw_payload` — these are not present in the result-list DOM; recovering them would
  require a detail-page fetch, which is future enhancement scope.
- Added `parcel_grid_identifiers` to `raw_payload` as a single raw string concatenating
  the Bexar grid columns (Lot, Block, NCB, County Block).
- Locked `inter_doc_type_delay` to 15 seconds (was an unresolved 10–15s range).
- Added §3.5 raw HTML audit persistence, with a 30-day retention/rotation policy and
  `raw_html_audit_enabled` / `raw_html_audit_retention_days` config.
- §13 now explicitly marks the detail-page fetch (`/doc/<internal_doc_id>`) as future
  enhancement scope, not v2 scope.
- §14 operator approval checklist updated for v2.
- §15 open questions replaced with the resolution record; §0 version bumped to v2.

---

PUBLICSEARCH SCRAPER SPEC v2 — AWAITING OPERATOR REVIEW
