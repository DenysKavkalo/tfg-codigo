"""Prepare raw review rows for descriptive and Bayesian analysis in R."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

if __package__ in (None, ""):
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from scraping.utils import ensure_parent


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for the preparation step."""
    parser = argparse.ArgumentParser(
        description="Prepare review-level yearly data for the R Bayesian analysis."
    )
    parser.add_argument("--input", required=True, help="Raw review-level CSV.")
    parser.add_argument("--output", required=True, help="Clean review-level CSV.")
    parser.add_argument(
        "--summary-output",
        required=True,
        help="Platform summary with n, total score, mean and standard deviation.",
    )
    return parser.parse_args()


def main() -> None:
    """Create the clean review CSV and the platform summary CSV."""
    args = parse_args()
    raw = read_raw_reviews(args.input)
    required_columns = {"status", "review_date", "rating_scaled_0_10"}
    missing_columns = required_columns - set(raw.columns)
    if missing_columns:
        raise ValueError(f"Missing required input columns: {sorted(missing_columns)}")

    clean = raw[raw["status"].eq("ok")].copy()
    clean = clean.dropna(subset=["review_date", "rating_scaled_0_10"])
    clean["review_date"] = parse_date_column(clean["review_date"])
    if "stay_date" in clean.columns:
        clean["stay_date"] = parse_date_column(clean["stay_date"])
    clean["rating_scaled_0_10"] = clean["rating_scaled_0_10"].astype(float)
    clean = clean.dropna(subset=["review_date"])
    clean = clean.sort_values(["hotel_id", "platform", "review_date"])

    keep_columns = [
        "hotel_id",
        "hotel_name",
        "city",
        "country",
        "platform",
        "source_platform",
        "provider_id",
        "provider_name",
        "review_id",
        "review_date",
        "review_year",
        "stay_date",
        "stay_year",
        "rating_raw",
        "rating_min",
        "rating_max",
        "rating_scaled_0_10",
        "source_url",
        "page",
        "scrape_date",
    ]
    clean = clean[[column for column in keep_columns if column in clean.columns]]

    summary = (
        clean.groupby(["hotel_id", "hotel_name", "platform"], as_index=False)
        .agg(
            n_reviews=("rating_scaled_0_10", "size"),
            total_score=("rating_scaled_0_10", "sum"),
            mean_score=("rating_scaled_0_10", "mean"),
            sd_score=("rating_scaled_0_10", "std"),
            min_review_date=("review_date", "min"),
            max_review_date=("review_date", "max"),
            min_stay_date=("stay_date", "min"),
            max_stay_date=("stay_date", "max"),
        )
        .sort_values(["hotel_id", "platform"])
    )

    ensure_parent(args.output)
    ensure_parent(args.summary_output)
    clean.to_csv(args.output, index=False, encoding="utf-8")
    summary.to_csv(args.summary_output, index=False, encoding="utf-8")

    print(f"Wrote {len(clean)} clean review rows to {args.output}")
    print(f"Wrote {len(summary)} summary rows to {args.summary_output}")


def read_raw_reviews(path: str) -> pd.DataFrame:
    """Read a raw CSV while detecting the field separator automatically."""
    path_obj = Path(path)
    return pd.read_csv(path_obj, sep=None, engine="python")


def parse_date_column(values: pd.Series) -> pd.Series:
    """Parse ISO and day-first date formats into pandas datetimes."""
    text = values.astype("string").str.strip()
    empty = text.isna() | text.eq("")

    parsed = pd.to_datetime(text, format="%Y-%m-%d", errors="coerce")
    missing = parsed.isna() & ~empty
    if missing.any():
        parsed.loc[missing] = pd.to_datetime(
            text.loc[missing],
            format="%d/%m/%Y",
            errors="coerce",
        )

    missing = parsed.isna() & ~empty
    if missing.any():
        parsed.loc[missing] = pd.to_datetime(
            text.loc[missing],
            errors="coerce",
            dayfirst=True,
        )

    return parsed


if __name__ == "__main__":
    main()
