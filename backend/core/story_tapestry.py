"""Whole-story emotional, dialogue, mystery and ending obligation accounting.

A false lead is allowed *only* when explicitly disclosed; an emotional
cliffhanger is allowed *only* when a later payoff actually references it.
Surprise must follow planted evidence. Ending, epilogue and optional postgame
are distinct. Findings identify source scenes rather than pretending an
unexamined manuscript is complete.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Mapping, Sequence

from core.chapter_continuity import MAX_SCENES, digest

STORY_MOMENTS = frozenset({
    "prologue", "inciting_incident", "emotional_turn", "cliffhanger",
    "surprise", "red_herring", "reveal", "tension_release",
    "comic_relief", "romance", "betrayal", "sacrifice", "loss",
    "reconciliation", "choice", "consequence", "climax", "denouement",
    "epilogue", "postgame",
})
SCENE_KINDS = frozenset({
    "prologue", "story", "side_story", "chapter_climax",
    "finale", "epilogue", "postgame",
})
THREAD_BEATS = frozenset({
    "setup", "foreshadow", "promise", "cliffhanger", "red_herring",
    "payoff", "resolution", "false_lead_disclosed", "surprise",
    "epilogue_callback",
})
OPENING = frozenset({"setup", "foreshadow", "promise", "cliffhanger", "red_herring"})
CLOSING = frozenset({"payoff", "resolution", "false_lead_disclosed"})
REVEAL = frozenset({"surprise", "false_lead_disclosed"})

def weave_tapestry(
    scenes: Sequence[Mapping[str, Any]], *,
    complete_source: bool = True, final_scene: int = MAX_SCENES,
    epilogue_required: bool = True,
) -> dict[str, Any]:
    """Check closed narrative arcs and cited emotional mechanics over one branch.

    All authored story moments are evidence submitted by editors, not proof that
    actual players felt emotion or found the story entertaining.
    """
    if len(scenes) > MAX_SCENES or final_scene < 1 or final_scene > MAX_SCENES:
        raise ValueError("Story manuscript exceeds supported bounds.")
    issues: list[dict[str, Any]] = []
    count = 0
    threads: dict[str, dict[str, Any]] = {}
    hits: dict[str, int] = defaultdict(int)
    ending = []
    by_scene: set[int] = set()
    milestones: list[dict[str, Any]] = []
    def issue(code: str, scene: int, thread: str | None, detail: str):
        nonlocal count
        count += 1
        if len(issues) < 200:
            issues.append({"code": code, "scene": scene, "thread_id": thread,
                           "detail": detail})
    ordered = sorted(scenes, key=lambda s: (s.get("scene", 0), s.get("act", 0)))
    for scene in ordered:
        n = scene.get("scene")
        if type(n) is not int or not 1 <= n <= MAX_SCENES or n in by_scene:
            issue("invalid_scene_identity", int(n) if type(n) is int else 0,
                  None, "Invalid or duplicate scene coordinate.")
            continue
        by_scene.add(n)
        role = scene.get("scene_kind", "story")
        if role not in SCENE_KINDS:
            issue("invalid_scene_kind", n, None, "Unrecognized story stage.")
        if role in ("finale", "epilogue"):
            ending.append({"scene": n, "stage": role})
        moments = scene.get("story_moments", [])
        beats = scene.get("thread_beats", [])
        moment_names: set[str] = set()
        for m in moments:
            kind = m.get("kind")
            plot = m.get("plot_id")
            intensity = m.get("intensity")
            if kind not in STORY_MOMENTS or type(intensity) is not int or not 0 <= intensity <= 100:
                issue("invalid_emotional_moment", n, None, "Story moment lacks a valid kind/intensity.")
                continue
            if plot not in {p.get("id") for p in scene.get("plot_points", [])}:
                issue("unmarked_emotional_moment", n, None,
                      "Emotional moment must point to a highlighted script passage.")
            moment_names.add(kind)
            hits[kind] += 1
        if role == "epilogue" and "epilogue" not in moment_names:
            issue("unmarked_epilogue", n, None, "Epilogue must identify its emotional closing passage.")
        if role == "finale" and "climax" not in moment_names:
            issue("unmarked_climax", n, None, "Finale needs a highlighted climax.")
        for beat in beats:
            thread = beat.get("thread_id")
            action = beat.get("role")
            plot = beat.get("plot_id")
            if not isinstance(thread, str) or not thread or action not in THREAD_BEATS:
                issue("invalid_thread_beat", n, None, "Malformed plot-thread role.")
                continue
            if plot not in {p.get("id") for p in scene.get("plot_points", [])}:
                issue("unmarked_thread_beat", n, thread,
                      "Every obligation needs an exact highlighted plot-point citation.")
                continue
            current = threads.get(thread)
            if action in OPENING:
                if current and current["status"] == "open":
                    # Foreshadow/refinement of the same thread may be repeated,
                    # but it does not create a second obligation.
                    current["developments"].append({"scene": n, "role": action, "plot_id": plot})
                elif current and current["status"] == "closed":
                    issue("reopened_closed_thread", n, thread,
                          "A closed plot must use a new thread identity.")
                else:
                    threads[thread] = {
                        "thread_id": thread, "introduced_scene": n,
                        "kind": action, "status": "open",
                        "intro_plot_id": plot,
                        "developments": [],
                        "closure_scene": None, "closure_kind": None,
                        "closure_plot_id": None,
                    }
            elif action in CLOSING:
                if not current or current["status"] != "open":
                    issue("orphan_payoff", n, thread, "Resolution has no open setup.")
                    continue
                if n <= current["introduced_scene"]:
                    issue("unearned_payoff", n, thread, "Payoff must come after setup.")
                    continue
                if current["kind"] == "red_herring" and action != "false_lead_disclosed":
                    issue("red_herring_not_disclosed", n, thread,
                          "A false lead must explicitly disclose why it was wrong.")
                    continue
                if current["kind"] != "red_herring" and action == "false_lead_disclosed":
                    issue("false_lead_without_misdirection", n, thread,
                          "False-lead disclosure lacks a planted red herring.")
                    continue
                current["status"] = "closed"
                current["closure_scene"] = n
                current["closure_kind"] = action
                current["closure_plot_id"] = plot
                milestones.append({"thread_id": thread,
                                   "setup_scene": current["introduced_scene"],
                                   "payoff_scene": n, "payoff_kind": action})
            elif action == "surprise":
                if not current or current["status"] != "open" or n <= current["introduced_scene"]:
                    issue("unearned_surprise", n, thread,
                          "Surprise must pay off a planted earlier clue.")
                else:
                    current["developments"].append({"scene": n, "role": action, "plot_id": plot})
            elif action == "epilogue_callback":
                if role != "epilogue" or not current or current["status"] != "closed":
                    issue("epilogue_callback_invalid", n, thread,
                          "Epilogue callback must cite a previously closed plot.")
    if epilogue_required:
        epilogues = [x["scene"] for x in ending if x["stage"] == "epilogue"]
        finales = [x["scene"] for x in ending if x["stage"] == "finale"]
        if not epilogues:
            issue("epilogue_missing", final_scene, None, "Story needs an authored epilogue.")
        if not finales:
            issue("finale_missing", final_scene, None, "Story needs an authored climax/finale.")
        if epilogues and finales and max(finales) >= min(epilogues):
            issue("ending_order_wrong", max(epilogues), None,
                  "Epilogue must occur after the finale.")
        if epilogues and max(epilogues) != final_scene:
            issue("epilogue_not_terminal", max(epilogues), None,
                  "Epilogue must be the final scene of the complete manuscript.")
    open_threads = sorted([{
        "thread_id": k, "introduced_scene": v["introduced_scene"],
        "kind": v["kind"], "intro_plot_id": v["intro_plot_id"],
    } for k, v in threads.items() if v["status"] == "open"], key=lambda x: x["thread_id"])
    if complete_source and open_threads:
        for x in open_threads[:200]:
            issue("dangling_plot_thread", x["introduced_scene"], x["thread_id"],
                  "An authored setup, cliffhanger or red herring lacks payoff.")
    # A finale/epilogue does not remove red-herring obligations. They need
    # explicit disclosure. Open threads in unfinished drafts remain visible.
    result = {
        "schema_version": "jeeves.story.tapestry.v1",
        "scenes_scanned": len(by_scene), "complete_source": bool(complete_source),
        "final_scene": final_scene, "ending_stages": ending,
        "moment_counts": dict(sorted(hits.items())),
        "threads_recorded": len(threads),
        "threads_closed": sum(v["status"] == "closed" for v in threads.values()),
        "open_threads": open_threads[:200],
        "open_thread_count": len(open_threads),
        "closed_milestones": milestones[:200],
        "issue_count": count, "issues": issues,
        "closure_ready": bool(complete_source) and count == 0 and not open_threads,
        "entertainment_quality_guaranteed": False,
    }
    result["receipt_digest"] = digest(result)
    return result
