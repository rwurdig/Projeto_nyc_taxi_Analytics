from __future__ import annotations

import csv
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from google.cloud import bigquery

from nyc_taxi.months import YearMonth
from nyc_taxi.settings import Settings

MAX_BYTES_BILLED = 10 * 1024**3


class ExportError(RuntimeError):
    pass


@dataclass(frozen=True)
class Analysis:
    sql_name: str
    csv_name: str
    headers: tuple[str, ...]


@dataclass(frozen=True)
class ExportedResult:
    path: Path
    row_count: int


ANALYSES = (
    Analysis(
        "01_best_pickup_windows.sql",
        "01_best_pickup_windows.csv",
        (
            "rank",
            "pickup_zone_id",
            "borough",
            "zone_name",
            "day_type",
            "pickup_hour",
            "trip_count",
            "active_days",
            "gross_receipts_per_engaged_hour",
        ),
    ),
    Analysis(
        "02_distance_tradeoffs.sql",
        "02_distance_tradeoffs.csv",
        (
            "distance_band",
            "trip_count",
            "trip_share_pct",
            "average_distance_miles",
            "average_duration_minutes",
            "gross_receipts_per_engaged_hour",
        ),
    ),
    Analysis(
        "03_airport_tradeoffs.sql",
        "03_airport_tradeoffs.csv",
        (
            "pickup_group",
            "trip_count",
            "average_distance_miles",
            "average_duration_minutes",
            "gross_receipts_per_engaged_hour",
        ),
    ),
    Analysis(
        "04_credit_card_tipping.sql",
        "04_credit_card_tipping.csv",
        (
            "pickup_hour",
            "credit_card_trip_count",
            "positive_tip_trip_share_pct",
            "average_recorded_tip_amount",
            "recorded_tip_rate_pct",
        ),
    ),
    Analysis(
        "05_follow_on_demand.sql",
        "05_follow_on_demand.csv",
        (
            "rank",
            "dropoff_zone_id",
            "borough",
            "zone_name",
            "destination_trips",
            "next_hour_pickups",
            "pickups_per_dropoff",
        ),
    ),
    Analysis(
        "06_data_quality_summary.sql",
        "06_data_quality_summary.csv",
        ("metric", "record_count", "percent_of_rows"),
    ),
)


def _query(
    client: bigquery.Client,
    settings: Settings,
    month: YearMonth,
    analysis: Analysis,
):
    resource = resources.files("nyc_taxi").joinpath(
        "sql", "analysis", analysis.sql_name
    )
    if not resource.is_file():
        raise ExportError(f"missing SQL resource: {analysis.sql_name}")
    sql = resource.read_text(encoding="utf-8").replace(
        "__PROJECT_ID__", settings.project_id
    )
    config = bigquery.QueryJobConfig(
        use_legacy_sql=False,
        maximum_bytes_billed=MAX_BYTES_BILLED,
        query_parameters=[
            bigquery.ScalarQueryParameter("source_month", "DATE", month.first_day)
        ],
    )
    result = client.query(
        sql,
        project=settings.project_id,
        location=settings.location,
        job_config=config,
    ).result()
    actual_headers = tuple(field.name for field in result.schema)
    if actual_headers != analysis.headers:
        raise ExportError(
            f"{analysis.sql_name} returned {actual_headers}; "
            f"expected {analysis.headers}"
        )
    return result


def export_results(
    client: bigquery.Client,
    settings: Settings,
    month: YearMonth,
    output_root: str | Path | None = None,
) -> tuple[ExportedResult, ...]:
    output_dir = Path("results" if output_root is None else output_root) / str(month)
    output_dir.mkdir(parents=True, exist_ok=True)
    exported: list[ExportedResult] = []

    for analysis in ANALYSES:
        result = _query(client, settings, month, analysis)
        path = output_dir / analysis.csv_name
        row_count = 0
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream, lineterminator="\n")
            writer.writerow(analysis.headers)
            for row in result:
                writer.writerow(row[column] for column in analysis.headers)
                row_count += 1
        exported.append(ExportedResult(path, row_count))

    return tuple(exported)
