"""
tax_deed_auction_listing translator (Duval-specific).

Converts raw records from scrapers/tax_deed_sales.py (RealTaxDeed
portal) into framework signals.

Expected raw_payload fields:
    parcel_id    — Duval RE# (e.g. "000123-0000")
    address      — property address
    opening_bid  — opening bid amount (string)
    sale_status  — auction status (e.g. "scheduled")

Returns one signal per tax deed listing, doc_type = tax_deed.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from scaffold.pipeline.translators import register

CANONICAL_DOC_TYPE = "tax_deed"


def _signal_id(source_id: str, raw_record_id: str) -> str:
    h = hashlib.sha1(
        f"{source_id}|{raw_record_id}".encode("utf-8")
    ).hexdigest()[:16]
    return f"sig_{h}"


@register("tax_deed_auction_listing")
def translate_tax_deed_listing(
    raw_records: list[dict],
    county_config: dict,
    source_config: dict,
) -> tuple[list[dict], list[dict], dict[str, dict]]:
    signals: list[dict] = []
    parcels: list[dict] = []
    per_signal_meta: dict[str, dict] = {}
    now = (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )

    source_id = source_config.get("_source_id", "tax_deed_sales")
    field_map = source_config.get("field_map")

    seen_parcels: set = set()

    for rec in raw_records:
        payload = rec.get("raw_payload") or {}
        if field_map:
            mapped = dict(payload)
            for canonical, source_field in field_map.items():
                if source_field in mapped:
                    mapped[canonical] = mapped.pop(source_field)
            payload = mapped

        parcel_id = (payload.get("parcel_id") or "").strip()
        address = (payload.get("address") or "").strip()
        opening_bid = (payload.get("opening_bid") or "").strip()
        sale_status = (payload.get("sale_status") or "scheduled").strip()

        if not parcel_id:
            continue

        if parcel_id not in seen_parcels:
            seen_parcels.add(parcel_id)
            parcels.append({
                "parcel_id": parcel_id,
                "source_id": source_id,
                "situs_address": address,
                "owner_name": "",
                "situs_city": "",
                "situs_zip": "",
                "source_fetched_at": rec.get("source_fetched_at", now),
            })

        sig_id = _signal_id(source_id, rec.get("raw_record_id", ""))

        signal = {
            "signal_id": sig_id,
            "raw_record_id": rec.get("raw_record_id", ""),
            "source_id": source_id,
            "source_url": rec.get("source_url", ""),
            "source_fetched_at": rec.get("source_fetched_at", now),
            "doc_type": CANONICAL_DOC_TYPE,
            "doc_type_subtype_label": f"Tax Deed — {sale_status}",
            "doc_number": parcel_id,
            "filing_date": "",
            "primary_parcel_id": parcel_id,
            "grantor": "",
            "grantee": "",
            "consideration": opening_bid,
            "case_number": "",
            "lead_pattern": "tax",
            "parser_confidence": rec.get("parser_confidence", 85),
            "translator": "tax_deed_auction_listing",
            "translated_at": now,
        }
        signals.append(signal)
        per_signal_meta[sig_id] = {
            "opening_bid": opening_bid,
            "sale_status": sale_status,
        }

    return signals, parcels, per_signal_meta
