"""
Adapter test for scrapers/tax_collector.py (Duval Tax Collector / LienHub).

Uses injectable fetch_fn to return fixture HTML.

Fixtures: scaffold/tests/fixtures/tax_collector/
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scrapers import tax_collector as tc

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "tax_collector"


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
        return _load("lienhub_empty.html")


def _assert(label, cond, detail=""):
    if cond:
        print(f"  [PASS] {label}")
        return True
    print(f"  [FAIL] {label}  --  {detail}")
    return False


def test_parse_lienhub_typical():
    html = _load("lienhub_typical.html")
    session = tc.TaxCollectorSession()
    records = session._parse_lienhub_listings(html)

    ok = True
    ok &= _assert("2 auction listings parsed", len(records) == 2, f"got {len(records)}")
    if len(records) >= 2:
        ok &= _assert("listing 0: parcel_id", records[0]["parcel_id"] == "000123-0000")
        ok &= _assert("listing 0: address has MAIN",
                      "MAIN" in records[0]["situs_address"])
        ok &= _assert("listing 0: opening_bid", records[0]["opening_bid"] == "$5,250.00")
        ok &= _assert("listing 0: auction_date", records[0]["auction_date"] == "06/15/2026")
        ok &= _assert("listing 1: parcel_id", records[1]["parcel_id"] == "000456-0000")
    return 0 if ok else 1


def test_parse_lienhub_empty():
    html = _load("lienhub_empty.html")
    session = tc.TaxCollectorSession()
    records = session._parse_lienhub_listings(html)
    return 0 if _assert("empty yields 0 records", len(records) == 0) else 1


def test_merge_new():
    merged = tc.merge_with_prior(
        [{"raw_record_id": "raw_a", "source_id": "tax_collector", "raw_payload": {},
          "source_fetched_at": "", "first_seen_at": "", "last_seen_at": ""}], {})
    return 0 if _assert("merge new: NEW_RECORD",
                        merged[0]["change_status"] == "NEW_RECORD") else 1


def test_merge_same():
    rec = {"raw_record_id": "raw_a", "source_id": "tax_collector",
           "raw_payload": {}, "source_fetched_at": "", "first_seen_at": "",
           "last_seen_at": ""}
    prior = {rec["raw_record_id"]: dict(rec)}
    merged = tc.merge_with_prior([rec], prior)
    return 0 if _assert("merge same: SAME",
                        merged[0]["change_status"] == "SAME") else 1


def test_run_writes_jsonl():
    fake = FakeFetch({"lienhub.com": "lienhub_typical.html"})
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "tax_collector.jsonl"
        stats = tc.run(output_path=out, fetch_fn=fake)

        ok = True
        ok &= _assert("run: current_count == 2",
                      stats["current_count"] == 2, f"got {stats['current_count']}")
        ok &= _assert("run: output_path set", stats["output_path"] == str(out))
        ok &= _assert("run: jsonl exists", out.exists() and out.stat().st_size > 0)

        lines = out.read_text(encoding="utf-8").strip().split("\n")
        first = json.loads(lines[0])
        ok &= _assert("run: first record source_id",
                      first.get("source_id") == "tax_collector")
        return 0 if ok else 1


def test_run_merge_persists():
    fake = FakeFetch({"lienhub.com": "lienhub_typical.html"})
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "tax_collector.jsonl"
        stats1 = tc.run(output_path=out, fetch_fn=fake)
        stats2 = tc.run(output_path=out, fetch_fn=fake)
        ok = True
        ok &= _assert("run #2: no new records",
                      stats2["new_record_count"] == 0,
                      f"got {stats2['new_record_count']}")
        ok &= _assert("run #2: total_after_merge preserved",
                      stats2["total_after_merge"] == stats1["total_after_merge"])
        return 0 if ok else 1


def main() -> int:
    print("[adapter test] scrapers/tax_collector.py")
    rcs = [
        test_parse_lienhub_typical(),
        test_parse_lienhub_empty(),
        test_merge_new(),
        test_merge_same(),
        test_run_writes_jsonl(),
        test_run_merge_persists(),
    ]
    failures = sum(1 for rc in rcs if rc != 0)
    print(f"\nfailures: {failures} of {len(rcs)}")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
