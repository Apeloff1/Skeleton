"""Chapter-local narrative memory and fail-closed game-story dramaturgy.

100 chapters × 10 consecutive acts = 1000 global acts, 9999 scenes total.
Every scene records on-source plot highlighters, visual/sound editorial direction,
causal dramaturgy and a prospective chapter outcome. A chapter cannot turn
without a source-linked cliffhanger or resolution. This is a *source quality
gate*, not proof that the subjective finished film or game is perfect.
"""
from __future__ import annotations

from collections import defaultdict
from .story_canon_fabric import (
    StoryCanonError, array, colors, digest, ident, number, require, shape, text)

CHAPTERS = 100
ACTS = 1000
SCENES = 9999
ACTS_PER_CHAPTER = 10
KINDS = frozenset(("prologue", "prelude", "main", "interlude", "epilogue"))
PACING = frozenset(("slow_burn", "rising", "reversal", "high_intensity",
                   "aftermath"))
CLOSURES = frozenset(("ongoing", "cliffhanger", "resolution"))
HIGHLIGHT_PALETTE = {
    "foreshadowing": "#D99A28",
    "reveal": "#C86FDC",
    "conflict": "#E76363",
    "motivation": "#54A6EE",
    "relationship": "#65B5A1",
    "prop": "#9B86E0",
    "suspense": "#E0A064",
    "payoff": "#75B979",
}
CAMERA = frozenset(("wide", "medium", "closeup", "extreme_closeup",
                    "tracking", "over_shoulder", "first_person",
                    "establishing", "interactive", "fixed"))
CUTS = frozenset(("straight", "match_cut", "cross_cut", "dissolve",
                  "continuous", "player_control", "fade"))


def chapter_of_act(act):
    number(act, 1, ACTS, "global act")
    return (act - 1) // ACTS_PER_CHAPTER + 1


def storytelling_template(chapter, *, form="main"):
    number(chapter, 1, CHAPTERS, "original chapter")
    require(form in KINDS, "unknown authored storytelling form")
    return {
        "chapter_title": "", "form": form, "pacing": "rising",
        "tension_before": 0, "tension_after": 0,
        "stakes": "", "dramatic_question": "", "hook": "",
        "chapter_outcome": "ongoing",
        "plot_highlights": [], "closed_highlights": [],
        "editorial": {
            "camera": "interactive", "cut": "player_control",
            "performance": "", "soundscape": "",
            "continuity_notes": [],
        },
    }


