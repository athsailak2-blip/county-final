"""
Bexar County foreclosure-notices adapter — Phase 2 first scraper.

Pulls the current-month mortgage AND tax foreclosure notices from the
Bexar County Clerk-published ArcGIS map (`maps.bexar.org/foreclosures`)
via its underlying REST service at:

    https://maps.bexar.org/arcgis/rest/services/CC/ForeclosuresProd/MapServer

Layers:

    0 — Mortgage   (Notice of Substitute Trustee's Sale, etc.)
    1 — Tax        (Tax foreclosure notices)

Field schema (both layers, verified 2026-05-14):

    OBJECTID, ADDRESS, DOC_NUMBER, YEAR, MONTH, SCHOOL_DIST,
    TYPE, CITY, ZIP, Shape

The adapter writes one JSONL file per layer to
`data/raw/foreclosure_notices_map.jsonl` (deduped + change-tracked
relative to the prior run). Each line conforms to the framework raw
record shape (architecture/09_output_schemas.md §1).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scaffold.scrapers._arcgis_featureserver import (  # noqa: E402
    ArcGISFeatureServer,
)


SOURCE_ID = "foreclosure_notices_map"
SERVICE_URL = (
    "https://maps.bexar.org/arcgis/rest/services/CC/ForeclosuresProd/MapServer"
)
USER_AGENT = "xcerebro-bexar-foreclosure-notices/0.1 (+private repo)"

LAYERS = [
    {
        "layer_id": 0,
        "layer_name": "Mortgage",
        "category_hint": "mortgage_foreclosure",
    },
    {
        "layer_id": 1,
        "layer_name": "Tax",
        "category_hint": "tax_foreclosure",
    },
]


def _now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def _raw_record_id(layer_id: int, doc_number: str, address: str) -> str:
    """Stable hash for a record across re-runs."""
    key = "|".join(["bexar_foreclosure_map", str(layer_id),
                    (doc_number or "").strip().upper(),
                    (address or "").strip().upper()])
    return "raw_" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:24]


def _normalize_feature(feature: dict, layer_meta: dict, now: str) -> dict:
    attrs = feature.get("attributes", {}) or {}
    doc_number = (attrs.get("DOC_NUMBER") or "").strip()
    address = (attrs.get("ADDRESS") or "").strip()
    year = attrs.get("YEAR")
    month = attrs.get("MONTH")
    raw_type = (attrs.get("TYPE") or "").strip()

    # The map publishes month/year of recording only — no day. Use the
    # first-of-month as a conservative event_date proxy. Real day-of-
    # recording is in the Notice document itself (cross-link via
    # DOC_NUMBER to the PublicSearch portal in a downstream join).
    event_date = None
    if year and month:
        try:
            event_date = f"{int(year):04d}-{int(month):02d}-01"
        except (TypeError, ValueError):
            event_date = None

    raw_payload = {
        "doc_type": raw_type,
        "doc_number": doc_number,
        "address": address,
        "city": (attrs.get("CITY") or "").strip(),
        "zip": (attrs.get("ZIP") or "").strip(),
        "school_district": (attrs.get("SCHOOL_DIST") or "").strip(),
        "recording_year": year,
        "recording_month": month,
        "recording_event_date": event_date,
        "layer_id": layer_meta["layer_id"],
        "layer_name": layer_meta["layer_name"],
        "category_hint": layer_meta["category_hint"],
        "object_id": feature.get("_object_id"),
        "geometry": feature.get("geometry"),
    }

    return {
        "raw_record_id": _raw_record_id(layer_meta["layer_id"],
                                         doc_number, address),
        "source_id": SOURCE_ID,
        "source_url": (
            f"{SERVICE_URL}/{layer_meta['layer_id']}/query?"
            f"where=DOC_NUMBER%3D%27{doc_number}%27&outFields=*&f=json"
        ),
        "source_fetched_at": now,
        "raw_payload": raw_payload,
        "raw_text": None,
        "first_seen_at": now,
        "last_seen_at": now,
        "change_status": "NEW_RECORD",  # rewritten by merge step
        "parser_confidence": 95 if doc_number and address else 70,
    }


def _load_prior(path: Path) -> dict:
    """Map raw_record_id -> prior record, for change tracking."""
    if not path.exists():
        return {}
    out: dict = {}
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            rid = rec.get("raw_record_id")
            if rid:
                out[rid] = rec
    return out


def merge_with_prior(current: list, prior_by_id: dict) -> list:
    """Annotate each record with change_status against the prior run."""
    out = []
    current_ids = set()
    for rec in current:
        rid = rec["raw_record_id"]
        current_ids.add(rid)
        prev = prior_by_id.get(rid)
        if prev is None:
            rec["change_status"] = "NEW_RECORD"
        else:
            rec["first_seen_at"] = prev.get("first_seen_at", rec["first_seen_at"])
            rec["last_seen_at"] = rec["source_fetched_at"]
            if prev.get("raw_payload") == rec["raw_payload"]:
                rec["change_status"] = "SAME"
            else:
                rec["change_status"] = "UPDATED"
        out.append(rec)
    # Records present in prior but absent now are stale; preserve them
    # for ttl/expiry tracking downstream.
    for rid, prev in prior_by_id.items():
        if rid in current_ids:
            continue
        prev = dict(prev)
        prev["change_status"] = "DISAPPEARED"
        out.append(prev)
    return out


def fetch_all(server: ArcGISFeatureServer, *,
              where: str = "1=1",
              max_features: int | None = None) -> Iterable[dict]:
    """Yield normalized raw records across BOTH layers."""
    now = _now_iso()
    for layer in LAYERS:
        for feat in server.iter_features(
            layer_id=layer["layer_id"],
            where=where,
            out_fields="*",
            return_geometry=True,
            max_features=max_features,
        ):
            yield _normalize_feature(feat, layer, now)


def run(*, output_path: Path | None = None,
        where: str = "1=1",
        max_features: int | None = None,
        fetch_fn=None) -> dict:
    """Run the scraper end-to-end. Returns a small stats blob."""
    output_path = output_path or REPO_ROOT / "data" / "raw" / "foreclosure_notices_map.jsonl"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    server = ArcGISFeatureServer(SERVICE_URL,
                                  user_agent=USER_AGENT,
                                  fetch_fn=fetch_fn)
    current = list(fetch_all(server, where=where, max_features=max_features))
    prior = _load_prior(output_path)
    merged = merge_with_prior(current, prior)

    tmp = output_path.with_suffix(".jsonl.tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        for rec in merged:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    tmp.replace(output_path)

    stats = {
        "source_id": SOURCE_ID,
        "service_url": SERVICE_URL,
        "current_count": len(current),
        "prior_count": len(prior),
        "total_after_merge": len(merged),
        "new_record_count": sum(1 for r in merged if r["change_status"] == "NEW_RECORD"),
        "same_record_count": sum(1 for r in merged if r["change_status"] == "SAME"),
        "updated_record_count": sum(1 for r in merged if r["change_status"] == "UPDATED"),
        "disappeared_record_count": sum(1 for r in merged if r["change_status"] == "DISAPPEARED"),
        "output_path": str(output_path),
    }
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Pull Bexar County foreclosure notices via ArcGIS REST."
    )
    parser.add_argument("--out",
                        default=None,
                        help="Output JSONL path. Default: data/raw/foreclosure_notices_map.jsonl")
    parser.add_argument("--where", default="1=1",
                        help="ArcGIS WHERE clause (e.g. 'YEAR>=2026').")
    parser.add_argument("--max-features", type=int, default=None,
                        help="Cap on records pulled (testing).")
    args = parser.parse_args()

    out = Path(args.out) if args.out else None
    stats = run(output_path=out, where=args.where, max_features=args.max_features)
    print(json.dumps(stats, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
