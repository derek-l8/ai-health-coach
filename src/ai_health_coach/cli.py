"""Command-line interface for the synthetic-only application scaffold."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from datetime import date, datetime
from pathlib import Path

from ai_health_coach import __version__

SLEEP_NIGHT_FIXTURE = Path("fixtures/synthetic/sleep-night-observations.json")


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser without exposing provider or personal-data inputs."""
    parser = argparse.ArgumentParser(prog="ai-health-coach")
    parser.add_argument(
        "--synthetic-smoke",
        action="store_true",
        help="emit the deterministic synthetic scaffold status",
    )
    parser.add_argument(
        "--synthetic-score-night",
        action="store_true",
        help="run the deterministic nightly sleep-score calculation on synthetic data",
    )
    return parser


def _synthetic_score_night() -> int:
    from ai_health_coach.observations import MetricObservation
    from ai_health_coach.sleep_scoring import run_nightly_calculation
    from ai_health_coach.storage import ObservationStore

    store = ObservationStore()
    store.ingest(
        MetricObservation.from_mapping(item)
        for item in json.loads(SLEEP_NIGHT_FIXTURE.read_text(encoding="utf-8"))
    )
    summary = run_nightly_calculation(
        store,
        local_date=date(2024, 3, 10),
        timezone="America/New_York",
        sleep_window_start=datetime.fromisoformat("2024-03-09T23:00:00-05:00"),
        sleep_window_end=datetime.fromisoformat("2024-03-10T07:00:00-04:00"),
        input_data_cutoff=datetime.fromisoformat("2024-03-10T08:00:00-04:00"),
        calculated_at=datetime.fromisoformat("2024-03-10T08:05:00-04:00"),
    )
    summary["mode"] = "synthetic-score-night"
    summary["private_data_accessed"] = False
    print(json.dumps(summary, sort_keys=True))
    return 0


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

    if args.synthetic_score_night:
        return _synthetic_score_night()

    print("Personal AI Health Coach scaffold: use --synthetic-smoke to verify the CLI.")
    return 0
