"""
Evidence-ledger builder.

Every claim that appears on a dashboard row must trace back to an
evidence record per architecture/08_evidence_ledger.md. Evidence records
carry:

  evidence_id, field_name, value, source_id, source_url,
  source_reliability_grade, raw_record_id, signal_id,
  parser_confidence, captured_at, status
"""

from __future__ import annotations

import uuid


def attach_evidence_for_signal(lead: dict, signal: dict, raw_record: dict | None = None,
                                grade: str = "A") -> dict:
    """Build a single evidence entry for a signal contribution."""
    evidence = {
        "evidence_id": "ev_" + uuid.uuid4().hex,
        "field_name": "patterns",
        "value": signal.get("pattern"),
        "source_id": signal.get("source_id") or signal.get("source") or "unknown_source",
        "source_url": signal.get("source_url", ""),
        "source_reliability_grade": grade,
        "raw_record_id": (raw_record or {}).get("raw_record_id") or signal.get("raw_record_id") or signal["signal_id"],
        "signal_id": signal["signal_id"],
        "parser_confidence": signal.get("doc_type_confidence", 100),
        "captured_at": signal.get("event_date") or "",
        "status": "Confirmed",
    }
    lead.setdefault("evidence_ids", []).append(evidence["evidence_id"])
    return evidence
