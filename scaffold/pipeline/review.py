"""
Review-queue rules per domain/05_review_queue_rules.md.

Lead flows: STACKED_LEAD -> (review_flags evaluated) -> APPROVED_FOR_DASHBOARD
or REVIEW_REQUIRED. The dashboard's default Client View hides
REVIEW_REQUIRED leads; Operator View shows them with the flag set.
"""

from __future__ import annotations


def evaluate_review_queue(lead: dict, *, now: str | None = None) -> dict:
    # Preserve any preset review flags attached upstream (e.g. by a
    # source translator that already detected a cross-county leak or
    # an incomplete source record). The review-queue evaluator then
    # adds its own rule-based flags on top.
    flags = list(lead.get("review_flags") or [])
    # Suppress the generic "match_confidence_low" flag when a more
    # specific matcher flag is already present — they describe the
    # same underlying cause but the specific one is more actionable.
    _matcher_flags = {
        "multi_parcel_address",
        "address_match_uncertain",
        "parcel_not_found_in_bcad",
    }
    if lead.get("match_confidence", 100) < 80 and not _matcher_flags & set(flags):
        flags.append("match_confidence_low")
    if lead.get("doc_type_normalization", {}).get("doc_type_review_required"):
        flags.append("low_doc_type_confidence")
    if lead.get("title_complexity_score", 0) >= 60:
        flags.append("high_title_complexity_review")
    if not lead.get("patterns"):
        flags.append("no_pattern_fired")
    # Dedupe while preserving order.
    seen = set()
    deduped = []
    for f in flags:
        if f not in seen:
            seen.add(f)
            deduped.append(f)
    lead["review_flags"] = deduped

    transition_to = "REVIEW_REQUIRED" if deduped else "APPROVED_FOR_DASHBOARD"
    lead["lead_status"] = transition_to
    lead.setdefault("lead_status_history", []).append(
        {
            "status": transition_to,
            "transitioned_at": now or "",
            "reason": ("; ".join(deduped)) if deduped else "no review flags triggered",
        }
    )
    return lead
