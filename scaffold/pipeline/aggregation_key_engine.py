"""
aggregation_key_engine — v5.4.0 staged pipeline, the §18 aggregation key.

STATUS: SCAFFOLD ONLY (v5.4.0 Session 1). Every function in this module is a
signature + contract docstring + `raise NotImplementedError`. No key logic
exists yet — it is built in Session 3. The behavioral spec these functions
must satisfy lives in scaffold/tests/v5_4_0_pending/.

Contract: knowledge_base/architecture/18_signal_aggregation_contract.md.

This engine computes the §18.B aggregation key — the tuple
`(parcel_id, canonical_doc_type, signal_type)` — that is the dedup boundary
for signal aggregation. Records sharing the full key collapse into one signal
with a count badge; records differing in any component stay distinct (the
§18.F anti-collapse rule). The leads-base writer stamps each base record with
its key; the aggregator groups by it.

This module is universal framework code: the aggregation-key shape and the
anti-collapse rule are universal; the per-county signal_type display labels
are passed in at call time (config/counties/<county_slug>.json
`signal_type_labels`). No county / state / vendor literal appears here.
"""

from __future__ import annotations

from typing import Optional


def resolve_signal_type(
    canonical_doc_type: str,
    *,
    signal_type_labels: dict,
) -> str:
    """Resolve the operator-facing signal_type for a canonical doc type (§18.B).

    `signal_type` is the operator-facing semantic category (e.g. "Hospital
    Lien", "Estate-Titled Property", "Federal Tax Lien"). §18.I locates the
    per-county display labels in config/counties/<county_slug>.json under
    `signal_type_labels`.

    NOTE (contract finding F-4): §18.B places signal_type in the aggregation
    key alongside canonical_doc_type, but §18.I describes signal_type as a
    display label keyed off canonical_doc_type. If signal_type is a pure
    function of canonical_doc_type, its presence in the key is redundant.
    Session 3 must resolve whether the canonical_doc_type -> signal_type map
    is one-to-one (signal_type redundant in the key) or many-to-one
    (signal_type meaningful in the key).

    Args:
        canonical_doc_type: The normalized doc type.
        signal_type_labels: The per-county canonical_doc_type -> display-label
            map.

    Returns:
        The resolved signal_type display label.

    Raises:
        NotImplementedError: always — v5.4.0 Session 1 scaffold.
    """
    raise NotImplementedError(
        "aggregation_key_engine.resolve_signal_type is a v5.4.0 Session 1 "
        "scaffold stub; signal_type resolution is built in Session 3."
    )


def compute_aggregation_key(
    *,
    parcel_id: Optional[str],
    canonical_doc_type: str,
    signal_type: str,
) -> dict:
    """Compute the §18.B aggregation key for one record.

    The key is the tuple `(parcel_id, canonical_doc_type, signal_type)`. It is
    the dedup boundary: multiple raw records that share the full key collapse
    into a single signal with a count badge; records that differ in any
    component remain distinct signals (§18.F anti-collapse rule).

    WARNING (contract finding F-3): §18.B assumes a non-null parcel_id.
    §13.14 explicitly allows UNRESOLVED leads with parcel_id = None. Grouping
    null-parcel records by this key alone would over-collapse distinct
    UNRESOLVED properties into one signal. Session 3 must define the
    null-parcel identity fallback (e.g. instrument_number) the aggregator
    uses; this function returns the key as specified and does not itself
    resolve that ambiguity.

    Args:
        parcel_id: The resolved parcel id, or None when the lead is
            UNRESOLVED / REVIEW_REQUIRED.
        canonical_doc_type: The normalized doc type.
        signal_type: The operator-facing signal type from
            `resolve_signal_type`.

    Returns:
        The aggregation key as a dict with keys parcel_id, canonical_doc_type,
        signal_type — conforming to the `aggregation_key` object in
        leads_base_record.schema.json.

    Raises:
        NotImplementedError: always — v5.4.0 Session 1 scaffold.
    """
    raise NotImplementedError(
        "aggregation_key_engine.compute_aggregation_key is a v5.4.0 Session 1 "
        "scaffold stub; key computation is built in Session 3."
    )


def aggregation_key_tuple(aggregation_key: dict) -> tuple:
    """Return a hashable tuple form of an aggregation-key dict.

    The aggregator groups base records by this tuple. Two keys are the same
    group if and only if their tuples are equal.

    Args:
        aggregation_key: An aggregation-key dict as produced by
            `compute_aggregation_key`.

    Returns:
        The `(parcel_id, canonical_doc_type, signal_type)` tuple — hashable,
        usable as a dict key for grouping.

    Raises:
        NotImplementedError: always — v5.4.0 Session 1 scaffold.
    """
    raise NotImplementedError(
        "aggregation_key_engine.aggregation_key_tuple is a v5.4.0 Session 1 "
        "scaffold stub; built in Session 3."
    )
