"""
parcel_lookup — drive the Duval PA scraper to enrich OR records.

Reads data/raw/official_records.jsonl, identifies lead-eligible records,
collects the unique grantor + grantee names, and runs each through the
PA portal to retrieve:
  - RE# (parcel_id)
  - owner name + mailing address
  - situs address / city / zip
  - assessed value, just value, land value, building value, taxable value
  - year_built, tax_district, property_use, subdivision
  - last_sale_date, last_sale_price

Outputs:
  data/raw/parcel_master.jsonl    framework-canonical parcel records with
                                   FL-DUVAL- prefix
  data/intermediates/name_to_re.json  name → RE# index the OR translator
                                       consults at translate-time

The parcel_id format is FL-DUVAL-NNNNNN-NNNN (matching the county config's
parcel_id_prefix).
"""

from __future__ import annotations

import json
import re
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scaffold.network.provider import ScrappeyProvider
from scrapers.property_appraiser import PASession, _normalize_name, _format_re_dashed

OR_PATH = REPO_ROOT / "data" / "raw" / "official_records.jsonl"
PARCEL_OUT = REPO_ROOT / "data" / "raw" / "parcel_master.jsonl"
INDEX_OUT = REPO_ROOT / "data" / "intermediates" / "name_to_re.json"

PARCEL_ID_PREFIX = "FL-DUVAL-"

# Debtor-field routing: for each lead doc type, which raw_payload field
# is the property owner (the party to look up in PA). The other field is
# the filer/plaintiff/creditor. Confirmed by examining sample records.
DEBTOR_FIELD_BY_TYPE = {
    "JUDGMENT": "grantor",
    "CC COURT JUDGMENT": "grantee",
    "JUDGMENT/SENTENCE": "grantee",
    "JUDGMENT/RESTITUTION": "grantee",
    "LIEN": "grantee",
    "NOTICE COMMENCEMENT": "grantor",
    "FINANCE STATEMENT/UCC": "grantee",
    "PROBATE": "grantor",
    "LIS PENDENS": "grantee",
    "WARRANT": "grantee",
    "WARRANT NO FEE": "grantee",
    "DEATH CERTIFICATE": "grantor",
}

# Government filers / credit companies that will never match a PA parcel —
# we filter these out at name-collection time to save API calls.
NON_DEBTOR_PATTERNS = re.compile(
    r"\b("
    r"FLORIDA STATE|STATE OF|REV DEPT|REVENUE|"
    r"CITY OF|JACKSONVILLE CITY|"
    r"UNITED STATES|U\.S\.|"
    r"BANK OF AMERICA|BARCLAYS|MIDFIRST|VYSTAR|LAKEVIEW|COMERICA|"
    r"MIDLAND|LVNV|VELOCITY|CROWN|"
    r"ACE DOOR|RED FOX|PREFERRED BUILDERS|GAY|"
    r"ESTATE\s*$"  # bare ESTATE placeholder (deceased estate records)
    r")\b",
    re.IGNORECASE,
)


