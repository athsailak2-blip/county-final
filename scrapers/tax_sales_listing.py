"""
Harris County delinquent tax sale listing scraper adapter.

Pulls the current monthly tax foreclosure sale property listing from:
    https://www.hctax.net/Property/listings/taxsalelisting

Confirmed mechanism:
- GET returns full listing HTML.
- Each listing row exposes:
    - Account#    (div.account)
    - Cause#      (div.SuitNumber)
    - Adjudged Value (div.adjudgedValue)
    - Property detail link `/property/listings/saledetail?account=...`
    - HCAD statement form action `https://public.hcad.org/records/outsider/hc.asp?acct=...`
- No confirmed login/TOU hard gate on simple GET.

Outputs:
    data/raw/foreclosure_notices_map.jsonl
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

try:
    import httpx
    from bs4 import BeautifulSoup
except Exception:  # pragma: no cover - optional deps at import time
    httpx = None  # type: ignore
    BeautifulSoup = None  # type: ignore

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

SOURCE_ID = "foreclosure_notices_map"
LISTING_URL = "https://www.hctax.net/Property/listings/taxsalelisting"
DEFAULT_OUTPUT = REPO_ROOT / "data" / "raw" / "foreclosure_notices_map.jsonl"
USER_AGENT = "xcerebro-harris-tax-sales/0.1 (+private repo)"
REQUEST_TIMEOUT = 60


def _now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def _raw_record_id(account_number: str, cause_number: str) -> str:
    key = "|".join([
        "harris_tax_sale_listing",
        (account_number or "").strip().upper(),
        (cause_number or "").strip().upper(),
    ])
    return "raw_" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:24]


def _normalize_whitespace(s: str) -> str:
    return " ".join(s.split()).strip()


_RE_MONEY = re.compile(r"[\$\s,]")


def _parse_money(text: str) -> Optional[str]:
    val = _normalize_whitespace(text)
    if not val:
        return None
    return _RE_MONEY.sub("", val)


def _parse_listing_records(html: str) -> list[dict]:
    if BeautifulSoup is None:
        return []
    soup = BeautifulSoup(html, "html.parser")
    records: list[dict] = []

    # Each listing card appears to be grouped in a table row or card.
    # Strong signals: Account# and Cause# labels inside the page.
    for block in soup.select("div.row"):
        account_el = block.select_one("div.account strong")
        cause_el = block.select_one("div.SuitNumber strong")
        adjudged_el = block.select_one("div.adjudgedValue strong")
        if not account_el and not cause_el:
            continue

        account_number = _normalize_whitespace(account_el.get_text()) if account_el else ""
        cause_number = _normalize_whitespace(cause_el.get_text()) if cause_el else ""
        adjudged_raw = _normalize_whitespace(adjudged_el.get_text()) if adjudged_el else ""
        adjudged_value = _parse_money(adjudged_raw)

        detail_href = ""
        for a in block.select("a[href]"):
            href = a.get("href", "") or ""
            if "saledetail?account=" in href:
                detail_href = href
                break

        if not account_number and not cause_number:
            continue

        records.append({
            "account_number": account_number,
            "cause_number": cause_number,
            "adjudged_value": adjudged_value,
            "detail_path": detail_href,
        })

    return records


def run(
    *,
    output_path: Path | None = None,
    fetch_hint: str = "GET",
) -> dict:
    """Fetch the public listing page and emit canonical raw records."""
    out = output_path or DEFAULT_OUTPUT
    out.parent.mkdir(parents=True, exist_ok=True)
    now = _now_iso()
    meta = {
        "source_id": SOURCE_ID,
        "fetched_at": now,
        "url": LISTING_URL,
        "fetch_hint": fetch_hint,
        "count": 0,
        "output_path": str(out),
    }

    try:
        if httpx is None:
            raise RuntimeError("httpx is not installed")
        resp = httpx.get(
            LISTING_URL,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
            },
            timeout=REQUEST_TIMEOUT,
            follow_redirects=True,
        )
        resp.raise_for_status()
        html = resp.text
    except Exception as exc:
        meta["error"] = f"{type(exc).__name__}: {exc}"
        return {"meta": meta, "raw_records": []}

    records = _parse_listing_records(html)
    raw_records = []
    with out.open("w", encoding="utf-8") as fh:
        for rec in records:
            raw = {
                "raw_record_id": _raw_record_id(rec["account_number"], rec["cause_number"]),
                "source_id": SOURCE_ID,
                "fetched_at": now,
                "raw_payload": {
                    "account_number": rec["account_number"],
                    "cause_number": rec["cause_number"],
                    "adjudged_value": rec["adjudged_value"],
                    "detail_path": rec["detail_path"],
                    "source_url": LISTING_URL,
                    "fetch_hint": fetch_hint,
                },
            }
            fh.write(json.dumps(raw, ensure_ascii=False) + "\n")
            raw_records.append(raw)

    meta["count"] = len(raw_records)
    return {"meta": meta, "raw_records": raw_records}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Harris tax sale listing adapter")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    result = run(output_path=args.out)
    print(json.dumps(result, indent=2))
