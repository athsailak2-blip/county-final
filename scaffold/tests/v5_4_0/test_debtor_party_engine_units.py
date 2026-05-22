#!/usr/bin/env python3
"""v5.4.0 unit tests — §17 debtor party engine.

Added in v5.4.0 Session 2. Wired into run_all.py via scaffold/tests/v5_4_0/.
Exercises debtor_party_engine across the full §17 surface:

  - all 17 §17.C mapped doc types resolve to a real debtor;
  - the F-5 default rule routes an unmapped doc type to REVIEW_REQUIRED with
    review_reason "no_debtor_rule_for_doc_type";
  - the §17.F owner-type classifier across all 5 outputs;
  - all 7 §17.D filer-suppression groups.

Every resolve_debtor_party call self-validates its output against
debtor_resolved_record.schema.json (the engine raises ValueError on a
non-conforming record), so a clean return is also a schema-conformance check.

Run: python3 scaffold/tests/v5_4_0/test_debtor_party_engine_units.py
Exit 0 = pass, non-zero = fail.
"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scaffold.pipeline import debtor_party_engine as engine


def _party(name: str, name_type: str) -> dict:
    return {"name": name, "name_type": name_type, "raw_role": name_type}


def _raw_event(doc_type, *, parties=None, document_body_text=None) -> dict:
    """Build a schema-complete raw_event_record for one canonical doc type."""
    return {
        "raw_event_id": f"raw_{doc_type}_0001",
        "source_id": "unit_test_source",
        "source_role": "PRIMARY_EVENT_SOURCE",
        "canonical_doc_type": doc_type,
        "raw_doc_type": doc_type.upper(),
        "instrument_number": f"INST-{doc_type}-0001",
        "recorded_date": "2026-04-01",
        "event_date": None,
        "source_url": f"https://example.test/{doc_type}/0001",
        "parties": parties or [],
        "document_body_text": document_body_text,
        "property_refs": {
            "parcel_id": None,
            "situs_address": "100 EXAMPLE WAY",
            "legal_description": None,
            "case_number": None,
        },
        "amounts": [],
        "evidence_ids": [f"ev_{doc_type}_0001"],
        "parser_name": "unit_test",
        "parser_version": "1.0.0",
        "parser_confidence": 90,
        "captured_at": "2026-04-05T12:00:00Z",
    }


# A neutral individual debtor name — not a known filer, classifies INDIVIDUAL.
DEBTOR = "DOE, MARGARET R"

# §17.C STRUCTURED doc types: (doc_type, debtor name_type to tag the party).
STRUCTURED_CASES = [
    ("hospital_lien", "TP"),
    ("code_lien", "TP"),
    ("administrative_lien", "TP"),
    ("federal_tax_lien", "TP"),
    ("state_tax_lien", "TP"),
    ("mechanic_lien", "GR"),
    ("construction_lien", "GR"),
    ("lis_pendens", "DF"),
    ("civil_judgment", "DF"),
    ("abstract_of_judgment", "DF"),
    ("executor_deed", "GR"),
    ("administrator_deed", "GR"),
    ("sheriff_sale", "DF"),
]

# §17.C DOCUMENT_BODY doc types: (doc_type, document body carrying the debtor).
BODY_CASES = [
    ("affidavit_of_heirship", "AFFIDAVIT OF HEIRSHIP\nDECEDENT: DOE, MARGARET R\n"),
    ("foreclosure_notice", "NOTICE OF FORECLOSURE SALE\nMORTGAGOR: DOE, MARGARET R\n"),
    ("trustee_sale", "NOTICE OF TRUSTEE'S SALE\nGRANTOR: DOE, MARGARET R\n"),
    ("probate", "IN THE ESTATE OF MARGARET R DOE\nPENDING IN PROBATE COURT\n"),
]

# (name, expected §17.F owner type).
OWNER_TYPE_CASES = [
    ("ACME HOLDINGS LLC", "ENTITY"),
    ("ESTATE OF JOHN DOE", "ESTATE"),
    ("DOE FAMILY TRUST", "TRUST"),
    ("DOE, JANE A", "INDIVIDUAL"),
    ("—", "UNKNOWN"),
]

# (name, §17.D group the match label must start with).
SUPPRESSION_CASES = [
    ("CITY OF EXAMPLE", "government_entity"),
    ("EXAMPLE COMPTROLLER", "state_agency"),
    ("EXAMPLE GENERAL HOSPITAL", "hospital_entity"),
    ("EXAMPLE MORTGAGE COMPANY", "mortgage_lender"),
    ("FREDDIE MAC", "federal_mortgage_agency"),
    ("NATIONSTAR", "servicer"),
    ("SUBSTITUTE TRUSTEE", "trustee"),
]


def main() -> int:
    checks: list[tuple[str, bool]] = []

    def check(desc: str, ok: bool) -> None:
        checks.append((desc, bool(ok)))

    # --- structural: the §17.C table and §17.D groups -----------------------
    rules = engine.UNIVERSAL_DEBTOR_PARTY_RULES
    check("§17.C UNIVERSAL_DEBTOR_PARTY_RULES has all 17 mapped doc types",
          len(rules) == 17)
    check("§17.C table maps `probate` (row 17)", "probate" in rules)
    check("§17.D defines 7 filer-suppression groups",
          len(engine._FILER_SUPPRESSION_PATTERNS) == 7)

    # --- the 17 §17.C mapped doc types resolve to a real debtor -------------
    for doc_type, name_type in STRUCTURED_CASES:
        try:
            out = engine.resolve_debtor_party(
                _raw_event(doc_type, parties=[_party(DEBTOR, name_type)])
            )
            ok = (out.get("debtor_resolution_status") == "RESOLVED"
                  and "DOE" in str(out.get("owner_name", "")).upper())
        except Exception as exc:  # noqa: BLE001 — surface engine errors as fails
            ok = False
            print(f"  (exception for {doc_type}: {exc})")
        check(f"§17.C {doc_type} → RESOLVED to the debtor", ok)

    for doc_type, body in BODY_CASES:
        try:
            out = engine.resolve_debtor_party(
                _raw_event(doc_type, document_body_text=body)
            )
            ok = (out.get("debtor_resolution_status") == "RESOLVED"
                  and "DOE" in str(out.get("owner_name", "")).upper())
        except Exception as exc:  # noqa: BLE001
            ok = False
            print(f"  (exception for {doc_type}: {exc})")
        check(f"§17.C {doc_type} (document-body) → RESOLVED to the debtor", ok)

    # --- F-5 default rule: an unmapped doc type routes to REVIEW_REQUIRED ----
    try:
        f5 = engine.resolve_debtor_party(_raw_event("tax_sale"))
        f5_ok = (
            f5.get("debtor_resolution_status") == "REVIEW_REQUIRED"
            and f5.get("review_reason") == "no_debtor_rule_for_doc_type"
            and f5.get("debtor_extraction_method") == "REVIEW_ROUTED"
            and "unidentified party" in str(f5.get("owner_name", "")).lower()
        )
    except Exception as exc:  # noqa: BLE001
        f5_ok = False
        print(f"  (exception for F-5 default: {exc})")
    check("F-5 default: unmapped `tax_sale` → REVIEW_REQUIRED, "
          "review_reason 'no_debtor_rule_for_doc_type'", f5_ok)

    # --- §17.F owner-type classification, all 5 outputs ---------------------
    for name, expected in OWNER_TYPE_CASES:
        got = engine.classify_owner_type(name)
        check(f"§17.F classify_owner_type({name!r}) == {expected}",
              got == expected)

    # --- §17.D filer suppression, all 7 groups ------------------------------
    for name, group in SUPPRESSION_CASES:
        label = engine.match_known_filer(name)
        check(f"§17.D match_known_filer({name!r}) → {group}",
              isinstance(label, str) and label.startswith(group))

    # an individual name is NOT flagged as a filer
    check("§17.D match_known_filer does not flag an individual name",
          engine.match_known_filer(DEBTOR) is None)

    # --- report -------------------------------------------------------------
    failed = [d for d, ok in checks if not ok]
    for desc, ok in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {desc}")

    if failed:
        print(f"FAIL: §17 debtor party engine unit tests — "
              f"{len(failed)} of {len(checks)} checks failed")
        return 1

    print(f"PASS: §17 debtor party engine unit tests — "
          f"all {len(checks)} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
