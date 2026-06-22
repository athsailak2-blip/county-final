"""
Duval County property_appraiser adapter — Duval PA public search portal.

Pulls parcel detail from the Duval County Property Appraiser's public
search portal at paopropertysearch.coj.net.

The portal is an ASP.NET WebForms application with __VIEWSTATE-backed
form posts. Strategy: drive the form via Scrappey browser actions, then
parse the returned HTML for the results table (search results) or the
detail panel (single parcel).

Public search flow:
  1. GET https://paopropertysearch.coj.net/  (loads default Search.aspx)
  2. Fill tbName (or tbRE6 + tbRE4) and click bSearch
  3. Parse gridResults table to get RE# + owner + address
  4. Click the RE# link to navigate to Detail.aspx?RE=NNNNNNNNNN
  5. Parse the detail panel for assessed value, mailing address, etc.

The detail page contains:
  - RE# (NNNNNN-NNNN)
  - Owner(s) + mailing address
  - Primary Site Address (situs)
  - Value Summary: 2025 Certified + 2026 In Progress
    - Total Building Value, Extra Feature Value,
      Land Value (Market/Agric.), Just (Market) Value,
      Assessed Value, Cap Diff/Portability Amt, Exemptions, Taxable Value
  - Sales History (book/page, date, price, type, qualified, vacant/imp)
  - Buildings section (if any) — year_built
  - Land & Legal

Search results table columns:
  [0] RE#            (linked to Detail.aspx?RE=NNNNNNNNNN)
  [1] Owner
  [2] Street Number
  [3] Street Name
  [4] Street Type
  [5] Unit
  [6] (empty)
  [7] City
  [8] Zip
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from bs4 import BeautifulSoup

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

SOURCE_ID = "property_appraiser"
BASE_URL = "https://paopropertysearch.coj.net"
ENTRY_URL = BASE_URL + "/"
DETAIL_URL_TMPL = BASE_URL + "/Detail.aspx?RE={re10}"

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


def _normalize_whitespace(s: str) -> str:
    return _WHITESPACE.sub(" ", s).strip()


def _normalize_name(name: str) -> str:
    """Strip extra punctuation, collapse whitespace, title-case cautiously.

    The PA portal is whitespace-token-friendly: "DOE JOHN" or "DOE, JOHN"
    both work. We always uppercase since the PA backend matches
    case-insensitively but we want a stable cache key.
    """
    n = _normalize_whitespace(name).upper()
    n = n.replace(",", " ").replace(".", " ")
    n = _WHITESPACE.sub(" ", n)
    return n.strip()


def _parse_re(re_str: str) -> str:
    """Convert '000029-0000' or '0000290000' to canonical 10-digit form."""
    digits = re.sub(r"\D", "", re_str or "")
    if len(digits) == 10:
        return digits
    if len(digits) == 9:
        return "0" + digits
    return digits


def _format_re_dashed(re10: str) -> str:
    """Convert 10-digit RE# to 'NNNNNN-NNNN' display form."""
    re10 = re.sub(r"\D", "", re10)
    if len(re10) != 10:
        return re10
    return f"{re10[:6]}-{re10[6:]}"


