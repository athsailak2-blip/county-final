"""
End-to-end smoke test: foreclosure + owner-name pattern signal.

Demonstrates that the production pipeline correctly:

  1. Translates a foreclosure-map raw record into a signal + placeholder
     parcel.
  2. Matches the placeholder to a (synthetic) parcel-master record whose
     owner name matches an estate / living-trust pattern.
  3. Emits a derived owner-name signal that stacks with the
     foreclosure signal on the same parcel.
  4. Produces a multi-pattern lead with stack_depth >= 2 that
     dashboard.js will render with the heir-candidate badge.

Run with: python3 scaffold/tests/test_owner_name_signal_integration.py
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scaffold.pipeline.build_leads import (  # noqa: E402
    _adapt_translator_signal,
    _apply_parcel_master_matching,
    run_pipeline,
)
from scaffold.pipeline.owner_name_patterns import (  # noqa: E402
    emit_owner_name_signals_for_parcels,
)
from scaffold.pipeline.translators import lookup as lookup_translator  # noqa: E402


# Load the live Bexar config once. Tests pass it through to the
# translator so cross-county-leak and sale-date rules see the same
# accepted_municipalities + sale_date_rule that production uses.
_CFG_PATH = REPO_ROOT / "config" / "counties" / "bexar_tx.json"
with _CFG_PATH.open() as _fh:
    COUNTY_CONFIG = json.load(_fh)


passes = []
fails = []


def _assert(label, cond, detail=""):
    if cond:
        passes.append(label)
        print(f"  [PASS] {label}")
    else:
        fails.append((label, detail))
        print(f"  [FAIL] {label}  --  {detail}")


def _foreclosure_raw_record(address: str, doc_number: str, zip_code: str,
                              city: str = "SAN ANTONIO") -> dict:
    """Build a foreclosure-map raw record in the canonical §4.32 shape."""
    return {
        "raw_record_id": "raw_int_test_" + doc_number,
        "source_id": "foreclosure_notices_map",
        "source_url": (
            "about:test/foreclosures/" + doc_number
        ),
        "source_fetched_at": "2026-05-14T19:00:00Z",
        "raw_payload": {
            "doc_type": "MORTGAGE",
            "doc_number": doc_number,
            "address": address,
            "city": city,
            "zip": zip_code,
            "school_district": "SYNTH ISD",
            "recording_year": 2026,
            "recording_month": 6,
            "recording_event_date": "2026-06-01",
            "layer_id": 0,
            "layer_name": "Mortgage",
            "category_hint": "mortgage_foreclosure",
            "object_id": 99999,
        },
        "raw_text": None,
        "first_seen_at": "2026-05-14T19:00:00Z",
        "last_seen_at": "2026-05-14T19:00:00Z",
        "change_status": "NEW_RECORD",
        "parser_confidence": 95,
    }


def _bcad_parcel(situs: str, owner: str, zip_code: str,
                  *, prop_id: int = 999001,
                  exempt_hs: bool = False, exempt_ov65: bool = False) -> dict:
    """Build a canonical-shape parcel record (post-translator shape)."""
    return {
        "parcel_id": f"BCAD-{prop_id:08d}",
        "address": situs.upper().strip(),
        "city": "SAN ANTONIO",
        "situs_state": "TX",
        "zip": zip_code,
        "owner_name": owner,
        "owner_mailing_address": situs,
        "owner_mailing_city": "SAN ANTONIO",
        "owner_mailing_state": "TX",
        "owner_mailing_zip": zip_code,
        "year_built": 1985,
        "land_value": 80000,
        "improvement_value": 220000,
        "assessed_value": 300000,
        "property_use": "1",
        "exempt_homestead": exempt_hs,
        "exempt_over_65": exempt_ov65,
        "exempt_disabled": False,
        "legal_description": "INT_TEST_LOT",
        "parcel_master_status": "matched_pending_join",
    }


def _run_e2e(foreclosure_raws: list, bcad_records: list) -> dict:
    """Run the production pipeline against fixture inputs."""
    source_cfg = dict(COUNTY_CONFIG["sources"]["foreclosure_notices_map"])
    source_cfg["_source_id"] = "foreclosure_notices_map"
    translate_fn = lookup_translator(source_cfg.get("translator", "foreclosure_notices"))
    raw_signals, placeholders, per_signal_meta = translate_fn(
        foreclosure_raws, COUNTY_CONFIG, source_cfg
    )
    signals = [_adapt_translator_signal(s, "foreclosure_notices_map") for s in raw_signals]
    per_signal_meta_by_url = dict(per_signal_meta)

    parcels = _apply_parcel_master_matching(
        signals=signals,
        placeholders=placeholders,
        bcad_records=bcad_records,
        per_signal_meta_by_url=per_signal_meta_by_url,
    )

    # Owner-name signal emission with defensive guard.
    parcels_with_lead_signals = {
        sig.get("primary_parcel_id") or sig.get("parcel_id")
        for sig in signals
        if sig.get("primary_parcel_id") or sig.get("parcel_id")
    }
    emitted = emit_owner_name_signals_for_parcels(
        parcels=parcels,
        parcels_with_lead_signals=parcels_with_lead_signals,
        source_id="parcel_master",
    )
    adapted_owner_name = [_adapt_translator_signal(s, "parcel_master") for s in emitted]
    for new_sig in adapted_owner_name:
        parent_meta = next(
            (per_signal_meta_by_url[u]
             for u, m in per_signal_meta_by_url.items()
             if m.get("primary_parcel_id") == new_sig.get("parcel_id")),
            None,
        )
        if parent_meta and not new_sig.get("filing_date"):
            new_sig["filing_date"] = parent_meta.get("expected_sale_date")
        per_signal_meta_by_url[new_sig["source_url"]] = {
            "preset_review_flags": [],
            "expected_sale_date": (parent_meta or {}).get("expected_sale_date"),
            "match_confidence": (parent_meta or {}).get("match_confidence", 95),
            "match_method": "derived_owner_name",
            "address": (parent_meta or {}).get("address", ""),
            "city": (parent_meta or {}).get("city", ""),
            "zip": (parent_meta or {}).get("zip", ""),
        }
    signals.extend(adapted_owner_name)

    return run_pipeline(
        mode="production",
        parcels=parcels,
        raw_signals=signals,
        county_id=COUNTY_CONFIG.get("county_id", ""),
        county_name=COUNTY_CONFIG.get("county_name", ""),
        state=COUNTY_CONFIG.get("state", ""),
        scoring_overrides=COUNTY_CONFIG.get("scoring_overrides", {}),
        as_of=date(2026, 5, 14),
        per_signal_meta=per_signal_meta_by_url,
        build_label="SOURCE_LIMITED",
        build_label_reason="integration smoke test",
        deployment=COUNTY_CONFIG.get("deployment") or {},
    )


def test_foreclosure_plus_estate_owner_yields_heir_lead():
    print("[integration — foreclosure + ESTATE OF owner]")
    fc = _foreclosure_raw_record(
        address="123 SYNTHETIC HEIR LN",
        doc_number="INT-EST-001",
        zip_code="78210",
    )
    bcad = _bcad_parcel(
        situs="123 SYNTHETIC HEIR LN",
        owner="ESTATE OF SYNTHETIC DOE",
        zip_code="78210",
        prop_id=999100,
    )
    result = _run_e2e([fc], [bcad])

    rows = result["payload"]["records"]
    _assert("exactly 1 lead produced", len(rows) == 1,
            f"got {len(rows)}")

    row = rows[0]
    patterns = set(row["display_patterns"])
    _assert("lead carries foreclosure pattern",
            "foreclosure" in patterns)
    _assert("lead carries estate pattern (from owner-name)",
            "estate" in patterns)
    _assert("stack_depth >= 2 (foreclosure + estate stacked)",
            row["stack_depth"] >= 2,
            f"got {row['stack_depth']}")
    _assert("score elevated above plain foreclosure (>= 75) by the stack",
            row["display_score"] >= 75,
            f"got {row['display_score']} / {row['display_tier']}")
    _assert("owner name visible on the lead",
            "ESTATE OF SYNTHETIC DOE" in row["display_owner"])
    _assert("evidence chain length >= 2 (foreclosure + estate-name)",
            len(row["evidence_ids"]) >= 2)


def test_foreclosure_plus_living_trust_owner_yields_trust_lead():
    print("\n[integration — foreclosure + LIVING TRUST owner]")
    fc = _foreclosure_raw_record(
        address="456 SYNTHETIC TRUST CT",
        doc_number="INT-TRT-001",
        zip_code="78230",
    )
    bcad = _bcad_parcel(
        situs="456 SYNTHETIC TRUST CT",
        owner="DOE FAMILY REVOCABLE LIVING TRUST",
        zip_code="78230",
        prop_id=999200,
    )
    result = _run_e2e([fc], [bcad])
    row = result["payload"]["records"][0]
    patterns = set(row["display_patterns"])
    _assert("lead carries foreclosure", "foreclosure" in patterns)
    _assert("lead carries transfer (from living-trust owner-name)",
            "transfer" in patterns)
    _assert("entity_owned does NOT fire (TRUST excluded from entity regex)",
            "entity_owned" not in row["display_attributes"])
    _assert("stack_depth >= 2", row["stack_depth"] >= 2)
    _assert("score elevated above plain foreclosure (>= 75) by the stack",
            row["display_score"] >= 75,
            f"got {row['display_score']} / {row['display_tier']}")


def test_foreclosure_plus_estate_owner_with_ov65_reaches_hot():
    print("\n[integration — heir candidate + senior_owner (OV65) -> Hot tier]")
    fc = _foreclosure_raw_record(
        address="700 SYNTHETIC HEIR DR",
        doc_number="INT-EST-002",
        zip_code="78207",
    )
    bcad = _bcad_parcel(
        situs="700 SYNTHETIC HEIR DR",
        owner="ESTATE OF SYNTHETIC MARTINEZ",
        zip_code="78207",
        prop_id=999500,
        exempt_hs=True,
        exempt_ov65=True,
    )
    result = _run_e2e([fc], [bcad])
    row = result["payload"]["records"][0]
    _assert("senior_owner fires from OV65",
            "senior_owner" in row["display_attributes"])
    _assert("absentee suppressed by HS exemption",
            "absentee" not in row["display_attributes"])
    _assert("Hot tier achieved with foreclosure + estate + senior_owner",
            row["display_score"] >= 80,
            f"got {row['display_score']} / {row['display_tier']}")


def test_foreclosure_plain_owner_stays_strong_no_extra_signals():
    print("\n[integration — foreclosure + plain owner stays Strong]")
    fc = _foreclosure_raw_record(
        address="789 SYNTHETIC PLAIN DR",
        doc_number="INT-PLN-001",
        zip_code="78201",
    )
    bcad = _bcad_parcel(
        situs="789 SYNTHETIC PLAIN DR",
        owner="DOE JOHN & JANE",
        zip_code="78201",
        prop_id=999300,
    )
    result = _run_e2e([fc], [bcad])
    row = result["payload"]["records"][0]
    _assert("plain owner -> only foreclosure pattern",
            row["display_patterns"] == ["foreclosure"])
    _assert("plain owner -> stack_depth 1",
            row["stack_depth"] == 1)
    _assert("plain owner -> not Hot tier (no stacking bonus)",
            row["display_tier"] in ("Strong", "Workable"))


def test_foreclosure_plus_entity_owner_fires_attribute_not_signal():
    print("\n[integration — foreclosure + LLC owner -> entity_owned attribute]")
    fc = _foreclosure_raw_record(
        address="321 SYNTHETIC HOLDINGS WAY",
        doc_number="INT-LLC-001",
        zip_code="78245",
    )
    bcad = _bcad_parcel(
        situs="321 SYNTHETIC HOLDINGS WAY",
        owner="SYNTHETIC HOLDINGS LLC",
        zip_code="78245",
        prop_id=999400,
    )
    result = _run_e2e([fc], [bcad])
    row = result["payload"]["records"][0]
    _assert("entity_owned attribute fires for LLC owner",
            "entity_owned" in row["display_attributes"])
    _assert("only foreclosure pattern (no signal-class entity emission)",
            row["display_patterns"] == ["foreclosure"])
    _assert("stack_depth 1 (no new signal from LLC owner)",
            row["stack_depth"] == 1)


def main() -> int:
    print("[owner_name_signal_integration tests]\n")
    test_foreclosure_plus_estate_owner_yields_heir_lead()
    test_foreclosure_plus_living_trust_owner_yields_trust_lead()
    test_foreclosure_plus_estate_owner_with_ov65_reaches_hot()
    test_foreclosure_plain_owner_stays_strong_no_extra_signals()
    test_foreclosure_plus_entity_owner_fires_attribute_not_signal()
    print(f"\npasses: {len(passes)}  fails: {len(fails)}")
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
