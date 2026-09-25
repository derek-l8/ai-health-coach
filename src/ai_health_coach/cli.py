"""Command-line interface for the synthetic-only application scaffold."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path

from ai_health_coach import __version__

SLEEP_NIGHT_FIXTURE = Path("fixtures/synthetic/sleep-night-observations.json")


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser without exposing provider or personal-data inputs."""
    parser = argparse.ArgumentParser(prog="ai-health-coach")
    commands = parser.add_mutually_exclusive_group()
    commands.add_argument(
        "--synthetic-smoke",
        action="store_true",
        help="emit the deterministic synthetic scaffold status",
    )
    commands.add_argument(
        "--synthetic-score-night",
        action="store_true",
        help="run the deterministic nightly sleep-score calculation on synthetic data",
    )
    commands.add_argument(
        "--synthetic-evaluate",
        action="store_true",
        help="evaluate baseline arms on the generated 60-day synthetic study",
    )
    commands.add_argument(
        "--write-synthetic-study",
        type=Path,
        metavar="PATH",
        help="write the generated 60-day synthetic study CSV",
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


def _synthetic_evaluate() -> int:
    from ai_health_coach.evaluation import (
        GoogleOnlyArm,
        HistoricalMedianArm,
        RollingAverageArm,
        metric_report,
        rolling_origin_predictions,
    )
    from ai_health_coach.synthetic_study import generate_labeled_examples

    examples = generate_labeled_examples()
    reports: dict[str, object] = {}
    for arm in (HistoricalMedianArm(), RollingAverageArm(), GoogleOnlyArm()):
        predictions = rolling_origin_predictions(
            examples,
            arm,
            minimum_training_rows=20,
        )
        reports[arm.name] = asdict(
            metric_report(predictions, eligible_count=len(examples) - 20)
        )
    print(
        json.dumps(
            {
                "mode": "synthetic-evaluate",
                "private_data_accessed": False,
                "synthetic": True,
                "target": "morning_readiness",
                "days": len(examples),
                "reports": reports,
            },
            sort_keys=True,
        )
    )
    return 0


def _write_synthetic_study(path: Path) -> int:
    from ai_health_coach.synthetic_study import write_synthetic_dataset

    write_synthetic_dataset(path)
    print(
        json.dumps(
            {
                "mode": "write-synthetic-study",
                "path": str(path),
                "private_data_accessed": False,
                "synthetic": True,
            },
            sort_keys=True,
        )
    )
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

    if args.synthetic_evaluate:
        return _synthetic_evaluate()

    if args.write_synthetic_study is not None:
        return _write_synthetic_study(args.write_synthetic_study)

    print("Personal AI Health Coach scaffold: use --synthetic-smoke to verify the CLI.")
    return 0
