"""Priceline review parser for embedded hotel review data."""

from __future__ import annotations

import json
from urllib.parse import urlparse, urlunparse

from bs4 import BeautifulSoup
from dateutil import parser as date_parser

from scraping.reviews.base import (
    ReviewRecord,
    iso_year,
    normalise_source_review_id,
    stable_review_id,
)
from scraping.utils import parse_decimal, scale_to_0_10


def build_priceline_reviews_page_url(base_url: str, page: int) -> str:
    """Return the Priceline review page URL."""
    return base_url


def parse_priceline_reviews(html: str, source_url: str, page: int) -> list[ReviewRecord]:
    """Parse Priceline HTML into ReviewRecord objects."""
    records: list[ReviewRecord] = []
    for review in _extract_reviews(html):
        rating = parse_decimal(review.get("score"))
        review_date = _parse_datetime(review.get("datetime"))
        positive = str(review.get("positive") or "").strip()
        negative = str(review.get("negative") or "").strip()
        source_review_id = normalise_source_review_id(
            review.get("reviewId") or review.get("id") or review.get("review_id")
        )
        hotel_identity = review.get("hotelId") or _url_without_query(source_url)

        records.append(
            ReviewRecord(
                review_id=stable_review_id(
                    f"priceline:{hotel_identity}",
                    source_review_id,
                    review.get("firstName"),
                    review_date,
                    rating,
                    positive,
                    negative,
                ),
                source_review_id=source_review_id,
                platform_override=None,
                source_platform="priceline",
                provider_id=None,
                provider_name="Priceline",
                review_date=review_date,
                review_year=iso_year(review_date),
                stay_date=None,
                stay_year=None,
                rating_raw=rating,
                rating_min=0.0,
                rating_max=10.0,
                rating_scaled_0_10=scale_to_0_10(
                    rating,
                    rating_min=0.0,
                    rating_max=10.0,
                    method="proportional",
                ),
                review_title=None,
                source_url=source_url,
                page=page,
            )
        )
    return records


def _extract_reviews(html: str) -> list[dict]:
    """Extract and deduplicate embedded Priceline review dictionaries."""
    reviews: list[dict] = []
    soup = BeautifulSoup(html, "lxml")
    buffer_node = soup.find("script", id="hotel-reviews-buffer")
    if buffer_node and buffer_node.string:
        try:
            payload = json.loads(buffer_node.string)
            reviews.extend(entry for entry in payload if isinstance(entry, dict))
        except json.JSONDecodeError:
            pass

    decoded_html = html.replace('\\"', '"').replace("\\u0026", "&")
    reviews.extend(_extract_decoded_hotel_reviews(decoded_html))

    deduped: list[dict] = []
    seen: set[tuple[object, ...]] = set()
    for review in reviews:
        key = (
            review.get("hotelId"),
            review.get("datetime"),
            review.get("firstName"),
            review.get("score"),
            review.get("positive"),
            review.get("negative"),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(review)
    return deduped


def _extract_decoded_hotel_reviews(decoded_html: str) -> list[dict]:
    """Extract hotelReviews arrays from decoded Priceline HTML."""
    reviews: list[dict] = []
    search_from = 0
    while True:
        index = decoded_html.find('"hotelReviews":', search_from)
        if index < 0:
            break
        start = decoded_html.find("[", index)
        if start < 0:
            break
        end = _find_balanced_array_end(decoded_html, start)
        if end is None:
            break
        try:
            payload = json.loads(decoded_html[start:end])
            reviews.extend(entry for entry in payload if isinstance(entry, dict))
        except json.JSONDecodeError:
            pass
        search_from = end
    return reviews


def _find_balanced_array_end(value: str, start: int) -> int | None:
    """Return the end index of a JSON array while respecting strings."""
    depth = 0
    in_string = False
    escaped = False
    for index, char in enumerate(value[start:], start):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                return index + 1
    return None


def _parse_datetime(value: object) -> str | None:
    """Parse a date-like Priceline value to ISO format."""
    if not value:
        return None
    try:
        return date_parser.parse(str(value), fuzzy=True).date().isoformat()
    except (ValueError, TypeError, OverflowError):
        return None


def _url_without_query(url: str) -> str:
    """Return a URL without query parameters."""
    parsed = urlparse(url)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))
