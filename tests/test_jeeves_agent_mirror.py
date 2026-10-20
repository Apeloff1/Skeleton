"""Regression: installed Jeeves mirrors retain identical functionality."""

from pathlib import Path

from scripts.check_jeeves_agent_mirror import REQUIRED, check_parity


def test_current_jeeves_delivery_mirrors_match_exact_source():
    result = check_parity()
    assert result["status"] == "passed", result
    assert result["checked"] == 13
    assert all(row["canonical_sha256"] == row["mirror_sha256"]
               for row in result["files"])


def test_code_change_in_mirror_is_detected_with_hash_evidence(tmp_path: Path):
    for name in REQUIRED:
        left = tmp_path / "skeleton/jeeves/agent" / name
        right = tmp_path / "skeleton/ai/agents/jeeves/agent" / name
        left.parent.mkdir(parents=True, exist_ok=True)
        right.parent.mkdir(parents=True, exist_ok=True)
        left.write_text("# canonical\n", encoding="utf-8")
        right.write_text("# canonical\n", encoding="utf-8")
    assert check_parity(tmp_path)["status"] == "passed"
    bad = tmp_path / "skeleton/ai/agents/jeeves/agent/delivery_milestone_queue.py"
    bad.write_text("# outdated implementation\n", encoding="utf-8")
    failure = check_parity(tmp_path)
    assert failure["status"] == "blocked"
    differing = [x for x in failure["files"] if x["status"] != "matched"]
    assert len(differing) == 1
    assert differing[0]["name"] == "delivery_milestone_queue.py"
    assert differing[0]["canonical_sha256"] != differing[0]["mirror_sha256"]


def test_missing_mirror_never_passes_parity(tmp_path: Path):
    report = check_parity(tmp_path)
    assert report["status"] == "blocked"
    assert all(entry["status"] == "missing" for entry in report["files"])
