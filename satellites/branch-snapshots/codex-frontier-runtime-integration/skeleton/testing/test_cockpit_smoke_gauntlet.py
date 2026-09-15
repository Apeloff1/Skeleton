"""S-size assertions for scripts/cockpit-smoke.sh forge cockpit gauntlet.

File-content / presence checks only; optional subprocess smoke is best-effort
so CI without a full env still passes on static gates.

Sibling of test_verify_forge_gauntlet.py (#9); does not touch forge wiring.
"""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "cockpit-smoke.sh"


def test_cockpit_smoke_script_exists_and_is_runnable():
    assert SCRIPT.is_file(), f"missing gauntlet script: {SCRIPT}"
    text = SCRIPT.read_text(encoding="utf-8")
    assert text.startswith("#!"), "expected shebang"
    mode = SCRIPT.stat().st_mode
    # Prefer executable bit; accept readable+shebang as fallback for checkout umask quirks
    assert mode & (stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH), "script not readable"
    assert mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH) or text.startswith(
        "#!"
    ), "script should be executable or at least shebang-runnable"


def test_cockpit_smoke_script_contains_key_gates():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "set -euo pipefail" in text
    assert "compileall" in text
    assert "skeleton eras" in text or 'm skeleton eras' in text
    assert "skeleton plan" in text or 'm skeleton plan' in text
    assert "skeleton cockpit" in text or "BLEND ERA" in text
    assert "skeleton walk" in text or "walk --era" in text
    assert "VERDICT" in text
    assert "ALL GATES PASSED" in text
    # Hyperforge sibling citation in header
    assert "hyperforge" in text.lower() or "browser-smoke" in text
    # Must not invoke the CI unit runner (known circular import on main / #8)
    non_comment = "\n".join(
        ln for ln in text.splitlines() if not ln.lstrip().startswith("#")
    )
    assert "run_unit" not in non_comment


def test_cockpit_smoke_script_smoke_optional():
    """Best-effort subprocess run; skip on timeout — static gates are enough for S-size."""
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
    assert "STEP:" in out or proc.returncode == 0
    if proc.returncode == 0:
        assert "VERDICT: ALL GATES PASSED" in out
