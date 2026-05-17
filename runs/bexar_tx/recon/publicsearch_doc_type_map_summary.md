# Bexar County (TX) — PublicSearch Doc Type Classification

Source: `runs/bexar_tx/recon/doctype_dropdown.json` (RP / Land Records, 124 codes). Classification only — **no numeric scoring applied.**

Updated 2026-05-16 (second revision) — daily refresh decoupled from confidence; operator-selected list applied; CORE + EXPANDED tier model introduced.

Updated 2026-05-16 (third revision) — STL, FTL, LETTERS promoted to Daily Refresh Core (screenshot oversight resolved). Daily refresh expanded to 20 codes.

## 1. Daily Refresh Core (8 codes, high signal, low noise)

`daily_refresh_tier = CORE`. Always pulled daily.

- `LIS PEN` — LIS PENDENS — confidence HIGH, review LOW
- `MECHLN` — MECHANICS LIEN — confidence HIGH, review LOW
- `PROBATE` — PROBATE — confidence HIGH, review LOW
- `WILL` — WILL & TESTAMENT — confidence HIGH, review LOW
- `DECREE` — DECREE — confidence HIGH, review MEDIUM
- `FTL` — FEDERAL TAX LIEN — confidence HIGH, review LOW
- `STL` — STATE TAX LIEN — confidence HIGH, review LOW
- `LETTERS` — LETTERS — confidence HIGH, review MEDIUM

## 2. Daily Refresh Expanded (12 codes, operator-selected, may need review)

`daily_refresh_tier = EXPANDED`. Operator-selected; pulled daily regardless of confidence label.

- `AFFIDAV` — AFFIDAVIT — confidence MEDIUM, review HIGH
- `CSUP LN` — CHILD SUPPORT LN — confidence MEDIUM, review MEDIUM
- `JUDG` — JUDGMENT — confidence MEDIUM, review HIGH
- `SJ` — State-Judgment — confidence MEDIUM, review HIGH
- `HOSP LN` — HOSPITAL LIEN — confidence LOW, review HIGH
- `LNLD LN` — LANDLORD LIEN — confidence LOW, review HIGH
- `LIEN` — LIEN — confidence LOW, review HIGH
- `MEMO` — MEMORANDUM — confidence LOW, review HIGH
- `NOTICE` — NOTICE — confidence LOW, review HIGH
- `MOD` — MODIFICATION — confidence LOW, review HIGH
- `PA` — POWER OF ATTORNEY — confidence LOW, review MEDIUM
- `FC` — FORECLOSURE — confidence HIGH, review MEDIUM, requires dedup against foreclosure_notices_map

## 3. Suppression / Lifecycle (28 codes)

Codes whose role is to terminate / release / void a prior filing (`LIFECYCLE_SUPPRESSION_DOC_TYPE`, `lifecycle_or_suppression_only = true`). **Note:** in v2 these may be used to age-out leads whose underlying signal has been released. They are NOT pulled in v1.

- `VOID UCCRP` — VOID UCC RP
- `PART RL STL` — PARTIAL RELEASE STL
- `RL STL` — RELEASE OF STATE TAX LIEN
- `VOID STL` — VOID STL
- `CANC J` — CANCELLATION OF JUDGMENT
- `CANCEL` — CANCELLATION
- `DISMISS` — DISMISSAL
- `P RL J` — PARTIAL RELEASE OF JUDGMENT
- `PART RL` — PARTIAL RELEASE
- `RECONV` — RECONVEYANCE
- `REINST` — REINSTATEMENT
- `REL H LN` — RELEASE OF HL
- `RELEASE` — RELEASE
- `REMOVAL` — REMOVAL
- `RESCISS` — RESCISSION
- `REVOCTN` — REVOCATION
- `RL H LN` — RL OF HOSP LN
- `RL J` — RELEASE OF JUDGMENT
- `SAT` — SATISFACTION
- `SAT J` — SATISFACTION OF JUDGMENT
- `SUBORD` — SUBORDINATION
- `TERMIN` — TERMINATION
- `VOID OPR` — VOID OPR
- `WAIVER` — WAIVER
- `SR` — State-Release
- `PART RL FTL` — PARTIAL RELEASE FTL
- `RL FTL` — RELEASE OF FTL
- `VOID FTL` — VOID FTL

## 4. Skip (65 codes, NOISY_SKIP)

Routine administrative / transactional recordings; not pulled in v1.

