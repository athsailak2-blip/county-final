"""
Translator test for publicsearch_clerk_recordings.

Verifies the translator correctly converts clerk-recording raw records
into signals + parcels, including doc-type detection, lead-pattern
assignment, non-lead filtering, and field_map bridging.
"""

from __future__ import annotations

import sys
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
SCAFFOLD_DIR = THIS_DIR.parent
FRAMEWORK_ROOT = SCAFFOLD_DIR.parent
sys.path.insert(0, str(FRAMEWORK_ROOT))

from scaffold.pipeline import translators

PASS = "PASS"
FAIL = "FAIL"
results: list[tuple[str, str, str]] = []


def case(name: str, passed: bool, detail: str = "") -> None:
    status = PASS if passed else FAIL
    results.append((status, name, detail))
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))


SOURCE_CONFIG_LIS_PENDENS = {
    "translator": "publicsearch_clerk_recordings",
    "_source_id": "official_records",
    "parcel_id_prefix": "CLRK-",
}

SOURCE_CONFIG_FIELD_MAP = {
    "translator": "publicsearch_clerk_recordings",
    "_source_id": "official_records",
    "parcel_id_prefix": "CLRK-",
    "field_map": {
        "doc_number": "instr_number",
        "doc_type": "doc_type_label",
        "record_date": "filing_date",
        "grantor": "grantor_name",
        "grantee": "grantee_name",
    },
}


def test_registered():
    print("\n[publicsearch_clerk_recordings registered]")
    names = translators.registered_names()
    case("clerk_recordings registered", "publicsearch_clerk_recordings" in names)


def test_empty_input():
    print("\n[empty input returns ([], [], {})]")
    fn = translators.lookup("publicsearch_clerk_recordings")
    sig, par, meta = fn([], {}, {})
    case("empty: signals empty", sig == [])
    case("empty: parcels empty", par == [])
    case("empty: meta empty", meta == {})


def test_lis_pendens_lead():
    print("\n[Lis Pendens produces foreclosure lead signal]")
    fn = translators.lookup("publicsearch_clerk_recordings")
    raw = [{
        "raw_record_id": "raw_lp_001",
        "source_id": "official_records",
        "source_url": "https://or.duvalclerk.com/showdetails.aspx?id=125",
        "source_fetched_at": "2026-06-02T12:00:00Z",
        "raw_payload": {
            "doc_number": "202612340003",
            "doc_type": "Lis Pendens",
            "record_date": "2026-06-01",
            "grantor": "WELLS FARGO BANK NA",
            "grantee": "DOE, JANE M",
            "consideration": "",
            "book_number": "OR",
            "page_number": "12347",
            "case_number": "16-2026-CA-001234",
            "detail_url": "https://or.duvalclerk.com/showdetails.aspx?id=125",
        },
        "parser_confidence": 95,
    }]
    sig, par, meta = fn(raw, {}, SOURCE_CONFIG_LIS_PENDENS)
    case("LP: 1 signal produced", len(sig) == 1, f"got {len(sig)}")
    case("LP: 1 parcel produced", len(par) == 1, f"got {len(par)}")
    if sig:
        s = sig[0]
        case("LP: signal doc_type = lis_pendens",
             s["doc_type"] == "lis_pendens", f"got {s['doc_type']}")
        case("LP: lead_pattern = foreclosure",
             s["lead_pattern"] == "foreclosure", f"got {s['lead_pattern']}")
        case("LP: doc_number preserved", s["doc_number"] == "202612340003")
        case("LP: grantee preserved", s["grantee"] == "DOE, JANE M")
        case("LP: case_number preserved",
             s["case_number"] == "16-2026-CA-001234")
        case("LP: translator set",
             s["translator"] == "publicsearch_clerk_recordings")
    if par:
        p = par[0]
        case("LP: parcel_id = CLRK-202612340003",
             p["parcel_id"] == "CLRK-202612340003")
        case("LP: owner_name falls back to grantee",
             p["owner_name"] == "DOE, JANE M")


