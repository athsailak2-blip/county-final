"""
foreclosure_auction_calendar translator (Duval-specific).

Converts raw records from scrapers/foreclosure_sales.py (RealForeclose
auction calendar) into framework signals.

Expected raw_payload fields:
    auction_day      — day of month (string)
    active_count     — number of active foreclosure auctions
    total_count      — total number of listings
    sale_time        — scheduled sale time (e.g. "11:00 AM ET")

Returns one signal per auction day, doc_type = notice_of_sale.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from scaffold.pipeline.translators import register
from scaffold.pipeline.normalize import normalize_doc_type
from scaffold.pipeline.doc_type_bridge import monolith_to_registry

CANONICAL_DOC_TYPE = "notice_of_sale"


def _signal_id(source_id: str, auction_key: str) -> str:
    h = hashlib.sha1(
        f"{source_id}|{auction_key}".encode("utf-8")
    ).hexdigest()[:16]
    return f"sig_{h}"


def _parcel_id(prefix: str, auction_key: str) -> str:
    h = hashlib.sha1(auction_key.encode("utf-8")).hexdigest()[:12].upper()
    return f"{prefix}{h}"


@register("foreclosure_auction_calendar")
def translate_foreclosure_auction(
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

    source_id = source_config.get("_source_id", "foreclosure_sales")
    parcel_id_prefix = source_config.get("parcel_id_prefix", "FCL-")
    year = source_config.get("calendar_year", datetime.now(timezone.utc).year)
    month = source_config.get("calendar_month", datetime.now(timezone.utc).month)

    seen_parcels: set = set()

    for rec in raw_records:
        payload = rec.get("raw_payload") or {}
        day = (payload.get("auction_day") or "").strip()
        if not day:
            continue

        active = payload.get("active_count", 0)
        total = payload.get("total_count", 0)
        sale_time = (payload.get("sale_time") or "11:00 AM ET").strip()

        filing_date = f"{year:04d}-{month:02d}-{int(day):02d}"
        auction_key = f"{year:04d}-{month:02d}-{day}"

        parcel_id = _parcel_id(parcel_id_prefix, auction_key)
        if parcel_id not in seen_parcels:
            seen_parcels.add(parcel_id)
            parcels.append({
                "parcel_id": parcel_id,
                "source_id": source_id,
                "situs_address": f"Auction Day {month}/{day}/{year}",
                "owner_name": "",
                "situs_city": "",
                "situs_zip": "",
                "source_fetched_at": rec.get("source_fetched_at", now),
            })

        sig_id = _signal_id(source_id, auction_key)

        signal = {
            "signal_id": sig_id,
            "raw_record_id": rec.get("raw_record_id", ""),
            "source_id": source_id,
            "source_url": rec.get("source_url", ""),
            "source_fetched_at": rec.get("source_fetched_at", now),
            "doc_type": CANONICAL_DOC_TYPE,
            "doc_type_subtype_label": f"Foreclosure Sale — {sale_time}",
            "doc_number": auction_key,
            "filing_date": filing_date,
            "primary_parcel_id": parcel_id,
            "grantor": "",
            "grantee": "",
            "consideration": "",
            "case_number": "",
            "lead_pattern": "foreclosure",
            "parser_confidence": rec.get("parser_confidence", 90),
            "translator": "foreclosure_auction_calendar",
            "translated_at": now,
        }
        signals.append(signal)
        per_signal_meta[sig_id] = {
            "active_count": active,
            "total_count": total,
            "sale_time": sale_time,
        }

    return signals, parcels, per_signal_meta