- `CORRECT` moved into this list — resolved from NEEDS_OPERATOR_REVIEW; per the prior Q3 operator decision, correction deeds are dropped from v1.
- `LIEN` was **removed** from this list — promoted to Daily Refresh Expanded.

- `WRM` — Water Rights/Maps
- `UCC` — UCC
- `UCC1 RP` — UCC 1 REAL PROPERTY
- `UCC3RP` — UCC 3 REAL PROPERTY
- `ACKNOW` — ACKNOWLEDGEMENT
- `ADDENDM` — ADDENDUM
- `AGREEMT` — AGREEMENT
- `AMEND` — AMENDMENT
- `APPLICA` — APPLICATION
- `APPT` — APPOINTMENT
- `ART INC` — ARTICLES OF INC
- `ASSN` — ASSIGNMENT
- `ASUMPTN` — ASSUMPTION
- `BFA` — BIRTH FROM ABROAD
- `BILLOFS` — BILL OF SALE
- `BOND` — BOND
- `BTI` — BOND TO INDEMNIFY
- `CEMTRY` — CEMETERY
- `CERT` — CERTIFICATE
- `CERT CP` — CERTIFIED COPY
- `CIQ` — CONFLICT OF INTEREST QUESTIONNAIRE
- `CONDAMC` — CONDOMINIUM ASSOCIATION MANAGEMENT CERTIFICATE
- `CONTRAC` — CONTRACT
- `CORP` — CORPORATE
- `CORRECT` — CORRECTION
- `DECLAR` — DECLARATION
- `DEED` — DEED
- `DESGN` — DESIGNATION
- `DT` — DEED OF TRUST
- `EASEMNT` — EASEMENT
- `EXT` — EXTENSION
- `LEASE` — LEASE
- `LOAN` — LOAN
- `M MORTG` — MASTER MORTGAGE
- `MARRIAGE OPR` — MARRIAGE LICENSE OPR
- `MISC` — MISCELLANEOUS
- `MORTG` — MORTGAGE
- `NOTE` — NOTE
- `ORDER` — ORDER
- `ORDIN` — ORDINANCE
- `OWNCERT` — PROPERTY OWNERS ASSOCIATION MANAGEMENT CERT
- `PLY` — POLYGRAPH LICENSE
- `PWB` — PUBLIC WEIGHER BOND
- `RENEW` — RENEWAL
- `REPLACE` — REPLACEMENT
- `RESIGN` — RESIGNATION
- `RESOLUT` — RESOLUTION
- `RESTRICT` — RESTRICTIONS
- `RFSHEET` — REFERENCE SHEET
- `RIC` — RETAIL INST CONTRACT
- `RT WAY` — RIGHT OF WAY AGREEMENT
- `STATEMT` — STATEMENT
- `SUB` — SUBSTITUTION
- `TRANS` — TRANSFER
- `TRUST` — TRUST
- `TX HMST` — TX HOMESTEAD
- `VARIANC` — VARIANCE
- `WATER P` — WATER RIGHTS/PERMIT
- `WP MAPS` — WATER PERMIT MAPS
- `ASSN SEC` — ASSIGNMENT SECURED
- `DT SEC` — DEED OF TRUST SECURED
- `WP` — WATER PERMIT
- `CP` — CONDOMINIUM PLAN
- `NC` — NURSING CERTIFICATE
- `DR` — DENTAL RECORDS

## 5. Stack-only / Context Signals (9 codes)

`CONTEXT_SIGNAL` codes that remain in the proposal but are NOT in the operator-selected daily list. Pulled only when a primary signal already references the same parcel. Not part of the v1 daily pull.

- `ASIGN J` — ASSIGNMENT OF JUDGMENT
- `HMST AF` — HOMESTEAD AFFIDAVIT
- `LEVY` — LEVY
- `P AS J` — PARTIAL ASSIGNMENT OF JUDGMENT
- `P TR J` — PARTIAL TRANSFER OF JUDGMENT
- `REST LN` — AFFIDAVIT RESTITUTION LIEN
- `TRANS J` — TRANSFER OF JUDGMENT
- `TRSCR J` — TRANSCRIPT OF JUDGMENT
- `PA SEC` — POWER OF ATTORNEY SECURED

## 6. Needs Operator Review

All previously-flagged codes resolved. No codes currently require operator review.

## 7. Codes mapped count table

