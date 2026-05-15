"""
Source-specific raw-record translators.

Each scraper emits raw records in a source-shaped JSONL (the framework
raw-record envelope from `architecture/09_output_schemas.md` §1).
Before those records can flow through the universal pipeline
(normalize -> stack -> score -> classify), they need to be translated
into the pipeline's normalize-ready signal shape AND paired with a
parcel record (synthesized from the raw record's address fields when a
real parcel master is not yet wired).

The translator API is intentionally narrow:

    translate(raw_records, *, county_config) -> (signals, parcels)

`signals` is a list of dicts shaped like
`scaffold/data/synthetic_signals.jsonl` rows (parcel_id, source,
source_url, pattern, subtype, filing_date, plus any source-specific
extra fields the downstream pipeline should preserve as evidence).

`parcels` is a list of dicts shaped like
`scaffold/data/synthetic_parcels.jsonl` rows. When no real parcel
master is available the translator synthesizes a minimal parcel
(parcel_id derived from the address, situs_* fields populated, all
enrichment fields empty/None).
"""

from __future__ import annotations

import hashlib
from datetime import date, timedelta


# ---------------------------------------------------------------------
# Bexar-specific accepted-city set
# ---------------------------------------------------------------------
# All known Bexar County municipalities (incorporated, from
# bexar_tx.json geography.municipalities) PLUS unincorporated Bexar
# communities observed in the foreclosure feed. Anything outside this
# set on a Bexar source's record is flagged
# `potential_cross_county_leak` per REVIEW_GATE_3 operator decision.
#
# This set lives in code (not config) because:
#   1. It is a derived QA list, not a primary config artifact.
#   2. New unincorporated communities discovered on subsequent runs
#      get added here as the operator confirms them.
#   3. The Bexar municipalities authoritative list IS in the county
#      config; this is its case-insensitive normalization + the
#      unincorporated-community extension.
BEXAR_ACCEPTED_CITIES = frozenset({
    # incorporated municipalities (config-derived)
    "SAN ANTONIO", "ALAMO HEIGHTS", "BALCONES HEIGHTS", "CASTLE HILLS",
    "CHINA GROVE", "CONVERSE", "ELMENDORF", "FAIR OAKS RANCH", "HELOTES",
    "HILL COUNTRY VILLAGE", "HOLLYWOOD PARK", "KIRBY", "LEON VALLEY",
    "LIVE OAK", "OLMOS PARK", "SANDY OAKS", "SCHERTZ", "SELMA",
    "SHAVANO PARK", "SOMERSET", "TERRELL HILLS", "UNIVERSAL CITY",
    "VON ORMY", "WINDCREST",
    # St. Hedwig spelling variants (Bexar incorporated municipality)
    "ST. HEDWIG", "SAINT HEDWIG", "ST HEDWIG",
    # known unincorporated Bexar communities seen in the foreclosure
    # feed -- accepted as legitimate Bexar parcels.
    "ADKINS", "ATASCOSA", "MACDONA", "EARLE",
})


# ---------------------------------------------------------------------
# Tex. Prop. Code Sec. 51.002 — non-judicial trustee sale date
# ---------------------------------------------------------------------

def first_tuesday_of_month(year: int, month: int) -> date | None:
    """
    Returns the date of the first Tuesday of the given month.

    Per Tex. Prop. Code Sec. 51.002, non-judicial trustee sales fall on
    the first Tuesday of each month. If that day is January 1 or July 4,
    the sale shifts to the first Wednesday (also per the statute).
    """
    if not year or not month:
        return None
    try:
        d = date(year, month, 1)
    except (ValueError, TypeError):
        return None
    # Monday is weekday 0; Tuesday is weekday 1.
    offset = (1 - d.weekday()) % 7
    first_tue = d + timedelta(days=offset)
    # Statute holiday shift
    if first_tue == date(year, 1, 1) or first_tue == date(year, 7, 4):
        return first_tue + timedelta(days=1)
    return first_tue


# ---------------------------------------------------------------------
# foreclosure_notices_map translator
# ---------------------------------------------------------------------

# Layer-to-canonical doc-type assignments per REVIEW_GATE_3
# operator decision 1: all Mortgage-layer records map to
# NOTICE_OF_SUBSTITUTE_TRUSTEE_SALE (the dominant Texas non-judicial
# form); all Tax-layer records map to TAX_FORECLOSURE_NOTICE.
_LAYER_DOC_TYPE = {
    0: ("NOTICE_OF_SUBSTITUTE_TRUSTEE_SALE", "Notice of Substitute Trustee's Sale", "foreclosure"),
    1: ("TAX_FORECLOSURE_NOTICE", "Tax Foreclosure Notice", "tax"),
}


