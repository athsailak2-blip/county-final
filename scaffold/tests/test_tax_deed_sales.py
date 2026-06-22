"""
Adapter test for scrapers/tax_deed_sales.py (Duval RealTaxDeed).

Uses injectable fetch_fn to return fixture HTML, exercising the adapter
end-to-end without network access.

Fixtures: scaffold/tests/fixtures/tax_deed_sales/
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scrapers import tax_deed_sales as tds

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "tax_deed_sales"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


class FakeFetch:
    def __init__(self, routes: dict):
        self.routes = routes
        self.calls = []

    def __call__(self, url: str, params_or_data: dict) -> str:
        self.calls.append({"url": url, "data": dict(params_or_data)})
        for key, html_name in self.routes.items():
            if key in url:
                return _load(html_name)
        return _load("listings_empty.html")


def _assert(label, cond, detail=""):
    if cond:
        print(f"  [PASS] {label}")
        return True
    print(f"  [FAIL] {label}  --  {detail}")
    return False


# -------------------------------------------------------------------------
# Unit tests — fetch_listings
# -------------------------------------------------------------------------

def test_listings_typical():
    fake = FakeFetch({"taxdeed": "listings_typical.html"})
    session = tds.TaxDeedSession(fetch_fn=fake)
    listings = session.fetch_listings()

    ok = True
    ok &= _assert("3 listings parsed", len(listings) == 3,
                  f"got {len(listings)}")
    if len(listings) >= 3:
        ok &= _assert("listing 0: parcel_id",
                      listings[0]["raw_payload"]["parcel_id"] == "000123-0000")
        ok &= _assert("listing 0: address contains MAIN ST",
                      "MAIN" in listings[0]["raw_payload"]["address"])
        ok &= _assert("listing 0: opening_bid",
                      "$50,000" in listings[0]["raw_payload"]["opening_bid"])
        ok &= _assert("listing 1: parcel_id 000456-0000",
                      listings[1]["raw_payload"]["parcel_id"] == "000456-0000")
        ok &= _assert("listing 1: address OAK AVE",
                      "OAK" in listings[1]["raw_payload"]["address"])
    ok &= _assert("every listing has source_id tax_deed_sales",
                  all(r["source_id"] == "tax_deed_sales" for r in listings))
    ok &= _assert("every listing has raw_record_id",
                  all(r["raw_record_id"].startswith("raw_") for r in listings))
    ok &= _assert("high confidence with parcel_id",
                  all(r["parser_confidence"] >= 85 for r in listings))
    return 0 if ok else 1


def test_listings_empty():
    fake = FakeFetch({"taxdeed": "listings_empty.html"})
    session = tds.TaxDeedSession(fetch_fn=fake)
    listings = session.fetch_listings()
    return 0 if _assert("empty listings yields 0", len(listings) == 0) else 1


def test_listings_missing_fields():
    fake = FakeFetch({"taxdeed": "listings_missing_fields.html"})
    session = tds.TaxDeedSession(fetch_fn=fake)
    listings = session.fetch_listings()

    ok = True
    ok &= _assert("2 listings from missing_fields fixture", len(listings) == 2,
                  f"got {len(listings)}")
    if len(listings) >= 2:
        ok &= _assert("first: parcel_id 000321-0000",
                      listings[0]["raw_payload"]["parcel_id"] == "000321-0000")
        ok &= _assert("first: confidence 85",
                      listings[0]["parser_confidence"] == 85)
        ok &= _assert("second: empty parcel_id lowers confidence",
                      listings[1]["parser_confidence"] == 60)
    return 0 if ok else 1


# -------------------------------------------------------------------------
# Merge with prior tests
# -------------------------------------------------------------------------

def _make_raw(rid, payload=None):
    return {
        "raw_record_id": rid,
        "source_id": "tax_deed_sales",
        "raw_payload": payload or {"parcel_id": "000123-0000"},
        "source_fetched_at": "2026-06-02T12:00:00Z",
        "first_seen_at": "2026-06-02T12:00:00Z",
        "last_seen_at": "2026-06-02T12:00:00Z",
    }


def test_merge_new():
    merged = tds.merge_with_prior([_make_raw("raw_a")], {})
    return 0 if _assert("merge new: NEW_RECORD",
                        merged[0]["change_status"] == "NEW_RECORD") else 1


def test_merge_same():
    rec = _make_raw("raw_a")
    prior = {rec["raw_record_id"]: dict(rec)}
    merged = tds.merge_with_prior([rec], prior)
    return 0 if _assert("merge same: SAME",
                        merged[0]["change_status"] == "SAME") else 1


def test_merge_updated():
    old = _make_raw("raw_a", {"parcel_id": "000123-0000", "opening_bid": "$50k"})
    new = _make_raw("raw_a", {"parcel_id": "000123-0000", "opening_bid": "$55k"})
    prior = {old["raw_record_id"]: dict(old)}
    merged = tds.merge_with_prior([new], prior)
    return 0 if _assert("merge updated: UPDATED",
                        merged[0]["change_status"] == "UPDATED") else 1


def test_merge_disappeared():
    old_a = _make_raw("raw_a")
    old_b = _make_raw("raw_b")
    prior = {old_a["raw_record_id"]: old_a, old_b["raw_record_id"]: old_b}
    merged = tds.merge_with_prior([dict(old_a)], prior)
    disappeared = [r for r in merged if r["change_status"] == "DISAPPEARED"]
    return 0 if _assert("merge: 1 DISAPPEARED", len(disappeared) == 1) else 1


# -------------------------------------------------------------------------
# Integration test — run()
# -------------------------------------------------------------------------

def test_run_writes_jsonl():
    fake = FakeFetch({"taxdeed": "listings_typical.html"})

    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "tax_deed_sales.jsonl"
        stats = tds.run(output_path=out, fetch_fn=fake)

        ok = True
        ok &= _assert("run: current_count == 3",
                      stats["current_count"] == 3,
                      f"got {stats['current_count']}")
        ok &= _assert("run: output_path set", stats["output_path"] == str(out))
        ok &= _assert("run: jsonl exists", out.exists() and out.stat().st_size > 0)

        lines = out.read_text(encoding="utf-8").strip().split("\n")
        first = json.loads(lines[0])
        ok &= _assert("run: first record source_id",
                      first.get("source_id") == "tax_deed_sales")
        return 0 if ok else 1


# -------------------------------------------------------------------------
# Main
# -------------------------------------------------------------------------

def main() -> int:
    print("[adapter test] scrapers/tax_deed_sales.py")
    rcs = [
        test_listings_typical(),
        test_listings_empty(),
        test_listings_missing_fields(),
        test_merge_new(),
        test_merge_same(),
        test_merge_updated(),
        test_merge_disappeared(),
        test_run_writes_jsonl(),
    ]
    failures = sum(1 for rc in rcs if rc != 0)
    print(f"\nfailures: {failures} of {len(rcs)}")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
