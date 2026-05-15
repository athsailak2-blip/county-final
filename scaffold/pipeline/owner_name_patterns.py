"""
Owner-name-pattern signal matcher.

Parcel-master rows carry an `owner_name` field. The strings in that
field — when they match specific patterns — are themselves leads:

  - `ESTATE OF JOHN DOE` or `HEIRS OF JANE DOE` -> estate signal.
    Heir-hunting opportunity, broader and faster than waiting for
    probate court filings to surface.
  - `DOE FAMILY LIVING TRUST` or `... REVOCABLE TRUST` -> transfer
    signal. Trust ownership often implies deceased / incapacitated
    original owner.
  - `FAMSACA LLC`, `... HOLDINGS`, `... CORP` -> entity_owned
    attribute (handled in `normalize.derive_attributes`, not here).

This module emits the first two as proper framework signals so they
stack onto leads alongside court / clerk / sheriff signals. The
entity case stays an attribute because the framework already
recognizes it; the operator's tightened regex is wired into
`normalize._ENTITY_SUFFIXES`.

The framework canonical entries for ESTATE_OWNER_NAME_PATTERN and
LIVING_TRUST_OWNER_NAME_PATTERN are added by the in-code
`CANONICAL.setdefault(...)` blocks in `normalize.py` so this module
does NOT modify the framework knowledge base.

See `runs/bexar_tx/backlog/v5.1.2-beta-framework-patches.md` for the
proposed framework patch that would promote these entries to
`knowledge_base/domain/canonical_doc_types.json`.
"""

from __future__ import annotations

import hashlib
import re
from typing import Optional


# --- Regex patterns (operator-authoritative, REVIEW_GATE_4 follow-up) ---

ESTATE_PATTERN = re.compile(
    r"\b(ESTATE OF|EST OF|ESTATE|HEIRS OF|HEIRS)\b",
    re.IGNORECASE,
)

LIVING_TRUST_PATTERN = re.compile(
    r"\b(LIVING TRUST|FAMILY TRUST|REVOCABLE TRUST|REV TRUST|TRUST|TRUSTEE)\b",
    re.IGNORECASE,
)


# --- Pattern -> canonical type table ---

_PATTERN_RULES = [
    {
        "name": "estate_owner_name_pattern",
        "regex": ESTATE_PATTERN,
        "canonical": "ESTATE_OWNER_NAME_PATTERN",
        "pattern": "estate",
        "subtype": "estate_owner_name_pattern",
        "confidence": 75,
        "subtype_label": "Estate owner-name pattern",
    },
    {
        "name": "living_trust_owner_name_pattern",
        "regex": LIVING_TRUST_PATTERN,
        "canonical": "LIVING_TRUST_OWNER_NAME_PATTERN",
        "pattern": "transfer",
        "subtype": "living_trust_owner_name_pattern",
        "confidence": 70,
        "subtype_label": "Living-trust owner-name pattern",
    },
]


def _matches(rule: dict, owner_name: str) -> Optional[str]:
    """Return the literal match (verbatim from owner_name) or None."""
    m = rule["regex"].search(owner_name or "")
    return m.group(0) if m else None


def emit_owner_name_signals(parcel: dict, *,
                              event_date: str | None = None,
                              source_id: str = "parcel_master_owner_name") -> list:
    """
    Return 0+ derived signals for the parcel based on owner-name pattern
    matches. Signals are emitted in the source-shaped envelope that
    `scaffold/pipeline/build_leads.normalize_signal` understands so the
    rest of the pipeline (normalize -> stack -> score -> classify)
    treats them indistinguishably from scraper-emitted signals.
    """
    out: list = []
    owner = (parcel.get("owner_name") or "").strip()
    if not owner:
        return out
    parcel_id = parcel.get("parcel_id")
    bcad_id = parcel.get("bcad_prop_id")

    for rule in _PATTERN_RULES:
        literal = _matches(rule, owner)
        if not literal:
            continue
        # Deterministic raw_record_id so re-runs on identical inputs
        # produce identical evidence chains.
        rid_seed = f"{rule['canonical']}|{parcel_id}|{owner}|{literal}".encode("utf-8")
        rid = "raw_" + hashlib.sha1(rid_seed).hexdigest()[:16]

        # Synthesize a source_url that points to the parcel-master
        # record this name pattern came from. Phase 5+ can swap this
        # for the BCAD per-parcel public URL.
        source_url = (
            f"parcel_master_owner_name://{parcel_id}"
            f"#pattern={rule['name']}"
        )

        signal = {
            "parcel_id": parcel_id,
            "source": source_id,
            "source_url": source_url,
            "raw_record_id": rid,
            "pattern": rule["pattern"],
            "subtype": rule["subtype_label"],
            "filing_date": event_date,
            "_synthetic": False,
            # The literal owner-name match becomes part of the audit
            # trail so the operator can see WHY the signal fired.
            "_owner_name_literal_match": literal,
            "_owner_name_full": owner,
            "_bcad_prop_id": bcad_id,
            # Confidence + canonical hint flows through the normalize
            # step via the synthetic subtype map (see normalize.py).
            "_pattern_confidence": rule["confidence"],
        }
        out.append(signal)
    return out


def detect_owner_name_classes(owner_name: str) -> set:
    """Diagnostic helper — returns the rule names that match."""
    out: set = set()
    for rule in _PATTERN_RULES:
        if _matches(rule, owner_name):
            out.add(rule["name"])
    return out
