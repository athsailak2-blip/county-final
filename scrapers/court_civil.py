"""
Harris County District Clerk civil/search scraper adapter.

Portal:
    - Search/login: https://www.hcdistrictclerk.com/Edocs/Public/Search.aspx?Tab=tabCivilMobile
    - Confirmed login fields: txtUserName / txtPassword / btnLogin
    - Confirmed live blocker: post-login search controls remain hidden/inaccessible to automation in headless browser sessions
    - Confirmed manual path: operator can save result text/HTML and we parse it locally

This adapter prefers a manual text capture when provided.
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
    from playwright.sync_api import sync_playwright
except Exception:  # pragma: no cover - optional at import time
    sync_playwright = None  # type: ignore

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

SOURCE_ID = "court_civil"
SEARCH_URL = "https://www.hcdistrictclerk.com/Edocs/Public/Search.aspx?Tab=tabCivilMobile"
DEFAULT_OUTPUT = REPO_ROOT / "data" / "raw" / "court_civil.jsonl"
USER_AGENT = "xcerebro-harris-court-civil/0.1 (+private repo)"


def _now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def _raw_record_id(case_number: str, style: str, case_type: str, filed_date: str) -> str:
    key = "|".join(
        [
            "harris_court_civil",
            (case_number or "").strip().upper(),
            (style or "").strip().upper(),
            (case_type or "").strip().upper(),
            (filed_date or "").strip(),
        ]
    )
    return "raw_" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:24]


def _normalize_whitespace(s: str) -> str:
    return " ".join(s.split()).strip()


_CASE_RE = re.compile(r"^(\d{6,}[A-Z0-9-]+-\s*\d+)$")
_SKIP_PREFIXES = (
    "Header",
    "jump to",
    "skip to",
    "Background Checks",
    "Child Support",
    "Contact Us",
    "Court Costs",
    "District Clerk",
    "e-Subpoena",
    "For Government",
    "Forms",
    "Jury",
    "Mandated",
    "Passport",
    "Search our Records",
    "court alerts",
    "Tech Help",
    "Logo",
    "Marilyn",
    "Harris County",
    "Image of",
    "Welcome ",
    "Main content",
    "System messages",
    "Search Results",
    "Instructions",
    "Instrucciones",
    "Print Result",
    "Click on the style",
    "picture-link",
    "Total records",
    "results pager",
    "Page ",
    "Search results",
    "Case (Cause) Number",
    "important note",
    "Footer",
    "Follow us",
    "HARRIS COUNTY DISTRICT CLERK",
    "About",
    "Hours and",
    "Jobs",
    "FAQS",
    "Media",
    "Public Datasets",
    "Public Reports",
    "Accessibility",
    "Privacy",
    "Social Media",
    "embedgooglemap",
)


def _is_skip(line: str) -> bool:
    for prefix in _SKIP_PREFIXES:
        if line.startswith(prefix):
            return True
    return False


def _parse_search_rows(source: str) -> list[dict]:
    """Parse court search results from manual text capture."""
    lines = source.splitlines()
    records: list[dict] = []
    current_case: Optional[str] = None
    chunks: list[str] = []

    for raw in lines:
        line = raw.strip("\r")
        if not line:
            continue
        if _is_skip(line):
            continue
        m = _CASE_RE.match(line)
        if m:
            if current_case is not None:
                text = "\t".join(chunks)
                parts = text.split("\t")
                status_case = parts[0] if parts else ""
                rest = parts[1:]
                date = ""
                court = ""
                region = ""
                offense = ""
                style_parts = []
                date_idx = None
                for i, pt in enumerate(rest):
                    if re.search(r"\b\d{1,2}/\d{1,2}/\d{4}\b", pt):
                        date_idx = i
                        date = pt
                        break
                if date_idx is not None:
                    style_parts = rest[:date_idx]
                    after = rest[date_idx + 1 :]
                    if len(after) >= 1:
                        court = after[0]
                    if len(after) >= 2:
                        region = after[1]
                    if len(after) >= 3:
                        offense = after[2]
                style = " ".join(style_parts).strip()
                status = ""
                case_type = ""
                m2 = re.match(r"(.+?)\s*-\s*(.+)", status_case)
                if m2:
                    status = m2.group(1).strip()
                    case_type = m2.group(2).strip()
                records.append(
                    {
                        "case_number": current_case,
                        "status": status,
                        "case_type": case_type,
                        "style": style,
                        "file_date": date,
                        "court": court,
                        "region": region,
                        "offense": offense,
                    }
                )
            current_case = m.group(1)
            chunks = []
        else:
            chunks.append(line)

    if current_case is not None:
        text = "\t".join(chunks)
        parts = text.split("\t")
        status_case = parts[0] if parts else ""
        rest = parts[1:]
        date = ""
        court = ""
        region = ""
        offense = ""
        style_parts = []
        date_idx = None
        for i, pt in enumerate(rest):
            if re.search(r"\b\d{1,2}/\d{1,2}/\d{4}\b", pt):
                date_idx = i
                date = pt
                break
        if date_idx is not None:
            style_parts = rest[:date_idx]
            after = rest[date_idx + 1 :]
            if len(after) >= 1:
                court = after[0]
            if len(after) >= 2:
                region = after[1]
            if len(after) >= 3:
                offense = after[2]
        style = " ".join(style_parts).strip()
        status = ""
        case_type = ""
        m2 = re.match(r"(.+?)\s*-\s*(.+)", status_case)
        if m2:
            status = m2.group(1).strip()
            case_type = m2.group(2).strip()
        records.append(
            {
                "case_number": current_case,
                "status": status,
                "case_type": case_type,
                "style": style,
                "file_date": date,
                "court": court,
                "region": region,
                "offense": offense,
            }
        )

    return records


def run(
    *,
    output_path: Path | None = None,
    username: str = "",
    password: str = "",
    search_party: str = "",
    manual_text_path: Path | str | None = None,
) -> dict:
    """Login and/or collect civil search results.

    Preferred manual path: pass manual_text_path to parse saved operator output.
    """
    out = output_path or DEFAULT_OUTPUT
    out.parent.mkdir(parents=True, exist_ok=True)
    now = _now_iso()
    meta = {
        "source_id": SOURCE_ID,
        "fetched_at": now,
        "url": SEARCH_URL,
        "count": 0,
        "output_path": str(out),
        "logged_in": False,
        "error": None,
        "post_url": None,
    }

    records: list[dict] = []
    raw_records: list[dict] = []

    if manual_text_path:
        try:
            text = Path(manual_text_path).read_text(encoding="utf-8", errors="ignore")
            records = _parse_search_rows(text)
        except Exception as exc:
            meta["error"] = f"{type(exc).__name__}: {exc}"
            return {"meta": meta, "raw_records": []}
    else:
        if not username or not password:
            meta["error"] = "missing credentials"
            return {"meta": meta, "raw_records": []}

        if sync_playwright is None:
            meta["error"] = "playwright is not installed"
            return {"meta": meta, "raw_records": []}

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True,
                    args=["--disable-blink-features=AutomationControlled"],
                )
                context = browser.new_context(
                    user_agent=USER_AGENT,
                    locale="en-US",
                )
                page = context.new_page()
                page.goto(SEARCH_URL, wait_until="domcontentloaded", timeout=60000)

                page.fill("#txtUserName", username)
                page.fill("#txtPassword", password)
                page.click("#btnLogin")
                page.wait_for_timeout(10000)

                html = page.content()
                if "logout" not in html.lower():
                    meta["error"] = "login_failed"
                    browser.close()
                    return {"meta": meta, "raw_records": []}

                meta["logged_in"] = True
                records = _parse_search_rows(html)
                browser.close()
        except Exception as exc:
            meta["error"] = f"{type(exc).__name__}: {exc}"
            return {"meta": meta, "raw_records": []}

    with out.open("w", encoding="utf-8") as fh:
        for rec in records:
            rec["source_url"] = SEARCH_URL
            rec["fetched_at"] = now
            raw = {
                "raw_record_id": _raw_record_id(
                    rec.get("case_number", ""),
                    rec.get("style", ""),
                    rec.get("case_type", ""),
                    rec.get("file_date", ""),
                ),
                "source_id": SOURCE_ID,
                "fetched_at": now,
                "raw_payload": rec,
            }
            fh.write(json.dumps(raw, ensure_ascii=False) + "\n")
            raw_records.append(raw)

    meta["count"] = len(raw_records)
    return {"meta": meta, "raw_records": raw_records}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Harris court civil adapter")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--username", default="")
    parser.add_argument("--password", default="")
    parser.add_argument("--search-party", default="")
    parser.add_argument("--manual-text-path", default="")
    args = parser.parse_args()
    result = run(
        output_path=args.out,
        username=args.username,
        password=args.password,
        search_party=args.search_party,
        manual_text_path=args.manual_text_path or None,
    )
    print(json.dumps(result, indent=2))
