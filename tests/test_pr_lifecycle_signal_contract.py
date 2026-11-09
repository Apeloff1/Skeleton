from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SIGNAL = ROOT / ".github" / "workflows" / "pr-lifecycle-signal.yml"
DRAINER = ROOT / ".github" / "workflows" / "pr-obsolete-run-drain.yml"


def test_lifecycle_signal_never_allocates_runner_work() -> None:
    text = SIGNAL.read_text(encoding="utf-8")

    assert "types: [synchronize, closed]" in text
    assert "permissions: {}" in text
    assert "if: ${{ false }}" in text
    assert "actions/checkout" not in text


def test_privileged_drainer_consumes_signal_at_requested_phase() -> None:
    text = DRAINER.read_text(encoding="utf-8")

    assert 'workflows: ["PR Lifecycle Signal"]' in text
    assert "types: [requested]" in text
    assert "types: [completed]" not in text
