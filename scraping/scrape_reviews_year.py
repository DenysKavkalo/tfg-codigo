"""Scrape quantitative hotel reviews from configured review sources."""

from __future__ import annotations

import argparse
import sys
from dataclasses import asdict
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import pandas as pd

if __package__ in (None, ""):
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from scraping.extractors import detect_bot_challenge
from scraping.http_client import Fetcher, save_html
from scraping.reviews.registry import (
    SUPPORTED_REVIEW_PLATFORMS,
    build_reviews_request,
    max_pages_for_platform,
    parse_reviews,
)
from scraping.utils import ensure_parent, safe_filename


REQUIRED_COLUMNS = {
    "hotel_id",
    "hotel_name",
    "city",
    "country",
    "platform",
    "reviews_url",
}

OUTPUT_COLUMNS = [
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
    "status",
    "error",
]


def parse_args() -> argparse.Namespace:
    """Parse and validate command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Scrape individual quantitative hotel reviews for a year or date period."
    )
    parser.add_argument("--input", required=True, help="CSV with reviewed review URLs.")
    parser.add_argument("--output", required=True, help="Output CSV with review-level data.")
    parser.add_argument("--year", type=int, help="Calendar year to keep.")
    parser.add_argument(
        "--start-date",
        help="Inclusive start date to keep, YYYY-MM-DD. Use with --end-date.",
    )
    parser.add_argument(
        "--end-date",
        help="Inclusive end date to keep, YYYY-MM-DD. Use with --start-date.",
    )
    parser.add_argument(
        "--platforms",
        nargs="+",
        default=list(SUPPORTED_REVIEW_PLATFORMS),
        help="Review platforms to scrape.",
    )
    parser.add_argument(
        "--exclude-output-platforms",
        nargs="*",
        default=[],
        help=(
            "Platform labels to remove after provider splitting, for example "
            "priceline_com_via_agoda."
        ),
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=80,
        help="Maximum review pages per source URL.",
    )
    parser.add_argument(
        "--empty-page-stop",
        type=int,
        default=3,
        help="Stop after this many consecutive pages without review cards.",
    )
    parser.add_argument(
        "--delay-seconds",
        type=float,
        default=2.0,
        help="Delay between requests.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=30,
        help="Request timeout per page.",
    )
    parser.add_argument(
        "--date-field",
        choices=("review_date", "stay_date"),
        default="review_date",
        help="Date used to filter the target calendar year.",
    )
    parser.add_argument(
        "--agoda-provider-mode",
        choices=("own", "separate"),
        default="own",
        help=(
            "Agoda review handling. 'own' keeps only Agoda's own reviews; "
            "'separate' keeps provider-labelled reviews as separate platforms."
        ),
    )
    parser.add_argument(
        "--render-js",
        action="store_true",
        help="Render pages with Playwright.",
    )
    parser.add_argument(
        "--retry-blocked-with-render-js",
        action="store_true",
        help="If requests receives a bot challenge, retry that page with Playwright.",
    )
    parser.add_argument(
        "--save-html-dir",
        default=None,
        help="Optional directory to save fetched HTML for reproducibility/debugging.",
    )
    args = parser.parse_args()
    validate_period_args(args)
    return args


def main() -> None:
    """Run the scraping workflow and write the raw audit CSV."""
    args = parse_args()
    platforms = [platform.lower().strip() for platform in args.platforms]
    args.exclude_output_platforms = {
        platform.lower().strip() for platform in args.exclude_output_platforms
    }
    unsupported = [
        platform for platform in platforms if platform not in SUPPORTED_REVIEW_PLATFORMS
    ]
    if unsupported:
        supported = ", ".join(SUPPORTED_REVIEW_PLATFORMS)
        raise ValueError(
            f"Unsupported review platform(s): {unsupported}. Supported: {supported}"
        )

    sources = pd.read_csv(args.input)
    missing = REQUIRED_COLUMNS - set(sources.columns)
    if missing:
        raise ValueError(f"Missing required input columns: {sorted(missing)}")

    sources["platform"] = sources["platform"].str.lower().str.strip()
    sources = sources[sources["platform"].isin(platforms)].copy()
    if sources.empty:
        raise ValueError("No source rows left after filtering by platform.")

    fetcher = Fetcher(
        timeout_seconds=args.timeout_seconds,
        delay_seconds=args.delay_seconds,
    )

    all_rows: list[dict[str, object]] = []
    for _, source in sources.iterrows():
        rows = scrape_source(source, args, fetcher)
        all_rows.extend(rows)

    output = pd.DataFrame(all_rows, columns=OUTPUT_COLUMNS)
    if not output.empty:
        ok_rows = output[output["status"].eq("ok")].drop_duplicates(
            subset=["hotel_id", "platform", "review_id"], keep="first"
        )
        audit_rows = output[~output["status"].eq("ok")]
        output = pd.concat([ok_rows, audit_rows], ignore_index=True).sort_values(
            ["hotel_id", "platform", "review_date", "page"],
            na_position="last",
        )

    ensure_parent(args.output)
    output.to_csv(args.output, index=False, encoding="utf-8")
    print(f"Wrote {len(output)} review rows to {args.output}")

    if not output.empty:
        summary = output.groupby(["hotel_id", "platform", "status"]).size()
        print(summary.to_string())


def scrape_source(
    source: pd.Series,
    args: argparse.Namespace,
    fetcher: Fetcher,
) -> list[dict[str, object]]:
    """Scrape one configured source row and return raw output rows."""
    rows: list[dict[str, object]] = []
    empty_pages = 0
    platform = str(source["platform"]).lower().strip()
    scrape_date = datetime.now(timezone.utc).isoformat()

    max_pages = max_pages_for_platform(platform, args.max_pages)
    reviews_url = review_source_url(source, args)
    for page in range(1, max_pages + 1):
        request_spec = build_reviews_request(platform, reviews_url, page)
        page_url = str(request_spec["url"])
        method = str(request_spec.get("method", "GET"))
        print(
            f"{source['hotel_id']} | {platform} | page {page}/{max_pages}",
            flush=True,
        )

        try:
            fetched = fetcher.fetch_request(
                page_url,
                render_js=args.render_js,
                method=method,
                json_body=request_spec.get("json_body"),
                headers=request_spec.get("headers"),
            )
            if args.save_html_dir:
                html_path = (
                    Path(args.save_html_dir)
                    / safe_filename(f"{source['hotel_id']}_{platform}_page_{page}.html")
                )
                save_html(fetched.html, html_path)

            challenge = detect_bot_challenge(fetched.html)
            records = parse_reviews(
                platform,
                fetched.html,
                source_url=str(request_spec.get("source_url", source["reviews_url"])),
                page=page,
            )
            if (
                challenge
                and not records
                and args.retry_blocked_with_render_js
                and not args.render_js
                and method == "GET"
            ):
                print(
                    f"{source['hotel_id']} | {platform} | page {page}: "
                    "bot challenge detected, retrying with Playwright",
                    flush=True,
                )
                fetched = fetcher.fetch(page_url, render_js=True)
                challenge = detect_bot_challenge(fetched.html)
                records = parse_reviews(
                    platform,
                    fetched.html,
                    source_url=str(request_spec.get("source_url", source["reviews_url"])),
                    page=page,
                )
                if args.save_html_dir:
                    html_path = (
                        Path(args.save_html_dir)
                        / safe_filename(
                            f"{source['hotel_id']}_{platform}_page_{page}_rendered.html"
                        )
                    )
                    save_html(fetched.html, html_path)

            if challenge and not records:
                rows.append(
                    base_error_row(
                        source,
                        page=page,
                        page_url=page_url,
                        scrape_date=scrape_date,
                        status="blocked",
                        error=f"Bot challenge detected: {challenge}",
                    )
                )
                break

            if not records:
                print(
                    f"{source['hotel_id']} | {platform} | page {page}: "
                    "0 review cards found",
                    flush=True,
                )
                empty_pages += 1
                if empty_pages >= args.empty_page_stop:
                    break
                continue

            empty_pages = 0
            kept_records = [
                record for record in records if selected_date_in_period(record, args)
            ]
            print(
                f"{source['hotel_id']} | {platform} | page {page}: "
                f"{len(records)} review cards found, {len(kept_records)} kept for "
                f"{period_label(args)} using {args.date_field}",
                flush=True,
            )
            for record in kept_records:
                record_dict = asdict(record)
                platform_override = record_dict.pop("platform_override", None)
                record_dict.pop("review_title", None)
                output_platform = platform_override or platform
                if output_platform in args.exclude_output_platforms:
                    continue
                rows.append(
                    {
                        "hotel_id": source["hotel_id"],
                        "hotel_name": source["hotel_name"],
                        "city": source["city"],
                        "country": source["country"],
                        "platform": output_platform,
                        **record_dict,
                        "scrape_date": scrape_date,
                        "status": "ok",
                        "error": None,
                    }
                )
        except Exception as exc:  # noqa: BLE001 - written to audit CSV
            rows.append(
                base_error_row(
                    source,
                    page=page,
                    page_url=page_url,
                    scrape_date=scrape_date,
                    status="error",
                    error=str(exc),
                )
            )

    return rows


def base_error_row(
    source: pd.Series,
    page: int,
    page_url: str,
    scrape_date: str,
    status: str,
    error: str,
) -> dict[str, object]:
    """Build an audit row for blocked or failed requests."""
    return {
        "hotel_id": source["hotel_id"],
        "hotel_name": source["hotel_name"],
        "city": source["city"],
        "country": source["country"],
        "platform": source["platform"],
        "source_platform": source["platform"],
        "provider_id": None,
        "provider_name": None,
        "review_id": None,
        "review_date": None,
        "review_year": None,
        "stay_date": None,
        "stay_year": None,
        "rating_raw": None,
        "rating_min": None,
        "rating_max": None,
        "rating_scaled_0_10": None,
        "source_url": page_url,
        "page": page,
        "scrape_date": scrape_date,
        "status": status,
        "error": error,
    }


def selected_date_in_period(record: object, args: argparse.Namespace) -> bool:
    """Return whether a review belongs to the requested date period."""
    selected_date = selected_iso_date(record, args.date_field)
    if not selected_date:
        return False

    if args.year is not None:
        return selected_date.year == args.year

    return parse_iso_date(args.start_date) <= selected_date <= parse_iso_date(
        args.end_date
    )


def selected_iso_date(record: object, date_field: str) -> date | None:
    """Extract a date field from a review record as a date object."""
    value = getattr(record, date_field)
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).date()
    except ValueError:
        return None


def validate_period_args(args: argparse.Namespace) -> None:
    """Validate that the temporal filter is complete and unambiguous."""
    has_period = bool(args.start_date or args.end_date)
    if args.year is None and not has_period:
        raise ValueError("Use either --year or --start-date and --end-date.")
    if args.year is not None and has_period:
        raise ValueError("Use either --year or --start-date/--end-date, not both.")
    if has_period and not (args.start_date and args.end_date):
        raise ValueError("--start-date and --end-date must be used together.")
    if has_period and parse_iso_date(args.start_date) > parse_iso_date(args.end_date):
        raise ValueError("--start-date must be before or equal to --end-date.")


def parse_iso_date(value: str) -> date:
    """Parse a YYYY-MM-DD date string."""
    try:
        return datetime.fromisoformat(value).date()
    except ValueError as exc:
        raise ValueError(f"Invalid date {value!r}. Expected YYYY-MM-DD.") from exc


def period_label(args: argparse.Namespace) -> str:
    """Return a readable label for the selected time period."""
    if args.year is not None:
        return f"year={args.year}"
    return f"period={args.start_date}..{args.end_date}"


def review_source_url(source: pd.Series, args: argparse.Namespace) -> str:
    """Return the effective source URL, including Agoda provider mode."""
    platform = str(source["platform"]).lower().strip()
    reviews_url = str(source["reviews_url"])
    if platform != "agoda":
        return reviews_url

    parsed = urlparse(reviews_url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["providerMode"] = args.agoda_provider_mode
    return urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            urlencode(query),
            parsed.fragment,
        )
    )


if __name__ == "__main__":
    main()
