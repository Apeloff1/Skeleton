from __future__ import annotations

from pathlib import Path
import subprocess
import sys


def test_core_package_resolves_to_repository_tree() -> None:
    import core
    import core.activation_security as activation_security

    repo_root = Path(__file__).resolve().parents[1]
    assert Path(core.__file__).resolve() == repo_root / "core" / "__init__.py"
    assert Path(activation_security.__file__).resolve() == repo_root / "core" / "activation_security.py"


def test_dependabot_policy_import_does_not_eagerly_load_reasoning_adapter() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    probe = """
import sys
import types

# Simulate an unrelated top-level package already owning the generic `core` name.
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
