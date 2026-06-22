"""
Duval County tax_deed_sales adapter — RealTaxDeed portal.

Pulls tax deed sale listings from the Duval County Clerk's Tax Deed
portal at taxdeed.duvalclerk.com.

Tax deed sales are governed by Chapter 197 Florida Statutes. Properties
are sold when the owner fails to pay delinquent property taxes. Sales
occur after a tax certificate holder applies for a tax deed.

Strategy
--------
1. Load homepage (establishes Scrappey browser session)
2. Use browser actions to click the "Lands Available" tab and "Search"
   button to trigger grid data load
3. Parse the jqGrid table into canonical raw_payload shape
4. Write data/raw/tax_deed_sales.jsonl
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from bs4 import BeautifulSoup

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

SOURCE_ID = "tax_deed_sales"
BASE_URL = "https://taxdeed.duvalclerk.com"
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


def _raw_record_id(parcel_id: str, case_number: str, certificate: str) -> str:
    key = "|".join([
        "duval_tax_deed_sales",
        (parcel_id or "").strip().upper(),
        (case_number or "").strip().upper(),
        (certificate or "").strip().upper(),
    ])
    return "raw_" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:24]


def _normalize_whitespace(s: str) -> str:
    return _WHITESPACE.sub(" ", s).strip()


def _clean_money(val: str) -> str:
    val = val.strip()
    if val.startswith("$"):
        val = val[1:]
    val = val.replace(",", "")
    return val


_SEARCH_BUTTONS = {
    "status": {"tab": "#idSaleDateRange > a", "button": "button[name='buttonSubmitSaleDate']"},
}


class TaxDeedSession:
    """Manages session with the Tax Deed sales portal."""

    def __init__(self, fetch_fn=None):
        self.client = None
        self.fetch_fn = fetch_fn

    def _fetch(self, url: str, data: dict | None = None, **extras) -> str:
        if self.fetch_fn:
            return self.fetch_fn(url, data or {}, **extras)
        import httpx
        with httpx.Client(verify=False, timeout=REQUEST_TIMEOUT,
                          headers={"User-Agent": USER_AGENT},
                          follow_redirects=True) as c:
            if data:
                resp = c.post(url, data=data)
            else:
                resp = c.get(url)
        resp.raise_for_status()
        return resp.text

    def fetch_listings(self) -> list[dict]:
        """Fetch tax deed sale listings from the Lands Available tab."""
        from scaffold.network.provider import ScrappeyProvider

        is_scrappey = isinstance(self.fetch_fn, ScrappeyProvider)

        if is_scrappey:
            html = self._get_lands_available_with_scrappey()
        else:
            html = self._fetch(BASE_URL)
            soup = BeautifulSoup(html, "lxml")
            table = soup.find("table", id="TaxDeed")
            if not table:
                return []
            rows = table.find_all("tr")[1:]
            return self._parse_grid_rows(rows)

        soup = BeautifulSoup(html, "lxml")
        table = soup.find("table", id="TaxDeed")
        if not table:
            return []
        rows = table.find_all("tr")[1:]
        return self._parse_grid_rows(rows)

    def _get_lands_available_with_scrappey(self) -> str:
        """Use Scrappey browser actions to get grid data from Lands Available tab."""
        html = self._fetch(BASE_URL)
        html = self._fetch(
            BASE_URL, {},
            browserActions=[
                {"type": "click", "cssSelector": "#idLandsAvailable > a", "wait": 1},
                {"type": "wait_for_selector", "cssSelector": "#tabs-10", "timeout": 10000},
                {"type": "click", "cssSelector": "button[name='buttonSubmitLandsAvailable']"},
                {"type": "wait_for_load_state", "waitForLoadState": "networkidle"},
                {"type": "wait", "wait": 3},
            ],
        )
        return html

    COLS = [
        "applicant", "case_number", "certificate", "parcel_id",
        "sale_date", "status", "opening_bid", "high_bid",
        "surplus", "owners",
    ]

    def _parse_grid_rows(self, rows: list) -> list[dict]:
        """Parse jqGrid rows into canonical listings."""
        listings = []
        for row in rows:
            cells = row.find_all("td")
            if len(cells) < 4:
                continue

            vals = {}
            for i, col in enumerate(self.COLS):
                if i < len(cells):
                    vals[col] = _normalize_whitespace(cells[i].get_text())
                else:
                    vals[col] = ""

            parcel_id = vals["parcel_id"]
            case_number = vals["case_number"]
            certificate = vals["certificate"]

            raw_payload = {
                "parcel_id": parcel_id,
                "case_number": case_number,
                "certificate": certificate,
                "sale_date": vals["sale_date"],
                "applicant": vals["applicant"],
                "status": vals["status"],
                "opening_bid": _clean_money(vals["opening_bid"]),
                "high_bid": _clean_money(vals["high_bid"]),
                "surplus": _clean_money(vals["surplus"]),
                "owners": vals["owners"],
            }

            listings.append({
                "raw_record_id": _raw_record_id(parcel_id, case_number, certificate),
                "source_id": SOURCE_ID,
                "source_url": BASE_URL,
                "source_fetched_at": _now_iso(),
                "raw_payload": raw_payload,
                "raw_text": None,
                "first_seen_at": _now_iso(),
                "last_seen_at": _now_iso(),
                "change_status": "NEW_RECORD",
                "parser_confidence": 85 if parcel_id else 60,
            })

        return listings

    def close(self):
        pass


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
    """Run the tax deed sales scraper."""
    output_path = output_path or REPO_ROOT / "data" / "raw" / f"{SOURCE_ID}.jsonl"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    session = TaxDeedSession(fetch_fn=fetch_fn)
    current = session.fetch_listings()
    session.close()

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
        description="Pull Duval County Tax Deed Sales (taxdeed.duvalclerk.com)."
    )
    parser.add_argument("--out", default=None,
                        help="Output JSONL path. Default: data/raw/tax_deed_sales.jsonl")
    args = parser.parse_args()

    out = Path(args.out) if args.out else None
    stats = run(output_path=out)
    print(json.dumps(stats, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
