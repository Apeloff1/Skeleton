"""Workspace bridge: full-source Jeeves canon retrieval and reviewed commit gates.

The index is a deterministic projection, NOT an unsupervised source mutation.
Every scene is checked against all approved predecessors on every build.
"""
from __future__ import annotations

from .story_canon_fabric import (
    BIBLE, PHASES, SCENE, MAX_SCENES, StoryCanonError,
    story_bible_template, story_scene_template, scene_path,
    validate_story_bible, verify_story_history, verify_story_scene,
    jeeves_story_brief,
)


def load_continuity_contract(workspace, project):
    """Load a reviewed 100-chapter / 1000-act / 9999-scene contract."""
    from .game_project_workspace import _json
    from .story_continuity_assurance import validate_contract
    if project != workspace.active():
        raise StoryCanonError("cannot inspect another project's canon")
    files = workspace.files("current", project)
    if "game/continuity_contract.json" not in {f.path for f in files}:
        return None
    base = _json(workspace.read("current", project,
                    "game/story_bible.json")["content"])
    contract = _json(workspace.read("current", project,
                    "game/continuity_contract.json")["content"])
    validate_contract(contract, base)
    return contract


def load_story_workspace(workspace, project):
    """Read all committed story sources without executing generated content."""
    if project != workspace.active():
        raise StoryCanonError("Jeeves may only author the active current project")
    files = workspace.files("current", project)
    paths = sorted(f.path for f in files if
                   f.path.startswith(("story/scenes/","story/chapters/")))
    if len(paths) > MAX_SCENES:
        raise StoryCanonError("full historical scene limit exceeded")
    for path in paths:
        # All nonconforming paths under reserved story area fail closed;
        # no silent omissions, wildcard matches or approximate memory.
        import re
        if not (re.fullmatch(r"story/scenes/act_[0-9]{4}/scene_[0-9]{6}\.json", path)
                or re.fullmatch(
                    r"story/chapters/chapter_[0-9]{3}/acts/act_[0-9]{4}/scene_[0-9]{6}\.json",
                    path)):
            raise StoryCanonError("noncanonical historical story scene path")
    import json
    from .game_project_workspace import _json
    bibfiles = [f for f in files if f.path == "game/story_bible.json"]
    if not bibfiles:
        if paths:
            raise StoryCanonError("story scene history exists without its approved bible")
        return None, [], None
    bible = _json(workspace.read("current", project,
                                "game/story_bible.json")["content"])
    validate_story_bible(bible)
    if bible["project"] != project:
        raise StoryCanonError("story world belongs to a different current project")
    scenes = []
    for path in paths:
        content = _json(workspace.read("current", project, path)["content"])
        if scene_path(content) != path or content.get("schema") != SCENE:
            raise StoryCanonError("scene source file identity does not match contents")
        scenes.append(content)
    index = verify_story_history(bible, scenes)
    # Strict source history cannot be bypassed by choosing a different
    # studio entry point or reading the source directly.
    contract = load_continuity_contract(workspace, project)
    if contract is not None:
        from .story_continuity_assurance import verify_production_history
        verify_production_history(bible, contract, scenes)
    return bible, scenes, index


def validate_story_workspace_source(workspace, project, path, source):
    """Required at BOTH proposed-source and human commit boundaries."""
    if path == "game/continuity_contract.json":
        from .story_continuity_assurance import validate_contract
        bible, scenes, _ = load_story_workspace(workspace, project)
        if bible is None or bible["phase"] != "design":
            raise StoryCanonError("no voice/face lock before reviewed world design")
        if scenes:
            raise StoryCanonError("cannot replace the visual/voice contract after scene one")
        current = load_continuity_contract(workspace, project)
        if current is not None and current != source:
            raise StoryCanonError("signed production contract is immutable once approved")
        validate_contract(source, bible)
        return {"kind":"immutable_100_chapter_production_contract",
                "source_digest":source["digest"],"human_commit_required":True}
    if path == "game/story_bible.json":
        validate_story_bible(source)
        if source["project"] != project:
            raise StoryCanonError("cannot retarget another game's story canon")
        current, scenes, _ = load_story_workspace(workspace, project)
        if load_continuity_contract(workspace, project) is not None and current != source:
            raise StoryCanonError("approved cast voices, faces and region style are locked")
        if current is None and source["phase"] != "foundation":
            raise StoryCanonError("first reviewed story source must be the foundation")
        if current is not None:
            old = PHASES.index(current["phase"])
            new = PHASES.index(source["phase"])
            if new < old or new > old + 1:
                raise StoryCanonError("story -> cast -> design must advance one phase at a time")
            if scenes and current != source:
                raise StoryCanonError(
                    "changing production canon needs a separately reviewed migration "
                    "of every affected scene, not an invisible rewrite")
        return {"kind": "story_bible", "phase": source["phase"],
                "source_digest": source["digest"], "human_commit_required": True}
    if not path.startswith(("story/scenes/","story/chapters/")):
        raise StoryCanonError("story validation was invoked for an unrelated source")
    if scene_path(source) != path:
        raise StoryCanonError("scene act/scene filename differs from source identity")
    bible, scenes, index = load_story_workspace(workspace, project)
    if bible is None:
        raise StoryCanonError("story foundation, cast and design must be approved first")
    if any((s.get("chapter"),s["act"],s["scene"]) ==
           (source.get("chapter"),source["act"],source["scene"])
           for s in scenes):
        raise StoryCanonError("approved story is append-only; no silent scene overwrite")
    contract = load_continuity_contract(workspace, project)
    if contract is not None:
        from .story_continuity_assurance import verify_production_history
        verify_production_history(bible, contract, [*scenes, source])
    return {"kind": "story_scene",
            **verify_story_scene(bible, scenes, source),
            "human_commit_required": True}


