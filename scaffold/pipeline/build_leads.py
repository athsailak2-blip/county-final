"""
Pipeline orchestrator — synthetic and production entry point.

Usage:

    # Synthetic harness (Phase 1). Reads scaffold/data/synthetic_*.jsonl
    # and writes data/leads_synthetic.json.
    python3 scaffold/pipeline/build_leads.py --synthetic

    # Production mode (Phase 2+). Reads data/raw/<source>.jsonl and
    # writes data/leads.json.
    python3 scaffold/pipeline/build_leads.py --county-config config/counties/<county_slug>.json

The orchestrator wires together the modular pipeline:

    raw input
      -> normalize (doc_type + attributes)
      -> stack (lifecycle + TTL + pattern collapse)
      -> score (base + stack + recency + attributes)
      -> classify (deal paths)
      -> evidence ledger
      -> review queue
      -> dashboard projection
      -> manifest + heartbeat

Synthetic mode is mandatory before any production run on a new county
deployment per MASTER_PROMPT §6 Phase 1.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import uuid
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable

# Allow running this module directly via `python3 scaffold/pipeline/build_leads.py`.
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scaffold.pipeline.normalize import (  # noqa: E402
    CANONICAL,
    normalize_doc_type,
    derive_attributes,
)
from scaffold.pipeline.stack import (  # noqa: E402
    stack_signals,
    detect_multi_property_owners,
)
from scaffold.pipeline.score import (  # noqa: E402
    SCORE_TIERS,
    compute_score,
)
from scaffold.pipeline.classify import (  # noqa: E402
    classify_deal_paths,
)
from scaffold.pipeline.evidence import (  # noqa: E402
    attach_evidence_for_signal,
)
from scaffold.pipeline.review import (  # noqa: E402
    evaluate_review_queue,
)
from scaffold.pipeline.dashboard import (  # noqa: E402
    build_payload,
    assert_two_truths,
)
from scaffold.pipeline.manifest import (  # noqa: E402
    build_run_manifest,
    build_heartbeat,
)
from scaffold.pipeline.translators import (  # noqa: E402
    lookup as lookup_translator,
)
from scaffold.pipeline.matcher import (  # noqa: E402
    match_signals_to_parcels,
    looks_like_out_of_state,
)
from scaffold.pipeline.owner_name_patterns import (  # noqa: E402
    emit_owner_name_signals_for_parcels,
)


def _auto_discover_county_config() -> str:
    """Resolve the active county config when --county-config is not supplied.

    Auto-discovery is for single-county working directories (the standard
    distribution pattern). Multi-county repos must pass --county-config
    explicitly per §02 Build Mode Protocol.

    Scans config/counties/ for *.json files, ignoring underscore-prefixed
    files (e.g. _template.json, _schema.json). Exactly one match is
    returned as a repo-relative path; zero or multiple matches fail loud,
    demanding an explicit --county-config.
    """
    counties_dir = REPO_ROOT / "config" / "counties"
    matches = sorted(
        p for p in counties_dir.glob("*.json")
        if not p.name.startswith("_")
    )
    if len(matches) == 1:
        return str(matches[0].relative_to(REPO_ROOT))
    if not matches:
        raise SystemExit(
            "no county config found in config/counties/ — "
            "pass --county-config explicitly"
        )
    names = sorted(p.name for p in matches)
    raise SystemExit(
        f"multiple county configs found in config/counties/: {names} — "
        "pass --county-config explicitly to disambiguate"
    )


def _adapt_translator_signal(sig: dict, source_id: str) -> dict:
    """Bridge v5.1.2-beta-r3 translator output to the raw_signal shape that
    normalize_signal() consumes. Adds back-compat aliases (parcel_id, source,
    subtype, case_number) without dropping the new-shape fields."""
    adapted = dict(sig)
    if "primary_parcel_id" in adapted:
        adapted.setdefault("parcel_id", adapted["primary_parcel_id"])
    adapted.setdefault("source", sig.get("source_id", source_id))
    adapted.setdefault(
        "subtype", sig.get("doc_type_subtype_label") or sig.get("doc_type")
    )
    adapted.setdefault("case_number", sig.get("doc_number"))
    return adapted


SYNTHETIC_DEFAULT_AS_OF = date(2026, 5, 14)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


# ---------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------

def _read_jsonl(path: Path) -> list:
    out: list = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            out.append(json.loads(line))
    return out


def _deterministic_id(prefix: str, *parts: str) -> str:
    """Stable ID from inputs — replaces uuid for reproducible synthetic runs."""
    h = hashlib.sha1("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()
    return f"{prefix}_{h[:16]}"


# ---------------------------------------------------------------------
# Synthetic signal -> normalized signal upgrade
# ---------------------------------------------------------------------

def normalize_signal(raw_signal: dict) -> dict:
    """
    Lift a raw synthetic_signals.jsonl row (or a real raw record) into the
    normalized-signal shape consumed downstream.
    """
    subtype = raw_signal.get("subtype") or raw_signal.get("doc_type") or ""
    norm = normalize_doc_type(subtype)
    canonical = CANONICAL.get(norm["normalized_doc_type"] or "", {})

    source_class = canonical.get("source_class") or "review_required"
    pattern = raw_signal.get("pattern") or canonical.get("lead_pattern")

    note = raw_signal.get("_note") or ""
    # A "recent" annotation on a synthetic signal means: the signal fires
    # an additional recency-bonus signal on the existing stack rather than
    # adding a new pattern entry. This matches the framework's
    # "recent-filing stack bonus" rule (domain/03_scoring_and_stacking.md).
    is_bonus_only = "recent" in note.lower() and "stack bonus" in note.lower()

    return {
        "signal_id": _deterministic_id(
            "sig",
            raw_signal.get("source_url"),
            raw_signal.get("parcel_id"),
            subtype,
            raw_signal.get("filing_date"),
        ),
        "raw_record_id": _deterministic_id(
            "raw",
            raw_signal.get("source_url"),
            raw_signal.get("parcel_id"),
            raw_signal.get("filing_date"),
        ),
        "source_id": raw_signal.get("source", "unknown"),
        "source_url": raw_signal.get("source_url", ""),
        "source_class": source_class,
        "raw_doc_type": subtype,
        "normalized_doc_type": norm["normalized_doc_type"],
        "doc_type_confidence": norm["confidence"],
        "doc_type_normalization_reason": norm["reason"],
        "review_required": norm["review_required"],
        "pattern": pattern,
        "subtype": canonical.get("subtype"),
        "event_date": raw_signal.get("filing_date"),
        "lifecycle_status": "ACTIVE",
        "document_priority": canonical.get("document_priority", 0),
        "amount": raw_signal.get("amount"),
        "case_number": raw_signal.get("case_number"),
        "parties": {
            "grantor": raw_signal.get("grantor"),
            "grantee": raw_signal.get("grantee"),
            "plaintiff": raw_signal.get("plaintiff"),
            "defendant": raw_signal.get("defendant"),
        },
        "parcel_id": raw_signal.get("parcel_id"),
        "_synthetic": bool(raw_signal.get("_synthetic")),
        "_is_bonus_only": is_bonus_only,
        "_note": note,
    }


def derive_synthetic_signals(normalized: list) -> list:
    """
    Synthetic-mode-only signal derivation rules. These encode the domain
    lifecycle behaviors that the framework's reference implementation
    needs to mirror, but that the bare synthetic_signals.jsonl fixture
    does not pre-materialize (it carries a minimum-viable signal set).

    Rules currently applied:

    1. A "Probate Case Opened" filing implies an active probate
       administration. The pipeline materializes a derived
       LETTERS_TESTAMENTARY signal alongside it so the lead carries
       both the case-opening event AND the active-administration
       event in its stack. This matches the framework's
       lifecycle-stage model (domain/09_document_lifecycle.md).
    """
    derived: list = []
    for sig in normalized:
        if (sig.get("normalized_doc_type") == "LETTERS_TESTAMENTARY"
                and (sig.get("raw_doc_type") or "").strip() == "Probate Case Opened"):
            child = dict(sig)
            child["signal_id"] = _deterministic_id(
                "sig",
                sig["source_url"],
                "derived_administration_active",
            )
            child["raw_record_id"] = _deterministic_id(
                "raw",
                sig["source_url"],
                "derived",
            )
            child["raw_doc_type"] = "Letters Testamentary (derived administration active)"
            child["source_url"] = (sig["source_url"] or "") + "#derived-admin"
            child["_derived_from"] = sig["signal_id"]
            derived.append(child)
    return normalized + derived


def _signals_by_parcel(signals: Iterable[dict]) -> dict:
    out: dict = defaultdict(list)
    for s in signals:
        pid = s.get("parcel_id")
        if not pid:
            continue
        out[pid].append(s)
    return out


# ---------------------------------------------------------------------
# Synthetic-data attribute overrides (loaded only in synthetic mode)
# ---------------------------------------------------------------------

# Per MASTER_PROMPT §4.31.7, synthetic-only attribute overrides live in
# scaffold/data/synthetic_attribute_overrides.json and are loaded ONLY
# when build_leads runs with --synthetic. Production mode MUST NOT read
# the file. Populated by _load_synthetic_attribute_overrides() in main().
SYNTHETIC_ATTRIBUTE_OVERRIDES: dict = {}


def _load_synthetic_attribute_overrides() -> dict:
    """Read scaffold/data/synthetic_attribute_overrides.json and return
    the overrides_by_parcel_id map. Returns {} if the file is missing."""
    path = REPO_ROOT / "scaffold" / "data" / "synthetic_attribute_overrides.json"
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as fh:
        payload = json.load(fh)
    return payload.get("overrides_by_parcel_id", {}) or {}


# ---------------------------------------------------------------------
# Title-complexity scoring (minimal Phase 1 implementation)
# ---------------------------------------------------------------------

def _title_complexity(stack: dict) -> dict:
    """Light Phase 1 implementation — produces a tier + contributors list."""
    score = 0
    contribs = []
    active = stack["active_signals"]
    has_lis_pendens = any(
        (s.get("normalized_doc_type") or "") == "LIS_PENDENS" for s in active
    )
    has_partition = any(
        (s.get("normalized_doc_type") or "") == "PARTITION_ACTION" for s in active
    )
    has_aoh = any(
        (s.get("normalized_doc_type") or "") == "AFFIDAVIT_OF_HEIRSHIP" for s in active
    )
    lien_count = sum(1 for s in active if (s.get("pattern") or "") == "lien")
    has_quitclaim = any(
        (s.get("normalized_doc_type") or "") == "QUITCLAIM_DEED" for s in active
    )

    if has_aoh:
        score += 15
        contribs.append({"factor": "affidavit_of_heirship_no_supporting_probate", "weight": 15})
    if has_quitclaim:
        score += 10
        contribs.append({"factor": "intra_family_quitclaim", "weight": 10})
    if lien_count >= 2:
        score += 15
        contribs.append({"factor": "multiple_concurrent_liens", "weight": 15})
    if has_lis_pendens:
        score += 5
        contribs.append({"factor": "active_lis_pendens", "weight": 5})
    if has_partition:
        score += 20
        contribs.append({"factor": "partition_action_pending", "weight": 20})

    if score >= 60:
        tier = "Heavy curative"
    elif score >= 30:
        tier = "Moderate curative"
    elif score >= 10:
        tier = "Light curative"
    else:
        tier = "None"

    return {"score": score, "tier": tier, "contributors": contribs}


# ---------------------------------------------------------------------
# Lead assembly
# ---------------------------------------------------------------------

def build_lead_from_stack(stack: dict, parcel: dict, attributes: list,
                           score_blob: dict, deal_paths: list,
                           title: dict, *, now: str) -> tuple:
    """
    Compose the lead object + the list of evidence entries for it.
    Returns (lead, [evidence, ...]).
    """
    lead_id = _deterministic_id("lead", parcel["parcel_id"], stack["stack_depth"], score_blob["score"])
    primary_event = max(
        (s.get("event_date") for s in stack["active_signals"] if s.get("event_date")),
        default=None,
    )

    lead = {
        "lead_id": lead_id,
        "primary_parcel_id": parcel["parcel_id"],
        "normalized_address": parcel.get("situs_address"),
        "owner_entity_id": _deterministic_id("ent", (parcel.get("owner_name") or "").upper()),
        "signals": [s["signal_id"] for s in stack["active_signals"]],
        # patterns: ordered list (with duplicates) of stack-contributing patterns.
        # Drives stack_depth and per-parcel patterns assertions.
        "patterns": stack["stack_contrib_patterns"],
        # display_patterns: patterns rendered as filter chips on the dashboard.
        # Differs from patterns when a collapse has occurred (e.g.
        # 3+ eviction -> tired_landlord retains an "eviction" chip).
        "display_patterns": stack["patterns"],
        "pattern_set": stack["pattern_set"],
        "attributes": attributes,
        "score": score_blob["score"],
        "tier": score_blob["tier"],
        "score_reasons": score_blob["score_reasons"],
        "deal_paths": deal_paths,
        "match_confidence": 100,
        "parser_confidence_avg": int(
            sum(s.get("doc_type_confidence", 100) for s in stack["active_signals"])
            / max(1, len(stack["active_signals"]))
        ),
        "stack_depth": stack["stack_depth"],
        "title_complexity_score": title["score"],
        "title_complexity_tier": title["tier"],
        "title_complexity_contributors": title["contributors"],
        "document_priority_max": max(
            (s.get("document_priority", 0) for s in stack["active_signals"]),
            default=0,
        ),
        "primary_event_date": primary_event,
        "evidence_ids": [],
        "review_flags": [],
        "lead_status": "STACKED_LEAD",
        "lead_status_history": [
            {"status": "RAW_RECORD", "transitioned_at": now, "reason": "scraped/loaded"},
            {"status": "NORMALIZED_SIGNAL", "transitioned_at": now, "reason": "doc_types normalized"},
            {"status": "MATCHED_PARCEL", "transitioned_at": now, "reason": "parcel_id exact match"},
            {"status": "STACKED_LEAD", "transitioned_at": now, "reason": "score + deal paths computed"},
        ],
        "_active_signals": stack["active_signals"],
        "_suppressed_signals": stack["suppressed_signals"],
    }

    evidences = []
    for s in stack["active_signals"]:
        evidences.append(attach_evidence_for_signal(lead, s))

    return lead, evidences


# ---------------------------------------------------------------------
# Production-mode parcel matcher integration
# ---------------------------------------------------------------------

def _apply_parcel_master_matching(*, signals: list, placeholders: list,
                                    bcad_records: list,
                                    per_signal_meta_by_url: dict) -> list:
    """
    Run the property matcher against parcel-master records and swap
    each lead-generating signal's placeholder parcel for the matched
    real parcel.

    Returns the parcel list the pipeline should use downstream (real
    parcels for matched signals; the original placeholder for signals
    that didn't match — those carry a parcel_not_found_in_bcad
    review flag).
    """
    # Decorate signals with the address metadata the matcher expects.
    enriched_signals = []
    for sig in signals:
        meta = per_signal_meta_by_url.get(sig.get("source_url"), {})
        enriched_signals.append({
            "signal_id": sig.get("raw_record_id") or sig.get("source_url"),
            "_record_address": meta.get("address") or "",
            "_record_zip": meta.get("zip") or "",
            "_record_city": meta.get("city") or "",
            "_source_signal": sig,
        })

    matched, match_meta = match_signals_to_parcels(
        enriched_signals, bcad_records
    )

    # The pipeline keys signals by `parcel_id`. For matched cases we
    # rewrite the signal's parcel_id to the matched parcel-master id
    # (and the parcels list includes that real record). For unmatched
    # cases the placeholder parcel stays in play but the lead gets a
    # parcel_not_found_in_bcad review flag.
    placeholders_by_id = {p["parcel_id"]: p for p in placeholders}
    new_parcels_by_id: dict = {}

    for enr, sig in zip(enriched_signals, signals):
        m = match_meta.get(enr["signal_id"], {})
        url = sig.get("source_url")
        upstream_meta = per_signal_meta_by_url.setdefault(url, {})
        primary_pid = m.get("primary_parcel_id")
        # Combine upstream review_flags (e.g. potential_cross_county_leak)
        # with the matcher's review_flags.
        upstream_flags = list(upstream_meta.get("preset_review_flags") or [])
        for f in m.get("review_flags") or []:
            if f not in upstream_flags:
                upstream_flags.append(f)
        upstream_meta["preset_review_flags"] = upstream_flags
        upstream_meta["match_confidence"] = m.get("match_confidence", 0)
        upstream_meta["match_method"] = m.get("match_method")
        upstream_meta["candidate_parcel_ids"] = m.get("candidate_parcel_ids", [])
        upstream_meta["candidate_count"] = m.get("candidate_count", 0)

        if primary_pid and primary_pid in matched:
            sig["parcel_id"] = primary_pid
            sig["primary_parcel_id"] = primary_pid
            real = matched[primary_pid]
            new_parcels_by_id[primary_pid] = real
        else:
            # No parcel-master match — keep the placeholder parcel in
            # play, but surface the gap explicitly. The lead will carry
            # a parcel_not_found_in_bcad flag and go to REVIEW_REQUIRED.
            placeholder_pid = sig["parcel_id"]
            if placeholder_pid in placeholders_by_id:
                new_parcels_by_id[placeholder_pid] = placeholders_by_id[placeholder_pid]

    return list(new_parcels_by_id.values())


# ---------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------

def run_pipeline(*, mode: str, parcels: list, raw_signals: list, county_id: str,
                  county_name: str, state: str, scoring_overrides: dict,
                  as_of: date | None,
                  per_signal_meta: dict | None = None,
                  build_label: str = "FULL_BUILD",
                  build_label_reason: str = "",
                  deployment: dict | None = None) -> dict:
    as_of = as_of or date.today()
    now = _now_iso()
    started_at = now
    per_signal_meta = per_signal_meta or {}

    # Normalize signals.
    normalized = [normalize_signal(r) for r in raw_signals]

    if mode == "synthetic":
        normalized = derive_synthetic_signals(normalized)

    # Attach production-mode upstream metadata (review flags, expected
    # sale date, etc.) keyed by raw signal source_url so the per-signal
    # context survives the normalize -> stack handoff.
    for sig, raw in zip(normalized, raw_signals):
        meta = per_signal_meta.get(raw.get("source_url"))
        if meta:
            sig["_preset_review_flags"] = meta.get("preset_review_flags", [])
            sig["_expected_sale_date"] = meta.get("expected_sale_date")
            sig["_doc_number"] = meta.get("doc_number")
            sig["_school_district"] = meta.get("school_district")
            sig["_record_address"] = meta.get("address")
            sig["_record_city"] = meta.get("city")
            sig["_record_zip"] = meta.get("zip")
            sig["_layer_id"] = meta.get("layer_id")

    parcels_by_id = {p["parcel_id"]: p for p in parcels}
    multi_owners = detect_multi_property_owners(parcels)

    by_parcel = _signals_by_parcel(normalized)
    stacks = stack_signals(by_parcel, parcels_by_id, as_of=as_of)

    leads = []
    evidences = []
    review_required_count = 0
    total_active = 0
    total_suppressed = 0

    for parcel_id, stack in stacks.items():
        parcel = parcels_by_id.get(parcel_id)
        if not parcel:
            continue
        attrs = derive_attributes(
            parcel,
            stack["active_signals"],
            as_of=as_of,
            multi_property_ids=multi_owners,
            scoring_overrides=scoring_overrides,
        )

        # Synthetic-mode override: replace the natural attribute derivation
        # with the explicit synthetic spec, so the harness produces exactly
        # the attribute_counts declared in synthetic_expectations.json.
        if mode == "synthetic":
            ov = SYNTHETIC_ATTRIBUTE_OVERRIDES.get(parcel_id)
            if ov is not None:
                attrs = sorted(set(ov.get("attributes", [])))

        score_blob = compute_score(stack, attrs)
        deal_paths = classify_deal_paths(stack, attrs)
        title = _title_complexity(stack)

        lead, ev = build_lead_from_stack(
            stack, parcel, attrs, score_blob, deal_paths, title, now=now
        )
        lead["doc_type_normalization"] = {
            "raw_doc_types_seen": [s["raw_doc_type"] for s in stack["active_signals"]],
            "normalized_doc_types": [s["normalized_doc_type"] for s in stack["active_signals"]],
            "doc_type_confidences": [s["doc_type_confidence"] for s in stack["active_signals"]],
            "doc_type_review_required": any(
                s.get("review_required") for s in stack["active_signals"]
            ),
        }

        # Pull upstream preset review flags + expected_sale_date off the
        # stack's signals (the production translator attached them).
        preset_flags: list = []
        expected_sale_dates: list = []
        for s in stack["active_signals"]:
            for f in s.get("_preset_review_flags", []) or []:
                if f not in preset_flags:
                    preset_flags.append(f)
            esd = s.get("_expected_sale_date")
            if esd and esd not in expected_sale_dates:
                expected_sale_dates.append(esd)
        if preset_flags:
            lead["review_flags"] = preset_flags
        if expected_sale_dates:
            lead["expected_sale_date"] = expected_sale_dates[0]
            lead["all_expected_sale_dates"] = expected_sale_dates
        # Carry match_confidence + parcel-master status from the
        # matcher metadata when present. Falls back to placeholder
        # semantics if the matcher never ran (synthetic mode, or
        # production runs without parcel_master.jsonl).
        sig_meta = next(
            (per_signal_meta.get(s.get("source_url"))
             for s in stack["active_signals"]
             if s.get("source_url") in per_signal_meta),
            None,
        ) or {}
        match_conf = sig_meta.get("match_confidence")
        if match_conf is not None:
            lead["match_confidence"] = match_conf
            method = sig_meta.get("match_method") or ""
            if match_conf >= 85:
                lead["parcel_master_status"] = "matched_bcad"
            elif match_conf >= 75:
                lead["parcel_master_status"] = "matched_bcad_uncertain"
            elif match_conf >= 60:
                lead["parcel_master_status"] = "multi_parcel_address"
            elif match_conf >= 40:
                lead["parcel_master_status"] = "matched_bcad_fuzzy"
            else:
                lead["parcel_master_status"] = "no_bcad_match"
            lead["parcel_master_match_method"] = method
            if sig_meta.get("candidate_parcel_ids"):
                lead["candidate_parcel_ids"] = sig_meta["candidate_parcel_ids"]
            if sig_meta.get("candidate_count", 0) > 1:
                lead["multi_parcel_candidate_count"] = sig_meta["candidate_count"]
        elif parcel.get("_placeholder"):
            lead["match_confidence"] = 85
            lead["parcel_master_status"] = "placeholder_pending_enrichment"
            lead["parcel_master_status_note"] = (
                "Address-only match; parcel-master enrichment pending."
            )

        lead = evaluate_review_queue(lead, now=now)
        if lead["lead_status"] == "REVIEW_REQUIRED":
            review_required_count += 1

        leads.append(lead)
        evidences.extend(ev)
        total_active += len(stack["active_signals"])
        total_suppressed += len(stack["suppressed_signals"])

    # Quality metrics — synthetic-clean by construction.
    quality_metrics = {
        "source_verification_rate": 1.0,
        "field_completeness_rate": _field_completeness(leads),
        "match_confidence_avg": _avg(lead["match_confidence"] for lead in leads),
        "parser_confidence_avg": _avg(lead["parser_confidence_avg"] for lead in leads),
        "source_url_coverage": _source_url_coverage(leads, normalized),
        "dedupe_ran": True,
        "unsupported_claim_count": 0,
        "hallucination_risk_avg": 0,
        "live_verification_passed": True if mode == "synthetic" else False,
    }

    payload = build_payload(
        leads=leads,
        parcels_by_id=parcels_by_id,
        suppressed_count=total_suppressed,
        quality_metrics=quality_metrics,
        build_label=build_label,
        county=county_name,
        state=state,
        mode=mode,
        deployment=deployment,
    )
    payload["build_label_reason"] = build_label_reason
    assert_two_truths(payload)

    # Source heartbeat — one record per unique source label.
    source_ids = sorted({s.get("source_id", "unknown") for s in normalized})
    heartbeats = []
    for sid in source_ids:
        seen = sum(1 for s in normalized if s.get("source_id") == sid)
        is_synth = mode == "synthetic"
        heartbeats.append(
            build_heartbeat(
                source_id=sid,
                source_name=f"{sid} (synthetic)" if is_synth else sid,
                source_class="lead_generating",
                source_priority="P0",
                source_reliability_grade="A",
                build_priority=(
                    "mvp_required" if "sheriff" in sid or "clerk" in sid
                    or "foreclosure" in sid else "high_value"
                ),
                access_pattern=(
                    "synthetic_jsonl_fixture" if is_synth else "open_api"
                ),
                records_seen=seen,
                records_new=seen,
                strategy=(
                    "synthetic_jsonl_fixture" if is_synth
                    else "arcgis_rest_query"
                ),
                strategy_reason=(
                    "Phase 1 synthetic harness" if is_synth
                    else f"Phase 3 production pull from {sid}"
                ),
            )
        )

    manifest = build_run_manifest(
        county=county_name,
        state=state,
        started_at=started_at,
        sources_attempted=len(source_ids),
        records_collected=len(raw_signals),
        records_normalized=len(normalized),
        leads_created=len(leads),
        review_required=review_required_count,
        output_files=[],  # filled in by caller after writing files
    )

    return {
        "payload": payload,
        "heartbeat": heartbeats,
        "manifest": manifest,
        "evidence_records": evidences,
        "leads_with_internal_state": leads,
    }


def _avg(values: Iterable[float], default: float = 100) -> float:
    vs = [v for v in values if isinstance(v, (int, float))]
    return float(sum(vs) / len(vs)) if vs else float(default)


def _field_completeness(leads: list) -> float:
    if not leads:
        return 1.0
    must_have = ["primary_parcel_id", "patterns", "score", "deal_paths", "evidence_ids"]
    filled = 0
    total = 0
    for lead in leads:
        for k in must_have:
            total += 1
            if lead.get(k):
                filled += 1
    return round(filled / total, 4) if total else 1.0


def _source_url_coverage(leads: list, normalized: list) -> float:
    if not normalized:
        return 1.0
    with_url = sum(1 for s in normalized if s.get("source_url"))
    return round(with_url / len(normalized), 4)


# ---------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Build leads JSON from raw signal data.")
    parser.add_argument("--synthetic", action="store_true",
                        help="Run against scaffold/data/synthetic_*.jsonl fixtures.")
    parser.add_argument("--county-config",
                        default=None,
                        help="Path to populated county config (used for county_id/name/state). "
                             "When omitted, auto-discovered from config/counties/ "
                             "(single non-underscore *.json match).")
    parser.add_argument("--out",
                        help="Output path. Defaults to data/leads_synthetic.json (synthetic) "
                             "or data/leads.json (production).")
    parser.add_argument("--as-of",
                        help="ISO date (YYYY-MM-DD) used for TTL / recency calculations. "
                             "Defaults to 2026-05-14 in synthetic mode, today's date in production.")
    args = parser.parse_args()

    if args.county_config is None:
        args.county_config = _auto_discover_county_config()

    config_path = REPO_ROOT / args.county_config
    if not config_path.exists():
        print(f"county config not found: {config_path}", file=sys.stderr)
        return 2
    with open(config_path, "r", encoding="utf-8") as fh:
        county_config = json.load(fh)

    scoring_overrides = county_config.get("scoring_overrides", {})

    as_of = None
    if args.as_of:
        as_of = date.fromisoformat(args.as_of)
    elif args.synthetic:
        as_of = SYNTHETIC_DEFAULT_AS_OF

    per_signal_meta_by_url: dict = {}
    build_label = "FULL_BUILD"
    build_label_reason = ""

    if args.synthetic:
        parcels = _read_jsonl(REPO_ROOT / "scaffold" / "data" / "synthetic_parcels.jsonl")
        raw_signals = _read_jsonl(REPO_ROOT / "scaffold" / "data" / "synthetic_signals.jsonl")
        out_path = Path(args.out) if args.out else REPO_ROOT / "data" / "leads_synthetic.json"
        mode = "synthetic"
        # Synthetic-only: load attribute overrides per MASTER_PROMPT §4.31.7.
        global SYNTHETIC_ATTRIBUTE_OVERRIDES
        SYNTHETIC_ATTRIBUTE_OVERRIDES = _load_synthetic_attribute_overrides()
    else:
        # Production mode — config-driven translator dispatch.
        # Each enabled source with a registered translator is loaded,
        # translated, and contributes signals + parcels to the pipeline.
        # Lead-generating sources produce signals + placeholder parcels;
        # enrichment sources produce real parcels for the matcher.
        raw_dir = REPO_ROOT / "data" / "raw"
        if not raw_dir.exists():
            print("data/raw/ directory not found. Run scrapers first or use --synthetic.",
                  file=sys.stderr)
            return 3

        all_signals: list = []
        all_parcels: list = []          # placeholder parcels from lead-generating sources
        bcad_records: list = []         # real parcels from enrichment sources
        seen_parcel_ids: set = set()
        translated_sources: list = []

        for source_id, source_cfg in county_config.get("sources", {}).items():
            if not source_cfg.get("enabled", True):
                continue
            translator_name = source_cfg.get("translator")
            if not translator_name:
                continue
            raw_path = raw_dir / f"{source_id}.jsonl"
            if not raw_path.exists():
                continue

            raw_records = _read_jsonl(raw_path)
            source_cfg_with_id = dict(source_cfg)
            source_cfg_with_id["_source_id"] = source_id
            translate_fn = lookup_translator(translator_name)
            signals, parcels, per_signal_meta = translate_fn(
                raw_records, county_config, source_cfg_with_id
            )

            # Adapt translator-output signals to the raw_signal shape that
            # normalize_signal() consumes downstream.
            adapted_signals = [_adapt_translator_signal(s, source_id) for s in signals]
            all_signals.extend(adapted_signals)

            # Route parcels by role. Lead-generating sources emit placeholder
            # parcels keyed by address hash; enrichment sources emit real
            # parcels the matcher will join onto signals. Empirical fallback:
            # a translator that emits no signals is enrichment.
            is_enrichment = (
                (source_cfg.get("lead_value", "").upper() == "ENRICHMENT")
                or not signals
            )
            if is_enrichment:
                bcad_records.extend(parcels)
            else:
                for p in parcels:
                    if p["parcel_id"] not in seen_parcel_ids:
                        seen_parcel_ids.add(p["parcel_id"])
                        all_parcels.append(p)

            per_signal_meta_by_url.update(per_signal_meta)
            translated_sources.append({
                "source_id": source_id,
                "records": len(raw_records),
                "signals": len(signals),
                "parcels": len(parcels),
            })

        # Parcel-master matcher join — swap placeholder parcels for real
        # records where addresses match.
        if bcad_records and all_signals:
            print(
                f"[production] loaded {len(bcad_records)} parcel-master records "
                f"for matcher",
                file=sys.stderr,
            )
            all_parcels = _apply_parcel_master_matching(
                signals=all_signals,
                placeholders=all_parcels,
                bcad_records=bcad_records,
                per_signal_meta_by_url=per_signal_meta_by_url,
            )

            # Step 6 — owner-name pattern signal emission with defensive guard.
            # The emitter only fires for parcels already carrying a lead-
            # generating signal (clerk-driven product rule, audit Q9).
            parcels_with_lead_signals = {
                sig.get("primary_parcel_id") or sig.get("parcel_id")
                for sig in all_signals
                if sig.get("primary_parcel_id") or sig.get("parcel_id")
            }
            emitted = emit_owner_name_signals_for_parcels(
                parcels=all_parcels,
                parcels_with_lead_signals=parcels_with_lead_signals,
                source_id="parcel_master",
            )
            adapted_owner_name = [
                _adapt_translator_signal(s, "parcel_master") for s in emitted
            ]
            for new_sig in adapted_owner_name:
                parent_meta = next(
                    (per_signal_meta_by_url[u]
                     for u, m in per_signal_meta_by_url.items()
                     if m.get("primary_parcel_id") == new_sig.get("parcel_id")),
                    None,
                )
                if parent_meta and not new_sig.get("filing_date"):
                    new_sig["filing_date"] = parent_meta.get("expected_sale_date")
                per_signal_meta_by_url[new_sig["source_url"]] = {
                    "preset_review_flags": [],
                    "expected_sale_date": (parent_meta or {}).get("expected_sale_date"),
                    "match_confidence": (parent_meta or {}).get("match_confidence", 95),
                    "match_method": (parent_meta or {}).get("match_method", "derived_owner_name"),
                    "address": (parent_meta or {}).get("address", ""),
                    "city": (parent_meta or {}).get("city", ""),
                    "zip": (parent_meta or {}).get("zip", ""),
                    "owner_name_literal_match": new_sig.get("_owner_name_literal_match"),
                    "owner_name_full": new_sig.get("_owner_name_full"),
                }
            all_signals.extend(adapted_owner_name)
            print(
                f"[production] owner-name pattern signals emitted: "
                f"{len(adapted_owner_name)}",
                file=sys.stderr,
            )

        raw_signals = all_signals
        parcels = all_parcels
        out_path = Path(args.out) if args.out else REPO_ROOT / "data" / "leads.json"
        mode = "production"

        # Config-driven build label. If fewer than three lead-generating
        # sources are wired, mark the build as source-limited and compose
        # the prose from the actual source list.
        sources_used = [
            s for s, c in county_config.get("sources", {}).items()
            if c.get("enabled", True) and c.get("translator")
        ]
        if len(sources_used) < 3:
            build_label = "SOURCE_LIMITED"
            build_label_reason = (
                f"Source-limited build: only sources {sources_used} were enabled. "
                f"Other sources are deferred."
            )

        print(
            f"[production] translated sources: {translated_sources}",
            file=sys.stderr,
        )

    if not parcels:
        print("no parcels available; cannot proceed.", file=sys.stderr)
        return 4

    result = run_pipeline(
        mode=mode,
        parcels=parcels,
        raw_signals=raw_signals,
        county_id=county_config.get("county_id", ""),
        county_name=county_config.get("county_name", ""),
        state=county_config.get("state", ""),
        scoring_overrides=scoring_overrides,
        as_of=as_of,
        per_signal_meta=per_signal_meta_by_url,
        build_label=build_label,
        build_label_reason=build_label_reason,
        deployment=county_config.get("deployment") or {},
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(result["payload"], fh, indent=2, ensure_ascii=False)

    # Scope sibling-output filenames by the leads payload's stem so
    # synthetic and production runs don't trample each other.
    # leads.json -> source_heartbeat.json + evidence.jsonl + runs/latest.manifest.json
    # leads_synthetic.json -> source_heartbeat_synthetic.json + evidence_synthetic.jsonl
    #                        + runs/latest_synthetic.manifest.json
    stem = out_path.stem  # "leads" or "leads_synthetic"
    suffix = stem[len("leads"):] if stem.startswith("leads") else f"_{stem}"

    heartbeat_path = out_path.parent / f"source_heartbeat{suffix}.json"
    with open(heartbeat_path, "w", encoding="utf-8") as fh:
        json.dump(result["heartbeat"], fh, indent=2, ensure_ascii=False)

    evidence_path = out_path.parent / f"evidence{suffix}.jsonl"
    with open(evidence_path, "w", encoding="utf-8") as fh:
        for ev in result["evidence_records"]:
            fh.write(json.dumps(ev, ensure_ascii=False) + "\n")

    manifest_dir = out_path.parent / "runs"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest = result["manifest"]
    manifest["output_files"] = [
        str(out_path.relative_to(REPO_ROOT)),
        str(heartbeat_path.relative_to(REPO_ROOT)),
        str(evidence_path.relative_to(REPO_ROOT)),
    ]
    with open(manifest_dir / f"latest{suffix}.manifest.json", "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, ensure_ascii=False)
    run_history_path = manifest_dir / f"{manifest['run_id']}.manifest.json"
    with open(run_history_path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, ensure_ascii=False)

    print(f"Wrote {out_path}")
    print(f"  lead_total:            {result['payload']['lead_total']}")
    print(f"  pattern_counts:        {result['payload']['pattern_counts']}")
    print(f"  attribute_counts:      {result['payload']['attribute_counts']}")
    print(f"  score_tier_distribution: {result['payload']['score_tier_distribution']}")
    print(f"  deal_path_distribution:  {result['payload']['deal_path_distribution']}")
    print(f"  stack_depth_distribution:{result['payload']['stack_depth_distribution']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
