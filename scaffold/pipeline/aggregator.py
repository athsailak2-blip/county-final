"""
aggregator — v5.4.0 staged pipeline, stage 4 (the idempotent §19 aggregator).

STATUS: SCAFFOLD ONLY (v5.4.0 Session 1). Every function in this module is a
signature + contract docstring + `raise NotImplementedError`. No aggregation
logic exists yet — it is built in Session 4. The behavioral spec these
functions must satisfy lives in scaffold/tests/v5_4_0_pending/.

Contracts:
  - knowledge_base/architecture/18_signal_aggregation_contract.md
  - knowledge_base/architecture/19_aggregator_idempotency_rule.md

This stage reads the stable per-source base files (`<source>_leads_base.json`)
and produces `matched_leads.json`, applying:

  - the §18.B aggregation key to group records into signals;
  - the §18.C within-group merge contract (count, instrument_numbers,
    source_urls, evidence_ids, earliest/latest_recorded_date,
    recorded_date_range);
  - the §18.D cross-source rule (same key from different sources collapses);
  - the §18.F anti-collapse rule (distinct signal_type never merges).

The §19 idempotency rule is the load-bearing invariant of this module:

  - the aggregator reads ONLY from `*_leads_base.json` files (§19.C);
  - the aggregator NEVER reads its own output (`matched_leads.json` or
    `dashboard/data.json`) as input — doing so re-aggregates prior leads and
    inflates counts on every run (§19.B);
  - running the aggregator twice on the same base files MUST produce
    byte-identical `matched_leads.json` (§19.D);
  - the aggregator self-checks idempotency before deploy (§19.E).

This module is universal framework code: the `<source>_leads_base.json`
naming convention and the aggregation rules are universal; the per-county
base-file inventory is read from config/counties/<county_slug>.json
(`pipeline.base_files`). No county / state / vendor literal appears here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Sequence


def aggregate(
    base_file_paths: Sequence[Path],
    *,
    output_path: Optional[Path] = None,
) -> list[dict]:
    """Aggregate per-source base files into matched-lead records (§18 / §19).

    Reads each `<source>_leads_base.json` in `base_file_paths`, groups the
    leads-base records by the §18.B aggregation key, merges each group per
    §18.C / §18.D, and returns the matched-lead records. When `output_path`
    is given, also writes `matched_leads.json` there.

    HARD CONTRACT (§19.C): this function reads ONLY `*_leads_base.json`
    inputs. It MUST refuse — raise ValueError — if any path in
    `base_file_paths` is `matched_leads.json`, `dashboard/data.json`, or
    otherwise equal to `output_path`. Reading its own output re-aggregates
    prior leads and inflates counts on every run (§19.B).

    Args:
        base_file_paths: Paths to the stable per-source
            `<source>_leads_base.json` files. The ONLY permitted input.
        output_path: Where to write `matched_leads.json`. When None, the
            result is returned without being written.

    Returns:
        A list of matched-lead records conforming to
        matched_lead_record.schema.json.

    Raises:
        ValueError: if any input path is the aggregator's own output
            (§19.C self-input prohibition).
        NotImplementedError: always — v5.4.0 Session 1 scaffold.
    """
    raise NotImplementedError(
        "aggregator.aggregate is a v5.4.0 Session 1 scaffold stub; the §18/§19 "
        "aggregation logic is built in Session 4."
    )


def merge_signal_group(base_records: Sequence[dict]) -> dict:
    """Merge base records that share an aggregation key into one signal (§18.C).

    Given N leads-base records that share the full §18.B aggregation key, the
    merged signal carries (§18.C):

      - `count` = N;
      - `instrument_numbers` = distinct instrument numbers across the group;
      - `source_urls` = distinct source proof URLs;
      - `evidence_ids` = distinct evidence ledger ids;
      - `source_ids` = distinct contributing source ids (§18.D);
      - `earliest_recorded_date` / `latest_recorded_date` = the date bounds;
      - `recorded_date_range` = the (earliest, latest) pair.

    §18.E legitimacy test: `count` is legitimate stacking only when it equals
    the number of distinct `instrument_numbers`. A `count` greater than the
    distinct instrument count is a dedup failure and must be surfaced, not
    silently emitted.

    Args:
        base_records: Leads-base records that share one aggregation key.

    Returns:
        One signal-group dict conforming to the `signals[]` item shape in
        matched_lead_record.schema.json.

    Raises:
        NotImplementedError: always — v5.4.0 Session 1 scaffold.
    """
    raise NotImplementedError(
        "aggregator.merge_signal_group is a v5.4.0 Session 1 scaffold stub; "
        "the §18.C within-group merge is built in Session 4."
    )


def idempotency_self_check(
    base_file_paths: Sequence[Path],
    *,
    output_path: Path,
) -> bool:
    """Run the §19.E idempotency self-check.

    After writing `matched_leads.json`, the aggregator runs once more in
    dry-run mode and compares output byte-for-byte against the written file
    (§19.D / §19.E). If the two differ without intervening base-file changes,
    the aggregator is non-idempotent: this function returns False and the
    build MUST refuse to deploy.

    Args:
        base_file_paths: The same per-source base files passed to `aggregate`.
        output_path: The `matched_leads.json` written by the prior
            `aggregate` call.

    Returns:
        True when the second run is byte-identical to `output_path`
        (idempotent); False when it differs (non-idempotent — refuse deploy).

    Raises:
        NotImplementedError: always — v5.4.0 Session 1 scaffold.
    """
    raise NotImplementedError(
        "aggregator.idempotency_self_check is a v5.4.0 Session 1 scaffold "
        "stub; the §19.E self-check is built in Session 4."
    )
