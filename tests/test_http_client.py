"""Tests for request pacing in the shared HTTP client."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from scraping.http_client import Fetcher


class FetcherDelayTests(unittest.TestCase):
    """Verify that failed requests still respect the configured delay."""

    @patch("scraping.http_client.sleep")
    def test_delay_is_applied_when_a_request_fails(self, mocked_sleep) -> None:
        fetcher = Fetcher(delay_seconds=1.25, max_retries=0)

        with patch.object(
            fetcher,
            "_fetch_with_requests",
            side_effect=RuntimeError("request failed"),
        ):
            with self.assertRaisesRegex(RuntimeError, "request failed"):
                fetcher.fetch_request("https://example.invalid/reviews")

        mocked_sleep.assert_called_once_with(1.25)


if __name__ == "__main__":
    unittest.main()