| Classification | Count |
|---|---|
| PRIMARY_LEAD_DOC_TYPE | 9 |
| SUPPORTING_DOC_TYPE | 13 |
| CONTEXT_SIGNAL | 9 |
| LIFECYCLE_SUPPRESSION_DOC_TYPE | 28 |
| FORECLOSURE_DUPLICATE_SKIP | 0 |
| NOISY_SKIP | 65 |
| NEEDS_OPERATOR_REVIEW | 0 |
| **TOTAL** | **124** |

Daily refresh: **20** codes (8 CORE + 12 EXPANDED). All **124 of 124** codes accounted for.

## 8. Codes NOT mapped to operator's stated priorities

Unchanged from the prior revision — operator-named lead types with no exact PublicSearch code:

- **Quitclaim deed** — no specific code. Closest umbrella: `DEED` (broad). Broad `DEED` was NOT pulled to compensate.
- **Partition deed** — no specific code. Closest umbrella: `DEED` (broad). `DECREE` may capture court-ordered partitions but is not a deed code. Broad `DEED` NOT pulled.
- **Correction deed** — no unambiguous code. `CORRECT` ('CORRECTION') covers correction of any instrument; per the Q3 operator decision, correction deeds are dropped from v1 and `CORRECT` now sits in the Skip list.
- **HOA lien** — no specific code. Operator selected the broad `LIEN` umbrella as the closest proxy; `LIEN` is now in Daily Refresh Expanded.
- **Affidavit of heirship** — no separate code. Folded into the `AFFIDAV` umbrella (and partially `DA`); the heirship subset must be isolated downstream.

## 9. Operator decisions applied

**Second revision —**

1. **Daily refresh decoupled from confidence label.** Per operator direction, `daily_refresh_enabled` is now driven solely by the operator-selected list, not by `operator_confidence_label`. A code may be daily-enabled with LOW confidence and/or HIGH review_intensity — these are valid combinations.
2. **CORE / EXPANDED / NOT_INCLUDED tier model introduced** via the new `daily_refresh_tier` field. CORE = high-signal/low-noise, always daily. EXPANDED = operator-selected, may be noisier, daily. NOT_INCLUDED = not pulled daily.
3. **New fields added to every entry:** `daily_refresh_tier`, `review_intensity` (LOW/MEDIUM/HIGH downstream-review effort), and `requires_dedup_against_foreclosure_notices_map` (boolean).
4. **FC promoted** from FORECLOSURE_DUPLICATE_SKIP to PRIMARY_LEAD_DOC_TYPE / EXPANDED, with `requires_dedup_against_foreclosure_notices_map = true`.
5. **SJ promoted** to SUPPORTING_DOC_TYPE / EXPANDED. (In the existing proposal SJ was classified CONTEXT_SIGNAL, not LIFECYCLE_SUPPRESSION as the operator instruction assumed — so no removal from the suppression list was needed.)
6. **LIEN promoted** from NEEDS_OPERATOR_REVIEW to SUPPORTING_DOC_TYPE / EXPANDED; its needs_operator_review flag is cleared.
7. **CORRECT resolved** from NEEDS_OPERATOR_REVIEW to NOISY_SKIP (Skip list); correction deeds dropped from v1 per the prior Q3 decision.

**Third revision —**

8. **FTL, STL, LETTERS promoted from NOT_INCLUDED to Daily Refresh Core.** These three codes were already PRIMARY_LEAD_DOC_TYPE classification but were not in the operator's original 17-code daily refresh list (screenshot oversight). Operator confirmed FTL/STL are core distress filings and LETTERS belongs with the probate bucket. Daily refresh now totals 20 codes (8 CORE + 12 EXPANDED).

## 10. Backlog tasks

- Run a 30-day comparison sample of PublicSearch `FC` vs `foreclosure_notices_map` to quantify overlap. Decide whether to deprecate the FC pull or keep it with dedup logic.
- Define downstream pattern-matching filters for `MEMO`, `NOTICE`, `MODIFICATION` sub-types (operator will provide patterns as deals surface).
- Define heirship-subset detection for `AFFIDAV` via grantor/grantee/legal-description regex.
- Define property-affecting subset detection for `JUDG`, `SJ`, `LIEN` via downstream filtering.

## 11. No numeric scoring included

This artifact and its companion JSON contain **no weights, no scores, no bonuses, no multipliers, and no `scoring_overrides`**. No existing lis pendens, tax lien, probate, or other scoring weights were read, raised, or lowered. Scoring calibration is deferred to a later phase.

