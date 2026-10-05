"""Synthetic demonstrations and explicitly configured private check-in capture."""

from __future__ import annotations

import argparse
import json
import math
from collections.abc import Sequence
from dataclasses import asdict
from datetime import date, datetime, timedelta
from importlib.resources import files
from pathlib import Path

from ai_health_coach import __version__

SLEEP_NIGHT_FIXTURE = files("ai_health_coach").joinpath(
    "fixtures", "sleep-night-observations.json"
)


def build_parser() -> argparse.ArgumentParser:
    """Expose synthetic commands and an opt-in private check-in service."""
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
    commands.add_argument(
        "--serve-checkins",
        action="store_true",
        help="serve the private phone form; requires --database and --timezone",
    )
    commands.add_argument(
        "--import-form-snapshot",
        type=Path,
        metavar="PATH",
        help="import a private snapshot exported by scripts/google-forms-study.js",
    )
    parser.add_argument("--database", type=Path, help="private database outside Git")
    parser.add_argument(
        "--timezone", help="IANA study timezone, e.g. America/Los_Angeles"
    )
    parser.add_argument(
        "--bind", default="127.0.0.1", help="explicit IPv4 bind address"
    )
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--cert", type=Path, help="HTTPS certificate trusted by your phone"
    )
    parser.add_argument("--key", type=Path, help="HTTPS certificate's private key")
    parser.add_argument("--afternoon-start-hours", type=float, default=5)
    parser.add_argument("--afternoon-end-hours", type=float, default=9)
    parser.add_argument(
        "--caffeine-cutoff",
        metavar="HH:MM",
        help="optional caffeine cutoff in the study timezone (24-hour time)",
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
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.import_form_snapshot is not None:
        from ai_health_coach.checkins import CheckInStore, private_database_path
        from ai_health_coach.forms_import import (
            MAX_SNAPSHOT_BYTES,
            import_form_snapshot,
        )

        if args.database is None:
            parser.error("--import-form-snapshot requires --database")
        try:
            database = private_database_path(args.database)
            database.parent.mkdir(parents=True, exist_ok=True)
            with args.import_form_snapshot.open("rb") as source:
                content = source.read(MAX_SNAPSHOT_BYTES + 1)
            store = CheckInStore(database)
            try:
                result = import_form_snapshot(
                    store, content, datetime.now().astimezone()
                )
            finally:
                store.close()
        except (ValueError, OSError) as error:
            parser.error(str(error))
        print(
            json.dumps(
                {"mode": "import-form-snapshot", **asdict(result)}, sort_keys=True
            )
        )
        return 0
    if args.serve_checkins:
        from ai_health_coach.checkin_server import serve_checkins
        from ai_health_coach.study_protocol import (
            EventConfiguration,
            EventType,
            EventWindowConfig,
            TriggerKind,
        )

        if args.database is None or args.timezone is None:
            parser.error("--serve-checkins requires --database and --timezone")
        if not 0 <= args.port <= 65535:
            parser.error("--port must be from 0 to 65535")
        if not all(
            math.isfinite(hours) and 0 <= hours <= 168
            for hours in (args.afternoon_start_hours, args.afternoon_end_hours)
        ):
            parser.error("afternoon boundaries must be finite hours from 0 to 168")
        try:
            config = EventConfiguration(
                version="event-config-1.1.0",
                timezone=args.timezone,
                caffeine_cutoff_local_time=args.caffeine_cutoff,
                windows=(
                    EventWindowConfig(EventType.WAKE, TriggerKind.MANUAL),
                    EventWindowConfig(
                        EventType.AFTERNOON,
                        TriggerKind.RELATIVE_TO_WAKE,
                        timedelta(hours=args.afternoon_start_hours),
                        timedelta(hours=args.afternoon_end_hours),
                    ),
                    EventWindowConfig(EventType.DAY_CLOSE, TriggerKind.MANUAL),
                ),
            )
            return serve_checkins(
                args.database, config, args.bind, args.port, args.cert, args.key
            )
        except (ValueError, OSError) as error:
            parser.error(str(error))
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

    print(
        "Personal AI Health Coach: use --help for demos and private check-in capture."
    )
    return 0
