"""Top-level source inventory remains complete without granting migration approval."""
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

def test_governed_retained_source_inventory_and_authority():
    data = json.loads((ROOT / "machine/ai_file_tree.json").read_text(encoding="utf-8"))
    names = [entry["path"] for entry in data["retained_outside_ai_tree"]]
    # Preserve the two historical source-inventory ordering exceptions.
    assert len(names) == len(set(names))
    for source in ("skeleton/mass_build", "skeleton/perf_profiler", "skeleton/provider_environment.py"):
        assert source in names
        assert (ROOT / source).exists()
    assert data["pre_move_readiness"]["retained_outside_ai_tree_count"] == len(names)
    assert data["implementation_signoff"]["signed"] is False
    assert data["verification_signoff"]["signed"] is False
