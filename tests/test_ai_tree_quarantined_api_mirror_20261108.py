"""Guard exact-source mirror admission without granting production authority."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def test_quarantined_v1_api_stays_private_and_source_mirrored():
    for rel in ("__init__.py", "auth.py", "edge.py", "quota_store/limiter.py"):
        source=ROOT/"skeleton/api/v1_edge"/rel
        mirror=ROOT/"skeleton/ai/runtime/api/v1_edge"/rel
        assert source.is_file() and mirror.read_bytes()==source.read_bytes()

def test_governed_tree_file_contracts():
    for canonical, mirror, rel in (
        ("skeleton/jeeves", "skeleton/ai/agents/jeeves", "worlds/world_canon.py"),
        ("skeleton/forge", "skeleton/ai/forge", "game_builder.py"),
        ("skeleton/forge", "skeleton/ai/forge", "canon_custody_v1/artifacts_consumption_history.py"),
        ("skeleton/audio", "skeleton/ai/runtime/extensions/audio", "original_synthesis.py"),
        ("skeleton/audio", "skeleton/ai/runtime/extensions/audio", "fixtures/footstep.json"),
    ):
        assert (ROOT/mirror/rel).read_bytes()==(ROOT/canonical/rel).read_bytes()

def test_mirror_signoffs_remain_unsigned():
    d=json.loads((ROOT/"machine/ai_file_tree.json").read_text(encoding="utf8"))
    assert d["implementation_signoff"]["signed"] is False
    assert d["verification_signoff"]["signed"] is False
    assert d["pre_move_readiness"]["retained_outside_ai_tree_count"] == len(d["retained_outside_ai_tree"])
