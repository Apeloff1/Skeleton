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


def load_story_workspace(workspace, project):
    """Read all committed story sources without executing generated content."""
    if project != workspace.active():
        raise StoryCanonError("Jeeves may only author the active current project")
    files = workspace.files("current", project)
    paths = sorted(f.path for f in files if f.path.startswith("story/scenes/"))
    if len(paths) > MAX_SCENES:
        raise StoryCanonError("full historical scene limit exceeded")
    for path in paths:
        # All nonconforming paths under reserved story area fail closed;
        # no silent omissions, wildcard matches or approximate memory.
        import re
        if not re.fullmatch(r"story/scenes/act_[0-9]{4}/scene_[0-9]{6}\.json", path):
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
    return bible, scenes, index


def validate_story_workspace_source(workspace, project, path, source):
    """Required at BOTH proposed-source and human commit boundaries."""
    if path == "game/story_bible.json":
        validate_story_bible(source)
        if source["project"] != project:
            raise StoryCanonError("cannot retarget another game's story canon")
        current, scenes, _ = load_story_workspace(workspace, project)
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
    if not path.startswith("story/scenes/"):
        raise StoryCanonError("story validation was invoked for an unrelated source")
    if scene_path(source) != path:
        raise StoryCanonError("scene act/scene filename differs from source identity")
    bible, scenes, index = load_story_workspace(workspace, project)
    if bible is None:
        raise StoryCanonError("story foundation, cast and design must be approved first")
    if any(s["act"] == source["act"] and s["scene"] == source["scene"]
           for s in scenes):
        raise StoryCanonError("approved story is append-only; no silent scene overwrite")
    return {"kind": "story_scene",
            **verify_story_scene(bible, scenes, source),
            "human_commit_required": True}


def next_story_scene_template(workspace, project, act, scene):
    bible, history, index = load_story_workspace(workspace, project)
    if bible is None or bible["phase"] != "design":
        raise StoryCanonError("approve story, cast and design before scene creation")
    source = story_scene_template(bible, sequence=len(history)+1,
                                  act=act, scene=scene)
    source["prior_digest"] = index["head_digest"]
    return {"path": scene_path(source), "document": source,
            "previous_history_digest": index["digest"],
            "requires_external_Jeeves_content_generation": True,
            "write_authorized": False}


def story_workspace_brief(workspace, project, *, cast, region, prompt,
                          max_bookmarks=48):
    bible, history, _ = load_story_workspace(workspace, project)
    if bible is None or bible["phase"] != "design":
        raise StoryCanonError("Jeeves needs approved story, cast and world design")
    return jeeves_story_brief(bible, history, cast=cast, region=region,
                              request=prompt, max_bookmarks=max_bookmarks)


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
            "model_weights_modified": False}
