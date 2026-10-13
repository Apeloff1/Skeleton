"""Ensure isolated exact-head AI chat CI can import all inherited test lanes.

Default pytest import mode can try to import tests/test_* through a third-party
installed 'tests' package instead of this repo's file. Plugin autoload is
intentionally disabled; the async plugin must be loaded explicitly.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/ai-chat-runtime-closure.yml"


def _step(text: str, start: str, end: str) -> str:
    return text.split("      - name: " + start, 1)[1].split("      - name: " + end, 1)[0]


def test_chat_runtime_isolated_collection_uses_file_imports_and_async_runtime():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert 'PYTEST_DISABLE_PLUGIN_AUTOLOAD: "1"' in workflow
    inherited = _step(workflow, "Run AI chat and inherited assistant regressions",
                      "Run live chat route cutover regressions")
    live = _step(workflow, "Run live chat route cutover regressions",
                 "Emit exact-head AI chat runtime evidence")
    assert "--noconftest" in inherited
    assert "tests/test_ai_chat_runtime_contract.py" in inherited
    for step in (inherited, live):
        assert "--import-mode=importlib" in step
        assert "-p pytest_asyncio.plugin" in step
        assert "python -m pytest" in step
