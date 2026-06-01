"""
Per-state foreclosure-regime profiles.

Each state's foreclosure regime determines how a lis pendens filing
should be classified:

  - JUDICIAL (NY, FL): foreclosure is a lawsuit; a lis pendens often IS
    the foreclosure filing.  lead_pattern -> "foreclosure".
  - NON-JUDICIAL (TX, GA, TN, DC, VA): foreclosure runs through a trustee
    / power-of-sale outside court; a lis pendens is OTHER litigation.
    lead_pattern -> "lis_pendens".
  - HYBRID (MD): ambiguous regime; lis pendens routes to review.
    lead_pattern -> None (seam seeds lis_pendens_unconfirmed_regime flag).

canonical_doc_types.json stores LIS_PENDENS.lead_pattern as the sentinel
value "by_state_profile".  scoring_seam.pattern_for_canonical_doc_type
resolves the sentinel at runtime via resolve_lis_pendens_pattern().
"""

from __future__ import annotations


STATE_PROFILES: dict[str, dict] = {
    # --- Judicial states: lis pendens IS the foreclosure filing ----------
    "NY": {
        "lis_pendens_mode": "foreclosure",
        "foreclosure_instruments": [],
    },
    "FL": {
        "lis_pendens_mode": "foreclosure",
        "foreclosure_instruments": [],
    },
    # --- Non-judicial states: lis pendens is OTHER litigation -------------
    "TX": {
        "lis_pendens_mode": "litigation",
        "foreclosure_instruments": [
            "Notice of Substitute Trustee's Sale",
            "Notice of Default",
        ],
    },
    "GA": {
        "lis_pendens_mode": "litigation",
        "foreclosure_instruments": [
            "Notice of Sale Under Power",
        ],
    },
    "TN": {
        "lis_pendens_mode": "litigation",
        "foreclosure_instruments": [
            "Substitution/Appointment of Substitute Trustee",
            "Substitute Trustee's Deed",
        ],
    },
    "DC": {
        "lis_pendens_mode": "litigation",
        "foreclosure_instruments": [
            "Notice of Foreclosure Sale of Real Property or Condominium Unit",
            "Notice of Default",
        ],
    },
    "VA": {
        "lis_pendens_mode": "litigation",
        "foreclosure_instruments": [
            "Notice of Trustee's Sale",
        ],
    },
    # --- Hybrid: ambiguous, route to review ------------------------------
    "MD": {
        "lis_pendens_mode": None,
        "foreclosure_instruments": [],
    },
}


def get_profile(state: str) -> dict | None:
    """Return the profile for a state code, or None if unknown."""
    return STATE_PROFILES.get(state.upper()) if state else None


def resolve_lis_pendens_pattern(state: str | None) -> str | None:
    """Resolve the lis pendens lead_pattern for a state.

    Returns:
      "foreclosure"  — judicial states (NY, FL): lis pendens IS foreclosure.
      "lis_pendens"  — non-judicial (TX, GA, TN, DC, VA): lis pendens is
                       litigation, not foreclosure.  review.py's hard guard
                       routes to lis_pendens_review / lis_pendens_commercial.
      None           — hybrid / unconfirmed (MD): no pattern fires; the seam
                       seeds a "lis_pendens_unconfirmed_regime" review flag so
                       ALL lis pendens go to REVIEW_REQUIRED without the
                       entity split.
    """
    if not state:
        # No state context — conservative: route to review via lis_pendens.
        return "lis_pendens"
    profile = STATE_PROFILES.get(state.upper())
    if profile is None:
        # Unknown state — conservative: route to review.
        return "lis_pendens"
    mode = profile.get("lis_pendens_mode")
    if mode == "foreclosure":
        return "foreclosure"
    if mode == "litigation":
        return "lis_pendens"
    # mode is None — hybrid regime (e.g. MD).  Return None so no pattern
    # fires; the seam detects the unresolved LIS_PENDENS and adds a plain
    # review flag (no commercial/review entity split).
    return None
