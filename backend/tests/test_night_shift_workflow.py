from __future__ import annotations

from pathlib import Path
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "night-shift.yml"
SCRIPT = REPO_ROOT / "skeleton" / "automation" / "night_shift.py"


def test_night_shift_workflow_bypasses_root_package_imports() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    # The scheduled runner intentionally installs no project dependencies.
    # Executing with `-m skeleton...` imports skeleton/__init__.py first and
    # can pull dependency-bearing subsystems into this lightweight job.
    assert "run: python skeleton/automation/night_shift.py" in text
    assert "python -m skeleton.automation.night_shift" not in text


def test_night_shift_script_starts_as_a_standalone_stdlib_entrypoint() -> None:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "--repo" in completed.stdout
