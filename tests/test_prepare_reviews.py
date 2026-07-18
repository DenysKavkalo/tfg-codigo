"""Tests for raw review validation and preparation."""

from __future__ import annotations

import unittest

import pandas as pd

from scraping.prepare_reviews_for_r import prepare_reviews


class PrepareReviewsTests(unittest.TestCase):
    """Verify filtering, deduplication and quality reporting."""

    def test_preparation_handles_legacy_dates_and_missing_stay_date(self) -> None:
        raw = pd.DataFrame(
            [
                _raw_row("r1", "01/02/2024", "9", "ok"),
                _raw_row("r1", "01/02/2024", "9", "ok"),
                _raw_row("r2", "invalid", "8", "ok"),
                _raw_row("r3", "2024-03-01", "12", "ok"),
                _raw_row(None, "2024-04-01", "7", "ok"),
                _raw_row("r4", "2024-05-01", None, "ok"),
                _raw_row(None, None, None, "error"),
            ]
        )

        clean, summary, quality = prepare_reviews(raw)

        self.assertEqual(len(clean), 1)
        self.assertEqual(clean.iloc[0]["review_id"], "r1")
        self.assertIn("stay_date", clean.columns)
        self.assertEqual(clean.iloc[0]["review_year"], 2024)
        self.assertTrue(pd.isna(clean.iloc[0]["stay_year"]))
        self.assertEqual(summary.iloc[0]["n_reviews"], 1)
        row = quality.iloc[0]
        self.assertEqual(row["duplicate_review_id_rows"], 1)
        self.assertEqual(row["missing_review_date_rows"], 1)
        self.assertEqual(row["out_of_range_rating_rows"], 1)
        self.assertEqual(row["missing_review_id_rows"], 1)
        self.assertEqual(row["missing_rating_rows"], 1)
        self.assertEqual(row["technical_incident_rows"], 1)
        self.assertEqual(row["clean_rows"], 1)

    def test_missing_required_column_is_reported(self) -> None:
        with self.assertRaisesRegex(ValueError, "hotel_name"):
            prepare_reviews(pd.DataFrame([{"hotel_id": "H1"}]))


def _raw_row(
    review_id: str | None,
    review_date: str | None,
    rating: str | None,
    status: str,
) -> dict[str, object]:
    return {
        "hotel_id": "H1",
        "hotel_name": "Hotel",
        "platform": "agoda",
        "review_id": review_id,
        "review_date": review_date,
        "rating_scaled_0_10": rating,
        "status": status,
    }


if __name__ == "__main__":
    unittest.main()
