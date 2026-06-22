"""
Duval County official_records adapter — Tyler OnCore public records portal.

Pulls recorded documents (deeds, mortgages, liens, lis_pendens, etc.)
from the Duval County Clerk's Official Records portal at or.duvalclerk.com.

The portal is an ASP.NET MVC application (Kendo UI grid for results).
Public search is available without login after accepting a disclaimer.
Search types include: Name, Instrument #, Doc Type, Record Date,
Consideration, Book/Page, Case #.

Strategy
--------
1. Accept disclaimer via browser actions (cookie-anchored POST)
2. Submit Record Date search via browser actions
3. Parse Kendo UI grid (`table.k-selectable`) results
4. Normalize each record into canonical framework raw_payload shape
5. Write data/raw/official_records.jsonl

Canonical fields emitted in raw_payload:
  doc_number      — instrument number (YYYYNNNNNNNN, 13-digit)
  doc_type        — document type label
  record_date     — recording date (M/D/YYYY)
  grantor         — first direct name (grantor)
  grantee         — first indirect name (grantee)
  book_type       — book type code (OR, etc.)
  book_page       — book/page reference
  legal           — legal description
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, date, timedelta, timezone
from pathlib import Path
from typing import Optional

from bs4 import BeautifulSoup

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

SOURCE_ID = "official_records"
BASE_URL = "https://or.duvalclerk.com"
SEARCH_URL = f"{BASE_URL}/search/SearchTypeRecordDate?Length=6"
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


def _raw_record_id(doc_number: str, record_date: str, doc_type: str) -> str:
    key = "|".join([
        "duval_official_records",
        (doc_number or "").strip(),
        (record_date or "").strip(),
        (doc_type or "").strip().upper(),
    ])
    return "raw_" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:24]


def _normalize_whitespace(s: str) -> str:
    return _WHITESPACE.sub(" ", s).strip()


class OnCoreSession:
    """Manages session with the Duval OR portal."""

    def __init__(self, fetch_fn=None):
        self.client = None
        self.fetch_fn = fetch_fn
        self._disclaimed = False

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

    def _is_disclaimer_page(self, html: str) -> bool:
        """Detect if the response is the disclaimer page (session lost)."""
        if not html or len(html) < 5000:
            return True
        return "btnButton" in html and "I accept the conditions above" in html

    def _is_results_page(self, html: str) -> bool:
        """Detect if the response contains the Kendo results grid."""
        return "k-selectable" in html

    def _fresh_provider(self):
        """Create a new ScrappeyProvider with a fresh session."""
        from scaffold.network.provider import ScrappeyProvider
        import os
        api_key = os.environ.get("SCRAPPEY_API_KEY", "")
        if not api_key:
            return None
        return ScrappeyProvider(api_key)

    def search_by_date(self, search_date: date) -> list[dict]:
        """Search for documents recorded on a specific date.

        Uses browser actions to:
          1. Accept the disclaimer (if shown)
          2. Fill the RecordDate field
          3. Click Search
        Then parses the Kendo UI grid.

        On session-related errors (closed browser, disclaimer redirect), retries
        with a fresh Scrappey session.
        """
        from scaffold.network.provider import ScrappeyProvider

        if not isinstance(self.fetch_fn, ScrappeyProvider):
            return self._search_by_date_http(search_date)

        date_str = search_date.strftime("%-m/%-d/%Y")
        max_attempts = 3

        for attempt in range(max_attempts):
            try:
                html = self._fetch(
                    SEARCH_URL,
                    {},
                    browserActions=[
                        {"type": "wait_for_load_state", "waitForLoadState": "domcontentloaded"},
                        {"type": "wait", "wait": 2},
                        # Accept disclaimer if shown
                        {"type": "if",
                         "condition": "document.querySelector('input#btnButton') !== null",
                         "then": [
                             {"type": "click", "cssSelector": "input#btnButton", "wait": 3},
                             {"type": "wait_for_load_state", "waitForLoadState": "domcontentloaded"},
                         ]},
                        # Fill the date and submit
                        {"type": "wait_for_selector", "cssSelector": "input[name='RecordDate']", "timeout": 15000},
                        {"type": "type", "cssSelector": "input[name='RecordDate']", "text": date_str},
                        {"type": "click", "cssSelector": "input#btnSearch"},
                        {"type": "wait_for_load_state", "waitForLoadState": "networkidle"},
                        {"type": "wait", "wait": 4},
                        # Set page size to 500 to get all records on one page
                        {"type": "execute_js",
                         "code": "var g = document.getElementById('RsltsGrid'); if(g && $(g).data('kendoGrid')) { $(g).data('kendoGrid').dataSource.pageSize(500); }"},
                        {"type": "wait", "wait": 2},
                        {"type": "wait_for_load_state", "waitForLoadState": "networkidle"},
                        {"type": "wait", "wait": 5},
                    ],
                )

                if self._is_results_page(html):
                    records = self._parse_results_grid(html, date_str)
                    if records:
                        return records
                    print(f"  [retry {attempt+1}/{max_attempts}] Results page empty for {date_str}", file=sys.stderr)
                elif self._is_disclaimer_page(html):
                    print(f"  [retry {attempt+1}/{max_attempts}] Got disclaimer page for {date_str}", file=sys.stderr)
                else:
                    print(f"  [retry {attempt+1}/{max_attempts}] Unexpected response for {date_str}: {len(html)} bytes", file=sys.stderr)

            except Exception as exc:
                print(f"  [retry {attempt+1}/{max_attempts}] Error for {date_str}: {exc}", file=sys.stderr)

            if attempt < max_attempts - 1:
                import time
                time.sleep(3)
                fresh = self._fresh_provider()
                if fresh is not None:
                    self.fetch_fn = fresh

        return []

    def _search_by_date_http(self, search_date: date) -> list[dict]:
        """Plain-HTTP fallback (likely won't work — site is JS-heavy)."""
        date_str = search_date.strftime("%-m/%-d/%Y")
        html1 = self._fetch(BASE_URL + "/search/Disclaimer", {"Disclaimer": "true"})
        html2 = self._fetch(
            BASE_URL + "/Search/Disclaimer?st=/search/SearchTypeRecordDate",
            {"disclaimer": "true"}
        )
        html3 = self._fetch(SEARCH_URL, {"RecordDate": date_str, "btnSearch": "Search"})
        return self._parse_results_grid(html3, date_str)

    GRID_COLS = [
        "row_checkbox", "row_number", "grantor", "grantee", "instrument_number",
        "record_date", "doc_type", "book_type", "book_page", "legal",
        "deleted", "after_verify",
    ]

    def _parse_results_grid(self, html: str, record_date: str) -> list[dict]:
        """Parse the Kendo UI results grid."""
        soup = BeautifulSoup(html, "lxml")
        records = []

        table = soup.find("table", class_="k-selectable")
        if not table:
            return records

        tbody = table.find("tbody")
        if not tbody:
            return records

        for row in tbody.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) < 7:
                continue

            vals = {}
            for i, col in enumerate(self.GRID_COLS):
                if i < len(cells):
                    vals[col] = _normalize_whitespace(cells[i].get_text())
                else:
                    vals[col] = ""

            doc_number = vals.get("instrument_number", "")
            doc_type = vals.get("doc_type", "")
            grantor = vals.get("grantor", "")
            grantee = vals.get("grantee", "")
            book_page = vals.get("book_page", "")
            legal = vals.get("legal", "")

            if not doc_number or not doc_number.isdigit():
                continue

            raw_payload = {
                "doc_number": doc_number,
                "doc_type": doc_type,
                "record_date": record_date,
                "grantor": grantor,
                "grantee": grantee,
                "book_type": vals.get("book_type", ""),
                "book_page": book_page,
                "legal": legal,
            }

            records.append({
                "raw_record_id": _raw_record_id(doc_number, record_date, doc_type),
                "source_id": SOURCE_ID,
                "source_url": f"{BASE_URL}/search/SearchTypeRecordDate/{record_date}",
                "source_fetched_at": _now_iso(),
                "raw_payload": raw_payload,
                "raw_text": None,
                "first_seen_at": _now_iso(),
                "last_seen_at": _now_iso(),
                "change_status": "NEW_RECORD",
                "parser_confidence": 95 if doc_number and doc_type else 70,
            })

        return records

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
        start_date: date | None = None,
        end_date: date | None = None,
        fetch_fn=None) -> dict:
    """Run the official records scraper for a date range.

    Default: yesterday (most recent business day).
    """
    output_path = output_path or REPO_ROOT / "data" / "raw" / f"{SOURCE_ID}.jsonl"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    start = start_date or date.today() - timedelta(days=1)
    end = end_date or start

    session = OnCoreSession(fetch_fn=fetch_fn)

    current: list[dict] = []
    current_date = start
    while current_date <= end:
        try:
            day_records = session.search_by_date(current_date)
            current.extend(day_records)
        except Exception as exc:
            print(f"  Failed for {current_date}: {exc}", file=sys.stderr)
        current_date += timedelta(days=1)

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
        "days_scraped": (end - start).days + 1,
        "current_count": len(current),
        "prior_count": len(prior),
        "total_after_merge": len(merged),
        "new_record_count": sum(1 for r in merged if r["change_status"] == "NEW_RECORD"),
        "output_path": str(output_path),
    }
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Pull Duval County Official Records (or.duvalclerk.com)."
    )
    parser.add_argument("--out", default=None,
                        help="Output JSONL path. Default: data/raw/official_records.jsonl")
    parser.add_argument("--start-date", default=None,
                        help="Start date YYYY-MM-DD. Default: yesterday.")
    parser.add_argument("--end-date", default=None,
                        help="End date YYYY-MM-DD. Default: same as start-date.")
    args = parser.parse_args()

    start = date.fromisoformat(args.start_date) if args.start_date else date.today() - timedelta(days=1)
    end = date.fromisoformat(args.end_date) if args.end_date else start

    from scaffold.network.provider import create_fetch_fn
    fetch = create_fetch_fn(backend="scrappey")
    out = Path(args.out) if args.out else None
    stats = run(fetch_fn=fetch, output_path=out, start_date=start, end_date=end)
    print(json.dumps(stats, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
