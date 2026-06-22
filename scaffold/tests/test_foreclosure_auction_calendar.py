"""
Translator test for foreclosure_auction_calendar.

Verifies the translator converts auction calendar raw records
into signals with notice_of_sale doc type and foreclosure lead pattern.
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
    "translator": "foreclosure_auction_calendar",
    "_source_id": "foreclosure_sales",
    "parcel_id_prefix": "FCL-",
}


def test_registered():
    print("\n[registered]")
    names = translators.registered_names()
    case("foreclosure_auction_calendar registered",
         "foreclosure_auction_calendar" in names)


def test_empty_input():
    print("\n[empty input]")
    fn = translators.lookup("foreclosure_auction_calendar")
    sig, par, meta = fn([], {}, {})
    case("empty: signals empty", sig == [])
    case("empty: parcels empty", par == [])
    case("empty: meta empty", meta == {})


def test_typical_auction_day():
    print("\n[typical auction day produces signal]")
    fn = translators.lookup("foreclosure_auction_calendar")
    raw = [{
        "raw_record_id": "raw_fc_001",
        "source_id": "foreclosure_sales",
        "source_url": "https://duval.realforeclose.com/index.cfm",
        "source_fetched_at": "2026-06-04T12:00:00Z",
        "raw_payload": {
            "auction_day": "1",
            "active_count": 3,
            "total_count": 5,
            "sale_time": "11:00 AM ET",
        },
        "parser_confidence": 90,
    }]
    sig, par, meta = fn(raw, {}, SOURCE_CONFIG)
    case("FC: 1 signal", len(sig) == 1, f"got {len(sig)}")
    case("FC: 1 parcel", len(par) == 1, f"got {len(par)}")
    if sig:
        s = sig[0]
        case("FC: doc_type = notice_of_sale",
             s["doc_type"] == "notice_of_sale")
        case("FC: lead_pattern = foreclosure",
             s["lead_pattern"] == "foreclosure")
        case("FC: doc_number includes date",
             s["doc_number"] is not None)
        case("FC: filing_date is YYYY-MM-DD format",
             len(s["filing_date"]) == 10 and "-" in s["filing_date"])
        case("FC: translator set",
             s["translator"] == "foreclosure_auction_calendar")


def test_empty_day_skipped():
    print("\n[empty auction_day is skipped]")
    fn = translators.lookup("foreclosure_auction_calendar")
    raw = [{
        "raw_record_id": "raw_fc_empty",
        "raw_payload": {
            "auction_day": "",
        },
    }]
    sig, par, meta = fn(raw, {}, SOURCE_CONFIG)
    case("empty day: 0 signals", len(sig) == 0)
    case("empty day: 0 parcels", len(par) == 0)


def test_multiple_days():
    print("\n[multiple auction days]")
    fn = translators.lookup("foreclosure_auction_calendar")
    raw = [
        {
            "raw_record_id": "raw_day_1",
            "raw_payload": {"auction_day": "1", "active_count": 3, "total_count": 5},
        },
        {
            "raw_record_id": "raw_day_2",
            "raw_payload": {"auction_day": "2", "active_count": 2, "total_count": 3},
        },
        {
            "raw_record_id": "raw_day_15",
            "raw_payload": {"auction_day": "15", "active_count": 1, "total_count": 2},
        },
    ]
    sig, par, meta = fn(raw, {}, SOURCE_CONFIG)
    case("multiple: 3 signals", len(sig) == 3, f"got {len(sig)}")
    case("multiple: 3 parcels", len(par) == 3, f"got {len(par)}")


def test_meta_preserves_counts():
    print("\n[meta preserves active/total counts]")
    fn = translators.lookup("foreclosure_auction_calendar")
    raw = [{
        "raw_record_id": "raw_meta",
        "raw_payload": {
            "auction_day": "10",
            "active_count": 5,
            "total_count": 8,
            "sale_time": "10:00 AM ET",
        },
    }]
    sig, par, meta = fn(raw, {}, SOURCE_CONFIG)
    if sig and meta:
        sig_id = sig[0]["signal_id"]
        m = meta.get(sig_id, {})
        case("meta: active_count preserved", m.get("active_count") == 5)
        case("meta: total_count preserved", m.get("total_count") == 8)
        case("meta: sale_time preserved",
             m.get("sale_time") == "10:00 AM ET")


def main() -> int:
    print("=" * 72)
    print("FORECLOSURE_AUCTION_CALENDAR TRANSLATOR TEST")
    print("=" * 72)
    test_registered()
    test_empty_input()
    test_typical_auction_day()
    test_empty_day_skipped()
    test_multiple_days()
    test_meta_preserves_counts()

    passed = sum(1 for r in results if r[0] == PASS)
    failed = sum(1 for r in results if r[0] == FAIL)
    print()
    print(f"RESULT: {passed} pass, {failed} fail")
    print("=" * 72)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
