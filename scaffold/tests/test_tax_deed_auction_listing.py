"""
Translator test for tax_deed_auction_listing.

Verifies the translator converts tax deed sale listing raw records
into signals with tax_deed doc type and tax lead pattern.
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
    "translator": "tax_deed_auction_listing",
    "_source_id": "tax_deed_sales",
}

FIELD_MAP_CONFIG = {
    "translator": "tax_deed_auction_listing",
    "_source_id": "tax_deed_sales",
    "field_map": {
        "parcel_id": "parcel_number",
        "address": "property_address",
    },
}


def test_registered():
    print("\n[registered]")
    names = translators.registered_names()
    case("tax_deed_auction_listing registered",
         "tax_deed_auction_listing" in names)


def test_empty_input():
    print("\n[empty input]")
    fn = translators.lookup("tax_deed_auction_listing")
    sig, par, meta = fn([], {}, {})
    case("empty: signals empty", sig == [])
    case("empty: parcels empty", par == [])
    case("empty: meta empty", meta == {})


def test_typical_listing():
    print("\n[typical tax deed listing]")
    fn = translators.lookup("tax_deed_auction_listing")
    raw = [{
        "raw_record_id": "raw_td_001",
        "source_id": "tax_deed_sales",
        "source_url": "https://taxdeed.duvalclerk.com/",
        "source_fetched_at": "2026-06-04T12:00:00Z",
        "raw_payload": {
            "parcel_id": "000123-0000",
            "address": "123 MAIN ST, JACKSONVILLE, FL",
            "opening_bid": "$50,000.00",
            "sale_status": "scheduled",
        },
        "parser_confidence": 85,
    }]
    sig, par, meta = fn(raw, {}, SOURCE_CONFIG)
    case("TD: 1 signal", len(sig) == 1, f"got {len(sig)}")
    case("TD: 1 parcel", len(par) == 1, f"got {len(par)}")
    if sig:
        s = sig[0]
        case("TD: doc_type = tax_deed", s["doc_type"] == "tax_deed")
        case("TD: lead_pattern = tax", s["lead_pattern"] == "tax")
        case("TD: doc_number = parcel_id",
             s["doc_number"] == "000123-0000")
        case("TD: consideration = opening_bid",
             s["consideration"] == "$50,000.00")
        case("TD: primary_parcel_id = parcel_id",
             s["primary_parcel_id"] == "000123-0000")
        case("TD: translator set",
             s["translator"] == "tax_deed_auction_listing")
    if par:
        p = par[0]
        case("TD: parcel_id preserved", p["parcel_id"] == "000123-0000")
        case("TD: address preserved",
             p["situs_address"] == "123 MAIN ST, JACKSONVILLE, FL")


def test_empty_parcel_id_skipped():
    print("\n[empty parcel_id is skipped]")
    fn = translators.lookup("tax_deed_auction_listing")
    raw = [{
        "raw_record_id": "raw_skip",
        "raw_payload": {
            "parcel_id": "",
            "address": "NO PARCEL ID",
            "opening_bid": "$10,000",
        },
    }]
    sig, par, meta = fn(raw, {}, SOURCE_CONFIG)
    case("skip: 0 signals", len(sig) == 0)
    case("skip: 0 parcels", len(par) == 0)


def test_multiple_listings():
    print("\n[multiple listings]")
    fn = translators.lookup("tax_deed_auction_listing")
    raw = [
        {
            "raw_record_id": "raw_list_1",
            "raw_payload": {
                "parcel_id": "000123-0000",
                "address": "123 MAIN ST",
                "opening_bid": "$50,000",
            },
        },
        {
            "raw_record_id": "raw_list_2",
            "raw_payload": {
                "parcel_id": "000456-0000",
                "address": "456 OAK AVE",
                "opening_bid": "$25,000",
            },
        },
    ]
    sig, par, meta = fn(raw, {}, SOURCE_CONFIG)
    case("multiple: 2 signals", len(sig) == 2, f"got {len(sig)}")
    case("multiple: 2 parcels", len(par) == 2, f"got {len(par)}")


def test_field_map_bridging():
    print("\n[field_map bridges non-canonical names]")
    fn = translators.lookup("tax_deed_auction_listing")
    raw = [{
        "raw_record_id": "raw_fm",
        "raw_payload": {
            "parcel_number": "000789-0000",
            "property_address": "789 PINE LN",
            "opening_bid": "$75,000",
        },
    }]
    sig, par, meta = fn(raw, {}, FIELD_MAP_CONFIG)
    case("FM: 1 signal via field_map", len(sig) == 1)
    if sig:
        case("FM: parcel_id from parcel_number",
             sig[0]["doc_number"] == "000789-0000")
    if par:
        case("FM: address from property_address",
             par[0]["situs_address"] == "789 PINE LN")


def main() -> int:
    print("=" * 72)
    print("TAX_DEED_AUCTION_LISTING TRANSLATOR TEST")
    print("=" * 72)
    test_registered()
    test_empty_input()
    test_typical_listing()
    test_empty_parcel_id_skipped()
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
