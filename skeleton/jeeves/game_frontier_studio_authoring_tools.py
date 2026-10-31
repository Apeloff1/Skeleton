"""Real host-authorized 50-command Forge Studio editing and Godot game delivery.

No hidden persistence owner. Existing host loaders and CAS commit callback
own game projects, exact-command ToolRegistry authorization owns privileges,
and the canonical original expedition compiler owns native Godot emission.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
import re
from typing import Any

from skeleton.forge.game_frontier_studio import (
    StudioError, StudioProject, compile_studio_expedition,
)
from skeleton.forge.game_frontier_studio_authoring import (
    apply_authoring_batch, authored_summary, authored_tile_region,
    project_digest, snapshot,
)
from .game_studio_tools import StudioCommand

_SAFE_DIRECTORY = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,79}$")


def studio_authoring_handlers(
    projects: Mapping[str, Callable[[], tuple[int, StudioProject]]], *,
    commit_project: Callable[[str, int, str, StudioProject], bool] | None = None,
    game_profiles: Mapping[str, object] | None = None,
    export_root: Path | None = None,
) -> dict[str, Callable[[StudioCommand, Any], dict]]:
    """Host-controlled production Studio operations over 50 real editing actions.

    commit_project MUST be an atomically versioned CAS writer controlled by the
    host, not a model-supplied callback. Each write is re-read and hash verified.
    """
    if (not isinstance(projects, Mapping) or not projects or
            any(type(key) is not str or not key or len(key) > 128 or
                not callable(reader) for key, reader in projects.items())):
        raise StudioError("Studio requires nonempty exact authorized project loaders")
    if commit_project is not None and not callable(commit_project):
        raise StudioError("host CAS writer must be a callable")
    if game_profiles is not None and (not isinstance(game_profiles, Mapping) or
            any(key not in projects for key in game_profiles)):
        raise StudioError("game compilation profiles must belong to authorized projects")
    if export_root is not None and (not isinstance(export_root, Path)
                                   or not export_root.is_dir()):
        raise StudioError("game export requires existing host-controlled directory")
    if export_root is not None and not game_profiles:
        raise StudioError("native game export requires host-provided game profiles")
    project_loaders = dict(projects)
    profiles = dict(game_profiles or {})
    root = export_root.resolve(strict=True) if export_root is not None else None

    def current(command: StudioCommand) -> tuple[int, StudioProject, str]:
        if not isinstance(command, StudioCommand) or command.project_id not in project_loaders:
            raise StudioError("unowned Studio project")
        value = project_loaders[command.project_id]()
        if type(value) is not tuple or len(value) != 2:
            raise StudioError("host must return version and current typed project")
        revision, project = value
        if (type(revision) is not int or revision < 0 or
                not isinstance(project, StudioProject) or
                project.project_id != command.project_id):
            raise StudioError("host source identity or revision invalid")
        return revision, project, project_digest(project)

    def expected(command: StudioCommand, revision: int, digest: str) -> None:
        if (type(command.payload.get("expected_revision")) is not int or
                command.payload.get("expected_revision") != revision or
                command.payload.get("expected_sha256") != digest):
            raise StudioError("stale source, digest or generation; refresh before editing")

    def inspect(command: StudioCommand, _: Any) -> dict:
        if command.payload:
            raise StudioError("inspect accepts no arbitrary source overrides")
        revision, project, digest = current(command)
        return {"generation": revision, **authored_summary(project)}

    def copy_tiles(command: StudioCommand, _: Any) -> dict:
        if set(command.payload) != {"layer", "x", "y", "width", "height"}:
            raise StudioError("exact viewport tile region required")
        _, project, _ = current(command)
        return authored_tile_region(project, command.payload["layer"],
                                    x=command.payload["x"], y=command.payload["y"],
                                    width=command.payload["width"],
                                    height=command.payload["height"])

    def proposed(command: StudioCommand, *, persist: bool) -> dict:
        if set(command.payload) != {"expected_revision", "expected_sha256", "steps"}:
            raise StudioError("source-bound authoring requires revision, digest and steps")
        revision, project, digest = current(command)
        expected(command, revision, digest)
        result = apply_authoring_batch(project, command.payload["steps"])
        changed = result["project"]
        evidence = result["receipt"]
        if not persist:
            return {"schema": "skeleton.game.studio_author_preview.v1",
                    **evidence, "persisted": False,
                    "summary": authored_summary(changed)}
        if commit_project is None:
            raise StudioError("host has not authorized a persistent Studio writer")
        if not evidence["actually_changed"]:
            raise StudioError("unchanged edits cannot advance project generation")
        if commit_project(command.project_id, revision, digest, changed) is not True:
            raise StudioError("host rejected or concurrently replaced this edit")
        latest_revision, latest, latest_digest = current(command)
        if (latest_revision <= revision or latest_digest != project_digest(changed)):
            raise StudioError("host did not commit the expected original Studio source")
        return {"schema": "skeleton.game.studio_author_commit.v1",
                "project_id": command.project_id, "generation": latest_revision,
                "previous_sha256": digest, "source_sha256": latest_digest,
                "action_count": evidence["action_count"],
                "receipt_sha256": evidence["receipt_sha256"],
                "persisted": True,
                "summary": authored_summary(latest)}

    def preview(command: StudioCommand, _: Any) -> dict:
        return proposed(command, persist=False)

    def edit(command: StudioCommand, _: Any) -> dict:
        return proposed(command, persist=True)

    def compile_project(command: StudioCommand, _: Any) -> dict:
        if command.payload:
            raise StudioError("compile reads only authorized current project")
        revision, project, digest = current(command)
        manifest = snapshot(project)
        return {"schema": "skeleton.game.studio_author_compile.v1",
                "generation": revision, "project_id": project.project_id,
                "content_sha256": digest,
                "map_layer_count": len(manifest["layers"]),
                "prefab_count": len(manifest["prefabs"]),
                "placed_actor_count": len(manifest["placements"]),
                "event_count": len(manifest["events"]),
                "native_quest_count": len(manifest["native_quests"]),
                "compiled": True, "native_executed": False}

    def compiled_game(command: StudioCommand, *, write: bool) -> dict:
        if command.project_id not in profiles:
            raise StudioError("host has no approved game-production profile")
        if write:
            if root is None or set(command.payload) != {"folder"}:
                raise StudioError("export requires a host-owned location and safe folder")
            leaf = command.payload["folder"]
            if type(leaf) is not str or _SAFE_DIRECTORY.fullmatch(leaf) is None:
                raise StudioError("game output folder is not a safe direct child")
        elif command.payload:
            raise StudioError("playable compilation uses only trusted source and profile")
        revision, project, digest = current(command)
        built = compile_studio_expedition(
            project, profiles[command.project_id], playtest_routes=4,
            include_godot=write,
        )
        if write:
            from scripts.build_original_expedition import export_new_game
            destination = root / leaf
            if destination.parent.resolve() != root:
                raise StudioError("export folder escaped authorized host root")
            files = built["godot_project_files"]
            # The existing exporter atomically refuses existing output paths.
            export_new_game(destination, files)
        return {
            "schema": "skeleton.game.studio_author_game.v1",
            "project_id": project.project_id, "generation": revision,
            "source_sha256": digest,
            "world_digest": built["world_digest"],
            "waypoint_count": built["waypoints"],
            "travel_edge_count": built["travel_edges"],
            "playtest": built["playtest"],
            "receipt_digest": built["receipt_digest"],
            "exported": write,
            "folder": leaf if write else None,
            "native_executed": False,
            "production_released": False,
        }

    def game(command: StudioCommand, _: Any) -> dict:
        return compiled_game(command, write=False)

    def export(command: StudioCommand, _: Any) -> dict:
        return compiled_game(command, write=True)

    result = {
        "game.studio.author.inspect": inspect,
        "game.studio.author.copy": copy_tiles,
        "game.studio.author.preview": preview,
        "game.studio.author.compile": compile_project,
        **({"game.studio.author.game": game} if profiles else {}),
        **({"game.studio.author.edit": edit} if commit_project else {}),
        **({"game.studio.author.export": export}
           if root is not None and profiles else {}),
    }
    return result
