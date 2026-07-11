"""Generic extraction helpers for ratings and bot-challenge detection."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass

from bs4 import BeautifulSoup

from scraping.utils import parse_decimal, parse_int


BOT_CHALLENGE_PATTERNS = (
    "Bot or Not?",
    "Eres un robot",
    "DataDome CAPTCHA",
    "captcha-delivery.com",
    "arkoselabs",
    "g-recaptcha",
    "Access Denied",
    "challenge-container",
    "verify that you're not a robot",
    "window.awswafcookiedomainlist",
    "/__challenge_",
    "htlSpiderActionErrorCode",
)


@dataclass
class ExtractionCandidate:
    """Candidate aggregate rating found in a page."""

    rating_raw: float | None = None
    rating_min: float | None = None
    rating_max: float | None = None
    n_reviews: int | None = None
    method: str = "unknown"
    source_text: str | None = None


def detect_bot_challenge(html: str) -> str | None:
    """Return the detected bot-challenge marker, if any."""
    lower = html.lower()
    for pattern in BOT_CHALLENGE_PATTERNS:
        if pattern.lower() in lower:
            return pattern
    return None


def extract_from_json_ld(soup: BeautifulSoup) -> ExtractionCandidate | None:
    """Extract aggregate rating data from JSON-LD blocks."""
    for script in soup.select('script[type="application/ld+json"]'):
        raw = script.string or script.get_text(strip=True)
        if not raw:
            continue
        for item in _loads_json_ld(raw):
            candidate = _extract_aggregate_rating(item)
            if candidate and candidate.rating_raw is not None:
                return candidate
    return None


def extract_from_microdata(soup: BeautifulSoup) -> ExtractionCandidate | None:
    """Extract aggregate rating data from schema.org microdata."""
    rating_node = soup.select_one('[itemprop="ratingValue"], meta[itemprop="ratingValue"]')
    if not rating_node:
        return None

    review_node = soup.select_one(
        '[itemprop="reviewCount"], [itemprop="ratingCount"], '
        'meta[itemprop="reviewCount"], meta[itemprop="ratingCount"]'
    )
    best_node = soup.select_one('[itemprop="bestRating"], meta[itemprop="bestRating"]')
    worst_node = soup.select_one('[itemprop="worstRating"], meta[itemprop="worstRating"]')

    rating_text = _node_value(rating_node)
    return ExtractionCandidate(
        rating_raw=parse_decimal(rating_text),
        rating_min=parse_decimal(_node_value(worst_node)),
        rating_max=parse_decimal(_node_value(best_node)),
        n_reviews=parse_int(_node_value(review_node)),
        method="microdata",
        source_text=rating_text,
    )


def extract_by_selectors(
    soup: BeautifulSoup,
    rating_selectors: Iterable[str],
    review_count_selectors: Iterable[str],
) -> ExtractionCandidate | None:
    """Extract rating data using caller-provided CSS selectors."""
    rating_text = None
    for selector in rating_selectors:
        node = soup.select_one(selector)
        rating_text = _node_value(node)
        rating = parse_decimal(rating_text)
        if rating is not None:
            break
    else:
        rating = None

    if rating is None:
        return None

    n_reviews = None
    for selector in review_count_selectors:
        node = soup.select_one(selector)
        n_reviews = parse_int(_node_value(node))
        if n_reviews is not None:
            break

    return ExtractionCandidate(
        rating_raw=rating,
        n_reviews=n_reviews,
        method="css_selector",
        source_text=rating_text,
    )


def extract_from_text_patterns(
    soup: BeautifulSoup,
    rating_max: float,
) -> ExtractionCandidate | None:
    """Extract rating data from common text patterns."""
    text = " ".join(soup.get_text(" ", strip=True).split())
    patterns = [
        rf"(\d+(?:[.,]\d+)?)\s*/\s*{int(rating_max)}",
        rf"(\d+(?:[.,]\d+)?)\s+of\s+{int(rating_max)}",
        rf"(\d+(?:[.,]\d+)?)\s+out\s+of\s+{int(rating_max)}",
        rf"scored\s+(\d+(?:[.,]\d+)?)",
        rf"rated\s+(\d+(?:[.,]\d+)?)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return ExtractionCandidate(
                rating_raw=parse_decimal(match.group(1)),
                rating_max=rating_max,
                method="text_pattern",
                source_text=match.group(0),
            )
    return None


def _loads_json_ld(raw: str) -> list[object]:
    """Load one or more JSON-LD objects from a script body."""
    raw = raw.strip()
    candidates: list[object] = []

    try:
        parsed = json.loads(raw)
        candidates.extend(_flatten_json_ld(parsed))
        return candidates
    except json.JSONDecodeError:
        pass

    # Some pages include several JSON objects in the same script tag.
    for match in re.finditer(r"\{.*?\}", raw, flags=re.DOTALL):
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            continue
        candidates.extend(_flatten_json_ld(parsed))

    return candidates


def _flatten_json_ld(value: object) -> list[object]:
    """Flatten JSON-LD lists and @graph containers."""
    if isinstance(value, list):
        items: list[object] = []
        for entry in value:
            items.extend(_flatten_json_ld(entry))
        return items
    if isinstance(value, dict):
        graph = value.get("@graph")
        if isinstance(graph, list):
            return [value, *graph]
        return [value]
    return []


def _extract_aggregate_rating(item: object) -> ExtractionCandidate | None:
    """Recursively find an aggregateRating object."""
    if isinstance(item, list):
        for entry in item:
            found = _extract_aggregate_rating(entry)
            if found:
                return found
        return None

    if not isinstance(item, dict):
        return None

    aggregate = item.get("aggregateRating")
    if isinstance(aggregate, list) and aggregate:
        aggregate = aggregate[0]
    if isinstance(aggregate, dict):
        rating_text = aggregate.get("ratingValue")
        return ExtractionCandidate(
            rating_raw=parse_decimal(rating_text),
            rating_min=parse_decimal(aggregate.get("worstRating")),
            rating_max=parse_decimal(aggregate.get("bestRating")),
            n_reviews=parse_int(
                aggregate.get("reviewCount")
                or aggregate.get("ratingCount")
                or aggregate.get("count")
            ),
            method="json_ld",
            source_text=str(rating_text) if rating_text is not None else None,
        )

    for value in item.values():
        if isinstance(value, (dict, list)):
            found = _extract_aggregate_rating(value)
            if found:
                return found
    return None


def _node_value(node) -> str | None:
    """Read the most useful textual value from a BeautifulSoup node."""
    if node is None:
        return None
    for attr in ("content", "aria-label", "title", "data-rating", "value"):
        value = node.get(attr)
        if value:
            return str(value)
    return node.get_text(" ", strip=True)
