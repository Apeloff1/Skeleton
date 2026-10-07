"""Regression coverage for the P2 local-inference workflow acceptance target."""
from pathlib import Path
import re

WORKFLOW = Path(".github/workflows/p2-local-inference.yml")


def test_p2_local_inference_workflow_references_existing_test_files() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    referenced = set(re.findall(r"skeleton/testing/test_[A-Za-z0-9_]+\.py", text))
    assert "skeleton/testing/test_local_inference.py" in referenced
    missing = sorted(path for path in referenced if not Path(path).is_file())
    assert not missing, f"P2 Local Inference references missing tests: {missing}"
