"""HTTP helpers used by the review scrapers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from time import sleep

import requests


DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0 Safari/537.36"
)


@dataclass
class FetchResult:
    """Response body and metadata returned by a fetch operation."""

    url: str
    html: str
    status_code: int | None
    fetched_with: str


class Fetcher:
    """Small HTTP client with retries, delays and optional browser rendering."""

    def __init__(
        self,
        timeout_seconds: int = 30,
        user_agent: str = DEFAULT_USER_AGENT,
        delay_seconds: float = 4.0,
        max_retries: int = 3,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.delay_seconds = delay_seconds
        self.max_retries = max_retries
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": user_agent,
                "Accept-Language": "en-US,en;q=0.9,es;q=0.8",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }
        )

    def fetch(self, url: str, render_js: bool = False) -> FetchResult:
        """Fetch a URL using the default GET request path."""
        return self.fetch_request(url=url, render_js=render_js)

    def fetch_request(
        self,
        url: str,
        render_js: bool = False,
        method: str = "GET",
        json_body: dict | None = None,
        headers: dict | None = None,
    ) -> FetchResult:
        """Fetch a URL using GET or POST, optionally rendering GET pages."""
        method = method.upper()
        if render_js and method != "GET":
            raise ValueError("Playwright rendering is only supported for GET requests.")

        if render_js:
            result = self._fetch_with_playwright(url)
        elif method == "POST":
            result = self._fetch_with_post(url, json_body=json_body, headers=headers)
        elif method == "GET":
            result = self._fetch_with_requests(url)
        else:
            raise ValueError(f"Unsupported HTTP method: {method}")
        sleep(max(0.0, self.delay_seconds))
        return result

    def _fetch_with_requests(self, url: str) -> FetchResult:
        """Fetch a GET URL with requests."""
        response = self._request_with_retries("GET", url)
        return FetchResult(
            url=str(response.url),
            html=response.text,
            status_code=response.status_code,
            fetched_with="requests",
        )

    def _fetch_with_post(
        self,
        url: str,
        json_body: dict | None,
        headers: dict | None,
    ) -> FetchResult:
        """Fetch a POST URL with a JSON body."""
        response = self._request_with_retries(
            "POST",
            url,
            json_body=json_body,
            headers=headers,
        )
        return FetchResult(
            url=str(response.url),
            html=response.text,
            status_code=response.status_code,
            fetched_with="requests_post",
        )

    def _request_with_retries(
        self,
        method: str,
        url: str,
        json_body: dict | None = None,
        headers: dict | None = None,
    ) -> requests.Response:
        """Execute an HTTP request and retry transient server errors."""
        retry_statuses = {429, 500, 502, 503, 504}
        last_response: requests.Response | None = None

        for attempt in range(self.max_retries + 1):
            response = self.session.request(
                method,
                url,
                json=json_body,
                headers=headers,
                timeout=self.timeout_seconds,
            )
            last_response = response
            if response.status_code not in retry_statuses:
                response.raise_for_status()
                return response
            if attempt < self.max_retries:
                sleep(min(8.0, 1.5 * (attempt + 1)))

        assert last_response is not None
        last_response.raise_for_status()
        return last_response

    def _fetch_with_playwright(self, url: str) -> FetchResult:
        """Render a GET page with Playwright and return its HTML."""
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError(
                "Playwright is not installed. Run: python -m pip install playwright"
            ) from exc

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(
                user_agent=self.session.headers["User-Agent"],
                locale="en-US",
            )
            page.goto(url, wait_until="networkidle", timeout=self.timeout_seconds * 1000)
            html = page.content()
            final_url = page.url
            browser.close()

        return FetchResult(
            url=final_url,
            html=html,
            status_code=None,
            fetched_with="playwright",
        )


def save_html(html: str, path: str | Path) -> None:
    """Write fetched HTML to disk for debugging or audit purposes."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
