# Phase 5 Recon Follow-Up — Bexar County, TX (publicsearch.us)

Date: 2026-05-16 · Two targeted Playwright tests (headless Chromium) · read-only, no login, no PDF downloads.

---

## ⚠️ Operator URL correction

The supplied test URLs used `recordedDateRange=04162026,05152026` (**MMDDYYYY**).
The portal **rejects that format with HTTP 500 "Internal Server Error"** — confirmed: zero rows, blank page.

The probe-confirmed format is **YYYYMMDD** (`recordedDateRange=20260416,20260515`).
Both tests below were run with the corrected format, covering the same intended window
(Apr 16 – May 15 2026). This is itself a finding: **the scraper must format `recordedDateRange` as `YYYYMMDD,YYYYMMDD`.**

---

## TEST 1 — Does the `docTypes` URL parameter filter results?  → **SUPPORTED**

`DOCTYPES_URL_PARAM: SUPPORTED`

| | URL A (no filter) | URL B (`&docTypes=AFFIDAV`) |
|---|---|---|
| Result count | `1-50 of 20,928 results` | `1-50 of 1,145 results` |
| First 5 Doc Type cells | `VOID OPR`, `RELEASE`, `ASSIGNMENT`, `RELEASE`, `RELEASE` (mixed) | `AFFIDAVIT`, `AFFIDAVIT`, `AFFIDAVIT`, `AFFIDAVIT`, `AFFIDAVIT` (all) |
| Param retained in final URL | n/a | yes — `docTypes=AFFIDAV` not stripped |
| Final URL | unchanged from requested | unchanged from requested |

**Evidence:** the result count collapses 20,928 → 1,145 and every visible row in URL B is `AFFIDAVIT`. The portal does not redirect or sanitize the parameter away.

**Architecture implication:** the scraper can use **direct per-doc-type result URLs** — no need to drive the `TokenizedNestedSelect` widget. Pattern:

```
https://bexar.tx.publicsearch.us/results?department=RP&recordedDateRange=YYYYMMDD,YYYYMMDD&searchType=advancedSearch&limit=50&docTypes=<CODE>
```

Note: `docTypes` is almost certainly comma-multi-valued (declared `TokenizedNestedSelect` in page config). Only the single-value case was tested here — verify multi-value (`docTypes=AFFIDAV,DEED`) before relying on it.

Screenshots: `screenshots/test1_url_a.png`, `screenshots/test1_url_b.png`

---

## TEST 2 — Detail page URL pattern  → `/doc/<internalDocId>`

- **No `<a href>` and no `data-href` anywhere in the result rows.** Rows navigate via a React click handler.
- The Doc Number cell (`td.col-7`) has **`cursor: pointer`** — confirmed clickable.
- Clicking the first row navigated to:
  `https://bexar.tx.publicsearch.us/doc/314427553`
- Detail page title: **"Document Preview"** — loads without a login or paywall.

**Pattern:** `https://bexar.tx.publicsearch.us/doc/<internalDocId>`

**Critical: the `/doc/` ID is NOT the recorded doc number.**

| Row 0 value | Source |
|---|---|
| `314427553` | internal document ID — used in `/doc/314427553` |
| `20260070780` | recorded instrument number — shown in the Doc Number column |

The internal ID is available **directly in each result row, no click needed**:
- checkbox: `<input id="table-checkbox-314427553">`
- checkbox `aria-label="Document 314427553, not selected, checkbox"`

**Architecture implication:** the scraper can build detail URLs straight from the result list by parsing `table-checkbox-<id>` — it does not need to click each row.

Saved: `raw_html/03_detail_page.html`, `screenshots/03_detail_page.png`

---

## Anti-bot / login walls

**None observed.** Headless Chromium loaded every page cleanly. No CAPTCHA, no bot challenge, no login prompt. The detail page ("Document Preview") rendered without authentication and showed no subscribe/purchase/unlock gating in the HTML. (The only 500 encountered was the bad MMDDYYYY date format — a portal validation error, not anti-bot.)

---

## Summary for translator design

1. Date range param: **`recordedDateRange=YYYYMMDD,YYYYMMDD`** (MMDDYYYY → HTTP 500).
2. `docTypes` URL param **works** — direct per-doc-type result URLs; no widget interaction.
3. Detail pages: **`/doc/<internalDocId>`**, ID lifted from row checkbox `table-checkbox-<id>` (≠ recorded doc number).
4. No auth / anti-bot barriers.

PHASE 5 FOLLOW-UP COMPLETE — AWAITING OPERATOR REVIEW
