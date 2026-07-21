from __future__ import annotations

import argparse
from collections.abc import Sequence

from nyc_taxi import __version__
from nyc_taxi.months import YearMonth


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nyc-taxi")
    parser.add_argument("--version", action="version", version=__version__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("setup", help="Create datasets, tables, and zone data")

    load = subparsers.add_parser("load", help="Process one source month")
    load.add_argument("--month", required=True, type=YearMonth.parse)
    load.add_argument("--force", action="store_true")

    discover = subparsers.add_parser("discover", help="Load recently published months")
    discover.add_argument("--lookback-months", type=int, default=3)

    export = subparsers.add_parser("export", help="Export analytical result CSVs")
    export.add_argument("--month", required=True, type=YearMonth.parse)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    from nyc_taxi.pipeline import dispatch

    return dispatch(args)


if __name__ == "__main__":
    raise SystemExit(main())
