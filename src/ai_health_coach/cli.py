"""Command-line interface for the synthetic-only application scaffold."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

from ai_health_coach import __version__


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser without exposing provider or personal-data inputs."""
    parser = argparse.ArgumentParser(prog="ai-health-coach")
    parser.add_argument(
        "--synthetic-smoke",
        action="store_true",
        help="emit the deterministic synthetic scaffold status",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the minimal command entry point."""
    args = build_parser().parse_args(argv)
    if args.synthetic_smoke:
        print(
            json.dumps(
                {
                    "application": "ai-health-coach",
                    "mode": "synthetic-smoke",
                    "private_data_accessed": False,
                    "version": __version__,
                },
                sort_keys=True,
            )
        )
        return 0

    print("Personal AI Health Coach scaffold: use --synthetic-smoke to verify the CLI.")
    return 0
