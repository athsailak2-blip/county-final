"""
Duval County tax_collector adapter — LienHub County-Held Certificates.

Pulls tax delinquency info / county-held tax certificates from
LienHub's Duval County portal.

Duval County sources:
  - LienHub County-Held: https://lienhub.com/county/duval/countyheld/certificates

Strategy
--------
1. Fetch the County-Held Certificates page (year-round data)
2. Parse the <table id="certs"> table
3. Map columns: Account # → parcel_id, Tax Year, Certificate #, Issued Date,
   Expiration Date, Purchase Amount
4. Write data/raw/tax_collector.jsonl

Canonical fields emitted in raw_payload:
  parcel_id        — RE# (NNNNNN-NNNN) from Account #
  tax_year         — tax year of the delinquent tax
  certificate_number — tax certificate number
  issued_date      — date certificate was issued
  expiration_date  — date certificate expires
  purchase_amount  — amount to purchase the certificate
  certificate_status — always "county_held"
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, date, timezone
from pathlib import Path
from typing import Optional

import httpx
from bs4 import BeautifulSoup

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

SOURCE_ID = "tax_collector"
BASE_URL = "https://taxcollector.coj.net"
LIEN_SEARCH_URL = "https://tclieninfo.coj.net"
LIENHUB_URL = "https://lienhub.com/county/duval"
LIENHUB_COUNTY_HELD_URL = "https://lienhub.com/county/duval/countyheld/certificates"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)
REQUEST_TIMEOUT = 30

_WHITESPACE = re.compile(r"\s+")


def _now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def _raw_record_id(parcel_id: str, tax_year: str, cert_number: str) -> str:
    key = "|".join([
        "duval_tax_collector",
        (parcel_id or "").strip().upper(),
        (tax_year or "").strip(),
        (cert_number or "").strip(),
    ])
    return "raw_" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:24]


def _clean_money(val: str) -> str:
    val = val.strip()
    if val.startswith("$"):
        val = val[1:]
    return val.replace(",", "")


def _normalize_whitespace(s: str) -> str:
    return _WHITESPACE.sub(" ", s).strip()


class TaxCollectorSession:
    """Manages session with the Duval Tax Collector portals."""

    def __init__(self, fetch_fn=None):
        self.client = httpx.Client(
            verify=False,
            timeout=REQUEST_TIMEOUT,
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
        )
        self.fetch_fn = fetch_fn

    def _fetch(self, url: str) -> str:
        if self.fetch_fn:
            return self.fetch_fn(url, {})
        resp = self.client.get(url)
        resp.raise_for_status()
        return resp.text

    def _post(self, url: str, data: dict = None) -> str:
        if self.fetch_fn:
            return self.fetch_fn(url, data or {})
        resp = self.client.post(url, data=data)
        resp.raise_for_status()
        return resp.text

    def fetch_lienhub_auctions(self) -> list[dict]:
        """Fetch county-held tax certificates from LienHub.

        LienHub lists year-round county-held certificates at
        /county/duval/countyheld/certificates — these are liens not
        sold to third parties in the annual May-June auction.
        """
        html = self._fetch(LIENHUB_COUNTY_HELD_URL)
        return self._parse_county_held(html)

    def _parse_county_held(self, html: str) -> list[dict]:
        """Parse the LienHub County-Held Certificates table."""
        soup = BeautifulSoup(html, "lxml")
        records = []

        table = soup.find("table", id="certs")
        if not table:
            return records

        rows = table.find_all("tr")
        if len(rows) < 2:
            return records

        for row in rows[1:]:
            cells = row.find_all(["td", "th"])
            if len(cells) < 6:
                continue

            parcel_id = _normalize_whitespace(cells[0].get_text())
            tax_year = _normalize_whitespace(cells[1].get_text())
            cert_number = _normalize_whitespace(cells[2].get_text())
            issued_date = _normalize_whitespace(cells[3].get_text())
            expiration_date = _normalize_whitespace(cells[4].get_text())
            purchase_amount = _clean_money(_normalize_whitespace(cells[5].get_text()))

            records.append({
                "parcel_id": parcel_id,
                "tax_year": tax_year,
                "certificate_number": cert_number,
                "issued_date": issued_date,
                "expiration_date": expiration_date,
                "purchase_amount": purchase_amount,
                "certificate_status": "county_held",
            })

        return records

    def close(self):
        if self.client:
            self.client.close()


def _load_prior(path: Path) -> dict:
    if not path.exists():
        return {}
    out = {}
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
    for rid, prev in prior_by_id.items():
        if rid in current_ids:
            continue
        prev = dict(prev)
        prev["change_status"] = "DISAPPEARED"
        out.append(prev)
    return out


def run(*, output_path: Path | None = None,
        fetch_fn=None) -> dict:
    """Run the tax collector scraper."""
    output_path = output_path or REPO_ROOT / "data" / "raw" / f"{SOURCE_ID}.jsonl"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    session = TaxCollectorSession(fetch_fn=fetch_fn)
    auctions = session.fetch_lienhub_auctions()
    session.close()

    current: list[dict] = []
    for entry in auctions:
        parcel_id = entry.get("parcel_id", "")
        tax_year = entry.get("tax_year", "")
        cert_number = entry.get("certificate_number", "")
        record_id = _raw_record_id(parcel_id, tax_year, cert_number)
        raw_payload = {
            "parcel_id": parcel_id,
            "tax_year": tax_year,
            "certificate_number": cert_number,
            "issued_date": entry.get("issued_date", ""),
            "expiration_date": entry.get("expiration_date", ""),
            "purchase_amount": entry.get("purchase_amount", ""),
            "certificate_status": entry.get("certificate_status", "county_held"),
        }
        current.append({
            "raw_record_id": record_id,
            "source_id": SOURCE_ID,
            "source_url": LIENHUB_COUNTY_HELD_URL,
            "source_fetched_at": _now_iso(),
            "raw_payload": raw_payload,
            "raw_text": None,
            "first_seen_at": _now_iso(),
            "last_seen_at": _now_iso(),
            "change_status": "NEW_RECORD",
            "parser_confidence": 90 if parcel_id else 60,
        })

    prior = _load_prior(output_path)
    merged = merge_with_prior(current, prior)

    tmp = output_path.with_suffix(".jsonl.tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        for rec in merged:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    tmp.replace(output_path)

    stats = {
        "source_id": SOURCE_ID,
        "current_count": len(current),
        "prior_count": len(prior),
        "total_after_merge": len(merged),
        "new_record_count": sum(1 for r in merged if r["change_status"] == "NEW_RECORD"),
        "output_path": str(output_path),
    }
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Pull Duval County Tax Collector data."
    )
    parser.add_argument("--out", default=None,
                        help="Output JSONL path. Default: data/raw/tax_collector.jsonl")
    args = parser.parse_args()

    out = Path(args.out) if args.out else None
    stats = run(output_path=out)
    print(json.dumps(stats, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
