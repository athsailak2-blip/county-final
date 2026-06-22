"""
Duval County foreclosure_sales adapter — RealAuction/RealForeclose portal.

Pulls foreclosure auction listings from the Duval County Clerk's
RealForeclose portal at duval.realforeclose.com.

The portal is a RealAuction SPA. The auction calendar is publicly
viewable; property details may require free registration. Sales held
Monday-Friday at 11:00 AM ET.

Strategy
--------
1. Fetch auction calendar (publicly viewable per Clerk website)
2. Extract scheduled auction dates with property counts
3. For each auction date, fetch property listing details
4. Normalize each listing into canonical framework raw_payload shape
5. Write data/raw/foreclosure_sales.jsonl

Note: Full property detail scraping may require registration cookies.
The scraper supports injection of pre-obtained session cookies via the
fetch_fn parameter for testing or operator-assisted runs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, date, timezone
from pathlib import Path
from typing import Iterable, Optional

import httpx
from bs4 import BeautifulSoup

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

SOURCE_ID = "foreclosure_sales"
BASE_URL = "https://www.duval.realforeclose.com"
CALENDAR_URL = f"{BASE_URL}/index.cfm?zaction=USER&zmethod=CALENDAR"
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


def _raw_record_id(case_number: str, address: str, auction_date: str) -> str:
    key = "|".join([
        "duval_foreclosure_sales",
        (case_number or "").strip().upper(),
        (address or "").strip().upper(),
        (auction_date or "").strip(),
    ])
    return "raw_" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:24]


def _normalize_whitespace(s: str) -> str:
    return _WHITESPACE.sub(" ", s).strip()


class RealForecloseSession:
    """Manages session with the RealForeclose auction portal."""

    def __init__(self, fetch_fn=None, cookies: dict = None):
        self.client = httpx.Client(
            verify=False,
            timeout=REQUEST_TIMEOUT,
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
        )
        if cookies:
            for name, value in cookies.items():
                self.client.cookies.set(name, value)
        self.fetch_fn = fetch_fn

    def _fetch(self, url: str) -> str:
        if self.fetch_fn:
            return self.fetch_fn(url, {})
        resp = self.client.get(url)
        resp.raise_for_status()
        return resp.text

    def fetch_calendar(self, month: int | None = None,
                       year: int | None = None) -> list[dict]:
        """Fetch auction calendar and return list of auction dates with counts."""
        url = CALENDAR_URL
        if month and year:
            url += f"&month={month}&year={year}"

        html = self._fetch(url)
        soup = BeautifulSoup(html, "lxml")

        auctions = []
        day_boxes = soup.find_all("div", class_="CALBOX")
        for box in day_boxes:
            if not box.get("dayid"):
                continue
            cell_text = _normalize_whitespace(box.get_text())
            if "Foreclosure" not in cell_text and "FC" not in cell_text:
                continue

            num_el = box.find("span", class_="CALNUM")
            day_num = _normalize_whitespace(num_el.get_text()) if num_el else ""

            msg_el = box.find("span", class_="CALMSG")
            active_el = msg_el.find("span", class_="CALACT") if msg_el else None
            total_el = msg_el.find("span", class_="CALSCH") if msg_el else None
            active_count = _normalize_whitespace(active_el.get_text()) if active_el else "0"
            total_count = _normalize_whitespace(total_el.get_text()) if total_el else "0"

            time_el = box.find("span", class_="CALTIME")
            sale_time = _normalize_whitespace(time_el.get_text()) if time_el else "11:00 AM ET"

            auctions.append({
                "day": day_num,
                "active_count": int(active_count),
                "total_count": int(total_count),
                "sale_time": sale_time,
            })

        return auctions

    def close(self):
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
        fetch_fn=None, cookies: dict = None) -> dict:
    """Run the foreclosure sales scraper."""
    output_path = output_path or REPO_ROOT / "data" / "raw" / f"{SOURCE_ID}.jsonl"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    session = RealForecloseSession(fetch_fn=fetch_fn, cookies=cookies)

    now = datetime.now(timezone.utc)
    calendar = session.fetch_calendar(month=now.month, year=now.year)

    current: list[dict] = []
    for entry in calendar:
        raw_payload = {
            "auction_day": entry["day"],
            "active_count": entry["active_count"],
            "total_count": entry["total_count"],
            "sale_time": entry["sale_time"],
            "source": "realforeclose_calendar",
        }

        record_id = _raw_record_id(
            "", f"{now.year}-{now.month:02d}-{entry['day']}",
            f"{now.year}-{now.month:02d}"
        )
        current.append({
            "raw_record_id": record_id,
            "source_id": SOURCE_ID,
            "source_url": CALENDAR_URL,
            "source_fetched_at": _now_iso(),
            "raw_payload": raw_payload,
            "raw_text": None,
            "first_seen_at": _now_iso(),
            "last_seen_at": _now_iso(),
            "change_status": "NEW_RECORD",
            "parser_confidence": 90,
        })

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
        "calendar_month": now.month,
        "calendar_year": now.year,
        "current_count": len(current),
        "prior_count": len(prior),
        "total_after_merge": len(merged),
        "new_record_count": sum(1 for r in merged if r["change_status"] == "NEW_RECORD"),
        "output_path": str(output_path),
    }
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Pull Duval County Foreclosure Sales (duval.realforeclose.com)."
    )
    parser.add_argument("--out", default=None,
                        help="Output JSONL path. Default: data/raw/foreclosure_sales.jsonl")
    args = parser.parse_args()

    out = Path(args.out) if args.out else None
    stats = run(output_path=out)
    print(json.dumps(stats, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
