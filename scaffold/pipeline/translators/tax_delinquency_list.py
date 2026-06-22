"""
tax_delinquency_list translator.

Converts raw records from scrapers/tax_collector.py (Duval Tax Collector /
LienHub portal) into framework signals.

Expected raw_payload fields:
    parcel_id          — Duval RE# (e.g. "000123-0000")
    situs_address      — property address
    tax_year           — tax year (string)
    tax_due            — amount due (numeric string)
    certificate_status — certificate status (sold/unsold/held/auction_scheduled)
    auction_date       — scheduled auction date if applicable

Returns one signal per listing, doc_type = tax_sale_certificate.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from scaffold.pipeline.translators import register

CANONICAL_DOC_TYPE = "tax_sale_certificate"


def _signal_id(source_id: str, raw_record_id: str) -> str:
    h = hashlib.sha1(
        f"{source_id}|{raw_record_id}".encode("utf-8")
    ).hexdigest()[:16]
    return f"sig_{h}"


@register("tax_delinquency_list")
def translate_tax_delinquency(
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

    source_id = source_config.get("_source_id", "tax_collector")
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
        if not parcel_id:
            continue

        address = (payload.get("situs_address") or "").strip()
        tax_year = (payload.get("tax_year") or "").strip()
        tax_due = (payload.get("tax_due") or "").strip()
        cert_status = (payload.get("certificate_status") or "unknown").strip()
        auction_date = (payload.get("auction_date") or "").strip()

        status_label = cert_status.replace("_", " ").title()
        filing_date = auction_date or f"{tax_year}-01-01" if tax_year else ""

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
            "doc_type_subtype_label": f"Tax Certificate — {status_label}",
            "doc_number": f"{tax_year}-{parcel_id}" if tax_year else parcel_id,
            "filing_date": filing_date,
            "primary_parcel_id": parcel_id,
            "grantor": "",
            "grantee": "",
            "consideration": tax_due,
            "case_number": "",
            "lead_pattern": "tax",
            "parser_confidence": rec.get("parser_confidence", 80),
            "translator": "tax_delinquency_list",
            "translated_at": now,
        }
        signals.append(signal)
        per_signal_meta[sig_id] = {
            "tax_year": tax_year,
            "certificate_status": cert_status,
            "auction_date": auction_date,
        }

    return signals, parcels, per_signal_meta
