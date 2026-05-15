"""
Signal stacking, lifecycle filtering, and pattern collapse.

Inputs
------
A list of normalized signals (each carrying a `parcel_id`,
`normalized_doc_type`, `pattern`, `event_date`, `source_class`, etc.)
plus a parcel master.

Outputs
-------
For each parcel that has at least one active lead-generating signal,
a "stack" object:

    {
        "parcel_id":            str,
        "active_signals":       [signal, ...]  # post-lifecycle, post-TTL
        "suppressed_signals":   [signal, ...]
        "patterns":             [str, ...]     # one entry per active signal
                                                # (post tired_landlord collapse)
        "pattern_set":          [str, ...]     # distinct patterns
        "stack_depth":          int            # len(patterns)
        "recent_flag":          bool           # any active signal <=30d
        "amounts":              [float, ...]
    }

Rules implemented
-----------------
- Per-doctype TTL: lien-family signals expire after 180d unless they
  carry an explicit suppression release. Foreclosure/code/estate signals
  follow the canonical document_priority + per-pattern TTL table.
- Negative-signal source class never contributes to active stack count
  but is recorded as suppressed_signals.
- Eviction collapse: 3+ EVICTION_FILING signals on the same parcel
  collapse to ONE pattern entry, replacing pattern "eviction" with
  pattern "tired_landlord" (per domain/01_lead_types.md).
- Discharge / release signals do not add to the active stack count
  even when the framework canonical entry's `suppresses` list does
  NOT include the original signal's doc type (i.e. the discharge is
  recorded but the lien stays ACTIVE for lifecycle tracking).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from .normalize import CANONICAL


# Per-pattern TTL in days for "active" status. After TTL, lifecycle moves
# from ACTIVE to EXPIRED and the signal stops contributing to the stack.
PATTERN_TTL_DAYS = {
    "foreclosure": 365,
    "tax": 730,
    "lien": 180,
    "estate": 1825,
    "code": 365,
    "transfer": 730,
    "bankruptcy": 730,
    "divorce": 365,
    "eviction": 365,
    "tired_landlord": 730,
    "surplus_owed": 1095,
    "title_issue": 730,
    "utility_distress": 180,
    "commercial_distress": 365,
}


def _parse_date(s):
    if not s:
        return None
    try:
        return date.fromisoformat(str(s)[:10])
    except (ValueError, TypeError):
        return None


def stack_signals(
    signals_by_parcel: dict,
    parcels_by_id: dict,
    *,
    as_of: date | None = None,
) -> dict:
    """
    Build a per-parcel stack object dict keyed by parcel_id.

    `signals_by_parcel` is a mapping parcel_id -> list[normalized signal].
    """
    today = as_of or date.today()
    out: dict = {}

    for parcel_id, sigs in signals_by_parcel.items():
        if not sigs:
            continue
        active = []
        suppressed = []
        amounts = []

        # First pass — annotate lifecycle.
        for sig in sigs:
            canonical = CANONICAL.get(sig.get("normalized_doc_type") or "", {})
            source_class = canonical.get("source_class", "review_required")
            pattern = sig.get("pattern") or canonical.get("lead_pattern")
            event = _parse_date(sig.get("event_date"))

            # Negative signals never count toward the active stack.
            if source_class == "negative_signal":
                sig["lifecycle_status"] = "ACTIVE"
                sig["suppressed"] = False
                sig["counts_in_stack"] = False
                suppressed.append(sig)
                continue

            # TTL filter — patterns lapse after their per-pattern TTL.
            ttl = PATTERN_TTL_DAYS.get(pattern, 365)
            if event and (today - event).days > ttl:
                sig["lifecycle_status"] = "EXPIRED"
                sig["suppressed"] = True
                sig["counts_in_stack"] = False
                suppressed.append(sig)
                continue

            # Bonus-only signal (e.g. a recent-filing re-fire on an existing
            # pattern). Counts as ACTIVE evidence + triggers recency bonus,
            # but does NOT add a new pattern entry to the stack.
            sig["lifecycle_status"] = "ACTIVE"
            sig["counts_in_stack"] = not sig.get("_is_bonus_only", False)
            active.append(sig)

            amt = sig.get("amount")
            if isinstance(amt, (int, float)) and amt > 0:
                amounts.append(float(amt))

        if not active:
            continue

        # Eviction collapse — 3+ active EVICTION_FILING signals collapse to
        # one tired_landlord pattern entry. We preserve ONE eviction pattern
        # marker on the display patterns list (so aggregate pattern_counts
        # carries an eviction tally) while keeping the stack-contributing
        # entry as the single tired_landlord cluster.
        eviction_active = [
            s
            for s in active
            if (s.get("normalized_doc_type") or "") == "EVICTION_FILING"
        ]
        eviction_collapsed = False
        if len(eviction_active) >= 3:
            for s in eviction_active:
                s["collapsed_into"] = "tired_landlord"
                s["counts_in_stack"] = False
            non_eviction = [
                s
                for s in active
                if (s.get("normalized_doc_type") or "") != "EVICTION_FILING"
            ]
            display_patterns = (
                [s.get("pattern") for s in non_eviction if s.get("pattern")]
                + ["eviction", "tired_landlord"]
            )
            stack_contrib_patterns = (
                [
                    s.get("pattern")
                    for s in non_eviction
                    if s.get("pattern") and s.get("counts_in_stack", True)
                ]
                + ["tired_landlord"]
            )
            eviction_collapsed = True
        else:
            display_patterns = [
                s.get("pattern")
                for s in active
                if s.get("pattern") and s.get("counts_in_stack", True)
            ]
            stack_contrib_patterns = list(display_patterns)

        recent_cutoff = today - timedelta(days=30)
        recent_flag = any(
            (_parse_date(s.get("event_date")) or date(1900, 1, 1))
            >= recent_cutoff
            for s in active
        )

        # Distinct ordered pattern set for the stack — drives stack_depth
        # and downstream scoring/classification. Differs from display
        # patterns when a collapse has occurred.
        seen = set()
        pattern_set = []
        for p in stack_contrib_patterns:
            if p and p not in seen:
                seen.add(p)
                pattern_set.append(p)

        out[parcel_id] = {
            "parcel_id": parcel_id,
            "active_signals": active,
            "suppressed_signals": suppressed,
            "patterns": [p for p in display_patterns if p],
            "pattern_set": pattern_set,
            "stack_depth": len(stack_contrib_patterns),
            "stack_contrib_patterns": stack_contrib_patterns,
            "recent_flag": recent_flag,
            "amounts": amounts,
            "eviction_collapsed": eviction_collapsed,
        }

    return out


# Owner-name sentinels that should NOT be grouped for multi-property
# detection. Production-mode placeholder parcels carry an "Unknown"
# owner name pending parcel-master enrichment; treating them all as
# the same owner produces a false multiple_properties attribute on
# every parcel. Phase 4 parcel-matcher replaces these with real
# owner names from BCAD.
_NON_GROUPABLE_OWNER_TOKENS = (
    "UNKNOWN",
    "PENDING",
    "PLACEHOLDER",
    "TBD",
)


def detect_multi_property_owners(parcels: list) -> set:
    """Return parcel_ids belonging to owners with >1 parcel in the dataset."""
    by_owner = defaultdict(list)
    for p in parcels:
        if p.get("_placeholder"):
            continue
        owner = (p.get("owner_name") or "").strip().upper()
        if not owner:
            continue
        if any(t in owner for t in _NON_GROUPABLE_OWNER_TOKENS):
            continue
        by_owner[owner].append(p.get("parcel_id"))
    out: set = set()
    for owner, ids in by_owner.items():
        if len(ids) >= 2:
            out.update(ids)
    return out
