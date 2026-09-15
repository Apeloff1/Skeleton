"""
tests/test_director_cascade.py — Manifest Item 18.

Verifies the Director correctly cascades a physics design choice into the
tileset + camera (cinematics) stages, and that reflection on a failing quality
score queues the affected downstream stages for revisit.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.director_agent import DirectorAgent, STAGE_DOWNSTREAM, MIN_QUALITY


def test_physics_cascades_into_tileset_and_camera():
    d = DirectorAgent()
    plan = d.plan_stage("build_x", "physics")
    downstream = plan["downstream"]
    assert "tileset" in downstream, "physics must cascade into tileset"
    assert "cinematics" in downstream, "physics must cascade into camera/cinematics"
    assert plan["sub_forges"][-1] == "physics"


def test_reflection_below_threshold_queues_revisit():
    d = DirectorAgent()
    d.plan_stage("build_y", "physics")
    r = d.reflect_on_quality("build_y", {"stage": "physics", "score": 60,
                                          "feedback": "collisions unstable"})
    assert r["passed"] is False
    assert "physics" in r["stages_to_revisit"]
    assert "tileset" in r["stages_to_revisit"]
    assert "cinematics" in r["stages_to_revisit"]
    assert "delta_instruction" in r and r["delta_instruction"]
    # exhaustive hint must be present in the delta (Item 19)
    assert "EXHAUSTIVE" in r["delta_instruction"].upper()


def test_reflection_pass_no_revisit():
    d = DirectorAgent()
    r = d.reflect_on_quality("build_z", {"stage": "physics", "score": MIN_QUALITY})
    assert r["passed"] is True
    assert r["stages_to_revisit"] == []


def test_state_tracks_forge_history():
    d = DirectorAgent()
    d.record_forge("build_w", "spec", "core_specs", 97)
    st = d.get_state("build_w")
    assert st["quality_scores"]["spec"] == 97
    assert any(e["stage"] == "spec" for e in st["artifact_history"])


if __name__ == "__main__":
    test_physics_cascades_into_tileset_and_camera()
    test_reflection_below_threshold_queues_revisit()
    test_reflection_pass_no_revisit()
    test_state_tracks_forge_history()
    print("✅ all director cascade tests passed")