def validate_storytelling(scene, *, known_highlights, previous=None):
    require("chapter" in scene and "storytelling" in scene,
            "chapter, act, scene and source-level dramaturgy required")
    chapter = number(scene["chapter"], 1, CHAPTERS, "chapter")
    require(chapter == chapter_of_act(scene["act"]),
            "chapter does not contain its ten approved acts")
    narrative = shape(scene["storytelling"], (
        "chapter_title","form","pacing","tension_before","tension_after",
        "stakes","dramatic_question","hook","chapter_outcome",
        "plot_highlights","closed_highlights","editorial"),
        "strict scene narrative structure")
    text(narrative["chapter_title"], "chapter title", 140)
    require(len(narrative["chapter_title"].strip()) >= 3,
            "chapter must have a meaningful original title")
    require(narrative["form"] in KINDS and narrative["pacing"] in PACING,
            "unapproved prose/cinematic section or pacing")
    before = number(narrative["tension_before"], 0, 10, "entry suspense")
    after = number(narrative["tension_after"], 0, 10, "exit suspense")
    require(narrative["chapter_outcome"] in CLOSURES,
            "outcome must continue or establish a cliffhanger/resolution")
    for key in ("stakes","dramatic_question","hook"):
        text(narrative[key], "story stakes/plot hook " + key, 1000)
        require(len(narrative[key].strip()) >= 12,
                "real dramatic stakes, explicit question and hook are required")
    edit = shape(narrative["editorial"], (
        "camera","cut","performance","soundscape","continuity_notes"),
        "cinematic scene edit")
    require(edit["camera"] in CAMERA and edit["cut"] in CUTS,
            "camera and editorial cutting need approved typed vocabulary")
    for key in ("performance","soundscape"):
        text(edit[key], "editorial direction " + key, 750)
        require(len(edit[key].strip()) >= 8, "authored performance/sound detail required")
    for note in array(edit["continuity_notes"], 32, "scene continuity notes", 1):
        text(note, "audited continuity note", 500)
        require(len(note.strip()) >= 6, "no placeholder continuity notes")
    on_scene = {
        item["id"] for category in ("events","dialogue","interactions","beats")
        for item in scene[category]
    }
    opened = []
    highlight_rows = array(narrative["plot_highlights"], 32,
                           "source-linked plot highlighters", 1)
    for item in highlight_rows:
        shape(item, ("id","kind","reference","color","importance","note"),
              "chapter context highlighter")
        key = ident(item["id"], "highlight")
        require(key not in known_highlights and key not in opened,
                "cannot reuse a historical plot-point highlight ID")
        require(item["kind"] in HIGHLIGHT_PALETTE and
                item["color"] == HIGHLIGHT_PALETTE[item["kind"]],
                "plot highlighter category/color must be consistent across chapters")
        require(item["reference"] in on_scene,
                "highlight must bookmark a *real* scene event, line or beat")
        number(item["importance"], 1, 5, "plot highlighter importance")
        text(item["note"], "chapter plot note", 600)
        require(len(item["note"].strip()) >= 8,
                "plot highlights cannot be placeholders")
        opened.append(key)
    closed = array(narrative["closed_highlights"], 32, "resolved plot threads")
    require(len(closed) == len(set(closed)),
            "a plot thread cannot be resolved more than once in one scene")
    for key in closed:
        ident(key,"resolved plot thread")
        require(key in known_highlights and not known_highlights[key]["closed"],
                "scene can only resolve an actual open historical highlighted plot point")
    if previous is None:
        require((chapter,scene["act"],scene["scene"]) == (1,1,1),
                "story must start at chapter 1 / act 1 / scene 1")
        require(narrative["form"] in ("prologue","prelude","main"),
                "first scene must begin with prelude, prologue or main story")
    else:
        earlier = previous["storytelling"]
        require(before == earlier["tension_after"],
                "suspense continuity cannot reset invisibly between scenes")
        if chapter != previous["chapter"]:
            require(chapter == previous["chapter"]+1,
                    "cannot skip a chapter in source production")
            require(earlier["chapter_outcome"] in ("cliffhanger","resolution"),
                    "previous chapter must close with a cliffhanger or resolution")
            require(narrative["form"] in ("prologue","prelude","main"),
                    "new chapter requires a valid thematic opening")
        else:
            require(earlier["chapter_outcome"] == "ongoing",
                    "chapter already ended; author the next chapter")
            require(narrative["chapter_title"] == earlier["chapter_title"],
                    "chapter title silently changed mid-story")
            require(narrative["form"] not in ("prologue","prelude"),
                    "opening prelude/prologue cannot silently recur inside a chapter")
    if narrative["form"] == "epilogue":
        require(narrative["chapter_outcome"] == "resolution",
                "epilogue must resolve, not leave the chapter mid-arc")
    if narrative["chapter_outcome"] == "resolution":
        require(closed, "resolution must explicitly close an earlier highlighted plot thread")
    if narrative["chapter_outcome"] == "cliffhanger":
        require(after >= 5, "cliffhanger must retain substantial authored suspense")
    return opened, closed