class PASession:
    """Manages session with the Duval PA portal.

    Uses Scrappey browser actions for navigation. Each search/detail
    call uses a single scrappey request with multi-step browser actions.
    """

    def __init__(self, fetch_fn=None):
        self.fetch_fn = fetch_fn
        self._cache_search: dict = {}
        self._cache_detail: dict = {}

    def _fetch(self, url: str, *, browser_actions: list,
               session_reset: bool = False) -> str:
        from scaffold.network.provider import ScrappeyProvider

        if session_reset and isinstance(self.fetch_fn, ScrappeyProvider):
            self.fetch_fn._session = None
        if not isinstance(self.fetch_fn, ScrappeyProvider):
            raise RuntimeError(
                "PASession requires a ScrappeyProvider fetch_fn "
                "(ASP.NET WebForms needs full browser support)."
            )
        return self.fetch_fn(url, {}, browserActions=browser_actions)

    # ------------------------------------------------------------------ search
    def search_by_name(self, name: str) -> list[dict]:
        """Search by owner/business name. Returns up to 500 result rows.

        Each result: {re10, owner, street_no, street_name, street_type,
                      unit, city, zip}
        """
        norm = _normalize_name(name)
        if not norm or len(norm) < 2:
            return []
        if norm in self._cache_search:
            return self._cache_search[norm]

        actions = [
            {"type": "wait_for_load_state", "waitForLoadState": "domcontentloaded"},
            {"type": "wait", "wait": 3},
            {"type": "wait_for_selector", "cssSelector": "#ctl00_cphBody_tbName",
             "timeout": 20000},
            {"type": "type", "cssSelector": "#ctl00_cphBody_tbName",
             "text": norm},
            {"type": "click", "cssSelector": "#ctl00_cphBody_bSearch"},
            {"type": "wait_for_load_state", "waitForLoadState": "networkidle"},
            {"type": "wait", "wait": 5},
        ]
        # If still on home page (search returned no results, table missing),
        # we'd otherwise be stuck — but 500 results is enough for our use.
        try:
            html = self._fetch(ENTRY_URL, browser_actions=actions,
                               session_reset=True)
        except Exception as exc:
            print(f"  [PA] search failed for {norm!r}: {exc}", file=sys.stderr)
            self._cache_search[norm] = []
            return []

        results = self._parse_results_table(html)
        self._cache_search[norm] = results
        return results

    def search_by_re(self, re_number: str) -> Optional[dict]:
        """Search by RE# (10-digit or 'NNNNNN-NNNN'). Returns first result row."""
        re10 = _parse_re(re_number)
        if len(re10) != 10:
            return None
        if re10 in self._cache_detail:
            return self._cache_detail[re10]
        re6, re4 = re10[:6], re10[6:]

        actions = [
            {"type": "wait_for_load_state", "waitForLoadState": "domcontentloaded"},
            {"type": "wait", "wait": 3},
            {"type": "wait_for_selector", "cssSelector": "#ctl00_cphBody_tbRE6",
             "timeout": 20000},
            {"type": "type", "cssSelector": "#ctl00_cphBody_tbRE6",
             "text": re6},
            {"type": "type", "cssSelector": "#ctl00_cphBody_tbRE4",
             "text": re4},
            {"type": "click", "cssSelector": "#ctl00_cphBody_bSearch"},
            {"type": "wait_for_load_state", "waitForLoadState": "networkidle"},
            {"type": "wait", "wait": 5},
        ]
        try:
            html = self._fetch(ENTRY_URL, browser_actions=actions,
                               session_reset=True)
        except Exception as exc:
            print(f"  [PA] RE# search failed for {re10}: {exc}", file=sys.stderr)
            return None
        results = self._parse_results_table(html)
        if results:
            # Update cache with the keyed result so detail lookup hits cache
            self._cache_detail[re10] = results[0]
            return results[0]
        return None

    # ------------------------------------------------------------- detail page
    def fetch_detail(self, re_number: str) -> Optional[dict]:
        """Navigate to detail page for an RE# and parse the panel.

        Returns canonical parcel dict: {parcel_id, owner_name, owner_mailing,
        situs_address, situs_city, situs_zip, just_value, assessed_value,
        land_value, building_value, year_built (if any building), tax_district,
        subdivision, property_use, total_area, last_sale, sales_history[]}.
        """
        re10 = _parse_re(re_number)
        if len(re10) != 10:
            return None
        if re10 in self._cache_detail and self._cache_detail[re10].get("just_value"):
            return self._cache_detail[re10]
        detail_url = DETAIL_URL_TMPL.format(re10=re10)

        actions = [
            {"type": "wait_for_load_state", "waitForLoadState": "domcontentloaded"},
            {"type": "wait", "wait": 3},
            {"type": "wait_for_selector", "cssSelector": "#ctl00_cphBody_tbRE6",
             "timeout": 20000},
            {"type": "type", "cssSelector": "#ctl00_cphBody_tbRE6",
             "text": re10[:6]},
            {"type": "type", "cssSelector": "#ctl00_cphBody_tbRE4",
             "text": re10[6:]},
            {"type": "click", "cssSelector": "#ctl00_cphBody_bSearch"},
            {"type": "wait_for_load_state", "waitForLoadState": "networkidle"},
            {"type": "wait", "wait": 5},
            {"type": "click", "cssSelector": "#ctl00_cphBody_gridResults a[href*='Detail.aspx']",
             "wait": 4},
            {"type": "wait_for_load_state", "waitForLoadState": "networkidle"},
            {"type": "wait", "wait": 6},
        ]
        try:
            html = self._fetch(ENTRY_URL, browser_actions=actions,
                               session_reset=True)
        except Exception as exc:
            print(f"  [PA] detail fetch failed for {re10}: {exc}",
                  file=sys.stderr)
            return None

        if "Property Details" not in html and "cannot be found" in html:
            return None
        parsed = self._parse_detail_page(html)
        if parsed and "parcel_id" not in parsed:
            parsed["parcel_id"] = _format_re_dashed(re10)
        # Reuse cached search row to avoid double-fetch
        self._cache_detail[re10] = parsed
        return parsed

    def get_parcel(self, re_number: str) -> Optional[dict]:
        """One-call helper: search-by-RE + parse detail (bypasses intermediate
        results table since search_by_re returns the first result row and
        we then navigate to its detail)."""
        row = self.search_by_re(re_number)
        if not row:
            return None
        return self.fetch_detail(re_number)

    # ------------------------------------------------------------------ parsers
    def _parse_results_table(self, html: str) -> list[dict]:
        """Parse the gridResults table after a search."""
        soup = BeautifulSoup(html, "lxml")
        table = soup.find("table", id="ctl00_cphBody_gridResults")
        if not table:
            return []
        rows = []
        for tr in table.find_all("tr"):
            cells = tr.find_all("td")
            if len(cells) < 9:
                continue
            re_cell = _normalize_whitespace(cells[0].get_text())
            if not re_cell or "-" not in re_cell:
                continue
            re10 = _parse_re(re_cell)
            if len(re10) != 10:
                continue
            link = cells[0].find("a")
            href = link.get("href", "") if link else ""
            row = {
                "re10": re10,
                "re_display": _format_re_dashed(re10),
                "owner": _normalize_whitespace(cells[1].get_text()),
                "street_no": _normalize_whitespace(cells[2].get_text()),
                "street_name": _normalize_whitespace(cells[3].get_text()),
                "street_type": _normalize_whitespace(cells[4].get_text()),
                "unit": _normalize_whitespace(cells[5].get_text()),
                "city": _normalize_whitespace(cells[7].get_text()),
                "zip": _normalize_whitespace(cells[8].get_text()),
                "detail_href": href,
            }
            rows.append(row)
        return rows

    def _parse_detail_page(self, html: str) -> Optional[dict]:
        """Parse the property detail page."""
        soup = BeautifulSoup(html, "lxml")
        text = soup.get_text(separator="\n")
        text = re.sub(r"\n\s*\n", "\n", text)
        text = re.sub(r"[ \t]+", " ", text)

        out: dict = {}

        # RE# — appears as a labeled value
        m = re.search(r"RE\s*#\s*\n?\s*(\d{6}-\d{4})", text)
        if m:
            out["parcel_id"] = m.group(1)

        # Owners block: at top of page, two-line block with mailing address.
        # Find "Owner" or first non-empty name before "Primary Site Address".
        primary_idx = text.find("Primary Site Address")
        if primary_idx > 0:
            head = text[:primary_idx]
            head_lines = [l.strip() for l in head.split("\n") if l.strip()]
            # Strip header/UI noise
            filtered = []
            for line in head_lines:
                lo = line.lower()
                if lo.startswith("property appraiser") or \
                   lo.startswith("basic search") or \
                   lo.startswith("advanced search") or \
                   lo.startswith("tangible search") or \
                   lo.startswith("tip:") or \
                   lo.startswith("collapse") or \
                   lo.startswith("new search") or \
                   lo.startswith("refine search"):
                    continue
                filtered.append(line)
            # Heuristic: first 1-3 lines are owner name(s), then a line with
            # a number (PO BOX / street#) starts the mailing address, and the
            # mailing line with state + ZIP ends the address.
            owners = []
            mailing_lines: list = []
            in_mailing = False
            for line in filtered:
                if not in_mailing:
                    # Owner line: all-uppercase, no digits, len > 3
                    has_state_zip = bool(re.search(r"[A-Z]{2}\s+\d{5}", line))
                    starts_with_digit = bool(re.match(r"^\d", line))
                    is_upper = line == line.upper() and any(c.isalpha() for c in line)
                    if has_state_zip or starts_with_digit:
                        in_mailing = True
                    elif is_upper and len(line) > 3:
                        owners.append(line)
                        continue
                if in_mailing:
                    mailing_lines.append(line)
            if owners:
                out["owner_name"] = owners[0]
            if len(owners) > 1:
                out["owner_name_2"] = owners[1]
            if mailing_lines:
                out["owner_mailing"] = _normalize_whitespace(
                    " ".join(mailing_lines)
                )

        # Primary Site Address
        m = re.search(
            r"Primary Site Address\s*\n\s*(.+?)(?:\n([A-Za-z .]+)\s+FL\s+(\d{5}))",
            text,
        )
        if m:
            out["situs_address"] = _normalize_whitespace(m.group(1))
            out["situs_city"] = _normalize_whitespace(m.group(2))
            out["situs_zip"] = m.group(3)
        else:
            # Fallback: simpler pattern
            m2 = re.search(
                r"Primary Site Address\s*\n\s*(.+?)\n(.+?)\s+FL\s+(\d{5})",
                text, re.DOTALL,
            )
            if m2:
                out["situs_address"] = _normalize_whitespace(m2.group(1))
                out["situs_city"] = _normalize_whitespace(m2.group(2))
                out["situs_zip"] = m2.group(3)

        # Tax District
        m = re.search(r"Tax District\s*\n\s*(\S+)", text)
        if m:
            out["tax_district"] = m.group(1)

        # Property Use
        m = re.search(r"Property Use\s*\n\s*(\S+)", text)
        if m:
            out["property_use"] = m.group(1)

        # Subdivision
        m = re.search(r"Subdivision\s*\n\s*([^\n]+)", text)
        if m:
            out["subdivision"] = _normalize_whitespace(m.group(1))

        # Total Area
        m = re.search(r"Total Area\s*\n\s*([\d,]+)", text)
        if m:
            out["total_area"] = int(m.group(1).replace(",", ""))

        # Value Summary — Assessed Value (2025 Certified column)
        m = re.search(
            r"Assessed Value\s*\n\s*\$([\d,.]+)\s*\n\s*\$([\d,.]+)",
            text,
        )
        if m:
            out["assessed_value_2025"] = float(m.group(1).replace(",", ""))
            out["assessed_value_2026"] = float(m.group(2).replace(",", ""))
        m = re.search(
            r"Just \(Market\) Value\s*\n\s*\$([\d,.]+)\s*\n\s*\$([\d,.]+)",
            text,
        )
        if m:
            out["just_value_2025"] = float(m.group(1).replace(",", ""))
            out["just_value_2026"] = float(m.group(2).replace(",", ""))
        m = re.search(
            r"Land Value \(Market\)\s*\n\s*\$([\d,.]+)\s*\n\s*\$([\d,.]+)",
            text,
        )
        if m:
            out["land_value_2025"] = float(m.group(1).replace(",", ""))
            out["land_value_2026"] = float(m.group(2).replace(",", ""))
        m = re.search(
            r"Total Building Value\s*\n\s*\$([\d,.]+)\s*\n\s*\$([\d,.]+)",
            text,
        )
        if m:
            out["building_value_2025"] = float(m.group(1).replace(",", ""))
            out["building_value_2026"] = float(m.group(2).replace(",", ""))
        m = re.search(
            r"Taxable Value\s*\n\s*\$([\d,.]+)\s*\n\s*\$([\d,.]+)",
            text,
        )
        if m:
            out["taxable_value_2025"] = float(m.group(1).replace(",", ""))
            out["taxable_value_2026"] = float(m.group(2).replace(",", ""))

        # Year built — appears in Buildings section as a labeled value
        m = re.search(r"Year Built\s*\n\s*(\d{4})", text)
        if m:
            out["year_built"] = int(m.group(1))

        # Sales History — most recent sale (first row in table)
        # Format: Book/Page, Sale Date, Sale Price, Deed Type, Qual/Unq, Vac/Imp
        m = re.search(
            r"Sales History\s*\n"
            r"(?:Book/Page\s*\n[\s\S]*?)?"
            r"(\d{5}-\d{5})\s*\n"
            r"(\d{1,2}/\d{1,2}/\d{4})\s*\n"
            r"\$([\d,.]+)",
            text,
        )
        if m:
            out["last_sale_book_page"] = m.group(1)
            out["last_sale_date"] = m.group(2)
            out["last_sale_price"] = float(m.group(3).replace(",", ""))

        # If we couldn't extract RE#, this is not a real detail page
        if "parcel_id" not in out:
            return None
        return out

    def close(self):
        pass


