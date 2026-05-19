# 17. Debtor Party Rules (v5.3.0+)

The debtor party rules contract defines, per canonical doc type, which party in a source
record is the debtor / owner — the lead subject — versus which party is the filer,
lienholder, or claimant. Getting this wrong inverts the identity of a lead.

This file is the universal contract. The per-county doc-type taxonomy that maps raw
document codes to canonical doc types lives in `config/counties/<county_slug>.json`.

---

## 17.0 Status and scope

- **Version:** v5.3.0 (Session A2 — Gap 5).
- **Date:** 2026-05-18.
- **Authoritative for:** every translator that produces a `matched_lead` from an
  event-based source record. The `owner_name` on a matched lead MUST be derived per this
  contract.
- **Scope:** universal — the per-doc-type debtor/filer rules, the filer-suppression
  patterns, the REVIEW_REQUIRED routing contract, and the owner-type classifier. The
  county-specific doc-type taxonomy and any county-specific suppression additions live
  in the county config.

---

## 17.A Purpose

The debtor party rules contract defines, per `canonical_doc_type`, which party in the
source record is the debtor / owner (the lead subject), versus which party is the filer,
lienholder, or claimant. The contract is universal; the per-county doc-type taxonomy
lives in `config/counties/<county_slug>.json`.

---

## 17.B Why this contract exists

A naive translator that uses column order, or the first-named party, as "owner" produces
filer-as-owner inversions. Different doc types invert party roles differently:

- **Hospital lien** — the hospital is the filer; the patient is the debtor.
- **Code / administrative lien** — the agency is the filer; the property owner is the
  debtor.
- **Federal / state tax lien** — the taxing authority is the filer; the taxpayer is the
  debtor.
- **Mechanic / construction lien** — the contractor is the filer; the property owner is
  the debtor.
- **Lis pendens** — the plaintiff is the filer; the defendant is the lead subject.
- **Judgment lien** — the judgment creditor is the filer; the debtor is the lead
  subject.
- **Executor / administrator deed** — the estate is the grantor and a grantee receives,
  but the LEAD SUBJECT is the estate / decedent (the property is estate-titled).
- **Foreclosure notice** — the lender / trustee files; the debtor is the property owner
  being foreclosed on.
- **Affidavit of heirship** — the heirs file; the decedent's estate is the lead subject.

Without explicit per-doc-type rules, the translator defaults to a positional or
first-name heuristic and produces wrong-party leads.

---

## 17.C The debtor_party_rules mapping

For each `canonical_doc_type`, the contract specifies:

- **`expected_debtor_name_type`** — which `name_type` role in the raw record carries the
  debtor identity (e.g. TP / taxpayer, DF / defendant, GR / grantor, GE / grantee).
- **`fallback_debtor_name_type`** — the secondary role used if the primary is missing.
- **`filer_name_types`** — the `name_type` roles that are KNOWN FILERS and must NEVER be
  promoted to `owner_name`.
- **`missing_debtor_behavior`** — `REVIEW_REQUIRED`: route to operator review with the
  `filer_entity` captured separately.

Required mapping (universal, doc-type-centric, county-agnostic):

    canonical_doc_type     expected_debtor   fallback   known_filers                              if missing
    ---------------------  ----------------  ---------  ----------------------------------------  ---------------
    hospital_lien          TP                GE         hospital entity patterns                  REVIEW_REQUIRED
    code_lien              TP                GE         municipal agency patterns                 REVIEW_REQUIRED
    administrative_lien    TP                GE         state agency patterns                     REVIEW_REQUIRED
    federal_tax_lien       TP                GE         IRS, United States, USA                   REVIEW_REQUIRED
    state_tax_lien         TP                GE         state revenue/comptroller, state-name      REVIEW_REQUIRED
    mechanic_lien          GR                DF         contractor/construction entity patterns   REVIEW_REQUIRED
    construction_lien      GR                DF         contractor/construction entity patterns   REVIEW_REQUIRED
    lis_pendens            DF                TP         plaintiff patterns                        REVIEW_REQUIRED
    civil_judgment         DF                TP         judgment creditor patterns                REVIEW_REQUIRED
    abstract_of_judgment   DF                TP         judgment creditor patterns                REVIEW_REQUIRED
    executor_deed          GR                --         (none -- the estate IS the lead)          REVIEW_REQUIRED
    administrator_deed     GR                --         (none -- the estate IS the lead)          REVIEW_REQUIRED
    affidavit_of_heirship  decedent from     --         heir-affiant patterns                     REVIEW_REQUIRED
                           document body
    foreclosure_notice     debtor from       --         mortgagee, trustee, lender patterns       REVIEW_REQUIRED
                           notice body
    trustee_sale           debtor from       --         trustee, mortgagee patterns               REVIEW_REQUIRED
                           notice body
    sheriff_sale           DF                --         sheriff, marshal patterns                 REVIEW_REQUIRED
    probate                decedent from     --         executor/administrator patterns           REVIEW_REQUIRED
                           document body

For the rows whose `expected_debtor` is "extracted from the document body" (affidavit of
heirship, foreclosure notice, trustee sale, probate), the debtor identity is not carried
in a structured `name_type` field and must be extracted from the document text; absence
of an extractable debtor routes to `REVIEW_REQUIRED`.