def validate_chapter_history(scenes, *, require_final=False):
    """Linear chronological audit, independent of all model-generated summaries."""
    require(type(scenes) in (list,tuple) and len(scenes) <= SCENES,
            "9999-scene canonical memory required")
    highlights = {}
    closed = []
    prior = None
    chapter_start = {}
    chapter_end = {}
    rising = defaultdict(bool)
    open_tension = {}
    seen_acts = set()
    for scene in scenes:
        current = scene["chapter"]
        opened, finished = validate_storytelling(
            scene, known_highlights=highlights, previous=prior)
        if current not in chapter_start:
            chapter_start[current] = scene["sequence"]
            open_tension[current] = scene["storytelling"]["tension_before"]
        if prior is not None and current != prior["chapter"]:
            old = prior["chapter"]
            require(rising[old],
                    "closed chapter never increased stakes/suspense across its scenes")
            chapter_end[old] = {
                "sequence":prior["sequence"],"scene_digest":prior["digest"],
                "ending":prior["storytelling"]["chapter_outcome"],
                "hook":prior["storytelling"]["hook"],
                "chapter_title":prior["storytelling"]["chapter_title"],
            }
        narrative = scene["storytelling"]
        rising[current] |= narrative["tension_after"] > narrative["tension_before"]
        for row in narrative["plot_highlights"]:
            highlights[row["id"]] = {
                "chapter":current,"sequence":scene["sequence"],
                "source_digest":scene["digest"],"kind":row["kind"],
                "color":row["color"],"reference":row["reference"],
                "importance":row["importance"],"note":row["note"],"closed":False,
            }
        for key in finished:
            highlights[key]["closed"] = True
            highlights[key]["closed_in_scene"] = scene["sequence"]
            closed.append(key)
        seen_acts.add(scene["act"])
        prior=scene
    if require_final:
        require(len(scenes) == SCENES and len(seen_acts) == ACTS and
                len(chapter_start) == CHAPTERS,
                "final signoff needs all 100 chapters, 1000 acts, 9999 scenes")
        require(prior["storytelling"]["chapter_outcome"] in
                ("cliffhanger","resolution"),
                "final story must end in resolution or an intentional cliffhanger")
        require(rising[CHAPTERS], "final chapter lacks rising tension")
        chapter_end[CHAPTERS] = {
            "sequence":prior["sequence"],"scene_digest":prior["digest"],
            "ending":prior["storytelling"]["chapter_outcome"],
            "hook":prior["storytelling"]["hook"],
            "chapter_title":prior["storytelling"]["chapter_title"],
        }
    return {
        "highlights":highlights,"resolved_highlights":closed,
        "chapter_starts":chapter_start,
        "closed_chapters":chapter_end,
        "rising_tension_by_chapter":dict(rising),
        "current_chapter":prior["chapter"] if prior else 1,
        "source_count":len(scenes),
    }


def chapter_context(bible, contract, scenes, *, chapter=None, max_prior_capsules=12):
    """One chapter's raw scene context; prior history only via source-linked capsules.

    Invoke after full source and receipt reparse. The model context intentionally
    does not copy 9999 scenes. All evidence remains reachable by highlight ID
    and the exact historical scene digest.
    """
    from .story_continuity_assurance import verify_production_history
    confirmation = verify_production_history(bible, contract, scenes)
    projection = validate_chapter_history(scenes)
    current = projection["current_chapter"]
    if chapter is None:
        chapter=current
    number(chapter,1,CHAPTERS,"requested chapter")
    number(max_prior_capsules,1,CHAPTERS,"prior chapter recall")
    require(chapter <= current and (not scenes or chapter in
            projection["chapter_starts"]),
            "cannot load a nonexistent future chapter")
    within=[s for s in scenes if s["chapter"]==chapter]
    chapters=projection["closed_chapters"]
    prior=[{"chapter":c, **data} for c,data in sorted(chapters.items())
           if c<chapter]
    markers=[{"id":key,**data} for key,data in projection["highlights"].items()
             if data["chapter"]==chapter]
    carry=[{"id":key,**data} for key,data in projection["highlights"].items()
           if data["chapter"]<chapter and not data["closed"]]
    output = {
        "schema":"skeleton.game_builder.jeeves_chapter_context.v1",
        "project":bible["project"],"chapter":chapter,"chapter_total":CHAPTERS,
        "act_total":ACTS,"scene_total":SCENES,
        "source_bible_digest":bible["digest"],
        "source_contract_digest":contract["digest"],
        "verified_source_head":confirmation["verified_source_head"],
        "verified_receipt_head":confirmation["verified_receipt_head"],
        "chapter_scene_count":len(within),
        "chapter_scene_sources":[{
            "sequence":s["sequence"],"act":s["act"],"scene":s["scene"],
            "digest":s["digest"],"receipt":s["assurance"]["digest"],
            "storytelling":s["storytelling"],
            "dialogue_refs":[x["id"] for x in s["dialogue"]],
            "event_refs":[x["id"] for x in s["events"]],
        } for s in within],
        "chapter_highlighters":markers,
        "unresolved_prior_highlighters":carry,
        "prior_chapter_endings":prior[-max_prior_capsules:],
        "older_chapters_retrievable_by_bookmark":True,
        "all_previous_chapters_reparsed":True,
        "full_world_and_character_states":confirmation["current_character_state"],
        "voice_and_style_locked_by":contract["digest"],
        "model_inference_performed":False,
        "fiction_quality_automatically_certified":False,
    }
    return {**output,"digest":digest(output)}
