"""Trip.com review request builder and parser."""

from __future__ import annotations

import json
import re
from datetime import datetime
from urllib.parse import parse_qs, urlparse, urlunparse

from dateutil import parser as date_parser

from scraping.reviews.base import ReviewRecord, iso_year, stable_review_id
from scraping.utils import parse_decimal, scale_to_0_10


TRIPCOM_REVIEWS_API = "https://www.trip.com/restapi/soa2/33269/getHotelCommentList"


def build_tripcom_reviews_request(base_url: str, page: int) -> dict[str, object]:
    """Build the Trip.com review API POST request for a page."""
    hotel_id = _hotel_id_from_url(base_url)
    page_size = _page_size_from_url(base_url)
    body = {
        "hotelId": hotel_id,
        "pageIndex": page,
        "pageSize": page_size,
        "repeatComment": 1,
        "needStaticInfo": False,
        "head": {
            "platform": "PC",
            "cver": "0",
            "cid": "tfg",
            "bu": "IBU",
            "group": "trip",
            "aid": "",
            "sid": "",
            "ouid": "",
            "locale": "en-XX",
            "region": "XX",
            "timezone": "1",
            "currency": "USD",
            "pageId": "10320668147",
            "vid": "tfg",
            "guid": "",
            "isSSR": False,
            "extension": [
                {"name": "cityId", "value": ""},
                {"name": "checkIn", "value": ""},
                {"name": "checkOut", "value": ""},
            ],
        },
    }
    return {
        "url": TRIPCOM_REVIEWS_API,
        "method": "POST",
        "json_body": body,
        "source_url": base_url,
        "headers": {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Referer": base_url,
        },
    }


def parse_tripcom_reviews(html: str, source_url: str, page: int) -> list[ReviewRecord]:
    """Parse Trip.com review responses into ReviewRecord objects."""
    comments = _extract_comment_list(html)
    records: list[ReviewRecord] = []

    for index, comment in enumerate(comments, start=1):
        rating = parse_decimal(comment.get("rating"))
        rating_max = parse_decimal(comment.get("ratingMax")) or parse_decimal(
            (comment.get("ratingInfo") or {}).get("ratingMax")
        )
        rating_max = rating_max or 10.0
        review_date = _parse_datetime(comment.get("createDate"))
        stay_date = _parse_datetime(comment.get("checkInDate"))
        title = comment.get("commentLevel")
        comment_id = comment.get("id")

        records.append(
            ReviewRecord(
                review_id=stable_review_id(
                    "tripcom",
                    _url_without_query(source_url),
                    comment_id,
                    review_date,
                    stay_date,
                    rating,
                    index,
                ),
                platform_override=None,
                source_platform="tripcom",
                provider_id=None,
                provider_name="Trip.com",
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


def _extract_comment_list(html: str) -> list[dict]:
    """Extract Trip.com comment dictionaries from JSON or embedded HTML."""
    json_comments = _extract_comment_list_from_json(html)
    if json_comments is not None:
        return json_comments

    pattern = '\\"commentList\\":'
    index = html.find(pattern)
    if index < 0:
        return []

    start = html.find("[", index)
    if start < 0:
        return []

    end = _find_balanced_array_end(html, start)
    if end is None:
        return []

    raw_array = html[start:end]
    json_text = raw_array.replace('\\"', '"')
    try:
        parsed = json.loads(json_text)
    except json.JSONDecodeError:
        return []

    return [entry for entry in parsed if isinstance(entry, dict)]


def _extract_comment_list_from_json(response_text: str) -> list[dict] | None:
    """Extract comments from a JSON API response."""
    try:
        payload = json.loads(response_text)
    except json.JSONDecodeError:
        return None

    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        return []
    comments = data.get("commentList")
    if comments is None:
        return []
    return [entry for entry in comments if isinstance(entry, dict)]


def _find_balanced_array_end(value: str, start: int) -> int | None:
    """Return the end index of a JSON array starting at a position."""
    depth = 0
    for index, char in enumerate(value[start:], start):
        if char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                return index + 1
    return None


def _parse_datetime(value: object) -> str | None:
    """Parse a date-like Trip.com value to ISO format."""
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


def _hotel_id_from_url(url: str) -> int:
    """Extract the Trip.com hotel identifier from a configured URL."""
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    if query.get("hotelId"):
        return int(query["hotelId"][0])

    match = re.search(r"hotel-detail-(\d+)", parsed.path)
    if match:
        return int(match.group(1))

    raise ValueError(
        "Trip.com review URL must contain hotel-detail-<id> or ?hotelId=<id>."
    )


def _page_size_from_url(url: str) -> int:
    """Extract the requested page size from a configured URL."""
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    if query.get("pageSize"):
        return int(query["pageSize"][0])
    return 20
