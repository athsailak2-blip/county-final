"""
Adapter test for scrapers/official_records.py (Duval Clerk OnCore).

Uses injectable fetch_fn to return fixture HTML, exercising the adapter
end-to-end without network access. Per engineering/05_verification_and_rollback.md
"Scraper fixture requirement".

Fixtures: scaffold/tests/fixtures/official_records/
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scrapers import official_records as ors

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "official_records"


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
        return _load("empty_results.html")


def _assert(label, cond, detail=""):
    if cond:
        print(f"  [PASS] {label}")
        return True
    print(f"  [FAIL] {label}  --  {detail}")
    return False


# -------------------------------------------------------------------------
# Unit tests — _parse_results_table
# -------------------------------------------------------------------------

def test_parse_happy_mixed_day():
    html = _load("happy_mixed_day.html")
    records = ors.OnCoreSession()._parse_results_table(html, "2026-06-01")

    ok = True
    ok &= _assert("3 records parsed from happy_mixed_day", len(records) == 3,
                  f"got {len(records)}")
    if len(records) >= 3:
        r0, r1, r2 = records[0], records[1], records[2]
        ok &= _assert("record 0: warranty deed doc_number",
                      r0["raw_payload"]["doc_number"] == "202612340001")
        ok &= _assert("record 0: doc_type WARRANTY DEED",
                      r0["raw_payload"]["doc_type"] == "WARRANTY DEED")
        ok &= _assert("record 0: grantor SMITH",
                      "SMITH" in r0["raw_payload"]["grantor"])
        ok &= _assert("record 0: consideration 350000",
                      r0["raw_payload"]["consideration"] == "350000.00")
        ok &= _assert("record 1: mortgage",
                      r1["raw_payload"]["doc_type"] == "MORTGAGE")
        ok &= _assert("record 1: consideration 280000",
                      r1["raw_payload"]["consideration"] == "280000.00")
        ok &= _assert("record 2: LIS PENDENS lead doc_type",
                      r2["raw_payload"]["doc_type"] == "LIS PENDENS")
        ok &= _assert("record 2: carries case_number",
                      r2["raw_payload"]["case_number"] == "16-2026-CA-001234")
    ok &= _assert("every record has source_id official_records",
                  all(r["source_id"] == "official_records" for r in records))
    ok &= _assert("every record has raw_record_id starting with raw_",
                  all(r["raw_record_id"].startswith("raw_") for r in records))
    ok &= _assert("every record has parser_confidence",
                  all(r.get("parser_confidence", 0) > 0 for r in records))
    return 0 if ok else 1


def test_parse_empty_results():
    html = _load("empty_results.html")
    records = ors.OnCoreSession()._parse_results_table(html, "2026-06-01")
    return 0 if _assert("empty results yields 0 records", len(records) == 0) else 1


def test_parse_no_table():
    html = _load("no_table.html")
    records = ors.OnCoreSession()._parse_results_table(html, "2026-06-01")
    return 0 if _assert("no table yields 0 records", len(records) == 0) else 1


def test_parse_partial_data():
    html = _load("partial_data.html")
    records = ors.OnCoreSession()._parse_results_table(html, "2026-06-02")

    ok = True
    ok &= _assert("partial data yields 2 records", len(records) == 2,
                  f"got {len(records)}")
    if len(records) >= 2:
        r0, r1 = records[0], records[1]
        ok &= _assert("JUDGMENT doc_type preserved",
                      r0["raw_payload"]["doc_type"] == "JUDGMENT")
        ok &= _assert("TAX LIEN doc_type preserved",
                      r1["raw_payload"]["doc_type"] == "TAX LIEN")
        ok &= _assert("empty grantor handled as empty string",
                      r1["raw_payload"]["grantor"] == "")
        ok &= _assert("record_date from param not HTML",
                      r0["raw_payload"]["record_date"] == "2026-06-02")
    return 0 if ok else 1


def test_parse_deterministic_record_id():
    html = _load("happy_mixed_day.html")
    records1 = ors.OnCoreSession()._parse_results_table(html, "2026-06-01")
    records2 = ors.OnCoreSession()._parse_results_table(html, "2026-06-01")
    ids1 = [r["raw_record_id"] for r in records1]
    ids2 = [r["raw_record_id"] for r in records2]
    return 0 if _assert("raw_record_ids are deterministic", ids1 == ids2) else 1


# -------------------------------------------------------------------------
# Merge with prior tests
# -------------------------------------------------------------------------

def _make_raw(rid, payload):
    return {
        "raw_record_id": rid,
        "source_id": "official_records",
        "raw_payload": payload,
        "source_fetched_at": "2026-06-02T12:00:00Z",
        "first_seen_at": "2026-06-02T12:00:00Z",
        "last_seen_at": "2026-06-02T12:00:00Z",
    }


def test_merge_new_records():
    current = [
        _make_raw("raw_a", {"doc_number": "1", "doc_type": "DEED"}),
        _make_raw("raw_b", {"doc_number": "2", "doc_type": "MORTGAGE"}),
    ]
    merged = ors.merge_with_prior(current, {})
    ok = True
    ok &= _assert("merge: 2 records with no prior", len(merged) == 2)
    ok &= _assert("merge: both are NEW_RECORD",
                  all(r["change_status"] == "NEW_RECORD" for r in merged))
    return 0 if ok else 1


def test_merge_same_records():
    rec = _make_raw("raw_a", {"doc_number": "1"})
    prior = {rec["raw_record_id"]: dict(rec)}
    merged = ors.merge_with_prior([rec], prior)
    ok = True
    ok &= _assert("merge SAME: 1 record", len(merged) == 1)
    ok &= _assert("merge SAME: status is SAME",
                  merged[0]["change_status"] == "SAME")
    return 0 if ok else 1


def test_merge_updated_records():
    old = _make_raw("raw_a", {"doc_number": "1", "doc_type": "DEED"})
    new = _make_raw("raw_a", {"doc_number": "1", "doc_type": "WARRANTY DEED"})
    prior = {old["raw_record_id"]: dict(old)}
    merged = ors.merge_with_prior([new], prior)
    return 0 if _assert("merge UPDATED: status changed",
                        merged[0]["change_status"] == "UPDATED") else 1


def test_merge_disappeared_records():
    old_a = _make_raw("raw_a", {"doc_number": "1"})
    old_b = _make_raw("raw_b", {"doc_number": "2"})
    prior = {old_a["raw_record_id"]: old_a, old_b["raw_record_id"]: old_b}
    current = [dict(old_a)]
    merged = ors.merge_with_prior(current, prior)
    ok = True
    ok &= _assert("merge DISAPPEARED: 2 total records", len(merged) == 2)
    disappeared = [r for r in merged if r["change_status"] == "DISAPPEARED"]
    ok &= _assert("merge DISAPPEARED: 1 disappeared", len(disappeared) == 1)
    ok &= _assert("merge DISAPPEARED: remaining is NEW_RECORD/SAME",
                  any(r["change_status"] in ("NEW_RECORD", "SAME")
                      for r in merged if r not in disappeared))
    return 0 if ok else 1


# -------------------------------------------------------------------------
# Integration test — run() with FakeFetch
# -------------------------------------------------------------------------

def test_run_writes_jsonl():
    fake = FakeFetch({
        "or.duvalclerk.com": "happy_mixed_day.html",
        "Search.aspx": "happy_mixed_day.html",
    })

    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "official_records.jsonl"
        stats = ors.run(output_path=out, fetch_fn=fake,
                        start_date=__import__("datetime").date(2026, 6, 1),
                        end_date=__import__("datetime").date(2026, 6, 1))

        ok = True
        ok &= _assert("run: stats output_path set",
                      stats["output_path"] == str(out))
        ok &= _assert("run: days_scraped == 1",
                      stats["days_scraped"] == 1)
        ok &= _assert("run: current_count > 0",
                      stats["current_count"] > 0)
        ok &= _assert("run: total_after_merge > 0",
                      stats["total_after_merge"] > 0)
        ok &= _assert("run: jsonl file exists",
                      out.exists() and out.stat().st_size > 0)

        lines = out.read_text(encoding="utf-8").strip().split("\n")
        ok &= _assert("run: jsonl has at least 1 line", len(lines) >= 1)
        first = json.loads(lines[0])
        ok &= _assert("run: first record has source_id official_records",
                      first.get("source_id") == "official_records")
        return 0 if ok else 1


def test_run_merge_persists():
    fake = FakeFetch({
        "or.duvalclerk.com": "happy_mixed_day.html",
        "Search.aspx": "happy_mixed_day.html",
    })

    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "official_records.jsonl"
        stats1 = ors.run(output_path=out, fetch_fn=fake,
                         start_date=__import__("datetime").date(2026, 6, 1),
                         end_date=__import__("datetime").date(2026, 6, 1))
        stats2 = ors.run(output_path=out, fetch_fn=fake,
                         start_date=__import__("datetime").date(2026, 6, 1),
                         end_date=__import__("datetime").date(2026, 6, 1))

        ok = True
        ok &= _assert("run #2: total same as run #1",
                      stats2["total_after_merge"] == stats1["total_after_merge"],
                      f"#1={stats1['total_after_merge']} #2={stats2['total_after_merge']}")
        ok &= _assert("run #2: no new records (duplicate data)",
                      stats2["new_record_count"] == 0,
                      f"got {stats2['new_record_count']} new records")
        return 0 if ok else 1


# -------------------------------------------------------------------------
# Main
# -------------------------------------------------------------------------

def main() -> int:
    print("[adapter test] scrapers/official_records.py")
    rcs = [
        test_parse_happy_mixed_day(),
        test_parse_empty_results(),
        test_parse_no_table(),
        test_parse_partial_data(),
        test_parse_deterministic_record_id(),
        test_merge_new_records(),
        test_merge_same_records(),
        test_merge_updated_records(),
        test_merge_disappeared_records(),
        test_run_writes_jsonl(),
        test_run_merge_persists(),
    ]
    failures = sum(1 for rc in rcs if rc != 0)
    print(f"\nfailures: {failures} of {len(rcs)}")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
