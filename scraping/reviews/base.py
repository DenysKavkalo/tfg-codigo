"""Common review data structures and identifiers."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime


@dataclass
class ReviewRecord:
    """Normalised review fields returned by platform-specific parsers."""

    review_id: str
    platform_override: str | None
    source_platform: str | None
    provider_id: int | None
    provider_name: str | None
    review_date: str | None
    review_year: int | None
    stay_date: str | None
    stay_year: int | None
    rating_raw: float | None
    rating_min: float
    rating_max: float
    rating_scaled_0_10: float | None
    review_title: str | None
    source_url: str
    page: int


def iso_year(value: str | None) -> int | None:
    """Extract the year from an ISO date string."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).year
    except ValueError:
        return None


def stable_review_id(*parts: object) -> str:
    """Build a stable short hash from review-identifying fields."""
    payload = "|".join("" if part is None else str(part) for part in parts)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]
