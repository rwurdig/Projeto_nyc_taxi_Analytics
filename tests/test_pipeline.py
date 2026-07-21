from __future__ import annotations

import argparse
import unittest
from datetime import date

from nyc_taxi.months import YearMonth, completed_months, source_url


class MonthTests(unittest.TestCase):
    def test_parse_month(self) -> None:
        month = YearMonth.parse("2023-01")
        self.assertEqual(month.first_day, date(2023, 1, 1))
        self.assertEqual(str(month), "2023-01")

    def test_rejects_noncanonical_month(self) -> None:
        for value in ("2023-1", "2023-13", "January"):
            with self.subTest(value=value), self.assertRaises(
                argparse.ArgumentTypeError
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


if __name__ == "__main__":
    unittest.main()
