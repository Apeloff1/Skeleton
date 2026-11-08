"""Source-identity parity for restored Jeeves, Forge and audio mirrors."""
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

def test_recovered_mirror_modules_are_byte_identical():
    for source,mirror,path in (
        ("skeleton/jeeves","skeleton/ai/agents/jeeves","worlds/world_canon.py"),
        ("skeleton/forge","skeleton/ai/forge","game_builder.py"),
        ("skeleton/forge","skeleton/ai/forge","canon_custody_v1/artifacts_consumption_history.py"),
        ("skeleton/audio","skeleton/ai/runtime/extensions/audio","original_synthesis.py"),
        ("skeleton/audio","skeleton/ai/runtime/extensions/audio","fixtures/footstep.json"),
    ):
        assert (ROOT/mirror/path).read_bytes() == (ROOT/source/path).read_bytes()

def test_no_source_custody_grants_cutover():
    data=json.loads((ROOT/"machine/ai_file_tree.json").read_text(encoding="utf8"))
    assert not data["implementation_signoff"]["signed"]
    assert not data["verification_signoff"]["signed"]
    assert data["pre_move_readiness"]["retained_outside_ai_tree_count"] == len(data["retained_outside_ai_tree"])
