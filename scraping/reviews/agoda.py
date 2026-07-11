"""Agoda review request builder and parser."""

from __future__ import annotations

import json
import re
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from dateutil import parser as date_parser

from scraping.reviews.base import ReviewRecord, iso_year, stable_review_id
from scraping.utils import parse_decimal, scale_to_0_10


AGODA_REVIEWS_API = "https://www.agoda.com/api/cronos/property/review/HotelReviews"
AGODA_PROVIDER_ID = 332
AGODA_PROVIDER_MODE_OWN = "own"
AGODA_PROVIDER_MODE_SEPARATE = "separate"

PROVIDER_PLATFORM_MAP = {
    332: "agoda",
    3038: "booking_via_agoda",
}


def build_agoda_reviews_request(base_url: str, page: int) -> dict[str, object]:
    """Build the Agoda review API POST request for a page."""
    parsed = urlparse(base_url)
    query = parse_qs(parsed.query)
    hotel_id = _query_int(query, "hotelId")
    if hotel_id is None:
        raise ValueError("Agoda review URL must include hotelId, for example ?hotelId=27983077")

    page_size = _query_int(query, "pageSize") or 20
    provider_id = _query_int(query, "providerId") or AGODA_PROVIDER_ID
    referer = query.get("referer", ["https://www.agoda.com/"])[0]

    body = {
        "hotelId": hotel_id,
        "hotelProviderId": provider_id,
        "demographicId": 0,
        "pageNo": page,
        "pageSize": page_size,
        "sorting": 1,
        "reviewProviderIds": [
            332,
            3038,
            27901,
            28999,
            29100,
            27999,
            27980,
            27989,
            29014,
        ],
        "isReviewPage": False,
        "isCrawlablePage": True,
        "paginationSize": 5,
    }

    return {
        "url": _base_api_url(base_url),
        "method": "POST",
        "json_body": body,
        "source_url": base_url,
        "headers": {
            "Origin": "https://www.agoda.com",
            "Referer": referer,
            "Content-Type": "application/json",
        },
    }


def parse_agoda_reviews(response_text: str, source_url: str, page: int) -> list[ReviewRecord]:
    """Parse Agoda review API responses into ReviewRecord objects."""
    try:
        payload = json.loads(response_text)
    except json.JSONDecodeError:
        return []

    comments = ((payload.get("commentList") or {}).get("comments")) or []
    records: list[ReviewRecord] = []
    provider_mode = _provider_mode(source_url)

    for index, comment in enumerate(comments, start=1):
        provider_id = _as_int(comment.get("providerId"))
        provider_name = _provider_name(comment, provider_id)
        if provider_mode == AGODA_PROVIDER_MODE_OWN and provider_id != AGODA_PROVIDER_ID:
            continue

        rating = parse_decimal(comment.get("rating"))
        rating_max = 10.0
        review_date = _parse_date(comment.get("reviewDate") or comment.get("formattedReviewDate"))
        stay_date = _parse_date(comment.get("checkInDate") or comment.get("checkInDateMonthAndYear"))
        review_id = comment.get("hotelReviewId") or comment.get("encryptedReviewData")
        title = comment.get("reviewTitle") or comment.get("ratingText")
        platform_override = _provider_platform(provider_id, provider_name, provider_mode)

        records.append(
            ReviewRecord(
                review_id=stable_review_id(
                    platform_override or "agoda",
                    review_id,
                    review_date,
                    stay_date,
                    rating,
                    index,
                ),
                platform_override=platform_override,
                source_platform="agoda",
                provider_id=provider_id,
                provider_name=provider_name,
                review_date=review_date,
                review_year=iso_year(review_date),
                stay_date=stay_date,
                stay_year=iso_year(stay_date),
                rating_raw=rating,
                rating_min=0.0,
                rating_max=rating_max,
                rating_scaled_0_10=scale_to_0_10(
                    rating,
                    rating_min=0.0,
                    rating_max=rating_max,
                    method="proportional",
                ),
                review_title=title,
                source_url=source_url,
                page=page,
            )
        )

    return records


def _provider_mode(source_url: str) -> str:
    """Read the configured Agoda provider handling mode from the URL."""
    query = parse_qs(urlparse(source_url).query)
    value = (query.get("providerMode") or [AGODA_PROVIDER_MODE_OWN])[0]
    value = str(value).lower().strip()
    if value == AGODA_PROVIDER_MODE_SEPARATE:
        return AGODA_PROVIDER_MODE_SEPARATE
    return AGODA_PROVIDER_MODE_OWN


def _provider_platform(
    provider_id: int | None,
    provider_name: str | None,
    provider_mode: str,
) -> str | None:
    """Return the analysis platform label for an Agoda provider."""
    if provider_mode != AGODA_PROVIDER_MODE_SEPARATE:
        return None
    if provider_id in PROVIDER_PLATFORM_MAP:
        return PROVIDER_PLATFORM_MAP[provider_id]
    provider_slug = _slug(provider_name or f"provider_{provider_id}")
    return f"{provider_slug}_via_agoda"


def _provider_name(comment: dict, provider_id: int | None) -> str:
    """Extract a readable provider name from an Agoda comment."""
    value = (
        comment.get("reviewProviderText")
        or comment.get("providerName")
        or comment.get("provider")
        or comment.get("source")
    )
    if value:
        return str(value).strip()
    if provider_id == AGODA_PROVIDER_ID:
        return "Agoda"
    return f"Provider {provider_id}"


def _slug(value: str) -> str:
    """Convert a provider name to a platform-safe slug."""
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return slug or "provider"


def _as_int(value: object) -> int | None:
    """Convert a value to int when possible."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _base_api_url(base_url: str) -> str:
    """Return the Agoda API URL without query parameters."""
    parsed = urlparse(base_url)
    if parsed.netloc and parsed.path:
        return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))
    return AGODA_REVIEWS_API


def _query_int(query: dict[str, list[str]], key: str) -> int | None:
    """Read an integer query parameter."""
    values = query.get(key)
    if not values:
        return None
    try:
        return int(values[0])
    except (TypeError, ValueError):
        return None


def _parse_date(value: object) -> str | None:
    """Parse a date-like Agoda value to ISO format."""
    if not value:
        return None
    try:
        return date_parser.parse(str(value), fuzzy=True).date().isoformat()
    except (ValueError, TypeError, OverflowError):
        return None
