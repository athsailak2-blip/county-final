"""
Translator test for tax_delinquency_list.

Verifies the translator converts tax certificate / delinquency records
into signals with tax_sale_certificate doc type and tax lead pattern.
"""

from __future__ import annotations

import sys
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
SCAFFOLD_DIR = THIS_DIR.parent
FRAMEWORK_ROOT = SCAFFOLD_DIR.parent
sys.path.insert(0, str(FRAMEWORK_ROOT))

from scaffold.pipeline import translators

PASS = "PASS"
FAIL = "FAIL"
results: list[tuple[str, str, str]] = []


def case(name: str, passed: bool, detail: str = "") -> None:
    status = PASS if passed else FAIL
    results.append((status, name, detail))
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))


SOURCE_CONFIG = {
    "translator": "tax_delinquency_list",
    "_source_id": "tax_collector",
}

FIELD_MAP_CONFIG = {
    "translator": "tax_delinquency_list",
    "_source_id": "tax_collector",
    "field_map": {
        "parcel_id": "re_number",
        "situs_address": "prop_address",
    },
}


def test_registered():
    print("\n[registered]")
    names = translators.registered_names()
    case("tax_delinquency_list registered", "tax_delinquency_list" in names)


def test_empty_input():
    print("\n[empty input]")
    fn = translators.lookup("tax_delinquency_list")
    sig, par, meta = fn([], {}, {})
    case("empty: signals empty", sig == [])
    case("empty: parcels empty", par == [])
    case("empty: meta empty", meta == {})


def test_typical_certificate():
    print("\n[typical tax certificate listing]")
    fn = translators.lookup("tax_delinquency_list")
    raw = [{
        "raw_record_id": "raw_tc_001",
        "source_id": "tax_collector",
        "source_url": "https://lienhub.com/county/duval",
        "source_fetched_at": "2026-06-04T12:00:00Z",
        "raw_payload": {
            "parcel_id": "000123-0000",
            "situs_address": "123 MAIN ST",
            "tax_year": "2025",
            "tax_due": "5250.00",
            "certificate_status": "auction_scheduled",
            "auction_date": "2026-06-15",
        },
        "parser_confidence": 80,
    }]
    sig, par, meta = fn(raw, {}, SOURCE_CONFIG)
    case("TC: 1 signal", len(sig) == 1, f"got {len(sig)}")
    case("TC: 1 parcel", len(par) == 1, f"got {len(par)}")
    if sig:
        s = sig[0]
        case("TC: doc_type = tax_sale_certificate", s["doc_type"] == "tax_sale_certificate")
        case("TC: lead_pattern = tax", s["lead_pattern"] == "tax")
        case("TC: doc_number includes tax year",
             s["doc_number"] == "2025-000123-0000")
        case("TC: consideration = tax_due", s["consideration"] == "5250.00")
        case("TC: primary_parcel_id = parcel_id",
             s["primary_parcel_id"] == "000123-0000")
        case("TC: translator set", s["translator"] == "tax_delinquency_list")
    if par:
        case("TC: parcel_id preserved", par[0]["parcel_id"] == "000123-0000")


def test_empty_parcel_skipped():
    print("\n[empty parcel_id skipped]")
    fn = translators.lookup("tax_delinquency_list")
    raw = [{
        "raw_record_id": "raw_skip",
        "raw_payload": {
            "parcel_id": "",
            "situs_address": "NO ID",
            "tax_year": "2025",
        },
    }]
    sig, par, meta = fn(raw, {}, SOURCE_CONFIG)
    case("skip: 0 signals", len(sig) == 0)
    case("skip: 0 parcels", len(par) == 0)


def test_multiple_listings():
    print("\n[multiple listings]")
    fn = translators.lookup("tax_delinquency_list")
    raw = [
        {"raw_record_id": "r1", "raw_payload": {
            "parcel_id": "000123-0000", "tax_year": "2025"}},
        {"raw_record_id": "r2", "raw_payload": {
            "parcel_id": "000456-0000", "tax_year": "2025"}},
    ]
    sig, par, meta = fn(raw, {}, SOURCE_CONFIG)
    case("multi: 2 signals", len(sig) == 2)
    case("multi: 2 parcels", len(par) == 2)


def test_field_map_bridging():
    print("\n[field_map bridges non-canonical names]")
    fn = translators.lookup("tax_delinquency_list")
    raw = [{
        "raw_record_id": "raw_fm",
        "raw_payload": {
            "re_number": "000789-0000",
            "prop_address": "789 PINE LN",
            "tax_year": "2025",
            "tax_due": "3200",
            "certificate_status": "held",
        },
    }]
    sig, par, meta = fn(raw, {}, FIELD_MAP_CONFIG)
    case("FM: 1 signal via field_map", len(sig) == 1)
    if sig:
        case("FM: parcel_id from re_number",
             sig[0]["primary_parcel_id"] == "000789-0000")
    if par:
        case("FM: address from prop_address",
             par[0]["situs_address"] == "789 PINE LN")


def main() -> int:
    print("=" * 72)
    print("TAX_DELINQUENCY_LIST TRANSLATOR TEST")
    print("=" * 72)
    test_registered()
    test_empty_input()
    test_typical_certificate()
    test_empty_parcel_skipped()
    test_multiple_listings()
    test_field_map_bridging()

    passed = sum(1 for r in results if r[0] == PASS)
    failed = sum(1 for r in results if r[0] == FAIL)
    print()
    print(f"RESULT: {passed} pass, {failed} fail")
    print("=" * 72)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
