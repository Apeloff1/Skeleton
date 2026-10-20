"""Real, owner-supplied Jeeves Studio handlers for executable expeditions.

Host controls project mapping, SQLite session authority and filesystem root.
This module does not register tools or grant itself privileges; existing
ToolRegistry plus exact-command authorizer must approve each invocation.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any
import re

from .game_frontier_expedition import (
    ExpeditionAction, ExpeditionEpisode, ExpeditionError, ExpeditionWorld,
    Traveler, find_route, verify_route,
)
from .game_frontier_expedition_qa import run_expedition_qa
from .game_frontier_expedition_godot import (
    emit_expedition_godot_project, verify_expedition_godot_project,
)
from .game_frontier_expedition_release import evaluate_expedition_release
from .game_frontier_expedition_save_store import ExpeditionSaveStore
from .game_studio_tools import StudioCommand

OPERATIONS=(
    "expedition.inspect","expedition.preview","expedition.qa",
    "expedition.release.inspect","expedition.start","expedition.action",
    "expedition.export",
)
_RUN_ID=re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,95}$")
_EXPORT_ID=re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,79}$")


def expedition_studio_handlers(
    projects: Mapping[str,tuple[ExpeditionWorld,Traveler]],
    *, save_store: ExpeditionSaveStore, export_root: Path,
) -> Mapping[str,Callable[[StudioCommand,Any],dict]]:
    """Build seven actual host-backed operations for existing Studio registry."""
    if not isinstance(projects,Mapping) or not projects:
        raise ExpeditionError("host must expose explicit existing original projects")
    for key,typed in projects.items():
        if (type(key) is not str or not isinstance(typed,tuple)
                or len(typed)!=2 or
                not isinstance(typed[0],ExpeditionWorld) or
                not isinstance(typed[1],Traveler)
                or typed[0].project_id!=key):
            raise ExpeditionError("project mapping must bind exact game/player source")
    if not isinstance(save_store,ExpeditionSaveStore):
        raise ExpeditionError("Studio actions require explicit durable game save owner")
    if not isinstance(export_root,Path) or not export_root.is_dir():
        raise ExpeditionError("Studio needs an existing host-controlled export root")
    source=dict(projects)
    root=export_root.resolve(strict=True)

    def owner(command:StudioCommand):
        if not isinstance(command,StudioCommand):
            raise ExpeditionError("typed authorized studio command required")
        if command.project_id not in source:
            raise ExpeditionError("unknown or unowned original game")
        return source[command.project_id]

    def inspect(command,context):
        world,traveler=owner(command)
        raw=command.payload
        run=raw.get("run_id")
        progress=None
        if run is not None:
            if type(run) is not str or not _RUN_ID.fullmatch(run):
                raise ExpeditionError("invalid durable game session identity")
            checkpoint=save_store.load(run,world,traveler)
            if checkpoint is not None:
                progress={
                    "generation":checkpoint.generation,
                    "state":checkpoint.episode.state(),
                    "receipt":checkpoint.receipt,
                }
        return {
            "schema":"skeleton.game.studio_expedition_inspect.v1",
            "project":world.project_id,"world_digest":world.digest,
            "waypoints":len(world.waypoints),"routes":len(world.by_edge),
            "destinations":list(world.destinations),
            "session":progress,"native_run_claimed":False,
        }

    def preview(command,context):
        world,traveler=owner(command)
        target=command.payload.get("destination",world.destinations[0])
        route=find_route(world,traveler,target)
        proof=verify_route(world,traveler,route)
        return {
            "schema":"skeleton.game.studio_expedition_preview.v1",
            "world_digest":world.digest,"route":list(route.edge_ids),
            "route_digest":route.digest,"won":proof["final_state"]["won"],
            "simulated_receipt":proof["receipt_head"],
            "native_run_claimed":False,
        }

    def qa(command,context):
        world,_=owner(command)
        seeds=command.payload.get("seeds",[11,42])
        if type(seeds) is not list or len(seeds)>8:
            raise ExpeditionError("authorized QA seed list must be finite")
        report=run_expedition_qa(
            world.project_id,world.source_digest,
            seeds=seeds,islands=command.payload.get("islands",9),
            alternatives=command.payload.get("alternatives",2),
        )
        return {
            "schema":"skeleton.game.studio_expedition_qa.v1",
            "source_digest":world.source_digest,"receipt":report["receipt_digest"],
            "scenarios_executed":report["cases_executed"],
            "routes_executed":report["executed_game_routes"],
            "blocked_cases":report["blocked_cases"],
            "native_runs":0,
        }

    def release_inspect(command,context):
        world,traveler=owner(command)
        from .game_frontier_expedition_qa import run_expedition_qa
        report=run_expedition_qa(
            world.project_id,world.source_digest,
            seeds=(11,),islands=6,alternatives=2)
        files=emit_expedition_godot_project(world,traveler)
        result=evaluate_expedition_release(world,traveler,files,report)
        return {
            "schema":result["schema"],"source_digest":result["source_digest"],
            "status":result["status"],"axes":result["axes"],
            "blocked_axes":result["blocked_axes"],
            "receipt":result["receipt_digest"],
            "production_release_approved":False,
        }

    def run_key(command):
        value=command.payload.get("run_id")
        if type(value) is not str or not _RUN_ID.fullmatch(value):
            raise ExpeditionError("session command must bind exact run identity")
        # Prefix the canonical source identity: another project never shares
        # the same persisted run even when an agent reuses an arbitrary name.
        return command.project_id+":"+value

    def start(command,context):
        world,traveler=owner(command)
        key=run_key(command)
        if save_store.load(key,world,traveler) is not None:
            raise ExpeditionError("durable session already exists")
        stored=save_store.save(key,ExpeditionEpisode(world,traveler))
        return {
            "schema":"skeleton.game.studio_expedition_session.v1",
            "run_id":key,"generation":stored.generation,
            "state":stored.episode.state(),"receipt":stored.receipt,
        }

    def action(command,context):
        world,traveler=owner(command)
        key=run_key(command)
        saved=save_store.load(key,world,traveler)
        if saved is None:
            raise ExpeditionError("cannot act before durable session creation")
        current=command.payload.get("expected_generation")
        if type(current) is not int or current!=saved.generation:
            raise ExpeditionError("game action requires current checkpoint generation")
        name=command.payload.get("kind")
        edge=command.payload.get("edge_id","")
        episode=saved.episode
        result=episode.step(ExpeditionAction(name,edge))
        stored=save_store.save(
            key,episode,expected_generation=saved.generation)
        return {
            "schema":"skeleton.game.studio_expedition_action.v1",
            "run_id":key,"generation":stored.generation,
            "state":result["state"],"events":list(result["events"]),
            "receipt":stored.receipt,"gameplay_receipt":result["receipt"],
        }

    def export(command,context):
        world,traveler=owner(command)
        leaf=command.payload.get("folder")
        if type(leaf) is not str or not _EXPORT_ID.fullmatch(leaf):
            raise ExpeditionError("export requires safe original project folder name")
        from scripts.build_original_expedition import export_new_game
        files=emit_expedition_godot_project(
            world,traveler,include_autoplay=True)
        proof=verify_expedition_godot_project(
            files,world,traveler,include_autoplay=True)
        destination=root/leaf
        # A model may only name a new direct child of this host-supplied root.
        if destination.parent.resolve()!=root:
            raise ExpeditionError("unapproved game export path")
        export_new_game(destination,files)
        return {
            "schema":"skeleton.game.studio_expedition_export.v1",
            "world_digest":world.digest,"folder":leaf,
            "file_count":len(files),"receipt":proof["receipt_digest"],
            "requires_real_native_playthrough":True,
        }

    return {
        "expedition.inspect":inspect,
        "expedition.preview":preview,
        "expedition.qa":qa,
        "expedition.release.inspect":release_inspect,
        "expedition.start":start,
        "expedition.action":action,
        "expedition.export":export,
    }