def _is_vacant(parcel: dict) -> bool:
    """Return True if parcel is vacant (no buildings)."""
    bld = parcel.get("building_value_2026") or parcel.get("building_value_2025")
    return not bld or bld == 0


def _build_address_string(parcel: dict) -> str:
    """Return formatted situs address line."""
    parts = []
    if parcel.get("situs_address"):
        parts.append(parcel["situs_address"])
    if parcel.get("situs_city"):
        parts.append(parcel["situs_city"])
    if parcel.get("situs_zip"):
        parts.append(f"FL {parcel['situs_zip']}")
    return ", ".join(parts)


# ----------------------------------------------------------------- CLI runner


def run(*, output_path: Path | None = None,
        fetch_fn=None,
        names: list[str] | None = None) -> dict:
    """Run PA enrichment for a list of owner names.

    Writes JSONL of {parcel_id, owner_name, owner_mailing, situs_address,
    situs_city, situs_zip, just_value, assessed_value, land_value,
    building_value, taxable_value, year_built, tax_district, subdivision,
    property_use, last_sale_date, last_sale_price, source_fetched_at}.
    """
    output_path = output_path or REPO_ROOT / "data" / "raw" / f"{SOURCE_ID}.jsonl"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not names:
        return {"source_id": SOURCE_ID, "records_written": 0}

    session = PASession(fetch_fn=fetch_fn)
    out_records: list[dict] = []
    seen_re: set = set()
    failures: list[str] = []

    for i, name in enumerate(names):
        norm = _normalize_name(name)
        if not norm:
            continue
        if (i + 1) % 25 == 0:
            print(f"  [PA] {i+1}/{len(names)} — {norm!r}", file=sys.stderr)
        try:
            results = session.search_by_name(norm)
        except Exception as exc:
            print(f"  [PA] search_by_name failed for {norm!r}: {exc}",
                  file=sys.stderr)
            failures.append(norm)
            time.sleep(2)
            continue
        if not results:
            continue
        # For each result, fetch detail (one per unique RE#)
        for row in results[:5]:  # cap at 5 matches per name
            re10 = row.get("re10")
            if not re10 or re10 in seen_re:
                continue
            try:
                detail = session.fetch_detail(re10)
            except Exception as exc:
                print(f"  [PA] detail failed for {re10}: {exc}", file=sys.stderr)
                failures.append(re10)
                time.sleep(1)
                continue
            if not detail:
                continue
            seen_re.add(re10)
            record = dict(detail)
            record["source_id"] = SOURCE_ID
            record["source_url"] = DETAIL_URL_TMPL.format(re10=re10)
            record["source_fetched_at"] = _now_iso()
            record["queried_name"] = name
            out_records.append(record)
            time.sleep(0.5)

    session.close()

    with open(output_path, "w", encoding="utf-8") as fh:
        for r in out_records:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    return {
        "source_id": SOURCE_ID,
        "names_queried": len(names),
        "records_written": len(out_records),
        "failures": len(failures),
        "output_path": str(output_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Pull Duval County Property Appraiser parcel details."
    )
    parser.add_argument("--names", default=None,
                        help="Path to a file with one name per line, OR a "
                             "comma-separated list.")
    parser.add_argument("--out", default=None,
                        help="Output JSONL path. Default: data/raw/property_appraiser.jsonl")
    args = parser.parse_args()

    if not args.names:
        print("Provide --names <file> or --names 'DOE JOHN,SMITH JANE'",
              file=sys.stderr)
        return 1

    p = Path(args.names)
    if p.exists():
        names = [l.strip() for l in p.read_text().splitlines() if l.strip()]
    else:
        names = [n.strip() for n in args.names.split(",") if n.strip()]

    from scaffold.network.provider import create_fetch_fn
    fetch = create_fetch_fn(backend="scrappey")

    out = Path(args.out) if args.out else None
    stats = run(output_path=out, fetch_fn=fetch, names=names)
    print(json.dumps(stats, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
