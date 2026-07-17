"""
Harris County clerk recordings scraper adapter.

Pulls recorded real property instrument index rows from:
    http://www.cclerk.hctx.net/applications/websearch/RP.aspx

Confirmed mechanism:
- Direct form POST is WAF-blocked to Maintenance.aspx.
- Playwright-rendered search successfully reaches results page `RP_R.aspx?ID=...`.
- Results are rendered in a ListView-style table with fields:
    File Number, File Date, Type, Names, Legal Description, Pages, Film Code

Outputs:
    data/raw/clerk_recordings.jsonl
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

from bs4 import BeautifulSoup

try:
    from playwright.sync_api import sync_playwright
except Exception:  # pragma: no cover - optional at import time
    sync_playwright = None  # type: ignore

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

SOURCE_ID = "clerk_recordings"
BASE_URL = "http://www.cclerk.hctx.net"
SEARCH_URL = f"{BASE_URL}/applications/websearch/RP.aspx"
DEFAULT_OUTPUT = REPO_ROOT / "data" / "raw" / "clerk_recordings.jsonl"
USER_AGENT = "xcerebro-harris-clerk-recordings/0.1 (+private repo)"


def _now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def _raw_record_id(doc_number: str, record_date: str, doc_type: str) -> str:
    key = "|".join(
        [
            "harris_clerk_recordings",
            (doc_number or "").strip(),
            (record_date or "").strip(),
            (doc_type or "").strip().upper(),
        ]
    )
    return "raw_" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:24]


def _normalize_whitespace(s: str) -> str:
    return " ".join(s.split()).strip()


def _parse_result_rows(html: str) -> list[dict]:
    # Parser fallback keyed on unique control indices from the ListView block.
    ctrl_ids = [
        m.group(1)
        for m in re.finditer(
            r'id="ctl00_ContentPlaceHolder1_ListView1_ctrl(\d+)_lblFileNo"', html
        )
    ]
    if not ctrl_ids:
        return []
    first_group = lambda text, pattern: (m.group(1) if (m := re.search(pattern, text)) else "")
    records: list[dict] = []
    for ctrl_id in ctrl_ids:
        prefix = f"ctl00_ContentPlaceHolder1_ListView1_ctrl{ctrl_id}_"
        file_no = first_group(html, rf'{re.escape(prefix)}lblFileNo">([^<]+)')
        file_date = first_group(html, rf'{re.escape(prefix)}lblFileDate">([^<]+)')
        doc_a = first_group(html, rf'{re.escape(prefix)}lnkdetailtest[^>]*>([^<]+)')
        names = re.findall(rf'{re.escape(prefix)}lblNames">([^<]+)', html)
        if not file_no and not names:
            continue
        records.append({
            "file_number": _normalize_whitespace(file_no),
            "file_date": _normalize_whitespace(file_date),
            "doc_type": _normalize_whitespace(doc_a),
            "names": [_normalize_whitespace(n) for n in names],
            "row_text": " | ".join([
                _normalize_whitespace(file_no),
                _normalize_whitespace(file_date),
                _normalize_whitespace(doc_a),
                ", ".join(_normalize_whitespace(n) for n in names),
            ]),
        })
    return records


def run(
    *,
    output_path: Path | None = None,
    date_from: str = "",
    date_to: str = "",
    instrument: str = "",
) -> dict:
    """Playwright-rendered search for Harris clerk recordings."""
    out = output_path or DEFAULT_OUTPUT
    out.parent.mkdir(parents=True, exist_ok=True)
    now = _now_iso()
    meta = {
        "source_id": SOURCE_ID,
        "fetched_at": now,
        "url": SEARCH_URL,
        "count": 0,
        "output_path": str(out),
    }

    if sync_playwright is None:
        meta["error"] = "playwright is not installed"
        return {"meta": meta, "raw_records": []}

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--disable-infobars',
                    '--disable-web-security',
                    '--disable-features=IsolateOrigins,site-per-process',
                ],
            )
            context = browser.new_context(
                user_agent=USER_AGENT,
                locale='en-US',
                viewport={'width': 1280, 'height': 800},
                extra_http_headers={
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Cache-Control': 'no-cache',
                    'Pragma': 'no-cache',
                },
            )
            context.add_init_script(
                """
                Object.defineProperty(navigator, 'webdriver', { get: () => false });
                window.chrome = { runtime: {} };
                Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3] });
                Object.defineProperty(navigator, 'languages', { get: () => ['en-US','en'] });
                """
            )
            page = context.new_page()
            page.set_default_timeout(90000)
            page.goto(SEARCH_URL, wait_until='domcontentloaded')
            page.wait_for_timeout(6000)

            if date_from:
                page.fill('#ctl00_ContentPlaceHolder1_txtFrom', date_from)
            if date_to:
                page.fill('#ctl00_ContentPlaceHolder1_txtTo', date_to)
            if instrument:
                page.fill('#ctl00_ContentPlaceHolder1_txtInstrument', instrument)

            page.click('#ctl00_ContentPlaceHolder1_btnSearch')
            page.wait_for_timeout(15000)

            html = page.content()
            rows = _parse_result_rows(html)
            raw_records: list[dict] = []
            with out.open('w', encoding='utf-8') as fh:
                for row in rows:
                    payload = {
                        'row_text': row.get('row_text', ''),
                        'cells': row.get('cells', []),
                    }
                    raw = {
                        'raw_record_id': _raw_record_id(
                            doc_number='',
                            record_date='',
                            doc_type=instrument or 'UNKNOWN',
                        ),
                        'source_id': SOURCE_ID,
                        'fetched_at': now,
                        'raw_payload': payload,
                    }
                    fh.write(json.dumps(raw, ensure_ascii=False) + '\n')
                    raw_records.append(raw)

            meta['count'] = len(raw_records)
            browser.close()
            return {'meta': meta, 'raw_records': raw_records}
    except Exception as exc:
        meta['error'] = f'{type(exc).__name__}: {exc}'
        return {'meta': meta, 'raw_records': []}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Harris clerk recordings adapter")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--date-from", default="")
    parser.add_argument("--date-to", default="")
    parser.add_argument("--instrument", default="DEED")
    args = parser.parse_args()
    result = run(
        output_path=args.out,
        date_from=args.date_from,
        date_to=args.date_to,
        instrument=args.instrument,
    )
    print(json.dumps(result, indent=2))
