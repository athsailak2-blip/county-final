"""
Adapter test for scrapers/foreclosure_sales.py (Duval RealForeclose).

Uses injectable fetch_fn to return fixture HTML, exercising the adapter
end-to-end without network access.

Fixtures: scaffold/tests/fixtures/foreclosure_sales/
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scrapers import foreclosure_sales as fcs

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "foreclosure_sales"


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
        return _load("calendar_empty.html")


def _assert(label, cond, detail=""):
    if cond:
        print(f"  [PASS] {label}")
        return True
    print(f"  [FAIL] {label}  --  {detail}")
    return False


# -------------------------------------------------------------------------
# Unit tests — fetch_calendar
# -------------------------------------------------------------------------

def test_calendar_typical():
    fake = FakeFetch({"realforeclose": "calendar_typical.html"})
    session = fcs.RealForecloseSession(fetch_fn=fake)
    auctions = session.fetch_calendar(month=6, year=2026)

    ok = True
    ok &= _assert("calendar: 3 auction dates", len(auctions) == 3,
                  f"got {len(auctions)}")
    if len(auctions) >= 3:
        ok &= _assert("day 1: active_count=3",
                      auctions[0]["active_count"] == 3)
        ok &= _assert("day 1: total_count=5",
                      auctions[0]["total_count"] == 5)
        ok &= _assert("day 1: sale_time",
                      "11:00 AM" in auctions[0]["sale_time"])
        ok &= _assert("day 2: active_count=2",
                      auctions[1]["active_count"] == 2)
        ok &= _assert("day 3: active_count=0",
                      auctions[2]["active_count"] == 0)
    return 0 if ok else 1


def test_calendar_empty():
    fake = FakeFetch({"realforeclose": "calendar_empty.html"})
    session = fcs.RealForecloseSession(fetch_fn=fake)
    auctions = session.fetch_calendar()
    return 0 if _assert("empty calendar yields 0 auctions",
                        len(auctions) == 0) else 1


def test_calendar_no_fc_date():
    fake = FakeFetch({"realforeclose": "calendar_no_fc_date.html"})
    session = fcs.RealForecloseSession(fetch_fn=fake)
    auctions = session.fetch_calendar()

    ok = True
    ok &= _assert("no-FC day skipped, only 1 auction",
                  len(auctions) == 1,
                  f"got {len(auctions)}")
    if auctions:
        ok &= _assert("only FC day is day 6",
                      auctions[0]["active_count"] == 1)
    return 0 if ok else 1


# -------------------------------------------------------------------------
# Merge with prior tests
# -------------------------------------------------------------------------

def _make_raw(rid):
    return {
        "raw_record_id": rid,
        "source_id": "foreclosure_sales",
        "raw_payload": {"auction_day": "1", "active_count": 3},
        "source_fetched_at": "2026-06-02T12:00:00Z",
        "first_seen_at": "2026-06-02T12:00:00Z",
        "last_seen_at": "2026-06-02T12:00:00Z",
    }


def test_merge_new():
    merged = fcs.merge_with_prior([_make_raw("raw_a")], {})
    return 0 if _assert("merge new: NEW_RECORD",
                        merged[0]["change_status"] == "NEW_RECORD") else 1


def test_merge_same():
    rec = _make_raw("raw_a")
    prior = {rec["raw_record_id"]: dict(rec)}
    merged = fcs.merge_with_prior([rec], prior)
    return 0 if _assert("merge same: SAME",
                        merged[0]["change_status"] == "SAME") else 1


def test_merge_disappeared():
    old_a = _make_raw("raw_a")
    old_b = _make_raw("raw_b")
    prior = {old_a["raw_record_id"]: old_a, old_b["raw_record_id"]: old_b}
    merged = fcs.merge_with_prior([dict(old_a)], prior)
    disappeared = [r for r in merged if r["change_status"] == "DISAPPEARED"]
    return 0 if _assert("merge disappeared: 1 DISAPPEARED",
                        len(disappeared) == 1) else 1


# -------------------------------------------------------------------------
# Integration test — run()
# -------------------------------------------------------------------------

def test_run_writes_jsonl():
    fake = FakeFetch({"realforeclose": "calendar_typical.html"})

    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "foreclosure_sales.jsonl"
        stats = fcs.run(output_path=out, fetch_fn=fake)

        ok = True
        ok &= _assert("run: current_count == 3",
                      stats["current_count"] == 3,
                      f"got {stats['current_count']}")
        ok &= _assert("run: output_path set", stats["output_path"] == str(out))
        ok &= _assert("run: jsonl exists", out.exists() and out.stat().st_size > 0)

        lines = out.read_text(encoding="utf-8").strip().split("\n")
        first = json.loads(lines[0])
        ok &= _assert("run: first record source_id",
                      first.get("source_id") == "foreclosure_sales")
        return 0 if ok else 1


# -------------------------------------------------------------------------
# Main
# -------------------------------------------------------------------------

def main() -> int:
    print("[adapter test] scrapers/foreclosure_sales.py")
    rcs = [
        test_calendar_typical(),
        test_calendar_empty(),
        test_calendar_no_fc_date(),
        test_merge_new(),
        test_merge_same(),
        test_merge_disappeared(),
        test_run_writes_jsonl(),
    ]
    failures = sum(1 for rc in rcs if rc != 0)
    print(f"\nfailures: {failures} of {len(rcs)}")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
