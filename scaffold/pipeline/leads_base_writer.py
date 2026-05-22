"""
leads_base_writer — v5.4.0 staged pipeline, stage 3 (the base-file writer).

STATUS: SCAFFOLD ONLY (v5.4.0 Session 1). Every function in this module is a
signature + contract docstring + `raise NotImplementedError`. No writer logic
exists yet — it is built in Session 3. The behavioral spec these functions
must satisfy lives in scaffold/tests/v5_4_0_pending/.

Contracts:
  - knowledge_base/architecture/18_signal_aggregation_contract.md (the key)
  - knowledge_base/architecture/19_aggregator_idempotency_rule.md (base files)
  - knowledge_base/protocols/02_build_mode_protocol.md §02.4 (writer duties)
  - knowledge_base/architecture/13_lead_origination_contract.md §13.14
    (parcel_resolution_status / enrichment_status decoupling)

This stage takes debtor-resolved records (debtor_resolved_record.schema.json),
stamps each with its §18.B aggregation key and resolved signal_type, attaches
the §13.14 status pair (parcel_resolution_status, enrichment_status), and
writes the stable per-source base file `<source>_leads_base.json`
(leads_base_record.schema.json).

§19.C makes the base file the load-bearing artifact: it is the ONLY input the
aggregator reads. Each base file is per-source and stable; the aggregator
re-derives `matched_leads.json` from the base files on every run, never from
its own previous output.

Every base record MUST carry `source_url`, `instrument_number`,
`recorded_date`, and `evidence_ids` (§02.4). A lead is NEVER dropped because
enrichment failed (§13.14).

This module is universal framework code: the `<source>_leads_base.json`
naming convention is universal; the per-county signal_type labels are passed
in at call time. No county / state / vendor literal appears here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence


def build_base_record(
    debtor_resolved_record: dict,
    *,
    signal_type_labels: dict,
) -> dict:
    """Build one leads-base record from a debtor-resolved record (§18 / §13.14).

    The contract:
      - resolve `signal_type` from `canonical_doc_type` via
        `aggregation_key_engine.resolve_signal_type`;
      - compute the §18.B `aggregation_key` via
        `aggregation_key_engine.compute_aggregation_key`;
      - carry forward owner_name, owner_type, filer_entity, review_reason
        from the debtor-resolved record;
      - set `parcel_resolution_status` (§13.14 — REVIEW_REQUIRED carried from
        §17 routing, else RESOLVED / UNRESOLVED) and `enrichment_status`
        independently; never drop a lead for enrichment failure;
      - carry forward source_url, instrument_number, recorded_date, and
        evidence_ids — all mandatory on every base record (§02.4).

    Args:
        debtor_resolved_record: A debtor-resolved record conforming to
            debtor_resolved_record.schema.json.
        signal_type_labels: The per-county canonical_doc_type ->
            display-label map.

    Returns:
        One leads-base record conforming to leads_base_record.schema.json.

    Raises:
        NotImplementedError: always — v5.4.0 Session 1 scaffold.
    """
    raise NotImplementedError(
        "leads_base_writer.build_base_record is a v5.4.0 Session 1 scaffold "
        "stub; base-record assembly is built in Session 3."
    )


def write_leads_base(
    source_id: str,
    base_records: Sequence[dict],
    *,
    output_dir: Path,
) -> Path:
    """Write the stable per-source base file `<source>_leads_base.json`.

    The output file is `<output_dir>/<source_id>_leads_base.json` — the
    §19.C / §19.G naming convention. The file is the stable per-source
    artifact the aggregator reads; the write MUST be deterministic (stable
    key ordering, stable record ordering) so that re-running the writer on
    unchanged inputs produces a byte-identical file, which is what makes the
    downstream §19.D aggregator idempotency invariant achievable.

    A translator / writer MUST NOT modify another source's base file (§02.4).

    Args:
        source_id: The source identifier — the `<source>` in the filename.
        base_records: Leads-base records conforming to
            leads_base_record.schema.json.
        output_dir: Directory the base file is written to.

    Returns:
        The path to the written `<source_id>_leads_base.json` file.

    Raises:
        NotImplementedError: always — v5.4.0 Session 1 scaffold.
    """
    raise NotImplementedError(
        "leads_base_writer.write_leads_base is a v5.4.0 Session 1 scaffold "
        "stub; the base-file writer is built in Session 3."
    )
