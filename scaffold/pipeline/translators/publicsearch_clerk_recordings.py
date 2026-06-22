"""
publicsearch_clerk_recordings translator (built-in, v5.1.2-beta-r3+).

Converts NORMALIZED clerk-recording records (produced by a county-side
scraper like scrapers/official_records.py) into framework signals +
placeholder parcels.

This translator processes recorded documents from a county clerk's
official records portal (typically Tyler OnCore or similar). Documents
include deeds, mortgages, liens, lis_pendens, judgments, and other
recorded instruments.

Expected raw_payload fields from scraper:
    doc_number      — instrument number
    doc_type        — document type label from the portal
    record_date     — recording date (YYYY-MM-DD)
    grantor         — grantor name(s), semicolon-joined
    grantee         — grantee name(s), semicolon-joined
    consideration   — sale consideration amount (numeric string)
    book_number     — recording book number
    page_number     — recording page number
    case_number     — associated court case number
    detail_url      — deep link to the record detail page

Canonical document types that generate leads:
    LIS_PENDENS, NOTICE_OF_PENDENCY, NOTICE_OF_DEFAULT,
    JUDGMENT, TAX_LIEN, MECHANICS_LIEN, PROBATE,
    NOTICE_OF_FORECLOSURE_SALE, NOTICE_OF_SALE

Enrichment-only document types:
    WARRANTY_DEED, QUITCLAIM_DEED, TRUSTEE_DEED, DEED_OF_TRUST,
    MORTGAGE, ASSIGNMENT, SATISFACTION, RELEASE
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from scaffold.pipeline.translators import register
from scaffold.pipeline.normalize import normalize_doc_type
from scaffold.pipeline.doc_type_bridge import monolith_to_registry


LEAD_GENERATING_KEYWORDS = [
    "lis pendens", "notice of pendency", "notice of default",
    "judgment", "tax lien", "mechanic's lien", "mechanics lien",
    "probate", "notice of foreclosure", "foreclosure sale",
    "notice of sale", "estate", "executor", "administrator",
    "guardianship", "bankruptcy", "eviction", "writ",
    "tax deed", "code enforcement", "code violation",
    "ucc", "finance statement", "federal tax lien", "state tax lien",
    "construction lien", "hoa lien", "homeowners association",
    "notice of commencement", "notice commencement",
    "claim of lien", "lien",
    "warrant", "death certificate",
]

ENRICHMENT_KEYWORDS = [
    "deed", "mortgage", "assignment", "satisfaction",
    "release", "subordination", "modification", "extension",
    "power of attorney", "affidavit", "certificate",
]


def _detect_lead_pattern(doc_type: str) -> str:
    dt = doc_type.lower().strip()
    for kw in ["lis pendens", "foreclosure", "notice of default",
               "notice of sale", "sheriff sale"]:
        if kw in dt:
            return "foreclosure"
    for kw in ["tax lien", "tax deed", "tax certificate"]:
        if kw in dt:
            return "tax"
    if "probate" in dt or "estate" in dt or "executor" in dt:
        return "estate"
    if "bankruptcy" in dt:
        return "bankruptcy"
    if "eviction" in dt:
        return "eviction"
    if "ucc" in dt or "finance statement" in dt:
        return "ucc"
    if "mechanic" in dt or "construction" in dt or "claim of lien" in dt:
        return "mechanics_lien"
    if "hoa" in dt or "homeowners" in dt:
        return "hoa_lien"
    if "federal tax" in dt or "state tax" in dt or "irs" in dt:
        return "tax_lien"
    if "lien" in dt:
        return "lien"
    if "judgment" in dt:
        return "lien"
    if "code" in dt:
        return "code"
    return "transfer"


def _is_lead_generating(doc_type: str) -> bool:
    dt = doc_type.lower().strip()
    for kw in LEAD_GENERATING_KEYWORDS:
        if kw in dt:
            return True
    return False


def _signal_id(prefix: str, raw_record_id: str) -> str:
    h = hashlib.sha1(
        f"{prefix}|{raw_record_id}".encode("utf-8")
    ).hexdigest()[:16]
    return f"sig_{h}"


def _apply_field_map(payload: dict, field_map: dict | None) -> dict:
    if not field_map:
        return payload
    mapped = dict(payload)
    for canonical, source_field in field_map.items():
        if source_field in mapped:
            mapped[canonical] = mapped.pop(source_field)
    return mapped


# Party role assignment: map doc_type to which party is the debtor/defendant
# vs plaintiff/filer/creditor.  §17 rules define expected name_type per
# canonical_doc_type.  The raw OR data supplies only grantor/GR and
# grantee/GE; we add defendant/DF, plaintiff/PL, and taxpayer/TP fields
# so the §17 engine can resolve debtors correctly per its rule table.
def _assign_party_roles(canonical_doc_type: str, doc_type: str,
                        grantor: str, grantee: str) -> dict:
    """Return {plaintiff, defendant, taxpayer} for the signal."""
    roles: dict = {"plaintiff": "", "defendant": "", "taxpayer": ""}
    dt = doc_type.lower()
    cdt = str(canonical_doc_type or "").lower()

    if cdt in ("lis_pendens",):
        roles["plaintiff"] = grantor
        roles["defendant"] = grantee
        roles["taxpayer"] = grantee
    elif cdt in ("judgment_lien", "civil_judgment", "abstract_of_judgment"):
        roles["defendant"] = grantor
        roles["plaintiff"] = grantee
    elif cdt in ("federal_tax_lien", "state_tax_lien"):
        roles["taxpayer"] = grantee
        roles["plaintiff"] = grantor
    elif cdt in ("writ_of_possession",):
        roles["defendant"] = grantee
        roles["plaintiff"] = grantor
    elif cdt in ("mechanics_lien", "construction_lien", "hoa_lien"):
        # §17 expects debtor in GR for mechanics_lien; OR data puts the
        # contractor/lienholder as GR.  No additional role needed.
        pass
    elif cdt in ("probate", "affidavit_of_heirship"):
        # §17 expects debtor in GR.
        pass
    elif cdt in ("ucc_financing_statement",):
        # Not in §17 rules → routed to REVIEW_REQUIRED by default.
        pass
    elif "warrant" in dt:
        roles["defendant"] = grantee
        roles["plaintiff"] = grantor
    elif "death certificate" in dt:
        roles["defendant"] = grantor
    elif "notice commencement" in dt:
        pass  # GR is the property owner; §17 mechanics_lien rule applies
    else:
        # General fallback for unclassified lead types
        roles["defendant"] = grantee or grantor
        roles["plaintiff"] = grantor if grantee else ""

    return roles


@register("publicsearch_clerk_recordings")
def translate_clerk_recordings(
    raw_records: list[dict],
    county_config: dict,
    source_config: dict,
) -> tuple[list[dict], list[dict], dict]:
    signals: list[dict] = []
    parcels: list[dict] = []
    per_signal_meta: dict = {}
    now = (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )

    translator_cfg = source_config.get("translator_config") or {}
    field_map = source_config.get("field_map")
    doc_type_synonyms = source_config.get("doc_type_synonyms") or {}

    parcel_id_prefix = source_config.get("parcel_id_prefix", "CLRK-")
    source_id = source_config.get("_source_id", "unknown")

    seen_parcels: set = set()

    for rec in raw_records:
        payload_raw = rec.get("raw_payload") or {}
        payload = _apply_field_map(payload_raw, field_map)

        doc_type = (payload.get("doc_type") or "").strip()
        if not doc_type:
            continue

        doc_number = (payload.get("doc_number") or "").strip()
        record_date = (payload.get("record_date") or "").strip()
        grantor = (payload.get("grantor") or "").strip()
        grantee = (payload.get("grantee") or "").strip()
        consideration = (payload.get("consideration") or "").strip()
        case_number = (payload.get("case_number") or "").strip()

        norm = normalize_doc_type(doc_type, county_synonyms=doc_type_synonyms)
        normalized_upper = norm.get("normalized_doc_type")
        if not normalized_upper:
            continue

        canonical_doc_type = monolith_to_registry(normalized_upper)
        if canonical_doc_type is None:
            canonical_doc_type = normalized_upper.upper() if normalized_upper else ""

        lead_pattern = _detect_lead_pattern(doc_type)
        is_lead = _is_lead_generating(doc_type)

        if not is_lead:
            continue

        parcel_id = f"{parcel_id_prefix}{doc_number}"
        if parcel_id not in seen_parcels:
            seen_parcels.add(parcel_id)
            parcels.append({
                "parcel_id": parcel_id,
                "source_id": source_id,
                "situs_address": "",
                "owner_name": grantee or grantor or "",
                "situs_city": "",
                "situs_zip": "",
                "source_fetched_at": rec.get("source_fetched_at", now),
            })

        sig_id = _signal_id(source_id, rec.get("raw_record_id", ""))
        roles = _assign_party_roles(canonical_doc_type, doc_type, grantor, grantee)

        signal = {
            "signal_id": sig_id,
            "raw_record_id": rec.get("raw_record_id", ""),
            "source_id": source_id,
            "source_url": rec.get("source_url", ""),
            "source_fetched_at": rec.get("source_fetched_at", now),
            "doc_type": canonical_doc_type,
            "doc_type_subtype_label": doc_type,
            "doc_number": doc_number,
            "filing_date": record_date,
            "primary_parcel_id": parcel_id,
            "grantor": grantor,
            "grantee": grantee,
            "plaintiff": roles["plaintiff"],
            "defendant": roles["defendant"],
            "taxpayer": roles["taxpayer"],
            "consideration": consideration,
            "case_number": case_number,
            "lead_pattern": lead_pattern,
            "parser_confidence": rec.get("parser_confidence", 85),
            "translator": "publicsearch_clerk_recordings",
            "translated_at": now,
        }
        signals.append(signal)
        per_signal_meta[sig_id] = {
            "normalized_doc_type": normalized_upper,
            "is_lead_generating": is_lead,
        }

    return signals, parcels, per_signal_meta
