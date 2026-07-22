from __future__ import annotations

import argparse
import unittest
from datetime import date
from types import SimpleNamespace

from nyc_taxi.months import YearMonth, completed_months, source_url
from nyc_taxi.pipeline import Pipeline, object_name
from nyc_taxi.settings import Settings


class MonthTests(unittest.TestCase):
    def test_parse_month(self) -> None:
        month = YearMonth.parse("2023-01")
        self.assertEqual(month.first_day, date(2023, 1, 1))
        self.assertEqual(str(month), "2023-01")

    def test_rejects_noncanonical_month(self) -> None:
        for value in ("2023-1", "2023-13", "January"):
            with (
                self.subTest(value=value),
                self.assertRaises(argparse.ArgumentTypeError),
            ):
                YearMonth.parse(value)

    def test_builds_tlc_url(self) -> None:
        month = YearMonth(2023, 1)
        self.assertEqual(
            source_url(month),
            "https://d37ci6vzurychx.cloudfront.net/trip-data/"
            "yellow_tripdata_2023-01.parquet",
        )

    def test_completed_months_cross_year_boundary(self) -> None:
        self.assertEqual(
            completed_months(date(2024, 2, 10), 3),
            [YearMonth(2023, 11), YearMonth(2023, 12), YearMonth(2024, 1)],
        )


class _RecordingPipeline(Pipeline):
    def __init__(self) -> None:
        settings = Settings("project", "123", raw_bucket="raw-bucket")
        super().__init__(settings, bigquery_client=object(), storage_client=object())
        self.events: list[str] = []

    def has_success(self, month: YearMonth) -> bool:
        return True

    def _insert_attempt(self, *args: object, **kwargs: object) -> None:
        self.events.append(str(args[2]))

    def _prepare_raw(self, month: YearMonth, force: bool) -> None:
        self.events.append(f"prepare:{force}")

    def _stage(self, month: YearMonth, run_id: str, gcs_uri: str) -> tuple[str, int]:
        self.events.append("stage")
        return "project.taxi_staging.raw", 10

    def transform_month(self, month: YearMonth, staging_table: str) -> None:
        self.events.append("transform")

    def _finish_attempt(
        self, run_id: str, status: str, row_count: int | None, message: str
    ) -> None:
        self.events.append(status)


class PipelineTests(unittest.TestCase):
    def test_month_has_stable_raw_object_name(self) -> None:
        self.assertEqual(
            object_name(YearMonth(2023, 1)),
            "yellow/source_month=2023-01/yellow_tripdata_2023-01.parquet",
        )

    def test_successful_month_is_skipped(self) -> None:
        pipeline = _RecordingPipeline()
        self.assertEqual(pipeline.load_month(YearMonth(2023, 1)), "SKIPPED")
        self.assertEqual(pipeline.events, ["SKIPPED"])

    def test_force_bypasses_successful_month(self) -> None:
        pipeline = _RecordingPipeline()
        self.assertEqual(
            pipeline.load_month(YearMonth(2023, 1), force=True), "SUCCEEDED"
        )
        self.assertEqual(
            pipeline.events,
            ["RUNNING", "prepare:True", "stage", "transform", "SUCCEEDED"],
        )

    def test_staging_rejects_missing_required_columns(self) -> None:
        table = SimpleNamespace(
            schema=[SimpleNamespace(name="tpep_pickup_datetime")],
            num_rows=10,
            expires=None,
        )

        class FakeBigQuery:
            def load_table_from_uri(self, *args: object, **kwargs: object) -> object:
                return SimpleNamespace(result=lambda: None)

            def get_table(self, table_id: str) -> object:
                return table

        settings = Settings("project", "123", raw_bucket="raw-bucket")
        pipeline = Pipeline(
            settings, bigquery_client=FakeBigQuery(), storage_client=object()
        )
        with self.assertRaisesRegex(RuntimeError, "missing required columns"):
            pipeline._stage(YearMonth(2023, 1), "run-id", "gs://raw/source")


if __name__ == "__main__":
    unittest.main()
