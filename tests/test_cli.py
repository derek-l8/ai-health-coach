"""Synthetic-only smoke coverage for the command entry point."""

from __future__ import annotations

import json
import subprocess
import sys


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
