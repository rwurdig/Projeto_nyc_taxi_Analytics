from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, order=True)
class YearMonth:
    year: int
    month: int

    @classmethod
    def parse(cls, value: str) -> YearMonth:
        try:
            parsed = date.fromisoformat(f"{value}-01")
        except ValueError as exc:
            raise argparse.ArgumentTypeError("month must use YYYY-MM") from exc
        if value != f"{parsed.year:04d}-{parsed.month:02d}":
            raise argparse.ArgumentTypeError("month must use YYYY-MM")
        return cls(parsed.year, parsed.month)

    @property
    def first_day(self) -> date:
        return date(self.year, self.month, 1)

    def add(self, months: int) -> YearMonth:
        index = self.year * 12 + self.month - 1 + months
        year, zero_based_month = divmod(index, 12)
        return YearMonth(year, zero_based_month + 1)

    def __str__(self) -> str:
        return f"{self.year:04d}-{self.month:02d}"


def source_url(month: YearMonth) -> str:
    return (
        "https://d37ci6vzurychx.cloudfront.net/trip-data/"
        f"yellow_tripdata_{month}.parquet"
    )


def completed_months(today: date, lookback: int) -> list[YearMonth]:
    if lookback < 1:
        raise ValueError("lookback must be at least 1")
    current = YearMonth(today.year, today.month)
    return [current.add(-offset) for offset in range(lookback, 0, -1)]
