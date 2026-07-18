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
    parser.add_argument(
        "--quality-output",
        help="Optional CSV report with filtering and data-quality indicators.",
    )
    return parser.parse_args()


def main() -> None:
    """Create the clean review CSV and the platform summary CSV."""
    args = parse_args()
    raw = read_raw_reviews(args.input)
    clean, summary, quality = prepare_reviews(raw)

    ensure_parent(args.output)
    ensure_parent(args.summary_output)
    clean.to_csv(args.output, index=False, encoding="utf-8")
    summary.to_csv(args.summary_output, index=False, encoding="utf-8")
    if args.quality_output:
        ensure_parent(args.quality_output)
        quality.to_csv(args.quality_output, index=False, encoding="utf-8")

    print(f"Wrote {len(clean)} clean review rows to {args.output}")
    print(f"Wrote {len(summary)} summary rows to {args.summary_output}")
    if args.quality_output:
        print(f"Wrote {len(quality)} quality rows to {args.quality_output}")


def prepare_reviews(
    raw: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Validate raw rows and return clean data, summary and quality report."""
    required_columns = {
        "hotel_id",
        "hotel_name",
        "platform",
        "review_id",
        "status",
        "review_date",
        "rating_scaled_0_10",
    }
    missing_columns = required_columns - set(raw.columns)
    if missing_columns:
        raise ValueError(f"Missing required input columns: {sorted(missing_columns)}")

    clean = raw[raw["status"].eq("ok")].copy()
    clean["review_date"] = parse_date_column(clean["review_date"])
    if "stay_date" in clean.columns:
        clean["stay_date"] = parse_date_column(clean["stay_date"])
    else:
        clean["stay_date"] = pd.NaT
    clean["review_year"] = clean["review_date"].dt.year.astype("Int64")
    clean["stay_year"] = clean["stay_date"].dt.year.astype("Int64")
    clean["rating_scaled_0_10"] = pd.to_numeric(
        clean["rating_scaled_0_10"], errors="coerce"
    )
    clean = clean.dropna(
        subset=["review_id", "review_date", "rating_scaled_0_10"]
    )
    clean = clean[clean["rating_scaled_0_10"].between(0, 10, inclusive="both")]
    clean = clean.drop_duplicates(
        subset=["hotel_id", "platform", "review_id"], keep="first"
    )
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
        "source_review_id",
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
    quality = build_quality_report(raw, clean)
    return clean, summary, quality


def build_quality_report(raw: pd.DataFrame, clean: pd.DataFrame) -> pd.DataFrame:
    """Summarise exclusions, duplicates and temporal coverage by data group."""
    audit = raw.copy()
    audit["parsed_review_date"] = parse_date_column(audit["review_date"])
    audit["parsed_rating"] = pd.to_numeric(
        audit["rating_scaled_0_10"], errors="coerce"
    )
    audit["is_ok"] = audit["status"].eq("ok")
    audit["is_duplicate"] = False
    valid_ids = audit["is_ok"] & audit["review_id"].notna()
    audit.loc[valid_ids, "is_duplicate"] = audit.loc[valid_ids].duplicated(
        subset=["hotel_id", "platform", "review_id"], keep="first"
    )

    quality_rows: list[dict[str, object]] = []
    for (hotel_id, platform), group in audit.groupby(
        ["hotel_id", "platform"], dropna=False
    ):
        clean_group = clean[
            clean["hotel_id"].eq(hotel_id) & clean["platform"].eq(platform)
        ]
        ok_group = group[group["is_ok"]]
        out_of_range = ok_group["parsed_rating"].notna() & ~ok_group[
            "parsed_rating"
        ].between(0, 10, inclusive="both")
        clean_months = clean_group["review_date"].dt.to_period("M").nunique()
        quality_rows.append(
            {
                "hotel_id": hotel_id,
                "platform": platform,
                "raw_rows": len(group),
                "status_ok_rows": int(group["is_ok"].sum()),
                "technical_incident_rows": int((~group["is_ok"]).sum()),
                "missing_review_id_rows": int(ok_group["review_id"].isna().sum()),
                "missing_review_date_rows": int(
                    ok_group["parsed_review_date"].isna().sum()
                ),
                "missing_rating_rows": int(ok_group["parsed_rating"].isna().sum()),
                "out_of_range_rating_rows": int(out_of_range.sum()),
                "duplicate_review_id_rows": int(group["is_duplicate"].sum()),
                "clean_rows": len(clean_group),
                "removed_rows": len(group) - len(clean_group),
                "months_with_reviews": int(clean_months),
                "min_review_date": clean_group["review_date"].min(),
                "max_review_date": clean_group["review_date"].max(),
            }
        )

    return pd.DataFrame(quality_rows).sort_values(["hotel_id", "platform"])


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
