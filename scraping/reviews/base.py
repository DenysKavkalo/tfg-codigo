"""Common review data structures and identifiers."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime


@dataclass
class ReviewRecord:
    """Normalised review fields returned by platform-specific parsers."""

    review_id: str
    source_review_id: str | None
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


def normalise_source_review_id(value: object) -> str | None:
    """Return a non-empty source identifier as text."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def stable_review_id(
    namespace: str,
    source_review_id: object = None,
    *fallback_parts: object,
) -> str:
    """Build an order-independent identifier for a review.

    Native platform identifiers take precedence. When none is available, the
    hash uses stable review attributes supplied by the parser; page and list
    positions must never be included among those attributes.
    """
    normalised_namespace = _normalise_hash_part(namespace)
    if not normalised_namespace:
        raise ValueError("A non-empty review identifier namespace is required.")

    native_id = normalise_source_review_id(source_review_id)
    if native_id is not None:
        identity_type = "native"
        identity_parts = [native_id]
    else:
        identity_type = "fallback"
        identity_parts = [_normalise_hash_part(part) for part in fallback_parts]
        if not any(identity_parts):
            raise ValueError(
                "A source review identifier or stable fallback fields are required."
            )

    payload = "|".join(
        ["review-id-v2", normalised_namespace, identity_type, *identity_parts]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]


def _normalise_hash_part(value: object) -> str:
    """Normalise a fallback field without depending on display formatting."""
    if value is None:
        return ""
    if isinstance(value, float):
        return format(value, ".12g")
    if isinstance(value, int):
        return str(value)
    return " ".join(str(value).strip().split()).casefold()