def _normalize_city(city: str) -> str:
    return (city or "").strip().upper()


def _parcel_id_from_address(address: str, city: str, zip_code: str) -> str:
    """Stable, deterministic parcel_id placeholder until Phase 4
    parcel matcher replaces it with a real BCAD parcel ID."""
    norm = "|".join([
        (address or "").strip().upper(),
        (city or "").strip().upper(),
        (zip_code or "").strip(),
    ])
    h = hashlib.sha1(norm.encode("utf-8")).hexdigest()[:12]
    return f"BX-ADDR-{h.upper()}"


def translate_foreclosure_notices_map(
    raw_records: list,
    *,
    accepted_cities: set | frozenset = BEXAR_ACCEPTED_CITIES,
) -> tuple:
    """
    Convert foreclosure_notices_map raw records into pipeline-ready
    (signals, parcels, per_signal_metadata) tuple.

    `signals` and `parcels` mirror the shape of the synthetic JSONL
    fixtures so the existing pipeline accepts them unchanged.

    `per_signal_metadata` is a parallel list (one entry per signal)
    carrying upstream-derived review flags and proof references that
    the pipeline should attach to the resulting lead WITHOUT
    propagating them through the synthetic-shaped signal envelope.
    """
    signals: list = []
    parcels: list = []
    per_signal_meta: list = []
    seen_parcel_ids: set = set()

    for raw in raw_records:
        payload = raw.get("raw_payload") or {}
        layer_id = payload.get("layer_id")
        canonical, subtype_label, pattern = _LAYER_DOC_TYPE.get(
            layer_id, (None, payload.get("doc_type"), None)
        )

        address = (payload.get("address") or "").strip()
        city = _normalize_city(payload.get("city") or "")
        zip_code = (payload.get("zip") or "").strip()
        doc_number = (payload.get("doc_number") or "").strip()
        event_date = payload.get("recording_event_date")
        year = payload.get("recording_year")
        month = payload.get("recording_month")

        parcel_id = _parcel_id_from_address(address, city, zip_code)

        # Synthesize a thin parcel record on first sight of this address.
        # Phase 4 will replace these with real BCAD parcel records.
        if parcel_id not in seen_parcel_ids:
            seen_parcel_ids.add(parcel_id)
            parcels.append({
                "parcel_id": parcel_id,
                "situs_address": address,
                "situs_city": city.title(),
                "situs_state": "TX",
                "situs_zip": zip_code,
                "mun_name": city.title(),
                "mun_code": city.replace(" ", "_").lower()[:8],
                "owner_name": "Unknown (pending parcel-master enrichment)",
                "owner_mailing_addr1": "",
                "owner_mailing_city": "",
                "owner_mailing_state": "",
                "owner_mailing_zip": "",
                "year_built": None,
                "assessed_value": None,
                "land_value": None,
                "improvement_value": None,
                "last_sale_date": None,
                "last_sale_price": None,
                "property_class": None,
                "acreage": None,
                # Marker so downstream code knows this is a placeholder
                # parcel, NOT a real parcel-master row.
                "_placeholder": True,
                "_source_record_id": raw.get("raw_record_id"),
            })

        signal_row = {
            "parcel_id": parcel_id,
            "source": raw.get("source_id"),
            "source_url": raw.get("source_url"),
            "raw_record_id": raw.get("raw_record_id"),
            "pattern": pattern,
            "subtype": subtype_label,
            "filing_date": event_date,
            "doc_number": doc_number,
            "recording_year": year,
            "recording_month": month,
            # No amounts published on the map.
            "amount": None,
            "_synthetic": False,
        }

        # Per REVIEW_GATE_3 op decision 3: expected_sale_date = first
        # Tuesday of recording_month (Jan-1 / July-4 -> Wednesday).
        sale_date = first_tuesday_of_month(year, month)
        signal_row["expected_sale_date"] = sale_date.isoformat() if sale_date else None

        # Per op decision 2: cross-county leak detection.
        review_flags: list = []
        if city and city not in accepted_cities:
            review_flags.append("potential_cross_county_leak")
        if not doc_number or not address:
            review_flags.append("incomplete_source_record")

        per_signal_meta.append({
            "preset_review_flags": review_flags,
            "expected_sale_date": signal_row["expected_sale_date"],
            "doc_number": doc_number,
            "school_district": (payload.get("school_district") or "").strip(),
            "address": address,
            "city": city,
            "zip": zip_code,
            "raw_record_url": raw.get("source_url"),
            "layer_id": layer_id,
        })

        signals.append(signal_row)

    return signals, parcels, per_signal_meta
