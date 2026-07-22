from __future__ import annotations

import csv
import tempfile
import unittest
from importlib import resources
from pathlib import Path
from types import SimpleNamespace

from nyc_taxi.analytics import ANALYSES, MAX_BYTES_BILLED, export_results
from nyc_taxi.months import YearMonth
from nyc_taxi.settings import Settings


class AnalysisTests(unittest.TestCase):
    def test_registry_contains_six_unique_outputs(self) -> None:
        self.assertEqual(len(ANALYSES), 6)
        self.assertEqual(len({item.sql_name for item in ANALYSES}), 6)
        self.assertEqual(len({item.csv_name for item in ANALYSES}), 6)

    def test_queries_are_parameterized_and_partition_filtered(self) -> None:
        for analysis in ANALYSES:
            with self.subTest(query=analysis.sql_name):
                sql = (
                    resources.files("nyc_taxi")
                    .joinpath("sql", "analysis", analysis.sql_name)
                    .read_text(encoding="utf-8")
                )
                self.assertIn("__PROJECT_ID__", sql)
                self.assertIn("@source_month", sql)
                self.assertIn("source_month = @source_month", sql)
                self.assertIn("ORDER BY", sql)

    def test_export_writes_expected_csv_contracts(self) -> None:
        class FakeResult(list[dict[str, object]]):
            def __init__(self, headers: tuple[str, ...]) -> None:
                super().__init__([{name: index for index, name in enumerate(headers)}])
                self.schema = [SimpleNamespace(name=name) for name in headers]

        class FakeClient:
            def __init__(self) -> None:
                self.calls = 0

            def query(self, sql: str, **kwargs: object) -> object:
                analysis = ANALYSES[self.calls]
                self.calls += 1
                config = kwargs["job_config"]
                assert config.maximum_bytes_billed == MAX_BYTES_BILLED
                assert kwargs["project"] == "project"
                assert kwargs["location"] == "us-central1"
                return SimpleNamespace(result=lambda: FakeResult(analysis.headers))

        settings = Settings("project", "123", raw_bucket="raw-bucket")
        with tempfile.TemporaryDirectory() as directory:
            client = FakeClient()
            exported = export_results(
                client, settings, YearMonth(2023, 1), Path(directory)
            )
            self.assertEqual(client.calls, 6)
            self.assertEqual(len(exported), 6)
            for item, analysis in zip(exported, ANALYSES, strict=True):
                with item.path.open(encoding="utf-8", newline="") as stream:
                    rows = list(csv.reader(stream))
                self.assertEqual(tuple(rows[0]), analysis.headers)
                self.assertEqual(item.row_count, 1)
