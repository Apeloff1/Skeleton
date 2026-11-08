"""Quarantine source parity and portable fixture holds, not release admission."""
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

def test_mirror_custody_is_byte_identical():
    for left, right in (
        ("backend/core/knowledge_fabric.py",
         "skeleton/ai/compat/backend_core/knowledge_fabric.py"),
        ("skeleton/jeeves/worlds/world_canon.py",
         "skeleton/ai/agents/jeeves/worlds/world_canon.py"),
        ("skeleton/forge/game_builder.py", "skeleton/ai/forge/game_builder.py"),
        ("skeleton/forge/canon_custody_v1/artifacts_consumption_history.py",
         "skeleton/ai/forge/canon_custody_v1/artifacts_consumption_history.py"),
        ("skeleton/audio/original_synthesis.py",
         "skeleton/ai/runtime/extensions/audio/original_synthesis.py"),
    ):
        assert (ROOT / left).read_bytes() == (ROOT / right).read_bytes()

def test_quarantine_and_source_ownership_not_cut_over():
    value = json.loads((ROOT/"machine/ai_file_tree.json").read_text(encoding="utf8"))
    assert len(value["retained_outside_ai_tree"]) == 163
    assert value["pre_move_readiness"]["retained_outside_ai_tree_count"] == 163
    assert not value["implementation_signoff"]["signed"]
    assert not value["verification_signoff"]["signed"]

def test_fixture_roots_are_portable_and_private():
    for path in (
        "skeleton/testing/test_ai_flight_http.py",
        "skeleton/testing/test_ai_knowledge_plane.py",
        "skeleton/testing/test_ai_flight_context_admission.py",
        "skeleton/testing/test_ai_git_knowledge.py",
    ):
        contents = (ROOT / path).read_text(encoding="utf8")
        assert "dir='/home/oai" not in contents
        assert "dir=Path.home()" in contents
