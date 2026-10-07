"""Fail closed before model-driven repository automation is activated.

The bot control planes run only after a small repository-native security baseline
passes against the trusted checkout. The checks execute without model or GitHub
credentials and their captured output is never surfaced through exceptions.
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
from typing import Mapping

REPO_ROOT = Path(__file__).resolve().parents[2]
GATED_WORKFLOWS = frozenset(
    {
        "Idle Studio",
        "Autonomous Studio Night Shift",
        "Shift Supervisor Control",
    }
)
SECURITY_GATES = (
    Path("backend/scripts/check_workflow_input_security.py"),
    Path("backend/scripts/check_workflow_action_allowlist.py"),
    Path("backend/scripts/check_workflow_permissions.py"),
    Path("backend/scripts/check_docker_secret_boundary.py"),
    Path("backend/scripts/check_secret_hygiene.py"),
    Path("backend/scripts/check_security_scan_surface.py"),
)
_CREDENTIAL_ENV = frozenset({"OPENAI_API_KEY", "GH_TOKEN", "GITHUB_TOKEN"})
_VERIFIED: set[tuple[str, str, str]] = set()


class ActivationSecurityError(RuntimeError):
    """Raised when a model-driven bot cannot prove its local security baseline."""


def _credential_free_env(source: Mapping[str, str] | None = None) -> dict[str, str]:
    env = dict(os.environ if source is None else source)
    for key in _CREDENTIAL_ENV:
        env.pop(key, None)
    return env


def run_bot_activation_security_baseline(
    *,
    repo_root: Path = REPO_ROOT,
    env: Mapping[str, str] | None = None,
) -> None:
    """Run the local security gates without credentials or output disclosure."""

    root = repo_root.resolve()
    safe_env = _credential_free_env(env)
    for relative in SECURITY_GATES:
        checker = root / relative
        if not checker.is_file() or checker.is_symlink():
            raise ActivationSecurityError(
                f"bot activation security checker is unavailable: {relative.as_posix()}"
            )
        try:
            completed = subprocess.run(
                [sys.executable, str(checker)],
                cwd=root,
                env=safe_env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=90,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise ActivationSecurityError(
                f"bot activation security checker could not run: {relative.name}"
            ) from exc
        if completed.returncode != 0:
            raise ActivationSecurityError(
                f"bot activation security baseline failed: {relative.name}"
            )


def enforce_bot_activation_security() -> None:
    """Require the baseline only inside the three model-driven bot workflows."""

    workflow = os.getenv("GITHUB_WORKFLOW", "").strip()
    if workflow not in GATED_WORKFLOWS:
        return

    sha = os.getenv("GITHUB_SHA", "").strip()
    root = str(REPO_ROOT.resolve())
    cache_key = (workflow, sha, root)
    if cache_key in _VERIFIED:
        return

    run_bot_activation_security_baseline()
    _VERIFIED.add(cache_key)


def main() -> int:
    try:
        run_bot_activation_security_baseline()
    except ActivationSecurityError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print("Bot activation security baseline passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
