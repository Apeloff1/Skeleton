from __future__ import annotations

from pathlib import Path
import subprocess
import sys


def test_policy_import_does_not_require_optional_reasoning_core() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    probe = """
import sys
import types

# Reproduce the collision that previously broke policy-test collection: an
# unrelated package can already own the generic top-level `core` name.
sys.modules['core'] = types.ModuleType('core')
import skeleton.automation.dependabot_merge_policy  # noqa: F401
assert 'skeleton.automation.chatgpt_adapter' not in sys.modules
"""
    completed = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
