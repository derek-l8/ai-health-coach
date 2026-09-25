"""Synthetic-only smoke coverage for the command entry point."""

from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path


def test_synthetic_smoke_command() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "ai_health_coach", "--synthetic-smoke"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "application": "ai-health-coach",
        "mode": "synthetic-smoke",
        "private_data_accessed": False,
        "version": "0.1.0",
    }


def test_synthetic_evaluation_command() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "ai_health_coach", "--synthetic-evaluate"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["synthetic"] is True
    assert payload["private_data_accessed"] is False
    assert payload["days"] == 60
    assert set(payload["reports"]) == {
        "google_only",
        "historical_median",
        "rolling_average",
    }


def test_cli_writes_synthetic_dataset(tmp_path: Path) -> None:
    dataset = tmp_path / "study.csv"

    dataset_result = subprocess.run(
        [
            sys.executable,
            "-m",
            "ai_health_coach",
            "--write-synthetic-study",
            str(dataset),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert dataset_result.returncode == 0, dataset_result.stderr
    with dataset.open(encoding="utf-8", newline="") as stream:
        assert len(list(csv.DictReader(stream))) == 60
