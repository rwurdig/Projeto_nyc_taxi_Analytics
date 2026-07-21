from __future__ import annotations

import argparse


def dispatch(args: argparse.Namespace) -> int:
    raise RuntimeError(f"command is not implemented yet: {args.command}")
