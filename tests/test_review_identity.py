"""Tests for stable review identities and scraper-level deduplication."""

from __future__ import annotations

import json
import unittest

import pandas as pd

from scraping.reviews.agoda import parse_agoda_reviews
from scraping.reviews.base import stable_review_id
from scraping.reviews.priceline import parse_priceline_reviews
from scraping.reviews.tripcom import parse_tripcom_reviews
from scraping.scrape_reviews_year import OUTPUT_COLUMNS, deduplicate_output_rows


class StableReviewIdTests(unittest.TestCase):
    """Verify that review identifiers do not depend on response ordering."""

    def test_native_identifier_takes_precedence(self) -> None:
        first = stable_review_id("agoda:1", "native-123", "2024-01-01", 8)
        changed_metadata = stable_review_id("agoda:1", "native-123", "2025-02-02", 3)
        self.assertEqual(first, changed_metadata)

    def test_fallback_identifier_normalises_text_and_numbers(self) -> None:
        first = stable_review_id("priceline:1", None, "Alice", "Good  room", 8.0)
        equivalent = stable_review_id("PRICELINE:1", None, " alice ", "good room", 8)
        self.assertEqual(first, equivalent)

    def test_agoda_identifier_survives_reordering_and_page_changes(self) -> None:
        comments = [
            {
                "providerId": 332,
                "hotelReviewId": "agoda-1",
                "rating": 9.2,
                "reviewDate": "2025-01-03",
                "reviewTitle": "Excellent",
            },
            {
                "providerId": 3038,
                "hotelReviewId": "booking-1",
                "rating": 8,
                "reviewDate": "2025-01-04",
                "reviewTitle": "Good",
            },
        ]
        source_url = (
            "https://www.agoda.com/api/cronos/property/review/HotelReviews"
            "?hotelId=2937&providerMode=separate"
        )
        first = parse_agoda_reviews(
            json.dumps({"commentList": {"comments": comments}}), source_url, page=1
        )
        second = parse_agoda_reviews(
            json.dumps({"commentList": {"comments": list(reversed(comments))}}),
            source_url,
            page=7,
        )
        self.assertEqual(_ids_by_source(first), _ids_by_source(second))

    def test_tripcom_identifier_survives_reordering_and_page_changes(self) -> None:
        comments = [
            {"id": "trip-1", "rating": 9, "createDate": "2025-01-03"},
            {"id": "trip-2", "rating": 8, "createDate": "2025-01-04"},
        ]
        source_url = (
            "https://www.trip.com/hotels/las-vegas-hotel-detail-737263/"
            "the-venetian-resort-las-vegas/"
        )
        first = parse_tripcom_reviews(
            json.dumps({"data": {"commentList": comments}}), source_url, page=1
        )
        second = parse_tripcom_reviews(
            json.dumps({"data": {"commentList": list(reversed(comments))}}),
            source_url,
            page=9,
        )
        self.assertEqual(_ids_by_source(first), _ids_by_source(second))

    def test_tripcom_embedded_parser_ignores_brackets_inside_text(self) -> None:
        comments = [
            {
                "id": "trip-bracket",
                "rating": 9,
                "createDate": "2025-01-03",
                "content": "Good room ] and quiet floor",
            }
        ]
        embedded = json.dumps({"commentList": comments}).replace('"', '\\"')
        source_url = (
            "https://www.trip.com/hotels/las-vegas-hotel-detail-737263/"
            "the-venetian-resort-las-vegas/"
        )

        records = parse_tripcom_reviews(embedded, source_url, page=1)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].source_review_id, "trip-bracket")

    def test_priceline_fallback_identifier_survives_reordering(self) -> None:
        reviews = [
            {
                "hotelId": "60761",
                "firstName": "Ana",
                "datetime": "2025-01-03",
                "score": 9,
                "positive": "Location",
                "negative": "",
            },
            {
                "hotelId": "60761",
                "firstName": "Luis",
                "datetime": "2025-01-04",
                "score": 8,
                "positive": "Room",
                "negative": "Noise",
            },
        ]
        source_url = "https://www.priceline.com/hotel-deals/example.ssp"
        first = parse_priceline_reviews(_priceline_html(reviews), source_url, page=1)
        second = parse_priceline_reviews(
            _priceline_html(list(reversed(reviews))), source_url, page=2
        )
        self.assertEqual(
            sorted(record.review_id for record in first),
            sorted(record.review_id for record in second),
        )

    def test_scraper_deduplicates_valid_rows_but_keeps_audit_rows(self) -> None:
        valid = _output_row(status="ok", review_id="stable-id", page=1)
        duplicate = _output_row(status="ok", review_id="stable-id", page=2)
        error_one = _output_row(status="error", review_id=None, page=3)
        error_two = _output_row(status="error", review_id=None, page=4)
        frame = pd.DataFrame(
            [valid, duplicate, error_one, error_two], columns=OUTPUT_COLUMNS
        )

        result = deduplicate_output_rows(frame)

        self.assertEqual(sum(result["status"].eq("ok")), 1)
        self.assertEqual(sum(result["status"].eq("error")), 2)


def _ids_by_source(records: list[object]) -> dict[str | None, str]:
    return {record.source_review_id: record.review_id for record in records}


def _priceline_html(reviews: list[dict[str, object]]) -> str:
    return (
        '<html><script id="hotel-reviews-buffer" type="application/json">'
        + json.dumps(reviews)
        + "</script></html>"
    )


def _output_row(status: str, review_id: str | None, page: int) -> dict[str, object]:
    row = {column: None for column in OUTPUT_COLUMNS}
    row.update(
        {
            "hotel_id": "H1",
            "platform": "agoda",
            "review_id": review_id,
            "review_date": "2025-01-01" if status == "ok" else None,
            "page": page,
            "status": status,
        }
    )
    return row


if __name__ == "__main__":
    unittest.main()
