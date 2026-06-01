from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
PUBLIC_SCRIPT_HELP_CASES = [
    ("setup-env.sh", ["help"], "Usage: ./scripts/setup-env.sh"),
    ("setup-db.sh", ["help"], "Usage: ./scripts/setup-db.sh [command] [args]"),
    ("run-server.sh", ["help"], "Usage: ./scripts/run-server.sh [command]"),
    ("run-all.sh", ["help"], "Usage: ./scripts/run-all.sh [command]"),
]


@pytest.mark.parametrize(("script_name", "arguments", "expected_output"), PUBLIC_SCRIPT_HELP_CASES)
def test_public_script_help_outputs_usage(
    script_name: str,
    arguments: list[str],
    expected_output: str,
) -> None:
    script_path = SCRIPTS_DIR / script_name

    result = subprocess.run(
        [str(script_path), *arguments],
        capture_output=True,
        cwd=PROJECT_ROOT,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert expected_output in result.stdout
    assert result.stderr == ""


@pytest.mark.parametrize(
    "script_name",
    ["setup-env.sh", "setup-db.sh", "run-server.sh", "run-all.sh"],
)
def test_public_scripts_are_executable(script_name: str) -> None:
    script_path = SCRIPTS_DIR / script_name

    assert script_path.exists()
    assert os.access(script_path, os.X_OK)


def test_scripts_have_valid_bash_syntax() -> None:
    script_paths = sorted(str(path) for path in SCRIPTS_DIR.rglob("*.sh"))

    result = subprocess.run(
        ["bash", "-n", *script_paths],
        capture_output=True,
        cwd=PROJECT_ROOT,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_legacy_setup_entrypoint_removed() -> None:
    assert not (SCRIPTS_DIR / "setup.sh").exists()
