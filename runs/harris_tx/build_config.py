"""
Build and write the populated Harris County, TX config via the framework's
locked atomic writer (scaffold/ops/write_county_config.py), following
MASTER_PROMPT Section 4.28. This script wiring-merges into the existing
config instead of overwriting.

Run with:
    python3 runs/harris_tx/build_config.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from scaffold.ops.write_county_config import write_county_config  # noqa: E402


def build_config() -> dict:
    return {
        "sources": {
            "clerk_recordings": {
                "access_pattern": "static_html",
                "recommended_adapter": "requests_form_scraper",
                "scraper_module": "scrapers/clerk_recordings.py",
                "category": "lead",
                "subtype": "clerk_recordings",
            },
            "foreclosure_notices_map": {
                "access_pattern": "public_records_only",
                "recommended_adapter": "requests_listing_scraper",
                "scraper_module": "scrapers/tax_sales_listing.py",
                "category": "lead",
                "subtype": "tax_delinquency",
            },
            "tax_collector": {
                "access_pattern": "static_html",
                "recommended_adapter": "requests_form_scraper",
                "scraper_module": "scrapers/tax_collector.py",
                "category": "lead",
                "subtype": "tax_delinquency",
            },
            "court_civil": {
                "access_pattern": "public_records_only",
                "recommended_adapter": "login_required_search_or_dataset",
                "scraper_module": "scrapers/court_civil.py",
                "category": "lead",
                "subtype": "court_civil",
            },
            "court_eviction": {
                "access_pattern": "static_html",
                "recommended_adapter": "jp_case_search_if_exposed",
                "scraper_module": "",
                "category": "lead",
                "subtype": "court_eviction",
            },
            "parcel_master": {
                "access_pattern": "spa_with_api",
                "recommended_adapter": "gis_public_data_or_search_scraper",
                "scraper_module": "scrapers/parcel_master.py",
                "category": "enrichment",
                "subtype": "parcel_master",
            },
            "gis_parcels": {
                "access_pattern": "public_records_only",
                "recommended_adapter": "dataset_download_scraper",
                "scraper_module": "scrapers/parcel_lookup.py",
                "category": "enrichment",
                "subtype": "gis_parcels",
            },
        }
    }


def _drop_keys(d: dict, keys: set[str]) -> dict:
    return {k: v for k, v in d.items() if k not in keys}


def main() -> None:
    target = REPO_ROOT / "config" / "counties" / "harris_tx.json"
    schema = REPO_ROOT / "config" / "counties" / "_schema.json"
    target.parent.mkdir(parents=True, exist_ok=True)

    existing = {}
    if target.exists():
        try:
            existing = json.loads(target.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = {}

    patch = build_config()
    merged = dict(existing)
    for src_name, src_patch in patch.get("sources", {}).items():
        current = merged.get("sources", {}).get(src_name, {})
        merged.setdefault("sources", {})[src_name] = {**current, **src_patch}

    result = write_county_config(
        config_dict=merged,
        target_path=str(target),
        schema_path=str(schema),
        overwrite=True,
    )
    print(result.summary())


if __name__ == "__main__":
    main()
