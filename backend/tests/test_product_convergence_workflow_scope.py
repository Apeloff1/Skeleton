from __future__ import annotations

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
ACTIVE_WORKFLOW = ROOT / ".github" / "workflows" / "product-convergence.yml"
ARCHIVED_WORKFLOW = ROOT / ".github" / "workflows-archive" / "product-convergence.yml"
# Validate trigger scope and zero-work close semantics if the workflow returns.
WORKFLOW = ACTIVE_WORKFLOW if ACTIVE_WORKFLOW.is_file() else ARCHIVED_WORKFLOW
TEST_RE = re.compile(r"tests/[A-Za-z0-9_./-]+\.py")


def test_product_convergence_test_trigger_matches_executed_suite() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    trigger, body = text.split("concurrency:", 1)

    assert 'backend/tests/**' not in trigger

    executed = set(TEST_RE.findall(body))
    triggered = {
        path.removeprefix("backend/")
        for path in re.findall(r'"(backend/tests/[A-Za-z0-9_./-]+\.py)"', trigger)
    }

    assert executed
    assert triggered == executed

    for test_path in executed:
        # Archived push-only definitions have one event scope; a future
        # active PR plus push definition must cover both event scopes.
        expected_count = 2 if ACTIVE_WORKFLOW.is_file() else 1
        assert trigger.count(f'- "backend/{test_path}"') == expected_count


def test_product_convergence_closure_is_zero_work_cancellation_tombstone() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    if ACTIVE_WORKFLOW.is_file():
        assert 'types: [opened, synchronize, reopened, closed]' in text
        assert 'group: product-convergence-${{ github.event.pull_request.number || github.ref }}' in text
        assert 'cancel-in-progress: true' in text
        assert "if: github.event_name != 'pull_request' || github.event.action != 'closed'" in text
    else:
        assert ARCHIVED_WORKFLOW.is_file()
        trigger = text.split("concurrency:", 1)[0]
        assert "  pull_request:" not in trigger
        assert "  push:" in trigger
        assert "branches: [main]" in trigger
