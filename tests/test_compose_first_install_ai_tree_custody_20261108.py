"""Guard first-install Compose source mirror custody and private fixture paths."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def test_mirrored_journal_game_and_audio_source():
    pairs=[
      ("skeleton/jeeves/worlds/world_canon.py","skeleton/ai/agents/jeeves/worlds/world_canon.py"),
      ("skeleton/forge/game_builder.py","skeleton/ai/forge/game_builder.py"),
      ("skeleton/forge/canon_custody_v1/artifacts_consumption_history.py","skeleton/ai/forge/canon_custody_v1/artifacts_consumption_history.py"),
      ("skeleton/audio/original_synthesis.py","skeleton/ai/runtime/extensions/audio/original_synthesis.py"),
    ]
    for source,mirror in pairs:
        assert (ROOT/source).read_bytes()==(ROOT/mirror).read_bytes()

def test_all_retained_roots_and_unsigned_cutover():
    manifest=json.loads((ROOT/"machine/ai_file_tree.json").read_text(encoding="utf-8"))
    retained=manifest["retained_outside_ai_tree"]
    names=[v["path"] for v in retained]
    assert len(set(names))==len(names)
    assert len(retained)==manifest["pre_move_readiness"]["retained_outside_ai_tree_count"]
    assert {"skeleton/mass_build","skeleton/perf_profiler","skeleton/provider_environment.py"} <= set(names)
    assert manifest["implementation_signoff"]["signed"] is False
    assert manifest["verification_signoff"]["signed"] is False