def test_bankruptcy_lead():
    print("\n[Bankruptcy produces bankruptcy lead signal]")
    fn = translators.lookup("publicsearch_clerk_recordings")
    raw = [{
        "raw_record_id": "raw_bk_001",
        "source_id": "official_records",
        "source_url": "about:test/bk_001",
        "source_fetched_at": "2026-06-02T12:00:00Z",
        "raw_payload": {
            "doc_number": "202612340020",
            "doc_type": "Bankruptcy",
            "record_date": "2026-06-01",
            "grantor": "SMITH, JOHN",
            "grantee": "",
            "consideration": "",
            "case_number": "16-2026-BK-000789",
        },
        "parser_confidence": 90,
    }]
    sig, par, meta = fn(raw, {}, SOURCE_CONFIG_LIS_PENDENS)
    case("BK: 1 signal", len(sig) == 1)
    if sig:
        s = sig[0]
        case("BK: doc_type = bankruptcy_petition",
             s["doc_type"] == "bankruptcy_petition")
        case("BK: lead_pattern = bankruptcy",
             s["lead_pattern"] == "bankruptcy")
        case("BK: grantor as owner_name fallback",
             s["grantor"] == "SMITH, JOHN")


def test_federal_tax_lien_lead():
    print("\n[Federal Tax Lien produces tax/lien lead signal]")
    fn = translators.lookup("publicsearch_clerk_recordings")
    raw = [{
        "raw_record_id": "raw_tl_001",
        "source_id": "official_records",
        "source_url": "about:test/tl_001",
        "raw_payload": {
            "doc_number": "202612340030",
            "doc_type": "Federal Tax Lien",
            "record_date": "2026-06-03",
            "grantor": "BROWN, CHARLES",
            "grantee": "INTERNAL REVENUE SERVICE",
            "consideration": "45000.00",
        },
        "parser_confidence": 95,
    }]
    sig, par, meta = fn(raw, {}, SOURCE_CONFIG_LIS_PENDENS)
    case("TL: 1 signal", len(sig) == 1)
    if sig:
        s = sig[0]
        case("TL: doc_type = federal_tax_lien",
             s["doc_type"] == "federal_tax_lien")
        case("TL: lead_pattern = tax",
             s["lead_pattern"] == "tax", f"got {s['lead_pattern']}")
        case("TL: consideration preserved",
             s["consideration"] == "45000.00")


def test_warranty_deed_skipped():
    print("\n[Warranty Deed is NOT lead-generating, skipped]")
    fn = translators.lookup("publicsearch_clerk_recordings")
    raw = [{
        "raw_record_id": "raw_wd_001",
        "raw_payload": {
            "doc_number": "202612340001",
            "doc_type": "Warranty Deed",
            "record_date": "2026-06-01",
            "grantor": "SMITH, JOHN A",
            "grantee": "JONES, ROBERT B",
            "consideration": "350000.00",
        },
        "parser_confidence": 95,
    }]
    sig, par, meta = fn(raw, {}, SOURCE_CONFIG_LIS_PENDENS)
    case("WD: 0 signals (non-lead)", len(sig) == 0, f"got {len(sig)}")
    case("WD: 0 parcels (non-lead)", len(par) == 0, f"got {len(par)}")


def test_mortgage_skipped():
    print("\n[MORTGAGE is NOT lead-generating, skipped]")
    fn = translators.lookup("publicsearch_clerk_recordings")
    raw = [{
        "raw_record_id": "raw_mt_001",
        "raw_payload": {
            "doc_number": "202612340002",
            "doc_type": "MORTGAGE",
            "record_date": "2026-06-01",
            "grantor": "JONES, ROBERT B",
            "grantee": "FIRST NATIONAL BANK",
            "consideration": "280000.00",
        },
        "parser_confidence": 95,
    }]
    sig, par, meta = fn(raw, {}, SOURCE_CONFIG_LIS_PENDENS)
    case("MT: 0 signals (non-lead)", len(sig) == 0)
    case("MT: 0 parcels (non-lead)", len(par) == 0)