def _is_lead_eligible(doc_type: str) -> bool:
    dt = (doc_type or "").lower()
    return any(
        kw in dt for kw in [
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
    )


def collect_lead_names(or_path: Path) -> tuple[list[str], Counter]:
    """Return (unique_names, doc_type_counts) for lead-eligible records.

    For each lead-eligible record, picks the debtor field per
    DEBTOR_FIELD_BY_TYPE. Falls back to grantee, then grantor, when the
    routed field is empty. Filters out government/credit-company filers
    that will never match a PA parcel.
    """
    name_counter: Counter = Counter()
    doc_type_counter: Counter = Counter()
    with open(or_path) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("change_status") == "DISAPPEARED":
                continue
            payload = rec.get("raw_payload", {}) or {}
            dt = payload.get("doc_type", "")
            if not _is_lead_eligible(dt):
                continue
            doc_type_counter[dt] += 1
            # Pick the debtor field per doc-type routing table
            debtor_field = DEBTOR_FIELD_BY_TYPE.get(dt, "grantee")
            n = payload.get(debtor_field, "")
            if not n:
                n = payload.get("grantee", "") or payload.get("grantor", "")
            if not n:
                continue
            first = n.split(";")[0].strip()
            if not first or len(first) < 3 or len(first) > 80:
                continue
            if first.lower() in {"none", "n/a", "unknown", "unassigned", ""}:
                continue
            # Skip known non-debtor filers
            if NON_DEBTOR_PATTERNS.search(first):
                continue
            name_counter[first] += 1
    return [n for n, _ in name_counter.most_common()], doc_type_counter


def _match_score(query_norm: str, candidate_owner: str) -> int:
    """Heuristic match score between normalized query and candidate owner."""
    q = query_norm
    c = _normalize_name(candidate_owner)
    if not q or not c:
        return 0
    if q == c:
        return 100
    # Last-name match (token-based): if the first token of both matches
    # (e.g. "DOE JOHN" vs "DOE JANE")
    q_tokens = q.split()
    c_tokens = c.split()
    if q_tokens and c_tokens and q_tokens[0] == c_tokens[0]:
        return 70
    # Substring match
    if q in c or c in q:
        return 50
    return 0


def best_match(query_name: str, candidates: list[dict]) -> Optional[dict]:
    """Pick the best RE# candidate for a given query name."""
    if not candidates:
        return None
    norm = _normalize_name(query_name)
    scored = [
        (c, _match_score(norm, c.get("owner", "")))
        for c in candidates
    ]
    scored.sort(key=lambda t: (-t[1], t[0].get("re10", "")))
    top = scored[0]
    if top[1] >= 50:
        return top[0]
    return None


def run(*, fetch_fn=None, max_names: Optional[int] = None) -> dict:
    if not OR_PATH.exists():
        return {"error": f"OR data not found at {OR_PATH}"}

    names, doc_type_counter = collect_lead_names(OR_PATH)
    print(f"[parcel_lookup] found {len(names)} unique names across "
          f"{sum(doc_type_counter.values())} lead-eligible records",
          file=sys.stderr)
    print(f"[parcel_lookup] doc types: {dict(doc_type_counter.most_common(5))}",
          file=sys.stderr)

    if max_names:
        names = names[:max_names]
        print(f"[parcel_lookup] truncated to first {max_names} names",
              file=sys.stderr)

    if fetch_fn is None:
        import os
        from scaffold.network.provider import ScrappeyProvider
        api_key = os.environ.get("SCRAPPEY_API_KEY", "")
        if not api_key:
            return {"error": "SCRAPPEY_API_KEY not set"}
        fetch_fn = ScrappeyProvider(api_key)
        fetch_fn._session = None  # fresh session

    session = PASession(fetch_fn=fetch_fn)
    name_to_re: dict = {}
    parcel_records: list[dict] = []
    seen_re: set = set()
    failures: list[str] = []

    for i, name in enumerate(names):
        norm = _normalize_name(name)
        if not norm:
            continue
        print(f"  [{i+1:3d}/{len(names)}] {norm!r}", file=sys.stderr, flush=True)
        try:
            results = session.search_by_name(norm)
        except Exception as exc:
            print(f"  [parcel_lookup] search failed for {norm!r}: {exc}",
                  file=sys.stderr, flush=True)
            failures.append(norm)
            time.sleep(2)
            continue
        if not results:
            name_to_re[norm] = None
            print(f"     -> 0 results", file=sys.stderr, flush=True)
            time.sleep(0.3)
            continue
        match = best_match(norm, results)
        if not match:
            name_to_re[norm] = None
            print(f"     -> {len(results)} results, no name match",
                  file=sys.stderr, flush=True)
            time.sleep(0.3)
            continue
        re10 = match["re10"]
        name_to_re[norm] = re10
        if re10 in seen_re:
            print(f"     -> {len(results)} results, best RE {re10} (cached)",
                  file=sys.stderr, flush=True)
            time.sleep(0.2)
            continue
        try:
            detail = session.fetch_detail(re10)
        except Exception as exc:
            print(f"  [parcel_lookup] detail failed for {re10}: {exc}",
                  file=sys.stderr, flush=True)
            failures.append(re10)
            time.sleep(1)
            continue
        if not detail:
            seen_re.add(re10)
            print(f"     -> RE {re10} no detail", file=sys.stderr, flush=True)
            time.sleep(0.3)
            continue
        seen_re.add(re10)
        # Build framework-canonical parcel record
        parcel_id = f"{PARCEL_ID_PREFIX}{detail.get('parcel_id') or _format_re_dashed(re10)}"
        # Map PA fields to canonical parcel-master fields
        record = {
            "parcel_id": parcel_id,
            "address": detail.get("situs_address", ""),
            "owner_name": detail.get("owner_name", ""),
            "owner_mailing_address": (
                # PA gives a single mailing line; put in addr1 field
                detail.get("owner_mailing", "").split(",")[0].strip()
                if detail.get("owner_mailing") else ""
            ),
            "owner_mailing_city": (
                # Parse from "CITY, ST ZIP"
                _parse_mailing_city(detail.get("owner_mailing", ""))
            ),
            "owner_mailing_state": (
                _parse_mailing_state(detail.get("owner_mailing", ""))
            ),
            "owner_mailing_zip": (
                _parse_mailing_zip(detail.get("owner_mailing", ""))
            ),
            "city": detail.get("situs_city", ""),
            "zip": detail.get("situs_zip", ""),
            "assessed_value": int(detail.get("assessed_value_2026", 0) or 0),
            "land_value": int(detail.get("land_value_2026", 0) or 0),
            "improvement_value": int(detail.get("building_value_2026", 0) or 0),
            "year_built": detail.get("year_built"),
            "property_use": detail.get("property_use", ""),
            "acres": (detail.get("total_area") or 0) / 43560.0
                if detail.get("total_area") else None,
            "last_sale_date": _parse_iso_date(detail.get("last_sale_date", "")),
            "last_sale_price": detail.get("last_sale_price"),
            "legal_description": detail.get("subdivision", ""),
            "parcel_master_status": "matched_pending_join",
            # Auxiliary Duval-specific fields
            "duval": {
                "re10": re10,
                "tax_district": detail.get("tax_district", ""),
                "subdivision": detail.get("subdivision", ""),
                "just_value": detail.get("just_value_2026"),
                "taxable_value": detail.get("taxable_value_2026"),
                "queried_name": name,
            },
        }
        parcel_records.append(record)
        print(f"     -> RE {re10} owner={detail.get('owner_name','')[:30]!r} "
              f"av={detail.get('assessed_value_2026')}",
              file=sys.stderr, flush=True)
        time.sleep(0.5)
        # Flush the index periodically
        if (i + 1) % 10 == 0:
            INDEX_OUT.write_text(
                json.dumps(name_to_re, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    session.close()

    PARCEL_OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(PARCEL_OUT, "w", encoding="utf-8") as fh:
        for r in parcel_records:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    INDEX_OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(INDEX_OUT, "w", encoding="utf-8") as fh:
        json.dump(name_to_re, fh, ensure_ascii=False, indent=2)

    return {
        "names_queried": len(names),
        "parcels_written": len(parcel_records),
        "index_entries": len(name_to_re),
        "index_resolved": sum(1 for v in name_to_re.values() if v),
        "failures": len(failures),
        "doc_type_breakdown": dict(doc_type_counter.most_common()),
        "parcel_output": str(PARCEL_OUT),
        "index_output": str(INDEX_OUT),
    }


def _parse_mailing_city(mailing: str) -> str:
    m = re.search(r"\b([A-Z][A-Z\s]+?),\s*[A-Z]{2}\s+\d{5}", mailing.upper())
    if m:
        return m.group(1).strip().title()
    return ""


def _parse_mailing_state(mailing: str) -> str:
    m = re.search(r",\s*([A-Z]{2})\s+\d{5}", mailing.upper())
    if m:
        return m.group(1)
    return "FL"


def _parse_mailing_zip(mailing: str) -> str:
    m = re.search(r"\b(\d{5})(?:-\d{4})?", mailing)
    if m:
        return m.group(1)
    return ""


def _parse_iso_date(s: str) -> str:
    """Convert M/D/YYYY to YYYY-MM-DD."""
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", (s or "").strip())
    if not m:
        return ""
    mo, dy, yr = m.groups()
    return f"{yr}-{int(mo):02d}-{int(dy):02d}"


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(
        description="Look up Duval PA parcels for lead-eligible OR parties."
    )
    parser.add_argument("--max-names", type=int, default=None,
                        help="Cap the number of unique names to look up.")
    args = parser.parse_args()
    stats = run(max_names=args.max_names)
    print(json.dumps(stats, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
