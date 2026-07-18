"""Shared parsing and filesystem utilities for the scraping pipeline."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path


NUMBER_RE = re.compile(r"[-+]?\d+(?:[.,]\d+)?(?:[.,]\d{3})*")


def parse_decimal(value: object) -> float | None:
    """Extract a decimal number from a value when possible."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip()
    match = NUMBER_RE.search(text)
    if not match:
        return None

    token = match.group(0)
    return _normalise_number_token(token)


def _normalise_number_token(token: str, integer_context: bool = False) -> float | None:
    """Normalise decimal and thousands separators before numeric parsing."""
    token = token.strip().replace(" ", "")
    if not token:
        return None

    if "," in token and "." in token:
        last_comma = token.rfind(",")
        last_dot = token.rfind(".")
        decimal_sep = "," if last_comma > last_dot else "."
        thousands_sep = "." if decimal_sep == "," else ","
        token = token.replace(thousands_sep, "")
        token = token.replace(decimal_sep, ".")
    elif "," in token:
        parts = token.split(",")
        if integer_context or all(len(part) == 3 for part in parts[1:]):
            token = "".join(parts)
        else:
            token = token.replace(",", ".")
    elif "." in token:
        parts = token.split(".")
        if integer_context or all(len(part) == 3 for part in parts[1:]):
            token = "".join(parts)

    try:
        return float(token)
    except ValueError:
        return None


def scale_to_0_10(
    rating: float | None,
    rating_min: float,
    rating_max: float,
    method: str = "proportional",
) -> float | None:
    """Scale a rating to the common 0-10 range."""
    if rating is None:
        return None
    if rating_max <= rating_min:
        return None

    if method == "proportional":
        scaled = 10.0 * rating / rating_max
    elif method == "minmax":
        scaled = 10.0 * (rating - rating_min) / (rating_max - rating_min)
    else:
        raise ValueError("scale method must be 'proportional' or 'minmax'")

    return max(0.0, min(10.0, round(scaled, 4)))


def safe_filename(value: str, max_length: int = 120) -> str:
    """Convert arbitrary text into a filesystem-safe filename."""
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    cleaned = cleaned.strip("._")
    if not cleaned:
        cleaned = hashlib.sha1(value.encode("utf-8")).hexdigest()[:12]
    return cleaned[:max_length]


def ensure_parent(path: str | Path) -> None:
    """Create the parent directory of a path if needed."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