def next_story_scene_template(workspace, project, act, scene, chapter=None):
    bible, history, index = load_story_workspace(workspace, project)
    if bible is None or bible["phase"] != "design":
        raise StoryCanonError("approve story, cast and design before scene creation")
    contract = load_continuity_contract(workspace, project)
    if contract is not None:
        from .story_continuity_assurance import SCENE_TARGET
        from .story_chapter_context import chapter_of_act, storytelling_template
        expected_chapter = chapter_of_act(act)
        if chapter is not None and chapter != expected_chapter:
            raise StoryCanonError("act belongs to a different canonical chapter")
        chapter = expected_chapter
        if len(history) >= SCENE_TARGET:
            raise StoryCanonError("all 9999 staged scenes are already completed")
        if type(act) is not int or type(scene) is not int or not 1 <= scene <= 9999:
            raise StoryCanonError("strict scene numbering requires 1..9999")
        if not history:
            if (act,scene) != (1,1):
                raise StoryCanonError("Jeeves must begin at act one, scene one")
        else:
            prior = history[-1]
            if not ((act == prior["act"] and scene == prior["scene"]+1) or
                    (act == prior["act"]+1 and scene == 1)):
                raise StoryCanonError(
                    "only the exact next scene in the current or next act is allowed")
    source = story_scene_template(bible, sequence=len(history)+1,
                                  chapter=chapter,act=act,scene=scene)
    if contract is not None:
        form=("prologue" if not history or
              chapter != history[-1]["chapter"] else "main")
        narrative=storytelling_template(chapter,form=form)
        if history:
            narrative["tension_before"]=history[-1]["storytelling"]["tension_after"]
            narrative["tension_after"]=narrative["tension_before"]
            if chapter==history[-1]["chapter"]:
                narrative["chapter_title"]=history[-1]["storytelling"]["chapter_title"]
        source["storytelling"]=narrative
    source["prior_digest"] = index["head_digest"]
    return {"path": scene_path(source), "document": source,
            "previous_history_digest": index["digest"],
            "continuity_contract_required_before_human_commit":
                contract is not None,
            "next_global_sequence": len(history)+1,
            "required_scene_target": 9999,
            "planned_chapters":100, "planned_acts":1000,
            "chapter":chapter,
            "requires_external_Jeeves_content_generation": True,
            "write_authorized": False}


def story_workspace_brief(workspace, project, *, cast, region, prompt,
                          max_bookmarks=48):
    bible, history, _ = load_story_workspace(workspace, project)
    if bible is None or bible["phase"] != "design":
        raise StoryCanonError("Jeeves needs approved story, cast and world design")
    brief = jeeves_story_brief(bible, history, cast=cast, region=region,
                               request=prompt, max_bookmarks=max_bookmarks)
    contract = load_continuity_contract(workspace,project)
    if contract is not None:
        from .story_chapter_context import chapter_context
        current = chapter_context(bible,contract,history)
        brief["active_chapter_context"] = current
        brief["chapter_context_receipt"] = current["digest"]
        brief["no_cross_chapter_memory_fabrication"] = True
    return brief


def story_workspace_status(workspace, project):
    bible, scenes, index = load_story_workspace(workspace, project)
    return {"schema": "skeleton.game_builder.story_production_status.v1",
            "project": project, "phase": bible["phase"] if bible else "unstarted",
            "source_digest": bible["digest"] if bible else None,
            "scenes_verified": len(scenes),
            "head_digest": index["head_digest"] if index else None,
            "historical_index_digest": index["digest"] if index else None,
            "human_approved_sources_only": True,
            "automated_game_assets_generated": False,
            "live_Jeeves_model_connected": False,
            "model_weights_modified": False,
            "required_production_scenes": 9999,
            "maximum_story_chapters": 100,
            "maximum_story_acts": 1000,
            "active_chapter": (scenes[-1].get("chapter",1) if scenes else 1),
            "scene_by_scene_confirmation_enabled":
                load_continuity_contract(workspace, project) is not None,
            "actual_audio_voice_consistency_verified": False,
            "actual_rendered_face_consistency_verified": False}