---

## 17.D Known filer suppression patterns (universal)

Patterns that MUST NEVER appear as `owner_name`, regardless of where they appear in the
raw record:

- **Government entities** — `CITY OF <*>`, `COUNTY OF <*>`, `STATE OF <*>`,
  `UNITED STATES OF AMERICA`, `UNITED STATES`, `IRS`, `INTERNAL REVENUE SERVICE`.
- **State agencies** — `<STATE> COMPTROLLER`, `<STATE> WORKFORCE COMMISSION`,
  `<STATE> DEPARTMENT OF <*>`.
- **Hospital entities by suffix** — name contains `HOSPITAL`, `HEALTH SYSTEM`,
  `MEDICAL CENTER`, `HOSPITALS OF <*>`.
- **Mortgage / lender entities by suffix** — name contains `MORTGAGE COMPANY`,
  `MORTGAGE CORP`, `MORTGAGE LLC`, `BANK N.A.`, `BANK NATIONAL ASSOCIATION`.
- **Federal mortgage agencies** — `FREDDIE MAC`, `FANNIE MAE`,
  `FEDERAL HOME LOAN MORTGAGE CORPORATION`, `FEDERAL NATIONAL MORTGAGE ASSOCIATION`,
  `GINNIE MAE`, `GOVERNMENT NATIONAL MORTGAGE ASSOCIATION`.
- **Servicers** — `NATIONSTAR`, `MR. COOPER`, `PHH MORTGAGE`, `NEWREZ`, `SHELLPOINT`,
  `RUSHMORE`, `SERVBANK`.
- **Trustee patterns** — `SUBSTITUTE TRUSTEE`, `TRUSTEE SERVICES`.

The suppression list is universal pattern matching. County-specific suppression entries
(local hospital systems, local government name variants) belong in
`config/counties/<county_slug>.json` under `debtor_party_rules.additional_suppressions`,
not in this contract.

---

## 17.E REVIEW_REQUIRED routing contract

When the expected debtor `name_type` is missing, OR a known filer pattern matches the
proposed owner:

- The `matched_lead` is emitted with `parcel_resolution_status = REVIEW_REQUIRED`.
- `owner_name` is set to a placeholder: `"<canonical_doc_type> against unidentified
  party"`.
- A separate field `filer_entity` captures the original filer name from the raw record.
- The lead is **NOT dropped** — it remains in the dashboard, visually distinct, as a
  research-pile entry for operator triage.
- A separate field `review_reason` captures the rule that triggered the routing — e.g.
  `"expected_debtor_name_type TP missing"`, or
  `"known_filer_pattern match on STATE OF <*>"`.

A wrong-party lead is worse than a flagged-for-review lead — review routing preserves the
record for an operator instead of asserting a false owner.

---

## 17.F Owner type classification

Classifier rules for `owner_type`:

- **ENTITY** — the name contains a corporate suffix: `LLC`, `INC`, `CORP`, `LP`, `LTD`,
  `P.A.` (professional association), `P.C.` (professional corporation), `PLLC`,
  `COMPANY`, `CO.`, `GROUP`, `ASSOCIATES`, `ENTERPRISES`, `PARTNERS`, `SERVICES`,
  `AUTHORITY`, `COMMISSION`, `DISTRICT`.
- **ESTATE** — the name matches a decedent pattern (word-boundary regex):
  `ESTATE OF <name>`, `EST OF <name>`, `<name> ESTATE`, `<name> EST OF`,
  `HEIRS OF <name>`. It MUST NOT match if `REAL ESTATE` precedes `ESTATE`, or if
  `ESTATE` appears as a substring inside a corporate name (`REAL ESTATE GROUP LLC` is
  ENTITY, not ESTATE).
- **TRUST** — the name matches `<name> TRUST`, `<name> REVOCABLE TRUST`,
  `<name> FAMILY TRUST`, `<name> LIVING TRUST` by word boundary. It MUST NOT match
  corporate names that merely contain `TRUST` (`TRUST COMPANY OF <*>` is ENTITY).
- **INDIVIDUAL** — the default when no other rule matches.
- **UNKNOWN** — only when the name is empty, `—`, or pure punctuation.

**Classifier precedence:** ENTITY beats ESTATE beats TRUST beats INDIVIDUAL. Word-boundary
and position rules MUST be enforced — substring matching alone produces false positives.

---

## 17.G Cross-reference to §13

This contract supplements §13, the Lead Origination Contract
(`13_lead_origination_contract.md`). §13 governs WHICH sources originate leads. §17
governs HOW debtor identity is extracted from a source record once it is recognized as
lead-originating. Together the two contracts define the integrity of `owner_name` on
matched leads.

---

## 17.H Universal versus county-specific separation

- **Universal** — the debtor_party_rules table, the filer-suppression patterns, and the
  classifier precedence. They live in this file.
- **County-specific** — the per-county doc-type taxonomy (mapping raw document codes to
  `canonical_doc_type` values) lives in `config/counties/<county_slug>.json`. Per-county
  additional suppression entries — county-specific hospital systems, local government
  name variants — live in `config/counties/<county_slug>.json` under
  `debtor_party_rules.additional_suppressions`.

This file therefore contains no county name, no state name, and no county-specific
example. The county-agnostic regression scanner enforces this.
