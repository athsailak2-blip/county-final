"""
Network provider — routes HTTP requests through Scrappey or Firecrawl
to bypass WAF / government firewalls.

Usage:
    from scaffold.network.provider import create_fetch_fn

    # Scrappey (supports POST + full browser sessions, for ASP.NET portals)
    fetch = create_fetch_fn(backend="scrappey")

    # Firecrawl (GET-only with profile-based cookie persistence)
    fetch = create_fetch_fn(backend="firecrawl")

    # Use with any scraper:
    from scrapers import official_records
    stats = official_records.run(fetch_fn=fetch)

API keys read from env vars if not passed explicitly:
    SCRAPPEY_API_KEY
    FIRECRAWL_API_KEY
"""

from __future__ import annotations

import os
import time
import urllib.parse
from typing import Callable, Optional

import httpx

PROVIDER_TIMEOUT = 180
MAX_RETRIES = 3
RETRY_BACKOFF = 2.0


class NetworkProviderError(RuntimeError):
    """Raised when the network provider API returns an error."""


class _BaseProvider:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.client = httpx.Client(timeout=PROVIDER_TIMEOUT)

    def close(self):
        self.client.close()


class ScrappeyProvider(_BaseProvider):
    """Stateful provider using Scrappey API (full browser mode).

    API docs: https://docs.scrappey.com

    Uses Scrappey's ``session`` parameter to maintain a headless browser
    across requests — cookies, redirects, and JavaScript state persist
    automatically.  A session lives for 200 s after the last request.

    ``proxyCountry: "UnitedStates"`` ensures US-based proxy routing for
    reliable connectivity to US government portals.
    """

    ENDPOINT = "https://publisher.scrappey.com/api/v1"

    def __init__(self, api_key: str):
        super().__init__(api_key)
        self._session: str | None = None

    def _api_request(self, body: dict) -> dict:
        url = f"{self.ENDPOINT}?key={self.api_key}"
        for attempt in range(MAX_RETRIES):
            try:
                resp = self.client.post(url, json=body)
                data = resp.json()
            except Exception as exc:
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_BACKOFF * (2 ** attempt))
                    continue
                raise NetworkProviderError(
                    f"Scrappey request failed after {MAX_RETRIES} attempts: {exc}"
                ) from exc

            status = data.get("data")
            if status != "success":
                error = data.get("error", str(data))
                raise NetworkProviderError(f"Scrappey returned error: {error}")
            return data

        raise NetworkProviderError("Scrappey: exhausted retries")

    def fetch(self, url: str, data: dict | None = None, **extras) -> str:
        body: dict = {
            "url": url,
            "proxyCountry": "UnitedStates",
        }

        if self._session:
            body["session"] = self._session

        # Support extra Scrappey parameters (browserActions, etc.)
        body.update(extras)

        if data:
            body["cmd"] = "request.post"
            body["postData"] = urllib.parse.urlencode(data, doseq=True)
        else:
            body["cmd"] = "request.get"

        result = self._api_request(body)

        sess = result.get("session")
        if sess:
            self._session = sess

        solution = result.get("solution", {})
        return solution.get("response", "") or ""

    def __call__(self, url: str, data: dict | None = None, **extras) -> str:
        return self.fetch(url, data, **extras)


