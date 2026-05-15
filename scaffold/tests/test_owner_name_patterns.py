"""
Tests for scaffold/pipeline/owner_name_patterns.py.

Verifies the operator's authoritative regex spec (REVIEW_GATE_4
follow-up, 2026-05-14):

  - ESTATE_PATTERN matches `ESTATE OF | EST OF | ESTATE | HEIRS OF | HEIRS`
  - LIVING_TRUST_PATTERN matches `LIVING TRUST | FAMILY TRUST | REVOCABLE TRUST | REV TRUST | TRUST | TRUSTEE`
  - Both fire as proper framework signals (not attributes)

Run with: python3 scaffold/tests/test_owner_name_patterns.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scaffold.pipeline.owner_name_patterns import (  # noqa: E402
    detect_owner_name_classes,
    emit_owner_name_signals,
)


passes = []
fails = []


def _assert(label, cond, detail=""):
    if cond:
        passes.append(label)
        print(f"  [PASS] {label}")
    else:
        fails.append((label, detail))
        print(f"  [FAIL] {label}  --  {detail}")


def _parcel(name, pid="BCAD-00100000", bcad_id=100000) -> dict:
    return {
        "parcel_id": pid,
        "bcad_prop_id": bcad_id,
        "owner_name": name,
    }


# ---------------------------------------------------------------------
# Estate pattern
# ---------------------------------------------------------------------

def test_estate_explicit_phrase():
    print("[estate — explicit phrase]")
    classes = detect_owner_name_classes("ESTATE OF JOHN DOE")
    _assert("ESTATE OF -> estate", "estate_owner_name_pattern" in classes)


def test_estate_abbreviation():
    print("\n[estate — EST OF abbreviation]")
    classes = detect_owner_name_classes("EST OF JOHN DOE")
    _assert("EST OF -> estate", "estate_owner_name_pattern" in classes)


def test_estate_heirs_of():
    print("\n[estate — HEIRS OF]")
    classes = detect_owner_name_classes("HEIRS OF JANE SMITH")
    _assert("HEIRS OF -> estate", "estate_owner_name_pattern" in classes)


def test_estate_word_boundary():
    print("\n[estate — word-boundary correctness]")
    # "REALESTATE" should NOT match `\bESTATE\b`.
    classes = detect_owner_name_classes("ALAMO REALESTATE INC")
    _assert("REALESTATE INC does NOT fire estate",
            "estate_owner_name_pattern" not in classes)
    # "HOMERS" should NOT match `\bHEIRS\b`.
    classes = detect_owner_name_classes("HOMERS LLC")
    _assert("HOMERS LLC does NOT fire estate",
            "estate_owner_name_pattern" not in classes)


def test_estate_case_insensitive():
    print("\n[estate — case-insensitive]")
    classes = detect_owner_name_classes("estate of jane doe")
    _assert("lowercase 'estate of' matches",
            "estate_owner_name_pattern" in classes)


def test_estate_bare_word():
    print("\n[estate — bare 'ESTATE']")
    classes = detect_owner_name_classes("DOE ESTATE")
    _assert("trailing 'ESTATE' matches", "estate_owner_name_pattern" in classes)


# ---------------------------------------------------------------------
# Living-trust pattern
# ---------------------------------------------------------------------

def test_trust_family_trust():
    print("\n[trust — FAMILY TRUST]")
    classes = detect_owner_name_classes("DOE FAMILY TRUST")
    _assert("FAMILY TRUST matches",
            "living_trust_owner_name_pattern" in classes)


def test_trust_revocable():
    print("\n[trust — REVOCABLE TRUST]")
    classes = detect_owner_name_classes("DOE REVOCABLE TRUST")
    _assert("REVOCABLE TRUST matches",
            "living_trust_owner_name_pattern" in classes)


def test_trust_rev_trust_abbreviation():
    print("\n[trust — REV TRUST]")
    classes = detect_owner_name_classes("DOE REV TRUST")
    _assert("REV TRUST matches",
            "living_trust_owner_name_pattern" in classes)


def test_trust_bare_trust():
    print("\n[trust — bare TRUST]")
    classes = detect_owner_name_classes("DOE TRUST")
    _assert("bare TRUST matches",
            "living_trust_owner_name_pattern" in classes)


def test_trust_trustee():
    print("\n[trust — TRUSTEE]")
    classes = detect_owner_name_classes("DOE JANE TRUSTEE")
    _assert("TRUSTEE matches",
            "living_trust_owner_name_pattern" in classes)


def test_trust_word_boundary():
    print("\n[trust — word boundary]")
    # "ENTRUSTED" should not match `\bTRUST\b`.
    classes = detect_owner_name_classes("ENTRUSTED CAPITAL LLC")
    _assert("ENTRUSTED does NOT fire trust",
            "living_trust_owner_name_pattern" not in classes)


# ---------------------------------------------------------------------
# Signal emission shape
# ---------------------------------------------------------------------

def test_emit_estate_signal_shape():
    print("\n[emission — estate signal shape]")
    parcel = _parcel("ESTATE OF JOHN DOE", "BCAD-00200000", 200000)
    signals = emit_owner_name_signals(parcel)
    _assert("emits 1 estate signal", len(signals) == 1)
    s = signals[0]
    _assert("signal.parcel_id is parcel's", s["parcel_id"] == "BCAD-00200000")
    _assert("signal.source identifies owner-name origin",
            s["source"] == "parcel_master_owner_name")
    _assert("signal.pattern == estate", s["pattern"] == "estate")
    _assert("signal.subtype is operator-readable",
            "Estate" in s["subtype"])
    _assert("signal._pattern_confidence == 75 (operator spec)",
            s["_pattern_confidence"] == 75)
    _assert("signal._owner_name_literal_match captured",
            s["_owner_name_literal_match"].upper() == "ESTATE OF")


def test_emit_trust_signal_shape():
    print("\n[emission — trust signal shape]")
    parcel = _parcel("DOE FAMILY REVOCABLE TRUST", "BCAD-00300000", 300000)
    signals = emit_owner_name_signals(parcel)
    _assert("emits 1 trust signal", len(signals) == 1)
    s = signals[0]
    _assert("signal.pattern == transfer", s["pattern"] == "transfer")
    _assert("signal._pattern_confidence == 70 (operator spec)",
            s["_pattern_confidence"] == 70)


def test_emit_no_match():
    print("\n[emission — no-match parcel]")
    parcel = _parcel("JOHN DOE")
    signals = emit_owner_name_signals(parcel)
    _assert("emits 0 signals for plain owner name", len(signals) == 0)


def test_emit_entity_owner_does_not_fire_signal():
    print("\n[emission — entity-only owner emits no signal]")
    parcel = _parcel("FAMSACA LLC")
    signals = emit_owner_name_signals(parcel)
    _assert("entity-only owner emits 0 signals (handled as attribute, not signal)",
            len(signals) == 0)


def test_emit_multi_match():
    print("\n[emission — multi-pattern parcel (estate + trust)]")
    # A pathological owner string that hits both patterns.
    parcel = _parcel("HEIRS OF JOHN DOE FAMILY TRUST")
    signals = emit_owner_name_signals(parcel)
    patterns = sorted([s["pattern"] for s in signals])
    _assert("both estate and transfer signals fire",
            patterns == ["estate", "transfer"],
            f"got {patterns}")


def test_emit_deterministic_ids():
    print("\n[emission — deterministic raw_record_id across runs]")
    parcel = _parcel("ESTATE OF JANE SMITH", "BCAD-00400000", 400000)
    a = emit_owner_name_signals(parcel)[0]
    b = emit_owner_name_signals(parcel)[0]
    _assert("identical inputs produce identical raw_record_id",
            a["raw_record_id"] == b["raw_record_id"])


def main() -> int:
    print("[owner_name_patterns tests]\n")
    test_estate_explicit_phrase()
    test_estate_abbreviation()
    test_estate_heirs_of()
    test_estate_word_boundary()
    test_estate_case_insensitive()
    test_estate_bare_word()
    test_trust_family_trust()
    test_trust_revocable()
    test_trust_rev_trust_abbreviation()
    test_trust_bare_trust()
    test_trust_trustee()
    test_trust_word_boundary()
    test_emit_estate_signal_shape()
    test_emit_trust_signal_shape()
    test_emit_no_match()
    test_emit_entity_owner_does_not_fire_signal()
    test_emit_multi_match()
    test_emit_deterministic_ids()
    print(f"\npasses: {len(passes)}  fails: {len(fails)}")
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
