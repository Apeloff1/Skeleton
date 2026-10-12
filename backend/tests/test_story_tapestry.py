"""Complete narrative tapestry with strict red herring and epilogue closure."""
from __future__ import annotations
import pytest
from core.story_tapestry import weave_tapestry


def scene(n, *, kind="story", moments=(), beats=(), points=()):
    return {
        "scene": n, "act": 1, "chapter": 1, "scene_kind": kind,
        "story_moments": list(moments), "thread_beats": list(beats),
        "plot_points": [{"id": p, "anchor": p} for p in points],
    }


def moment(kind, plot_id, intensity=85):
    return {"kind": kind, "plot_id": plot_id, "intensity": intensity,
            "objective": "Character responds to a dramatic situation.",
            "audience_effect": "Player experiences suspense or resolution."}


def beat(thread, role, point):
    return {"thread_id": thread, "role": role, "plot_id": point}


def complete_story():
    return [
        scene(1, kind="prologue", points=["opening", "false_clue", "danger"],
              beats=[beat("lost_king", "setup", "opening"),
                     beat("false_map", "red_herring", "false_clue"),
                     beat("hero_in_danger", "cliffhanger", "danger")],
              moments=[moment("prologue", "opening"), moment("cliffhanger", "danger"),
                       moment("red_herring", "false_clue")]),
        scene(2, points=["truth", "rescue", "misdirection"],
              beats=[beat("lost_king", "surprise", "truth"),
                     beat("hero_in_danger", "payoff", "rescue"),
                     beat("false_map", "false_lead_disclosed", "misdirection")],
              moments=[moment("surprise", "truth"), moment("tension_release", "rescue"),
                       moment("reveal", "misdirection")]),
        scene(3, kind="finale", points=["king_found"],
              beats=[beat("lost_king", "resolution", "king_found")],
              moments=[moment("climax", "king_found")]),
        scene(4, kind="epilogue", points=["aftermath"],
              beats=[beat("lost_king", "epilogue_callback", "aftermath")],
              moments=[moment("epilogue", "aftermath")]),
    ]


def codes(result):
    return {x["code"] for x in result["issues"]}


def test_red_herring_surprise_cliffhanger_and_epilogue_are_all_closed():
    manuscript = complete_story()
    report = weave_tapestry(manuscript, final_scene=4)
    assert report["closure_ready"] is True
    assert report["issue_count"] == 0
    assert report["threads_recorded"] == 3
    assert report["threads_closed"] == 3
    assert report["moment_counts"]["surprise"] == 1
    assert report["moment_counts"]["cliffhanger"] == 1
    assert report["moment_counts"]["epilogue"] == 1
    assert len(report["receipt_digest"]) == 64


def test_unexplained_red_herring_is_not_merely_resolved_by_a_generic_payoff():
    manuscript = complete_story()
    manuscript[1]["thread_beats"][2]["role"] = "payoff"
    report = weave_tapestry(manuscript, final_scene=4)
    assert "red_herring_not_disclosed" in codes(report)
    assert "dangling_plot_thread" in codes(report)
    assert report["closure_ready"] is False


def test_surprise_requires_planted_evidence_from_an_earlier_scene():
    manuscript = complete_story()
    manuscript[0]["thread_beats"] = [
        x for x in manuscript[0]["thread_beats"] if x["thread_id"] != "lost_king"
    ]
    report = weave_tapestry(manuscript, final_scene=4)
    assert "unearned_surprise" in codes(report)
    assert "orphan_payoff" in codes(report)


def test_cliffhanger_without_payoff_is_not_considered_entertainment_ready():
    manuscript = complete_story()
    manuscript[1]["thread_beats"] = [
        x for x in manuscript[1]["thread_beats"] if x["thread_id"] != "hero_in_danger"
    ]
    report = weave_tapestry(manuscript, final_scene=4)
    assert "dangling_plot_thread" in codes(report)
    assert any(x["thread_id"] == "hero_in_danger" for x in report["open_threads"])


def test_missing_epilogue_and_wrong_ending_order_are_explicit_errors():
    manuscript = complete_story()[:-1]
    report = weave_tapestry(manuscript, final_scene=4)
    assert "epilogue_missing" in codes(report)
    reversed_end = complete_story()
    reversed_end[2]["scene_kind"] = "epilogue"
    reversed_end[2]["story_moments"] = [moment("epilogue", "king_found")]
    reversed_end[3]["scene_kind"] = "finale"
    reversed_end[3]["story_moments"] = [moment("climax", "aftermath")]
    result = weave_tapestry(reversed_end, final_scene=4)
    assert "ending_order_wrong" in codes(result)


def test_epilogue_callback_needs_prior_closed_thread():
    manuscript = complete_story()
    manuscript[3]["thread_beats"] = [beat("unmentioned_quest", "epilogue_callback", "aftermath")]
    assert "epilogue_callback_invalid" in codes(weave_tapestry(manuscript, final_scene=4))


def test_unanchored_emotions_and_invalid_intensity_fail_closed():
    manuscript = complete_story()
    manuscript[1]["story_moments"].append(moment("betrayal", "unknown_marker", 101))
    result = weave_tapestry(manuscript, final_scene=4)
    assert "invalid_emotional_moment" in codes(result)
    manuscript[1]["story_moments"][-1]["intensity"] = 50
    result = weave_tapestry(manuscript, final_scene=4)
    assert "unmarked_emotional_moment" in codes(result)


def test_partial_source_never_claims_full_closure():
    result = weave_tapestry(complete_story(), complete_source=False, final_scene=4)
    assert result["closure_ready"] is False
    assert result["complete_source"] is False


def test_duplicate_scene_and_orphan_payoff_are_detected():
    m = complete_story()
    m.insert(1, scene(1, points=["another"],
                      beats=[beat("not_setup", "payoff", "another")]))
    result = weave_tapestry(m, final_scene=4)
    assert "invalid_scene_identity" in codes(result)


def test_historical_branch_end_requires_explicit_epilogue_not_sequel_excuse():
    m = complete_story()
    m[-1]["scene_kind"] = "postgame"
    result = weave_tapestry(m, final_scene=4)
    assert "epilogue_missing" in codes(result)
