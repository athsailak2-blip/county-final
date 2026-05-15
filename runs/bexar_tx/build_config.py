"""
Build and write the populated Bexar County, TX config via the framework's
locked atomic writer (scaffold/ops/write_county_config.py), per
MASTER_PROMPT.md Section 4.28. This script lives under runs/bexar_tx/
(operator-scoped, NOT framework-locked) and is invoked once by Claude
Code during Phase 0 Step 4.

Run with:
    python3 runs/bexar_tx/build_config.py

The script is idempotent only when overwrite=False is paired with a
pre-existing target. To re-run a recon and replace the existing config,
pass overwrite=True (Section 4.28.6).
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from scaffold.ops.write_county_config import write_county_config  # noqa: E402


PHASE0_TIMESTAMP = "2026-05-14T15:55:00Z"


def _source_skeleton() -> dict:
    """Default proof-packet fields shared by every source block."""
    return {
        "url": "",
        "official_status": "",
        "lead_value": "",
        "operator_override": False,
        "source_reliability_grade": "",
        "source_priority": "",
        "build_priority": "",
        "enabled": True,
        "paused_reason": "",
        "pause_until": "",
        "allowed_to_export": True,
        "source_freshness": "",
        "known_limitations": [],
        "last_verified_at": PHASE0_TIMESTAMP,
        "auth_required": False,
        "rate_limit_rpm": None,
        "fields": {},
        "doc_type_synonyms": {},
        "ttl_days": 365,
        "blocked_unblock_paths": [],
        "notes": "",
        "verification_note": "",
        "open_questions": [],
        "verified_from_url": "",
        "verification_method": "",
        "official_entity": "",
        "portal_type": "",
        "records_available": [],
        "search_fields": [],
        "access_method": "",
        "public_access_status": "",
        "document_access_status": "",
        "source_role": "",
        "verification_confidence": "",
        "sample_record_path_confirmed": False,
        "sample_record_type": "",
        "sample_search_possible": False,
        "sample_document_view_possible": False,
        "blocker": "",
        "next_access_strategy": "",
        "blocker_type": "",
        "auto_resolve_status": "NOT_ATTEMPTED",
        "final_resolution_status": "",
        "auto_resolve_attempts": [],
        "lifecycle_status": "ACTIVE",
        "suppression_reason": "",
        "expected_refresh_cadence": "",
        "source_freshness_status": "UNKNOWN",
        "stale_after_hours": None,
        "last_successful_fetch_at": "",
        "last_attempted_fetch_at": "",
        "last_record_seen_at": "",
        "record_ttl_days": None,
        "expire_if_not_seen_runs": None,
        "stale_record_policy": "",
        "quarantine_status": "NOT_QUARANTINED",
        "quarantine_reason": "",
        "estimated_runtime_minutes": None,
        "estimated_cost_category": "FREE",
        "portal_fingerprint_id": "",
        "portal_family": "",
        "fingerprinted_at": "",
        "fingerprint_confidence": "",
        "fingerprint_summary": "",
        "recommended_adapter": "",
        "credentials_required_kind": "",
        "credentials_declared": False,
        "manual_upload_path": "",
        "manual_upload_received_at": "",
    }


def _merge(*dicts: dict) -> dict:
    """Shallow-merge override dicts onto the skeleton; later wins."""
    out = _source_skeleton()
    for d in dicts:
        out.update(d)
    return out


def build_config() -> dict:
    # -------------------------------------------------------------------
    # SOURCES
    # -------------------------------------------------------------------

    clerk_recordings = _merge({
        "category": "lead",
        "subtype": "clerk_recordings",
        "url": "https://bexar.tx.publicsearch.us/",
        "access_pattern": "spa_with_api",
        "official_status": "OFFICIAL_VENDOR_PORTAL",
        "lead_value": "LEAD_GENERATING",
        "source_reliability_grade": "A",
        "source_priority": "P0",
        "build_priority": "high_value",
        "source_freshness": "DAILY",
        "scraper_module": "scrapers/clerk_seeded.py",
        "refresh_cadence": "daily",
        "ttl_days": 1095,
        "blocked_unblock_paths": [],
        "notes": (
            "PublicSearch / Neumo vendor portal hosting the Bexar County Clerk's "
            "Official Public Records (deeds, mortgages, liens, lis pendens, "
            "Notice of Trustee Sale, etc.). Officially linked from "
            "bexar.org/2950 (Real Property/Land Records)."
        ),
        "verification_note": (
            "Quick Search is publicly accessible with date-range, grantor/grantee, "
            "doc-type, doc-number search fields. Login is offered but optional. "
            "Document-image access policy not confirmed; index search is "
            "sufficient to detect lead-generating recording events."
        ),
        "open_questions": [
            "Confirm whether document image PDFs are free or paid on PublicSearch.",
            "Confirm rate-limit / robots policy with operator.",
        ],
        "verified_from_url": "https://www.bexar.org/2950/Real-PropertyLand-Records",
        "verification_method": "official_vendor_link",
        "official_entity": "Bexar County Clerk's Office",
        "portal_type": "land records / official public records search",
        "records_available": [
            "deeds", "mortgages", "deeds_of_trust", "liens",
            "lis_pendens", "notice_of_trustee_sale",
            "judgments", "federal_tax_liens", "release_of_lien",
            "assumed_name", "military_discharge",
        ],
        "search_fields": [
            "grantor_grantee_name", "document_type", "document_number",
            "subdivision", "date_range",
        ],
        "access_method": "SEARCHABLE_PUBLIC_PORTAL",
        "public_access_status": "PUBLIC_SEARCH_ONLY",
        "document_access_status": "DOCUMENTS_UNKNOWN",
        "source_role": "PRIMARY_LEAD_SOURCE",
        "verification_confidence": "HIGH",
        "sample_record_path_confirmed": True,
        "sample_record_type": "search_form",
        "sample_search_possible": True,
        "sample_document_view_possible": False,
        "blocker": "",
        "next_access_strategy": "",
        "expected_refresh_cadence": "DAILY",
        "stale_after_hours": 36,
        "record_ttl_days": 1095,
        "stale_record_policy": "KEEP_UNTIL_RELEASED",
        "portal_family": "publicsearch_neumo",
        "fingerprint_confidence": "MEDIUM",
        "fingerprint_summary": (
            "PublicSearch.us-hosted public records UI. SPA. Free quick search "
            "with date-range filters. Document image access likely cost-bearing."
        ),
        "recommended_adapter": "publicsearch_api_or_playwright",
        "estimated_runtime_minutes": 10,
        "estimated_cost_category": "FREE",
    })

    foreclosure_notices_map = _merge({
        "category": "lead",
        "subtype": "sheriff_sales",
        "url": "https://maps.bexar.org/foreclosures",
        "access_pattern": "spa_with_api",
        "official_status": "OFFICIAL_COUNTY",
        "lead_value": "LEAD_GENERATING",
        "source_reliability_grade": "A",
        "source_priority": "P0",
        "build_priority": "mvp_required",
        "source_freshness": "DAILY",
        "scraper_module": "scrapers/foreclosure_notices_map.py",
        "source_freshness_status": "FRESH",
        "last_successful_fetch_at": "2026-05-14T16:53:00Z",
        "last_attempted_fetch_at": "2026-05-14T16:53:00Z",
        "last_record_seen_at": "2026-05-14T16:53:00Z",
        "refresh_cadence": "daily",
        "ttl_days": 90,
        "blocked_unblock_paths": [],
        "notes": (
            "Bexar County Clerk-published map of the current month's mortgage "
            "AND tax foreclosure notices. CSV export, PDF export, document "
            "links. The single easiest P0 source — recommend MVP-first build."
        ),
        "verification_note": (
            "Free, no login. Provides data-table view, CSV export ('Export All "
            "to CSV' and 'Export Selected'), full-list PDF download, and "
            "out-links to foreclosure document PDFs. Backed by ArcGIS."
        ),
        "open_questions": [
            "Confirm month-rollover behavior: what happens to last month's "
            "notices once the new month begins?",
        ],
        "verified_from_url": "https://www.bexar.org/2950/Real-PropertyLand-Records",
        "verification_method": "official_page_link",
        "official_entity": "Bexar County Clerk's Office (GIS / Recordings Division)",
        "portal_type": "foreclosure notice map + tabular CSV export",
        "records_available": [
            "mortgage_foreclosure_notices", "tax_foreclosure_notices",
            "notice_of_trustee_sale", "sale_documents_pdf",
        ],
        "search_fields": [
            "address", "owner", "sale_date", "trustee", "map_bounds",
        ],
        "access_method": "MAP_LAYER",
        "public_access_status": "FULL_PUBLIC_ACCESS",
        "document_access_status": "DOCUMENTS_PUBLIC",
        "source_role": "PRIMARY_LEAD_SOURCE",
        "verification_confidence": "HIGH",
        "sample_record_path_confirmed": True,
        "sample_record_type": "map_layer",
        "sample_search_possible": True,
        "sample_document_view_possible": True,
        "expected_refresh_cadence": "DAILY",
        "stale_after_hours": 36,
        "record_ttl_days": 90,
        "stale_record_policy": "EXPIRE_IF_NOT_SEEN",
        "expire_if_not_seen_runs": 3,
        "portal_family": "arcgis_app",
        "fingerprint_confidence": "HIGH",
        "fingerprint_summary": (
            "Bexar County hosted ArcGIS web app exposing a current-month "
            "foreclosure-notice feature layer with CSV/PDF export and "
            "document-PDF out-links."
        ),
        "recommended_adapter": "arcgis_featureserver_or_csv_dump",
        "estimated_runtime_minutes": 3,
        "estimated_cost_category": "FREE",
    })

    court_civil = _merge({
        "category": "lead",
        "subtype": "court_civil",
        "url": "https://portal-txbexar.tylertech.cloud/Portal/",
        "access_pattern": "spa_with_api",
        "official_status": "OFFICIAL_COURT",
        "lead_value": "LEAD_GENERATING",
        "source_reliability_grade": "A",
        "source_priority": "P0",
        "build_priority": "high_value",
        "source_freshness": "DAILY",
        "scraper_module": "scrapers/court_civil.py",
        "refresh_cadence": "daily",
        "ttl_days": 1095,
        "blocked_unblock_paths": [],
        "notes": (
            "Tyler Technologies Odyssey-powered Justice Information Portal. "
            "Replaced search.bexar.org and apps.bexar.org/dklitsearch in a "
            "consolidated migration. Covers District Clerk Civil & Criminal "
            "records and dockets, County Clerk misdemeanors, hearings, jail, "
            "and bail bonds. Probate cases are also accessible via the same "
            "portal (declared as a separate source block for build clarity)."
        ),
        "verification_note": (
            "Public Smart Search confirmed; registration not required for "
            "public data. Vendor: Tyler Technologies. Free."
        ),
        "open_questions": [
            "Confirm civil case detail / document image access is free.",
            "Confirm Odyssey API access policy with operator / vendor.",
        ],
        "verified_from_url": "https://www.bexar.org/3856/New-Justice-Information-Portal",
        "verification_method": "official_page_link",
        "official_entity": "Bexar County District Clerk / County Clerk",
        "portal_type": "Tyler Odyssey court records portal",
        "records_available": [
            "civil_district_court_cases", "civil_district_court_dockets",
            "criminal_district_court_cases", "county_clerk_misdemeanors",
            "court_hearings", "jail_records", "bail_bond_records",
        ],
        "search_fields": [
            "party_name", "case_number", "date_range", "case_type", "court",
        ],
        "access_method": "SEARCHABLE_PUBLIC_PORTAL",
        "public_access_status": "PUBLIC_SEARCH_ONLY",
        "document_access_status": "DOCUMENTS_UNKNOWN",
        "source_role": "PRIMARY_LEAD_SOURCE",
        "verification_confidence": "HIGH",
        "sample_record_path_confirmed": True,
        "sample_record_type": "search_form",
        "sample_search_possible": True,
        "sample_document_view_possible": False,
        "expected_refresh_cadence": "DAILY",
        "stale_after_hours": 36,
        "record_ttl_days": 1095,
        "stale_record_policy": "KEEP_UNTIL_RELEASED",
        "portal_family": "tyler_odyssey",
        "fingerprint_confidence": "HIGH",
        "fingerprint_summary": (
            "Tyler Odyssey Portal v2 (tylertech.cloud). Smart Search across "
            "civil, criminal, misdemeanor, hearings, jail, bail bonds. Free "
            "public access; registration only for law-enforcement partners."
        ),
        "recommended_adapter": "tyler_odyssey_smart_search",
        "estimated_runtime_minutes": 8,
        "estimated_cost_category": "FREE",
    })

    court_probate = _merge({
        "category": "lead",
        "subtype": "court_probate",
        "url": "https://portal-txbexar.tylertech.cloud/Portal/",
        "access_pattern": "spa_with_api",
        "official_status": "OFFICIAL_COURT",
        "lead_value": "LEAD_GENERATING",
        "source_reliability_grade": "A",
        "source_priority": "P0",
        "build_priority": "high_value",
        "source_freshness": "DAILY",
        "scraper_module": "scrapers/court_probate.py",
        "refresh_cadence": "daily",
        "ttl_days": 1825,
        "blocked_unblock_paths": [],
        "notes": (
            "Probate court cases are filed with the County Clerk's Probate "
            "Department (100 Dolorosa, Suite 104) and indexed in the same "
            "Tyler Odyssey portal as civil. Declared as a separate source "
            "block because the lead pattern (estate openings, dependent "
            "administrations, heirship) is distinct from civil-distress patterns."
        ),
        "verification_note": (
            "Probate filings searchable through the consolidated Justice "
            "Information Portal. Texas Estates Code: probate records are "
            "public in most cases."
        ),
        "open_questions": [
            "Confirm whether the Tyler portal exposes case-type filter for probate.",
        ],
        "verified_from_url": "https://www.bexar.org/3396/Probate-Division",
        "verification_method": "official_page_link",
        "official_entity": "Bexar County Clerk - Probate Department / Probate Courts",
        "portal_type": "Tyler Odyssey probate records search",
        "records_available": [
            "probate_cases", "estate_openings", "heirship_proceedings",
            "guardianships", "dependent_administrations", "wills",
        ],
        "search_fields": [
            "decedent_name", "case_number", "filing_date_range",
        ],
        "access_method": "SEARCHABLE_PUBLIC_PORTAL",
        "public_access_status": "PUBLIC_SEARCH_ONLY",
        "document_access_status": "DOCUMENTS_UNKNOWN",
        "source_role": "PRIMARY_LEAD_SOURCE",
        "verification_confidence": "HIGH",
        "sample_record_path_confirmed": True,
        "sample_record_type": "search_form",
        "sample_search_possible": True,
        "sample_document_view_possible": False,
        "expected_refresh_cadence": "DAILY",
        "stale_after_hours": 48,
        "record_ttl_days": 1825,
        "stale_record_policy": "KEEP_UNTIL_RELEASED",
        "portal_family": "tyler_odyssey",
        "fingerprint_confidence": "HIGH",
        "fingerprint_summary": (
            "Same Tyler Odyssey portal as court_civil. Probate filings are "
            "indexed under County Clerk-Probate Department case categories."
        ),
        "recommended_adapter": "tyler_odyssey_smart_search",
        "estimated_runtime_minutes": 6,
        "estimated_cost_category": "FREE",
    })

    tax_collector = _merge({
        "category": "lead",
        "subtype": "tax_delinquency",
        "url": "https://bexar.acttax.com/act_webdev/bexar/index.jsp",
        "access_pattern": "static_html",
        "official_status": "OFFICIAL_VENDOR_PORTAL",
        "lead_value": "LEAD_GENERATING",
        "source_reliability_grade": "A",
        "source_priority": "P0",
        "build_priority": "high_value",
        "source_freshness": "DAILY",
        "scraper_module": "scrapers/tax_collector.py",
        "refresh_cadence": "daily",
        "ttl_days": 365,
        "blocked_unblock_paths": [],
        "notes": (
            "ACT Tax Solutions-hosted tax-account portal for the Bexar "
            "County Tax Assessor-Collector. Free public account search by "
            "owner / business / address / account / CAD ID. Delinquency "
            "status is visible at the per-account level (no separate "
            "delinquent-roll dump). Per the 12% July penalty + 1%/month "
            "interest + 20% Sep 1 collection-fee rule, accounts past Jan 31 "
            "carry visible delinquent balances."
        ),
        "verification_note": (
            "Officially linked from bexar.org/1529 (Property Tax). "
            "Vendor: ACT Tax Solutions. Free search; payments incur "
            "card-processing fee (2.10% credit; free for e-check)."
        ),
        "open_questions": [
            "Confirm whether ACT exposes a delinquent-only filter or list.",
            "Decide whether to pull delinquency via per-parcel BCAD walk or "
            "via PIA bulk request.",
        ],
        "verified_from_url": "https://www.bexar.org/1529/Property-Tax",
        "verification_method": "official_vendor_link",
        "official_entity": "Bexar County Tax Assessor-Collector",
        "portal_type": "tax account lookup with delinquent balance visibility",
        "records_available": [
            "tax_account_balance", "delinquent_balance", "payment_history",
            "exemption_status", "assessed_value",
        ],
        "search_fields": [
            "owner_name", "business_name", "property_address",
            "account_number", "cad_property_id", "fiduciary_number",
        ],
        "access_method": "SEARCHABLE_PUBLIC_PORTAL",
        "public_access_status": "FULL_PUBLIC_ACCESS",
        "document_access_status": "DOCUMENTS_PUBLIC",
        "source_role": "PRIMARY_LEAD_SOURCE",
        "verification_confidence": "HIGH",
        "sample_record_path_confirmed": True,
        "sample_record_type": "search_form",
        "sample_search_possible": True,
        "sample_document_view_possible": True,
        "expected_refresh_cadence": "DAILY",
        "stale_after_hours": 72,
        "record_ttl_days": 365,
        "stale_record_policy": "EXPIRE_AFTER_TTL",
        "portal_family": "acttax",
        "fingerprint_confidence": "HIGH",
        "fingerprint_summary": (
            "ACT Tax Solutions per-account lookup. Server-rendered forms, "
            "no captcha observed at search level."
        ),
        "recommended_adapter": "acttax_per_account_scraper",
        "estimated_runtime_minutes": 4,
        "estimated_cost_category": "FREE",
    })

    code_enforcement_sa = _merge({
        "category": "lead",
        "subtype": "code_enforcement",
        "url": "https://webapp1.sanantonio.gov/CodeComplaintStatus/",
        "access_pattern": "static_html",
        "official_status": "OFFICIAL_CITY",
        "lead_value": "LEAD_GENERATING",
        "source_reliability_grade": "B",
        "source_priority": "P1",
        "build_priority": "optional",
        "source_freshness": "WEEKLY",
        "scraper_module": "scrapers/code_enforcement_sa.py",
        "refresh_cadence": "weekly",
        "ttl_days": 365,
        "blocked_unblock_paths": [],
        "notes": (
            "City of San Antonio code enforcement complaint status. Covers "
            "city limits ONLY; does not cover unincorporated Bexar or the 25 "
            "other Bexar municipalities. Categories: vacant lots, dangerous "
            "premises, junked vehicles, minimum housing violations, zoning, "
            "dumping, graffiti. Status: Open / Pending / Closed. Demolitions "
            "and condemnations are not separately exposed."
        ),
        "verification_note": (
            "Free public search by address / complaint number / date / "
            "category. No login. Powered by the City's webapp1 host on "
            "sanantonio.gov (OFFICIAL_CITY origin)."
        ),
        "open_questions": [
            "Locate a portal (if any) for Bexar County Fire Marshal code "
            "enforcement in unincorporated areas.",
            "Locate dangerous-structure / demolition order publications.",
        ],
        "verified_from_url": "https://www.sa.gov/Directory/Departments/DSD/CES",
        "verification_method": "city_portal",
        "official_entity": "City of San Antonio Development Services - Code Enforcement",
        "portal_type": "code violation complaint status lookup",
        "records_available": [
            "code_violations", "complaint_status",
            "dangerous_premises_complaints", "vacant_lot_complaints",
            "minimum_housing_violations", "zoning_violations",
            "junked_vehicle_complaints",
        ],
        "search_fields": [
            "street_address", "complaint_number", "date_range",
            "category_code",
        ],
        "access_method": "SEARCHABLE_PUBLIC_PORTAL",
        "public_access_status": "FULL_PUBLIC_ACCESS",
        "document_access_status": "DOCUMENTS_NOT_AVAILABLE",
        "source_role": "SUPPORTING_LEAD_SOURCE",
        "verification_confidence": "HIGH",
        "sample_record_path_confirmed": True,
        "sample_record_type": "search_form",
        "sample_search_possible": True,
        "sample_document_view_possible": False,
        "expected_refresh_cadence": "WEEKLY",
        "stale_after_hours": 240,
        "record_ttl_days": 365,
        "stale_record_policy": "EXPIRE_IF_NOT_SEEN",
        "expire_if_not_seen_runs": 4,
        "portal_family": "city_custom_webapp",
        "fingerprint_confidence": "MEDIUM",
        "fingerprint_summary": (
            "Custom City of San Antonio webapp; classic server-rendered "
            "ASP-style search form."
        ),
        "recommended_adapter": "requests_form_scraper",
        "estimated_runtime_minutes": 5,
        "estimated_cost_category": "FREE",
    })

    parcel_master = _merge({
        "category": "enrichment",
        "subtype": "parcel_master",
        "url": "https://hgo.harrisgovern.com/bexar/property/search",
        "access_pattern": "spa_with_api",
        "official_status": "OFFICIAL_COUNTY",
        "lead_value": "ENRICHMENT",
        "source_reliability_grade": "A",
        "source_priority": "P2",
        "build_priority": "enrichment",
        "source_freshness": "MONTHLY",
        "scraper_module": "scrapers/parcel_master.py",
        "refresh_cadence": "monthly",
        "ttl_days": 9999,
        "blocked_unblock_paths": [],
        "fields": {
            "parcel_id": "",
            "owner_name": "",
            "owner_mailing_addr1": "",
            "owner_mailing_city": "",
            "owner_mailing_state": "",
            "owner_mailing_zip": "",
            "situs_address": "",
            "situs_city": "",
            "situs_zip": "",
            "year_built": "",
            "assessed_value": "",
            "land_value": "",
            "improvement_value": "",
            "last_sale_date": "",
            "last_sale_price": "",
            "deed_book": "",
            "deed_page": "",
            "property_class": "",
            "land_use_code": "",
            "acreage": "",
        },
        "notes": (
            "BCAD (Bexar Central Appraisal District) parcel master. The "
            "district is migrating from True Automation to Harris Govern / "
            "Aumentum. The new Harris Govern URL is the recommended "
            "build target; the True Automation URL "
            "(https://bexar.trueautomation.com/clientdb/?cid=110) remains "
            "live as the classic fallback. No bulk-download published; "
            "operator may file a request or pair this source with the "
            "Bexar ArcGIS parcel layer for bulk parcel geometry."
        ),
        "verification_note": (
            "Officially linked from bcad.org. Both NEW and Classic URLs "
            "publicly accessible. Free."
        ),
        "open_questions": [
            "Confirm bulk-download policy via operator request to BCAD.",
            "Decide whether to standardize on Harris Govern NEW or stay on "
            "True Automation Classic for the v1 build.",
        ],
        "verified_from_url": "https://bcad.org/",
        "verification_method": "official_vendor_link",
        "official_entity": "Bexar Central Appraisal District (BCAD)",
        "portal_type": "appraisal district parcel master search",
        "records_available": [
            "parcel_id", "owner_name_and_mailing_address",
            "situs_address", "assessed_value", "land_value",
            "improvement_value", "last_sale_date", "last_sale_price",
            "year_built", "exemption_status", "property_class",
        ],
        "search_fields": [
            "address", "owner_name", "property_id", "map_search",
        ],
        "access_method": "SEARCHABLE_PUBLIC_PORTAL",
        "public_access_status": "FULL_PUBLIC_ACCESS",
        "document_access_status": "DOCUMENTS_PUBLIC",
        "source_role": "ENRICHMENT_SOURCE",
        "verification_confidence": "HIGH",
        "sample_record_path_confirmed": True,
        "sample_record_type": "search_form",
        "sample_search_possible": True,
        "sample_document_view_possible": True,
        "expected_refresh_cadence": "MONTHLY",
        "stale_after_hours": 720,
        "record_ttl_days": 9999,
        "stale_record_policy": "NEVER_EXPIRE",
        "portal_family": "harris_govern_aumentum",
        "fingerprint_confidence": "MEDIUM",
        "fingerprint_summary": (
            "Harris Govern (Aumentum family) modern SPA on hgo.harrisgovern.com; "
            "legacy True Automation portal still operational at "
            "bexar.trueautomation.com/clientdb/?cid=110."
        ),
        "recommended_adapter": "harris_govern_search_scraper",
        "estimated_runtime_minutes": 6,
        "estimated_cost_category": "FREE",
    })

    gis_parcels = _merge({
        "category": "enrichment",
        "subtype": "gis_parcels",
        "url": "https://gis-bexar.opendata.arcgis.com/",
        "access_pattern": "open_api",
        "official_status": "OFFICIAL_COUNTY",
        "lead_value": "ENRICHMENT",
        "source_reliability_grade": "A",
        "source_priority": "P2",
        "build_priority": "enrichment",
        "source_freshness": "WEEKLY",
        "scraper_module": "scrapers/gis_parcels.py",
        "refresh_cadence": "weekly",
        "ttl_days": 9999,
        "blocked_unblock_paths": [],
        "notes": (
            "Bexar County Open Data Portal (ArcGIS Hub) with parcels, "
            "boundaries, addressing, JP precincts, and other GIS layers. "
            "REST endpoint: "
            "https://maps.bexar.org/arcgis/rest/services/Parcels/MapServer/0 "
            "— the practical bulk-pull point for parcel geometry and IDs."
        ),
        "verification_note": (
            "Open ArcGIS Hub. Free, no auth. Layers exportable in CSV, "
            "KML, GeoJSON, GeoTIFF, Zip, PNG; OGC WMS/WFS available."
        ),
        "open_questions": [],
        "verified_from_url": "https://gis-bexar.opendata.arcgis.com/",
        "verification_method": "official_domain",
        "official_entity": "Bexar County Information Technology / GIS",
        "portal_type": "open data / ArcGIS Hub",
        "records_available": [
            "parcels_polygon", "address_points",
            "jp_precincts", "school_districts",
            "voting_precincts", "subdivisions",
        ],
        "search_fields": [
            "parcel_id", "owner", "address", "map_bounds",
            "feature_query",
        ],
        "access_method": "API_ENDPOINT",
        "public_access_status": "FULL_PUBLIC_ACCESS",
        "document_access_status": "DOCUMENTS_PUBLIC",
        "source_role": "ENRICHMENT_SOURCE",
        "verification_confidence": "HIGH",
        "sample_record_path_confirmed": True,
        "sample_record_type": "api_endpoint",
        "sample_search_possible": True,
        "sample_document_view_possible": True,
        "expected_refresh_cadence": "WEEKLY",
        "stale_after_hours": 240,
        "record_ttl_days": 9999,
        "stale_record_policy": "NEVER_EXPIRE",
        "portal_family": "arcgis_hub",
        "fingerprint_confidence": "HIGH",
        "fingerprint_summary": (
            "Standard ArcGIS Hub at gis-bexar.opendata.arcgis.com. "
            "Parcels MapServer at maps.bexar.org/arcgis/rest/services/Parcels."
        ),
        "recommended_adapter": "arcgis_featureserver_client",
        "estimated_runtime_minutes": 3,
        "estimated_cost_category": "FREE",
    })

    sources = {
        "clerk_recordings": clerk_recordings,
        "foreclosure_notices_map": foreclosure_notices_map,
        "court_civil": court_civil,
        "court_probate": court_probate,
        "tax_collector": tax_collector,
        "code_enforcement_sa": code_enforcement_sa,
        "parcel_master": parcel_master,
        "gis_parcels": gis_parcels,
    }

    # -------------------------------------------------------------------
    # GEOGRAPHY
    # -------------------------------------------------------------------

    municipalities = [
        {"name": "San Antonio", "code": "san_antonio", "fips_place": "4865000"},
        {"name": "Alamo Heights", "code": "alamo_heights", "fips_place": "4801300"},
        {"name": "Balcones Heights", "code": "balcones_heights", "fips_place": "4805252"},
        {"name": "Castle Hills", "code": "castle_hills", "fips_place": "4812460"},
        {"name": "China Grove", "code": "china_grove", "fips_place": "4814464"},
        {"name": "Converse", "code": "converse", "fips_place": "4816432"},
        {"name": "Elmendorf", "code": "elmendorf", "fips_place": "4823380"},
        {"name": "Fair Oaks Ranch", "code": "fair_oaks_ranch", "fips_place": "4824624"},
        {"name": "Helotes", "code": "helotes", "fips_place": "4832960"},
        {"name": "Hill Country Village", "code": "hill_country_village", "fips_place": "4833824"},
        {"name": "Hollywood Park", "code": "hollywood_park", "fips_place": "4834580"},
        {"name": "Kirby", "code": "kirby", "fips_place": "4839364"},
        {"name": "Leon Valley", "code": "leon_valley", "fips_place": "4242272"},
        {"name": "Live Oak", "code": "live_oak", "fips_place": "4443184"},
        {"name": "Olmos Park", "code": "olmos_park", "fips_place": "4853828"},
        {"name": "Sandy Oaks", "code": "sandy_oaks", "fips_place": "4865606"},
        {"name": "Schertz", "code": "schertz", "fips_place": "4866128"},
        {"name": "Selma", "code": "selma", "fips_place": "4867280"},
        {"name": "Shavano Park", "code": "shavano_park", "fips_place": "4867436"},
        {"name": "Somerset", "code": "somerset", "fips_place": "4869020"},
        {"name": "St. Hedwig", "code": "st_hedwig", "fips_place": "4869620"},
        {"name": "Terrell Hills", "code": "terrell_hills", "fips_place": "4872068"},
        {"name": "Universal City", "code": "universal_city", "fips_place": "4874144"},
        {"name": "Von Ormy", "code": "von_ormy", "fips_place": "4875440"},
        {"name": "Windcrest", "code": "windcrest", "fips_place": "4879708"},
    ]

    geography = {
        "municipalities": municipalities,
        "parcel_id_format": "^[0-9]{5}-[0-9]{3}-[0-9]{4}$",
        "parcel_id_normalization": "strip-dashes",
        "address_format_notes": (
            "Bexar parcel IDs are most commonly published as a 5-3-4 digit "
            "dotted pattern at BCAD; the normalized form strips delimiters. "
            "Bexar covers 25 municipalities plus extensive unincorporated "
            "area; situs municipality is not always present in the parcel "
            "master and must be inferred from the GIS overlay."
        ),
    }

    # -------------------------------------------------------------------
    # SCORING / STORAGE / DASHBOARD / DEPLOYMENT / VERDICT
    # -------------------------------------------------------------------

    scoring_overrides = {
        "match_confidence_floor": 80,
        "review_queue_ratio_alert_threshold": 0.5,
        "high_equity_assessed_to_sale_ratio": 2.0,
        "long_term_owned_years": 15,
        "senior_owner_proxy_years": 25,
        "favorable_loan_era_start": "2020-01-01",
        "favorable_loan_era_end": "2022-06-30",
    }

    storage = {
        "mode": "STATIC_JSON_MODE",
        "supabase_enabled": False,
        "dashboard_payload": "data/leads.json",
        "retain_raw_records_days": 30,
        "retain_source_runs_days": 365,
    }

    dashboard = {
        "title": "Bexar County Distress Intelligence",
        "subtitle": "Daily-refreshed real estate distress signals",
        "primary_color": "#0F172A",
        "accent_color": "#3B82F6",
        "default_view": "all_leads",
        "precanned_views": [],
        "view_modes": ["CLIENT_VIEW", "OPERATOR_VIEW"],
        "build_label": "",
        "build_label_reason": "",
    }

    deployment = {
        "github_org": "xcerebro",
        "github_repo": "bexar",
        "live_url": "",
        "scheduled_task_name": "",
        "watchdog_task_name": "",
        "scheduler_runtime_class": "SCHEDULER_NOT_CONFIGURED",
        "scheduler_test_fired_at": "",
        "production_verification_status": "NOT_RUN",
        "production_verification_at": "",
        "last_known_good_commit": "",
        "last_known_good_dashboard_at": "",
    }

    # -------------------------------------------------------------------
    # BUILD VERDICT
    # -------------------------------------------------------------------
    # 5 PRIMARY_LEAD_SOURCES verified HIGH-confidence and accessible:
    #   - clerk_recordings (PublicSearch)
    #   - foreclosure_notices_map (Bexar County ArcGIS)
    #   - court_civil (Tyler Odyssey)
    #   - court_probate (Tyler Odyssey)
    #   - tax_collector (ACT Tax)
    # 1 SUPPORTING_LEAD_SOURCE verified HIGH:
    #   - code_enforcement_sa (city of San Antonio)
    # 2 ENRICHMENT_SOURCES verified HIGH:
    #   - parcel_master (BCAD)
    #   - gis_parcels (Bexar ArcGIS)
    # No LOW/BLOCKED sources. Phase 0.5 skipped.
    config = {
        "county_id": "bexar_tx",
        "county_name": "Bexar",
        "state": "TX",
        "subject_state_full": "Texas",
        "fips_code": "48029",
        "timezone": "America/Chicago",
        "operator_market_priority": "primary",
        "geography": geography,
        "sources": sources,
        "scoring_overrides": scoring_overrides,
        "storage": storage,
        "dashboard": dashboard,
        "deployment": deployment,
        "build_verdict": "READY_TO_BUILD",
        "build_verdict_reason": (
            "Five PRIMARY_LEAD_SOURCES verified at HIGH confidence with public, "
            "free access at the index/search level (clerk_recordings on "
            "PublicSearch; foreclosure_notices_map on Bexar County ArcGIS with "
            "CSV export; court_civil and court_probate on Tyler Odyssey Justice "
            "Information Portal; tax_collector on ACT Tax). Two enrichment "
            "sources verified HIGH (BCAD parcel master via Harris Govern; Bexar "
            "ArcGIS open-data parcels). P0 gate satisfied: foreclosure notices "
            "are daily-refreshed and exportable as CSV directly from the County "
            "Clerk-published map, which is sufficient to anchor an MVP build. "
            "No required P0 source is blocked. Phase 0.5 was not required."
        ),
        "build_verdict_at": PHASE0_TIMESTAMP,
        "auto_resolve_status": "NOT_ATTEMPTED",
        "final_resolution_status": "",
        "operator_override_audit": [],
    }

    return config


def main() -> int:
    config = build_config()
    target = REPO_ROOT / "config" / "counties" / "bexar_tx.json"
    schema = REPO_ROOT / "config" / "counties" / "_schema.json"

    result = write_county_config(
        config_dict=config,
        target_path=str(target),
        schema_path=str(schema),
        overwrite=True,
    )
    print(result.summary())
    return 0 if result.is_ok() else 1


if __name__ == "__main__":
    raise SystemExit(main())
