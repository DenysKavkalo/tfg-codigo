"""Registry that routes review requests and parsers by platform."""

from __future__ import annotations

from scraping.reviews.agoda import build_agoda_reviews_request, parse_agoda_reviews
from scraping.reviews.priceline import (
    build_priceline_reviews_page_url,
    parse_priceline_reviews,
)
from scraping.reviews.tripcom import (
    build_tripcom_reviews_request,
    parse_tripcom_reviews,
)


SUPPORTED_REVIEW_PLATFORMS = ("tripcom", "agoda", "priceline")

SINGLE_PAGE_PLATFORMS = {"priceline"}


def max_pages_for_platform(platform: str, requested_max_pages: int) -> int:
    """Apply platform-specific page limits."""
    if platform in SINGLE_PAGE_PLATFORMS:
        return min(requested_max_pages, 1)
    return requested_max_pages


def build_reviews_request(platform: str, base_url: str, page: int) -> dict[str, object]:
    """Build the request specification for a platform and page."""
    if platform == "tripcom":
        return build_tripcom_reviews_request(base_url, page)
    if platform == "agoda":
        return build_agoda_reviews_request(base_url, page)
    if platform == "priceline":
        return {
            "url": build_priceline_reviews_page_url(base_url, page),
            "method": "GET",
        }
    raise ValueError(f"Unsupported review platform: {platform}")


def parse_reviews(platform: str, response_text: str, source_url: str, page: int):
    """Parse review records using the platform-specific parser."""
    if platform == "tripcom":
        return parse_tripcom_reviews(response_text, source_url=source_url, page=page)
    if platform == "agoda":
        return parse_agoda_reviews(response_text, source_url=source_url, page=page)
    if platform == "priceline":
        return parse_priceline_reviews(
            response_text,
            source_url=source_url,
            page=page,
        )
    raise ValueError(f"Unsupported review platform: {platform}")
