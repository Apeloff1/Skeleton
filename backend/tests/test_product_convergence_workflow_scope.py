from __future__ import annotations

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "product-convergence.yml"
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

    # Every executed backend test is collected under this shared pytest
    # configuration. Changes to fixtures/collection policy can alter the
    # entire convergence suite even when no explicit test file changes.
    assert trigger.count('- "backend/tests/conftest.py"') == 2

    for test_path in executed:
        assert trigger.count(f'- "backend/{test_path}"') == 2