class FirecrawlProvider(_BaseProvider):
    """GET-only provider using Firecrawl API (V2).

    API docs: https://docs.firecrawl.dev

    Uses Firecrawl's ``profile`` parameter to persist cookies and browser
    session across requests.  Suitable for auction calendars, listing
    portals, and other sources that don't need programmatic POST.

    ``proxy: "enhanced"`` enables advanced anti-bot bypass (costs extra
    credits).  ``location.country: "US"`` ensures US proxy routing.
    """

    ENDPOINT = "https://api.firecrawl.dev/v2/scrape"

    def __init__(self, api_key: str, profile: str | None = None):
        super().__init__(api_key)
        self._profile = profile

    def fetch(self, url: str, data: dict | None = None) -> str:
        if data:
            raise NetworkProviderError(
                "Firecrawl does not support POST requests. "
                "Use Scrappey backend for sources that need form submission."
            )

        payload: dict = {
            "url": url,
            "formats": [{"type": "rawHtml"}],
            "proxy": "enhanced",
            "location": {"country": "US"},
        }
        if self._profile:
            payload["profile"] = {"name": self._profile}

        for attempt in range(MAX_RETRIES):
            try:
                resp = self.client.post(
                    self.ENDPOINT,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                )
                body = resp.json()
            except Exception as exc:
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_BACKOFF * (2 ** attempt))
                    continue
                raise NetworkProviderError(
                    f"Firecrawl request failed after {MAX_RETRIES} attempts: {exc}"
                ) from exc

            if not body.get("success"):
                error = body.get("error", str(body))
                raise NetworkProviderError(f"Firecrawl returned error: {error}")

            data_block = body.get("data", {})
            html = data_block.get("rawHtml", "") or data_block.get("html", "")
            return html

        raise NetworkProviderError("Firecrawl: exhausted retries")

    def __call__(self, url: str, data: dict | None = None) -> str:
        return self.fetch(url, data)


def create_fetch_fn(
    backend: str = "scrappey",
    api_key: str | None = None,
    profile: str | None = None,
) -> Callable[[str, dict | None], str]:
    """Create a fetch_fn compatible with scraper _fetch / _post.

    Args:
        backend: ``"scrappey"`` (supports GET+POST+session) or
                 ``"firecrawl"`` (GET only, with profile persistence).
        api_key: API key.  Reads from env var if not provided
                 (``SCRAPPEY_API_KEY`` or ``FIRECRAWL_API_KEY``).
        profile: Firecrawl profile name for cookie/session persistence.
                 Ignored for Scrappey.

    Returns:
        Callable with signature ``(url: str, data: dict | None) -> str``

    Raises:
        NetworkProviderError: if the API key is missing or the
                              provider cannot be initialised.
    """
    backend = backend.lower().strip()
    if backend == "scrappey":
        key = api_key or os.environ.get("SCRAPPEY_API_KEY", "")
        if not key:
            raise NetworkProviderError(
                "Scrappey API key not found. Set SCRAPPEY_API_KEY env var "
                "or pass api_key= to create_fetch_fn()."
            )
        return ScrappeyProvider(key)
    elif backend == "firecrawl":
        key = api_key or os.environ.get("FIRECRAWL_API_KEY", "")
        if not key:
            raise NetworkProviderError(
                "Firecrawl API key not found. Set FIRECRAWL_API_KEY env var "
                "or pass api_key= to create_fetch_fn()."
            )
        return FirecrawlProvider(key, profile)
    else:
        raise NetworkProviderError(
            f"Unknown backend: {backend!r}. Use 'scrappey' or 'firecrawl'."
        )


def main() -> int:
    """CLI entry point for testing connectivity.

    Usage:
        python3 -m scaffold.network.provider <url> [--backend scrappey|firecrawl]
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="Test network provider connectivity to a URL."
    )
    parser.add_argument("url", help="URL to fetch")
    parser.add_argument("--backend", default="scrappey",
                        choices=["scrappey", "firecrawl"],
                        help="Network provider backend")
    parser.add_argument("--api-key", default=None,
                        help="API key (default: reads from env)")
    parser.add_argument("--profile", default=None,
                        help="Firecrawl profile name")
    parser.add_argument("--post", default=None, nargs="*",
                        help="POST data as key=value pairs (Scrappey only)")
    parser.add_argument("--output", default=None,
                        help="Save response to file")
    args = parser.parse_args()

    try:
        post_data = None
        if args.post:
            post_data = {}
            for kv in args.post:
                if "=" in kv:
                    k, v = kv.split("=", 1)
                    post_data[k] = v

        fetch = create_fetch_fn(
            backend=args.backend,
            api_key=args.api_key,
            profile=args.profile,
        )
        html = fetch(args.url, post_data or {})
        print(f"Fetched {len(html)} bytes from {args.url}")
        if args.output:
            with open(args.output, "w", encoding="utf-8") as fh:
                fh.write(html)
            print(f"Saved to {args.output}")
        else:
            print(html[:2000])
        return 0
    except Exception as exc:
        print(f"Error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
