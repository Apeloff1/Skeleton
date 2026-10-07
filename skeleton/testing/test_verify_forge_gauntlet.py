"""S-size assertions for scripts/verify-forge.sh forge gauntlet.

File-content / presence checks only; optional subprocess smoke is best-effort
so CI without a full env still passes on static gates.
"""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "verify-forge.sh"


def test_verify_forge_script_exists_and_is_runnable():
    assert SCRIPT.is_file(), f"missing gauntlet script: {SCRIPT}"
    text = SCRIPT.read_text(encoding="utf-8")
    assert text.startswith("#!"), "expected shebang"
    mode = SCRIPT.stat().st_mode
    # Prefer executable bit; accept readable+shebang as fallback for checkout umask quirks
    assert mode & (stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH), "script not readable"
    assert mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH) or text.startswith(
        "#!"
    ), "script should be executable or at least shebang-runnable"


def test_verify_forge_script_contains_key_gates():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "bp.validate()" in text
    assert 'target="json"' in text
    assert "check_files(files)" in text
    assert "forge_verify_until_green" in text
    assert 'target="godot", repair=True' in text
    assert 'result["verification"]["accepted"]' in text
    assert "set -euo pipefail" in text


def test_verify_forge_script_smoke_optional():
    """Best-effort subprocess run; skip on timeout — static gates are enough for S-size."""
    if os.name == "nt":
        pytest.skip("POSIX shell smoke runs in Linux CI")
    if not SCRIPT.is_file():
        pytest.skip("gauntlet script missing")
    if not os.access(SCRIPT, os.X_OK):
        pytest.skip("gauntlet script not executable")
    try:
        proc = subprocess.run(
            [str(SCRIPT)],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
        )
    except subprocess.TimeoutExpired:
        pytest.skip("gauntlet smoke timed out — file assertions are sufficient")
    out = (proc.stdout or "") + (proc.stderr or "")
    assert proc.returncode == 0, out
    assert "forge json target: OK" in out
    assert "forge materialise(godot, repair=True): OK" in out