def test_multiple_records():
    print("\n[mixed lead + non-lead records processed correctly]")
    fn = translators.lookup("publicsearch_clerk_recordings")
    raw = [
        {
            "raw_record_id": "raw_mix_001",
            "raw_payload": {
                "doc_number": "202612340001",
                "doc_type": "Warranty Deed",
                "record_date": "2026-06-01",
            },
            "parser_confidence": 95,
        },
        {
            "raw_record_id": "raw_mix_002",
            "raw_payload": {
                "doc_number": "202612340002",
                "doc_type": "Lis Pendens",
                "record_date": "2026-06-01",
                "grantor": "BANK NA",
                "grantee": "DEFENDANT",
                "case_number": "16-2026-CA-001",
            },
            "parser_confidence": 95,
        },
        {
            "raw_record_id": "raw_mix_003",
            "raw_payload": {
                "doc_number": "202612340003",
                "doc_type": "Notice of Sale",
                "record_date": "2026-06-01",
                "grantor": "BANK NA",
                "grantee": "DEFENDANT",
            },
            "parser_confidence": 95,
        },
    ]
    sig, par, meta = fn(raw, {}, SOURCE_CONFIG_LIS_PENDENS)
    case("MIX: 2 signals from 3 records", len(sig) == 2, f"got {len(sig)}")
    case("MIX: 2 parcels", len(par) == 2, f"got {len(par)}")
    if len(sig) == 2:
        case("MIX: sig[0] is lis_pendens or notice_of_sale",
             sig[0]["doc_type"] in ("lis_pendens", "notice_of_sale"))
        case("MIX: sig[1] is the other lead type",
             sig[1]["doc_type"] in ("lis_pendens", "notice_of_sale"))


def test_field_map_bridging():
    print("\n[field_map bridges non-canonical raw_payload names]")
    fn = translators.lookup("publicsearch_clerk_recordings")
    raw = [{
        "raw_record_id": "raw_fm_001",
        "source_id": "official_records",
        "source_url": "about:test/fm_001",
        "source_fetched_at": "2026-06-02T12:00:00Z",
        "raw_payload": {
            "instr_number": "202612340100",
            "doc_type_label": "Lis Pendens",
            "filing_date": "2026-06-01",
            "grantor_name": "WELLS FARGO NA",
            "grantee_name": "DOE, JOHN",
        },
        "parser_confidence": 95,
    }]
    sig, par, meta = fn(raw, {}, SOURCE_CONFIG_FIELD_MAP)
    case("FM: 1 signal via field_map", len(sig) == 1, f"got {len(sig)}")
    if sig:
        s = sig[0]
        case("FM: doc_number resolved via instr_number",
             s["doc_number"] == "202612340100")
        case("FM: grantor resolved via grantor_name",
             s["grantor"] == "WELLS FARGO NA")
        case("FM: grantee resolved via grantee_name",
             s["grantee"] == "DOE, JOHN")


def test_unknown_doc_type_skipped():
    print("\n[unknown/unrecognized doc_type is skipped]")
    fn = translators.lookup("publicsearch_clerk_recordings")
    raw = [{
        "raw_record_id": "raw_unk_001",
        "raw_payload": {
            "doc_number": "202612340999",
            "doc_type": "Totally_Unknown_Type_XYZ",
            "record_date": "2026-06-01",
        },
        "parser_confidence": 80,
    }]
    sig, par, meta = fn(raw, {}, SOURCE_CONFIG_LIS_PENDENS)
    case("UNK: 0 signals (cannot normalize)", len(sig) == 0)
    case("UNK: 0 parcels", len(par) == 0)


def test_empty_doc_type_skipped():
    print("\n[empty doc_type is skipped]")
    fn = translators.lookup("publicsearch_clerk_recordings")
    raw = [{
        "raw_record_id": "raw_empty_001",
        "raw_payload": {
            "doc_number": "1",
            "doc_type": "",
            "record_date": "2026-06-01",
        },
    }]
    sig, par, meta = fn(raw, {}, SOURCE_CONFIG_LIS_PENDENS)
    case("EMPTY: 0 signals", len(sig) == 0)
    case("EMPTY: 0 parcels", len(par) == 0)


def main() -> int:
    print("=" * 72)
    print("PUBLICSEARCH_CLERK_RECORDINGS TRANSLATOR TEST")
    print("=" * 72)

    test_registered()
    test_empty_input()
    test_lis_pendens_lead()
    test_bankruptcy_lead()
    test_federal_tax_lien_lead()
    test_warranty_deed_skipped()
    test_mortgage_skipped()
    test_multiple_records()
    test_field_map_bridging()
    test_unknown_doc_type_skipped()
    test_empty_doc_type_skipped()

    passed = sum(1 for r in results if r[0] == PASS)
    failed = sum(1 for r in results if r[0] == FAIL)
    print()
    print(f"RESULT: {passed} pass, {failed} fail")
    print("=" * 72)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
