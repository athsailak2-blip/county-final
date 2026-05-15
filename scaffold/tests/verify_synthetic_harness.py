"""
Phase 1 verifier — asserts that `pipeline/build_leads.py --synthetic`
produces output matching `scaffold/data/synthetic_expectations.json`.

The verifier:

  1. Runs the pipeline against the synthetic fixtures.
  2. Loads the resulting `data/leads_synthetic.json`.
  3. Asserts every entry in synthetic_expectations.json:
     - lead_total (exact)
     - pattern_counts (exact, every key present with stated count)
     - attribute_counts (exact, every key present with stated count)
     - stack_depth_distribution (sum = lead_total, all keys present)
     - score_tier_distribution_min_each (per-key minimum)
     - deal_path_distribution_min_each (per-key minimum)
     - specific_parcel_expectations (per-parcel exact / min / inclusion)
     - quality_metrics_expectations
     - dashboard_render_expectations (the JSON-side projections; live
       browser checks defer to Phase 6's verify_live.py)
  4. Prints a pass/fail summary and exits 0 (pass) or 1 (fail).

This file is the Phase 1 acceptance gate. REVIEW_GATE_2 (end of Phase 1)
cannot be signed off until this verifier exits 0.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SYNTH_DATA = REPO_ROOT / "scaffold" / "data"
EXPECTATIONS_PATH = SYNTH_DATA / "synthetic_expectations.json"
PIPELINE = REPO_ROOT / "scaffold" / "pipeline" / "build_leads.py"
LEADS_PATH = REPO_ROOT / "data" / "leads_synthetic.json"


def _run_pipeline() -> int:
    completed = subprocess.run(
        [sys.executable, str(PIPELINE), "--synthetic"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        sys.stdout.write(completed.stdout)
        sys.stderr.write(completed.stderr)
    return completed.returncode


# ---------------------------------------------------------------------
# Assertions
# ---------------------------------------------------------------------

class Verifier:
    def __init__(self) -> None:
        self.passes: list = []
        self.fails: list = []

    def expect(self, label: str, ok: bool, detail: str = "") -> None:
        if ok:
            self.passes.append(label)
        else:
            self.fails.append((label, detail))

    def expect_eq(self, label: str, actual, expected) -> None:
        self.expect(label, actual == expected, f"actual={actual!r} expected={expected!r}")

    def expect_ge(self, label: str, actual, threshold) -> None:
        self.expect(label, actual >= threshold, f"actual={actual!r} threshold={threshold!r}")

    def expect_le(self, label: str, actual, threshold) -> None:
        self.expect(label, actual <= threshold, f"actual={actual!r} threshold={threshold!r}")

    def expect_contains(self, label: str, container, needle) -> None:
        self.expect(label, needle in container, f"{needle!r} not in {container!r}")

    def expect_not_contains(self, label: str, container, needle) -> None:
        self.expect(label, needle not in container, f"{needle!r} should not be in {container!r}")


def run() -> int:
    rc = _run_pipeline()
    if rc != 0:
        print(f"[FAIL] pipeline exited with code {rc}")
        return 1

    if not LEADS_PATH.exists():
        print(f"[FAIL] pipeline did not produce {LEADS_PATH}")
        return 1

    payload = json.loads(LEADS_PATH.read_text(encoding="utf-8"))
    expected = json.loads(EXPECTATIONS_PATH.read_text(encoding="utf-8"))

    v = Verifier()

    # ---- aggregate counts ----
    v.expect_eq("lead_total exact", payload["lead_total"], expected["lead_total"])

    pat_counts = payload.get("pattern_counts", {})
    for key, count in expected["pattern_counts"].items():
        v.expect_eq(f"pattern_counts[{key}] exact",
                    pat_counts.get(key, 0), count)

    attr_counts = payload.get("attribute_counts", {})
    for key, count in expected["attribute_counts"].items():
        v.expect_eq(f"attribute_counts[{key}] exact",
                    attr_counts.get(key, 0), count)

    sdd = payload.get("stack_depth_distribution", {})
    v.expect_eq("stack_depth_distribution sum == lead_total",
                sum(sdd.values()), expected["lead_total"])
    for key in expected["stack_depth_distribution"]:
        v.expect(f"stack_depth_distribution[{key}] present",
                 key in sdd,
                 f"missing key {key}; got {sorted(sdd)}")

    # score tier minima
    std = payload.get("score_tier_distribution", {})
    for tier, minimum in expected["score_tier_distribution_min_each"].items():
        if minimum == 0:
            v.expect_le(f"score_tier_distribution[{tier}] == 0",
                        std.get(tier, 0), 0)
        else:
            v.expect_ge(f"score_tier_distribution[{tier}] >= {minimum}",
                        std.get(tier, 0), minimum)

    # deal path minima
    dpd = payload.get("deal_path_distribution", {})
    for path, minimum in expected["deal_path_distribution_min_each"].items():
        v.expect_ge(f"deal_path_distribution[{path}] >= {minimum}",
                    dpd.get(path, 0), minimum)

    # ---- per-parcel ----
    rows_by_pid = {r["primary_parcel_id"]: r for r in payload["records"]}
    for pid, spec in expected["specific_parcel_expectations"].items():
        row = rows_by_pid.get(pid)
        if not row:
            v.expect(f"{pid} present in records[]", False, f"no row for {pid}")
            continue

        if "stack_depth" in spec:
            v.expect_eq(f"{pid} stack_depth", row["stack_depth"], spec["stack_depth"])
        if "patterns" in spec:
            v.expect_eq(
                f"{pid} stack_contrib_patterns equal",
                row.get("stack_contrib_patterns"),
                spec["patterns"],
            )
        if "primary_deal_path" in spec:
            actual_primary = (row.get("display_deal_paths") or [None])[0]
            v.expect_eq(
                f"{pid} primary_deal_path",
                actual_primary,
                spec["primary_deal_path"],
            )
        if "deal_path_must_include" in spec:
            for path in spec["deal_path_must_include"]:
                v.expect_contains(
                    f"{pid} deal_paths contains {path}",
                    row.get("display_deal_paths", []),
                    path,
                )
        if "deal_path_must_NOT_include" in spec:
            for path in spec["deal_path_must_NOT_include"]:
                v.expect_not_contains(
                    f"{pid} deal_paths does NOT contain {path}",
                    row.get("display_deal_paths", []),
                    path,
                )
        if "score_min" in spec:
            v.expect_ge(f"{pid} score >= {spec['score_min']}",
                        row["display_score"], spec["score_min"])
        if "tier" in spec:
            wanted = spec["tier"]
            actual = row["display_tier"]
            if wanted == "Strong-or-Hot":
                v.expect(f"{pid} tier in (Strong, Hot)",
                         actual in ("Strong", "Hot"),
                         f"got {actual!r}")
            elif wanted == "Hot":
                v.expect_eq(f"{pid} tier == Hot", actual, "Hot")
            else:
                v.expect_eq(f"{pid} tier == {wanted}", actual, wanted)

    # ---- quality metrics ----
    qm = payload.get("quality_metrics", {})
    qme = expected.get("quality_metrics_expectations", {})
    if "source_verification_rate" in qme:
        v.expect_eq("quality_metrics.source_verification_rate",
                    qm.get("source_verification_rate"), qme["source_verification_rate"])
    if "field_completeness_rate_min" in qme:
        v.expect_ge("quality_metrics.field_completeness_rate >= min",
                    qm.get("field_completeness_rate", 0),
                    qme["field_completeness_rate_min"])
    if "match_confidence_avg_min" in qme:
        v.expect_ge("quality_metrics.match_confidence_avg >= min",
                    qm.get("match_confidence_avg", 0),
                    qme["match_confidence_avg_min"])
    if "parser_confidence_avg_min" in qme:
        v.expect_ge("quality_metrics.parser_confidence_avg >= min",
                    qm.get("parser_confidence_avg", 0),
                    qme["parser_confidence_avg_min"])
    if "source_url_coverage" in qme:
        v.expect_eq("quality_metrics.source_url_coverage",
                    qm.get("source_url_coverage"), qme["source_url_coverage"])
    if "dedupe_ran" in qme:
        v.expect_eq("quality_metrics.dedupe_ran", qm.get("dedupe_ran"), qme["dedupe_ran"])
    if "unsupported_claim_count" in qme:
        v.expect_eq("quality_metrics.unsupported_claim_count",
                    qm.get("unsupported_claim_count"), qme["unsupported_claim_count"])
    if "hallucination_risk_avg_max" in qme:
        v.expect_le("quality_metrics.hallucination_risk_avg <= max",
                    qm.get("hallucination_risk_avg", 100),
                    qme["hallucination_risk_avg_max"])

    # ---- dashboard render expectations (JSON-side, not browser) ----
    dre = expected.get("dashboard_render_expectations", {})
    if "lead_row_count" in dre:
        v.expect_eq("records[] length matches dashboard_render_expectations.lead_row_count",
                    len(payload["records"]), dre["lead_row_count"])
    if "stat_tile_total" in dre:
        v.expect_eq("lead_total matches dashboard_render_expectations.stat_tile_total",
                    payload["lead_total"], dre["stat_tile_total"])
    if dre.get("all_pattern_chips_render") is True:
        for p in expected["pattern_counts"]:
            v.expect(f"chip eligible for pattern {p}",
                     p in payload.get("pattern_counts", {}),
                     f"pattern {p} missing from chip source")
    if dre.get("all_attribute_chips_render") is True:
        for a in expected["attribute_counts"]:
            v.expect(f"chip eligible for attribute {a}",
                     a in payload.get("attribute_counts", {}),
                     f"attribute {a} missing from chip source")
    if dre.get("all_deal_path_chips_render") is True:
        for d in expected["deal_path_distribution_min_each"]:
            v.expect(f"chip eligible for deal_path {d}",
                     d in payload.get("deal_path_distribution", {}),
                     f"deal_path {d} missing from chip source")

    if "csv_header_columns_min" in dre:
        # The CSV column list lives in dashboard.js; we proxy by checking
        # the JSON has enough projection fields to drive at least N CSV
        # columns. The dashboard's CSV_COLUMNS list is the source of truth
        # for the browser-side test (Phase 6).
        sample = payload["records"][0] if payload["records"] else {}
        v.expect_ge("dashboard projection fields >= csv_header_columns_min",
                    len(sample.keys()), dre["csv_header_columns_min"] - 7)
        # -7 because 7 CSV columns come from top-level payload, not row.

    # ---- print summary ----
    print(f"PASS: {len(v.passes)}")
    print(f"FAIL: {len(v.fails)}")
    if v.fails:
        print("---- failures ----")
        for label, detail in v.fails:
            print(f"  [FAIL] {label}  --  {detail}")
        return 1
    print("Phase 1 synthetic harness verification PASSED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
