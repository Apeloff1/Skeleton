"""Offline deterministic system-editor command line, no implicit writes.

Examples:
  python -m skeleton.ai.game_builder.system_editor_cli list
  python -m skeleton.ai.game_builder.system_editor_cli template --editor racing
  python -m skeleton.ai.game_builder.system_editor_cli preview --editor platformer
  python -m skeleton.ai.game_builder.system_editor_cli assembly --root WORKSPACE --project my_game
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .system_editors import (
    catalog, editor_source, preview_editor, validate_editor_document,
    make_editor_document,
    SystemEditorError,
)
from .system_editor_assembly import assemble_workspace_systems
from .advanced_gameplay_runtime import run_advanced_session, verify_advanced_session
from .advanced_level_scenes import make_advanced_scene,validate_advanced_scene
from .advanced_puzzle_solver import solve_advanced_puzzle
from .advanced_fighting_rollback import (run_peer_fight,verify_peer_fight,
    reconcile_peer_prediction,verify_peer_reconciliation)
from .advanced_rhythm_longrun import (run_long_rhythm,verify_long_rhythm,continue_long_rhythm)
from .advanced_rhythm_runtime import default_layout as original_rhythm_chart
from .advanced_rhythm_audio import render_original_beat_wav,original_audio_receipt
from .advanced_roguelike_longrun import (replay_long_roguelike,
    verify_long_roguelike,continue_long_roguelike)
from .advanced_world_planner import plan_original_world
from .advanced_stealth_planner import plan_stealth_route
from .advanced_parkour_planner import plan_parkour_route, verify_parkour_plan
from .advanced_sports_coach import plan_original_sports_match, verify_original_sports_plan
from .advanced_maze_planner import plan_original_maze, verify_original_maze_plan
from .advanced_rpg_planner import plan_original_rpg_chapter, verify_original_rpg_plan
from .advanced_npc_society_planner import (
    plan_original_civic_milestone, verify_original_civic_plan,
)
from .advanced_chunked_npc_world import (
    run_chunked_npc_world, verify_chunked_npc_world,
)
from .advanced_unified_npc_world import (
    run_unified_npc_world, verify_unified_npc_world,
)
from .advanced_social_quest_fusion import (
    run_social_quest_fusion, verify_social_quest_fusion,
)
from .advanced_economy_mirror import (
    analyze_original_economy, verify_original_economy_mirror,
)
from .advanced_economy_planner import (
    plan_original_trade, verify_original_trade_plan,
)
from .advanced_ecosystem_planner import (
    plan_original_ecology, verify_original_ecology_plan,
)
from .advanced_procedural_world_planner import (
    plan_original_frontier, verify_original_frontier_plan,
)
from .advanced_godot_export import (
    render_advanced_godot_package, write_advanced_godot_package,
)
from .advanced_platformer_godot import render_platformer_godot_package
from .advanced_deck_godot import render_deck_godot_package
from .advanced_shooter_godot import render_shooter_godot_package
from .advanced_tactics_godot import render_tactics_godot_package
from .advanced_defense_godot import render_defense_godot_package
from .advanced_racing_godot import render_racing_godot_package
from .advanced_survival_godot import render_survival_godot_package
from .advanced_farming_godot import render_farming_godot_package
from .advanced_factory_godot import render_factory_godot_package
from .advanced_colony_godot import render_colony_godot_package
from .advanced_economy_godot import render_economy_godot_package
from .advanced_dialogue_godot import render_dialogue_godot_package
from .advanced_gameplay_save import (
    export_advanced_savegame, import_advanced_savegame, continue_advanced_savegame,
)
from .game_project_workspace import GameWorkspace, WorkspaceError


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        prog="python -m skeleton.ai.game_builder.system_editor_cli",
        description="Typed, offline, bounded original game mechanics authoring")
    commands = result.add_subparsers(dest="operation", required=True)
    commands.add_parser("list", help="Enumerate real system editor capabilities")
    for name in ("template", "validate", "preview", "play"):
        p = commands.add_parser(name)
        p.add_argument("--editor", required=name != "validate")
        p.add_argument("--settings", help="Path to a local UTF-8 JSON settings object")
        if name == "validate":
            p.add_argument("--document", required=True)
        if name in ("preview", "play"):
            p.add_argument("--actions", help="Path to a bounded JSON action array")
        if name == "play":
            p.add_argument("--seed", type=int, default=0)
            p.add_argument("--scene", help="Reviewed original scene JSON document")
    scene = commands.add_parser("scene-template", help="Generate a typed advanced original scene")
    scene.add_argument("--editor",required=True)
    scene.add_argument("--seed",type=int,default=0)
    scene.add_argument("--scene-id",default="scene_01")
    scene.add_argument("--settings")
    scene.add_argument("--layout",help="Optional JSON authored geometry and resource map")
    solve=commands.add_parser("solve-puzzle",help="Bounded original puzzle reachability proof")
    solve.add_argument("--scene",required=True)
    solve.add_argument("--settings")
    solve.add_argument("--max-states",type=int,default=12000)
    solve.add_argument("--max-depth",type=int,default=96)
    stealth_plan=commands.add_parser("plan-stealth",
        help="Bounded AI-route rehearsal for actual authored infiltration")
    stealth_plan.add_argument("--scene",required=True)
    stealth_plan.add_argument("--settings")
    stealth_plan.add_argument("--max-states",type=int,default=30000)
    stealth_plan.add_argument("--max-depth",type=int,default=96)
    parkour_plan=commands.add_parser("plan-parkour",
        help="Search actual original traversal and independently prove any completed route")
    parkour_plan.add_argument("--scene",required=True)
    parkour_plan.add_argument("--settings")
    parkour_plan.add_argument("--max-states",type=int,default=20000)
    parkour_plan.add_argument("--max-depth",type=int,default=96)
    parkour_plan.add_argument("--beam-width",type=int,default=64)
    parkour_verify=commands.add_parser("verify-parkour-plan",
        help="Re-search a source-verified original course and verify an exact planner receipt")
    parkour_verify.add_argument("--record",required=True)
    parkour_verify.add_argument("--scene",required=True)
    parkour_verify.add_argument("--settings")
    sports_plan=commands.add_parser("plan-sports",
        help="Search source-bound original matches and independently prove a real win")
    sports_plan.add_argument("--scene",required=True)
    sports_plan.add_argument("--settings")
    sports_plan.add_argument("--max-states",type=int,default=16000)
    sports_plan.add_argument("--max-depth",type=int,default=64)
    sports_plan.add_argument("--beam-width",type=int,default=48)
    sports_verify=commands.add_parser("verify-sports-plan",
        help="Re-search and independently verify exact sporting strategy evidence")
    sports_verify.add_argument("--record",required=True)
    sports_verify.add_argument("--scene",required=True)
    sports_verify.add_argument("--settings")
    maze_plan=commands.add_parser("plan-maze",
        help="Search original shifting labyrinths and prove any actual earned keyed exit")
    maze_plan.add_argument("--scene",required=True)
    maze_plan.add_argument("--settings")
    maze_plan.add_argument("--max-states",type=int,default=12000)
    maze_plan.add_argument("--max-depth",type=int,default=96)
    maze_plan.add_argument("--beam-width",type=int,default=96)
    maze_verify=commands.add_parser("verify-maze-plan",
        help="Replay the exact authored maze and independently verify route search")
    maze_verify.add_argument("--record",required=True)
    maze_verify.add_argument("--scene",required=True)
    maze_verify.add_argument("--settings")
    rpg_director=commands.add_parser("plan-rpg",
        help="Plan original quest choices and replay-verify a witnessed story")
    rpg_director.add_argument("--scene",required=True)
    rpg_director.add_argument("--settings")
    rpg_director.add_argument("--max-nodes",type=int,default=8000)
    rpg_director.add_argument("--max-actions",type=int,default=128)
    rpg_director.add_argument("--social-choice",default="choose:trust",
        choices=["choose:trust","choose:challenge","choose:trade"])
    rpg_check=commands.add_parser("verify-rpg-plan",
        help="Reconstruct a complete real RPG chapter and verify witness receipts")
    rpg_check.add_argument("--record",required=True)
    rpg_check.add_argument("--scene",required=True)
    rpg_check.add_argument("--settings")
    frontier=commands.add_parser("plan-frontier",
        help="Prove an original frontier landmark expedition without inventing a game ending")
    frontier.add_argument("--scene",required=True)
    frontier.add_argument("--settings")
    frontier.add_argument("--max-actions",type=int,default=100)
    frontier.add_argument("--retire",action="store_true")
    frontier_check=commands.add_parser("verify-frontier-plan",
        help="Independently replay the original chunked frontier milestone")
    frontier_check.add_argument("--record",required=True)
    frontier_check.add_argument("--scene",required=True)
    frontier_check.add_argument("--settings")
    civic=commands.add_parser("plan-civic",
        help="Prove original NPC town witness resolution with finite player actions")
    civic.add_argument("--scene",required=True)
    civic.add_argument("--settings")
    civic.add_argument("--max-actions",type=int,default=100)
    civic.add_argument("--retire",action="store_true")
    civic_verify=commands.add_parser("verify-civic-plan",
        help="Re-run NPC social witnesses and verify exact source-bound evidence")
    civic_verify.add_argument("--record",required=True)
    civic_verify.add_argument("--scene",required=True)
    civic_verify.add_argument("--settings")
    ecology=commands.add_parser("plan-ecology",
        help="Prove a living ecosystem conservation checkpoint through real play")
    ecology.add_argument("--scene",required=True)
    ecology.add_argument("--settings")
    ecology.add_argument("--max-actions",type=int,default=100)
    ecology.add_argument("--retire",action="store_true")
    ecology_verify=commands.add_parser("verify-ecology-plan",
        help="Independently replay and re-evaluate a funded conservation plan")
    ecology_verify.add_argument("--record",required=True)
    ecology_verify.add_argument("--scene",required=True)
    ecology_verify.add_argument("--settings")
    streamed=commands.add_parser("chunked-npc-world",
        help="Play bounded original 21x21/35x35 resident world with recorded active simulation LOD")
    streamed.add_argument("--actions",required=True)
    streamed.add_argument("--settings")
    streamed.add_argument("--scenes")
    streamed.add_argument("--options",help="Registered bounded chunk dimensions and LOD budgets")
    streamed.add_argument("--seed",type=int,default=0)
    streamed_verify=commands.add_parser("verify-chunked-npc-world",
        help="Independently reproduce every active/deferred actor and world-state receipt")
    streamed_verify.add_argument("--record",required=True)
    unified=commands.add_parser("unified-npc-world",
        help="Run one physically authoritative original NPC dialogue/quest world")
    unified.add_argument("--actions",required=True)
    unified.add_argument("--settings",help="Original per-family typed rules")
    unified.add_argument("--scenes",help="Reviewed source scenes")
    unified.add_argument("--seed",type=int,default=0)
    unified_verify=commands.add_parser("verify-unified-npc-world",
        help="Replay exact source, time, physical NPC positions and causal world events")
    unified_verify.add_argument("--record",required=True)
    social=commands.add_parser("social-quest-fusion",
        help="Run real multi-engine Dialogue/NPC/Quest commands with bounded physical evidence")
    social.add_argument("--commands",required=True)
    social.add_argument("--settings",help="Per-engine typed JSON rules")
    social.add_argument("--scenes",help="Three reviewed source scene documents")
    social.add_argument("--seed",type=int,default=0)
    social_check=commands.add_parser("verify-social-quest-fusion",
        help="Re-execute all three source engines and verify original witness links")
    social_check.add_argument("--record",required=True)
    economic_mirror=commands.add_parser("economy-mirror",
        help="Compare bounded real market scenarios with independently replayed economic outcomes")
    economic_mirror.add_argument("--scene",required=True)
    economic_mirror.add_argument("--settings")
    economic_mirror.add_argument("--horizon",type=int,default=12)
    economic_mirror.add_argument("--max-scenarios",type=int,default=32)
    economic_check=commands.add_parser("verify-economy-mirror",
        help="Independently rerun economic strategy alternatives and source-evidence custody")
    economic_check.add_argument("--record",required=True)
    economic_check.add_argument("--scene",required=True)
    economic_check.add_argument("--settings")
    economy=commands.add_parser("plan-economy",
        help="Prove original market trading through genuine finite production and receipts")
    economy.add_argument("--scene",required=True)
    economy.add_argument("--settings")
    economy.add_argument("--max-actions",type=int,default=100)
    economy.add_argument("--retire",action="store_true")
    economy_check=commands.add_parser("verify-economy-plan",
        help="Independently replay finite-cash economic proof against the source")
    economy_check.add_argument("--record",required=True)
    economy_check.add_argument("--scene",required=True)
    economy_check.add_argument("--settings")
    world_plan=commands.add_parser("plan-original-world",
        help="Search and independently replay a safe original world ability path")
    world_plan.add_argument("--scene",required=True)
    world_plan.add_argument("--settings")
    world_plan.add_argument("--max-states",type=int,default=50000)
    world_plan.add_argument("--max-actions",type=int,default=128)
    marathon=commands.add_parser("roguelike-marathon",
        help="Execute thousands of original dungeon actions with independently verifiable checkpoints")
    marathon.add_argument("--actions",required=True)
    marathon.add_argument("--settings")
    marathon.add_argument("--scene")
    marathon.add_argument("--seed",type=int,default=0)
    marathon.add_argument("--checkpoint-interval",type=int,default=64)
    marathon_verify=commands.add_parser("roguelike-marathon-verify",
        help="Recompute longrun from original seed, authored scene and entire command log")
    marathon_verify.add_argument("--record",required=True)
    marathon_verify.add_argument("--settings")
    marathon_more=commands.add_parser("roguelike-marathon-continue",
        help="Resume a full-replay-verified original longrun ledger")
    marathon_more.add_argument("--record",required=True)
    marathon_more.add_argument("--actions",required=True)
    marathon_more.add_argument("--settings")
    versus=commands.add_parser("fighting-peer-replay",
        help="Replay original fully signed two-player arena inputs without trusting client state")
    versus.add_argument("--blue-actions",required=True)
    versus.add_argument("--red-actions",required=True)
    versus.add_argument("--settings")
    versus.add_argument("--scene")
    versus.add_argument("--seed",type=int,default=0)
    versus_check=commands.add_parser("fighting-peer-verify",
        help="Rebuild two real peers' deterministic arena inputs from original source")
    versus_check.add_argument("--record",required=True)
    versus_check.add_argument("--settings")
    rollback=commands.add_parser("fighting-rollback",
        help="Safely reconcile a late peer input prediction within authored frame budget")
    rollback.add_argument("--blue-actions",required=True)
    rollback.add_argument("--predicted-red",required=True)
    rollback.add_argument("--authoritative-red",required=True)
    rollback.add_argument("--settings")
    rollback.add_argument("--scene")
    rollback.add_argument("--seed",type=int,default=0)
    rollback_check=commands.add_parser("fighting-rollback-verify",
        help="Recalculate the full authoritative match and correction digest")
    rollback_check.add_argument("--record",required=True)
    rollback_check.add_argument("--settings")
    full_song=commands.add_parser("rhythm-longrun",
        help="Run 256 authored beats with replay-certified chronological checkpoints")
    full_song.add_argument("--actions",required=True)
    full_song.add_argument("--settings")
    full_song.add_argument("--scene")
    full_song.add_argument("--seed",type=int,default=0)
    full_song.add_argument("--checkpoint-interval",type=int,default=64)
    song_verify=commands.add_parser("rhythm-longrun-verify",
        help="Independently reconstruct original song clock, judgements and score")
    song_verify.add_argument("--record",required=True)
    song_verify.add_argument("--settings")
    song_more=commands.add_parser("rhythm-longrun-continue",
        help="Rebuild signed original chart and append bounded timing input")
    song_more.add_argument("--record",required=True)
    song_more.add_argument("--actions",required=True)
    song_more.add_argument("--settings")
    rhythm_audio=commands.add_parser("rhythm-audio",
        help="Render fully original bounded local WAV from signed chart without borrowed samples")
    rhythm_audio.add_argument("--scene")
    rhythm_audio.add_argument("--settings")
    rhythm_audio.add_argument("--seed",type=int,default=0)
    rhythm_audio.add_argument("--from-ms",type=int,default=0)
    rhythm_audio.add_argument("--duration-ms",type=int,default=10000)
    rhythm_audio.add_argument("--output",required=True)
    rhythm_audio.add_argument("--trusted-local-operator",action="store_true")
    native=commands.add_parser("godot-export",help="Real offline native Godot 4 puzzle source, proof and export presets")
    native.add_argument("--session",required=True)
    native.add_argument("--settings")
    native.add_argument("--output",required=True,help="New local destination; existing paths never overwritten")
    native.add_argument("--trusted-local-operator",action="store_true")
    save = commands.add_parser("save",help="Save a verified advanced game receipt")
    save.add_argument("--session",required=True)
    save.add_argument("--settings")
    load = commands.add_parser("load-save",help="Verify and restore a portable game save")
    load.add_argument("--savegame",required=True)
    cont = commands.add_parser("continue-save",help="Continue a verified portable game")
    cont.add_argument("--savegame",required=True)
    cont.add_argument("--actions",required=True)
    verify = commands.add_parser("verify-play", help="Independently verify advanced action receipts")
    verify.add_argument("--session", required=True)
    verify.add_argument("--settings")
    assembly = commands.add_parser("assembly", help="Validate approved current-game systems")
    assembly.add_argument("--root", required=True)
    assembly.add_argument("--project", required=True)
    assembly.add_argument("--trusted-local-operator", action="store_true")
    return result


def _load(path: str):
    source = Path(path)
    if source.is_symlink() or not source.is_file() or source.stat().st_size > 200000:
        raise SystemEditorError("editor input must be a bounded regular local JSON file")
    def distinct(pairs):
        values = {}
        for k, v in pairs:
            if k in values:
                raise SystemEditorError("duplicate JSON member rejected")
            values[k] = v
        return values
    return json.loads(source.read_text(encoding="utf-8"),
                      object_pairs_hook=distinct,
                      parse_constant=lambda value: (_ for _ in ()).throw(
                          SystemEditorError("non-finite JSON number rejected")))


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.operation == "list":
            output = {"schema":"skeleton.game_builder.system_editor_catalog.v1",
                      "editors":catalog()}
        elif args.operation == "assembly":
            output = assemble_workspace_systems(
                GameWorkspace(args.root), args.project,
                authorized=args.trusted_local_operator)
        elif args.operation == "validate":
            output = validate_editor_document(_load(args.document))
        elif args.operation == "scene-template":
            output = make_advanced_scene(args.editor,
                _load(args.settings) if args.settings else None,
                seed=args.seed,scene_id=args.scene_id,
                layout=_load(args.layout) if args.layout else None)
        elif args.operation == "solve-puzzle":
            output = solve_advanced_puzzle(
                _load(args.scene),
                _load(args.settings) if args.settings else None,
                max_states=args.max_states,max_depth=args.max_depth)
        elif args.operation == "plan-stealth":
            output=plan_stealth_route(
                _load(args.scene),
                _load(args.settings) if args.settings else None,
                max_states=args.max_states,max_depth=args.max_depth)
        elif args.operation == "plan-parkour":
            output=plan_parkour_route(
                _load(args.scene),
                _load(args.settings) if args.settings else None,
                max_states=args.max_states,max_depth=args.max_depth,
                beam_width=args.beam_width)
        elif args.operation == "verify-parkour-plan":
            output={"verified":verify_parkour_plan(
                _load(args.record),_load(args.scene),
                _load(args.settings) if args.settings else None)}
        elif args.operation == "plan-sports":
            output=plan_original_sports_match(
                _load(args.scene),
                _load(args.settings) if args.settings else None,
                max_states=args.max_states,max_depth=args.max_depth,
                beam_width=args.beam_width)
        elif args.operation == "verify-sports-plan":
            output={"verified":verify_original_sports_plan(
                _load(args.record),_load(args.scene),
                _load(args.settings) if args.settings else None)}
        elif args.operation == "plan-maze":
            output=plan_original_maze(
                _load(args.scene),
                _load(args.settings) if args.settings else None,
                max_states=args.max_states,max_depth=args.max_depth,
                beam_width=args.beam_width)
        elif args.operation == "verify-maze-plan":
            output={"verified":verify_original_maze_plan(
                _load(args.record),_load(args.scene),
                _load(args.settings) if args.settings else None)}
        elif args.operation == "plan-rpg":
            output=plan_original_rpg_chapter(
                _load(args.scene),
                _load(args.settings) if args.settings else None,
                max_nodes=args.max_nodes,max_actions=args.max_actions,
                social_choice=args.social_choice)
        elif args.operation == "verify-rpg-plan":
            output={"verified":verify_original_rpg_plan(
                _load(args.record),_load(args.scene),
                _load(args.settings) if args.settings else None)}
        elif args.operation == "plan-frontier":
            output=plan_original_frontier(
                _load(args.scene),
                _load(args.settings) if args.settings else None,
                max_actions=args.max_actions,retire=args.retire)
        elif args.operation == "verify-frontier-plan":
            output={"verified":verify_original_frontier_plan(
                _load(args.record),_load(args.scene),
                _load(args.settings) if args.settings else None)}
        elif args.operation == "plan-civic":
            output=plan_original_civic_milestone(
                _load(args.scene),
                _load(args.settings) if args.settings else None,
                max_actions=args.max_actions,retire=args.retire)
        elif args.operation == "verify-civic-plan":
            output={"verified":verify_original_civic_plan(
                _load(args.record),_load(args.scene),
                _load(args.settings) if args.settings else None)}
        elif args.operation == "plan-ecology":
            output=plan_original_ecology(
                _load(args.scene),
                _load(args.settings) if args.settings else None,
                max_actions=args.max_actions,retire=args.retire)
        elif args.operation == "verify-ecology-plan":
            output={"verified":verify_original_ecology_plan(
                _load(args.record),_load(args.scene),
                _load(args.settings) if args.settings else None)}
        elif args.operation == "chunked-npc-world":
            output=run_chunked_npc_world(
                _load(args.actions),
                _load(args.settings) if args.settings else None,
                scenes=_load(args.scenes) if args.scenes else None,
                seed=args.seed,
                options=_load(args.options) if args.options else None)
        elif args.operation == "verify-chunked-npc-world":
            output={"verified":verify_chunked_npc_world(_load(args.record))}
        elif args.operation == "unified-npc-world":
            output=run_unified_npc_world(
                _load(args.actions),
                _load(args.settings) if args.settings else None,
                scenes=_load(args.scenes) if args.scenes else None,
                seed=args.seed)
        elif args.operation == "verify-unified-npc-world":
            output={"verified":verify_unified_npc_world(_load(args.record))}
        elif args.operation == "social-quest-fusion":
            output=run_social_quest_fusion(
                _load(args.commands),
                _load(args.settings) if args.settings else None,
                scenes=_load(args.scenes) if args.scenes else None,
                seed=args.seed,
            )
        elif args.operation == "verify-social-quest-fusion":
            output={"verified":verify_social_quest_fusion(_load(args.record))}
        elif args.operation == "economy-mirror":
            output=analyze_original_economy(
                _load(args.scene),
                _load(args.settings) if args.settings else None,
                horizon=args.horizon,max_scenarios=args.max_scenarios)
        elif args.operation == "verify-economy-mirror":
            output={"verified":verify_original_economy_mirror(
                _load(args.record),_load(args.scene),
                _load(args.settings) if args.settings else None)}
        elif args.operation == "plan-economy":
            output=plan_original_trade(
                _load(args.scene),
                _load(args.settings) if args.settings else None,
                max_actions=args.max_actions,retire=args.retire)
        elif args.operation == "verify-economy-plan":
            output={"verified":verify_original_trade_plan(
                _load(args.record),_load(args.scene),
                _load(args.settings) if args.settings else None)}
        elif args.operation == "plan-original-world":
            output=plan_original_world(
                _load(args.scene),
                _load(args.settings) if args.settings else None,
                max_states=args.max_states,max_actions=args.max_actions)
        elif args.operation == "fighting-peer-replay":
            output=run_peer_fight(
                _load(args.settings) if args.settings else None,
                _load(args.blue_actions),_load(args.red_actions),
                seed=args.seed,scene=_load(args.scene) if args.scene else None)
        elif args.operation == "fighting-peer-verify":
            output={"verified":verify_peer_fight(
                _load(args.record),_load(args.settings) if args.settings else None)}
        elif args.operation == "fighting-rollback":
            output=reconcile_peer_prediction(
                _load(args.settings) if args.settings else None,
                _load(args.blue_actions),_load(args.predicted_red),
                _load(args.authoritative_red),seed=args.seed,
                scene=_load(args.scene) if args.scene else None)
        elif args.operation == "fighting-rollback-verify":
            output={"verified":verify_peer_reconciliation(
                _load(args.record),_load(args.settings) if args.settings else None)}
        elif args.operation == "rhythm-longrun":
            output=run_long_rhythm(
                _load(args.settings) if args.settings else None,
                _load(args.actions),seed=args.seed,
                scene=_load(args.scene) if args.scene else None,
                checkpoint_interval=args.checkpoint_interval)
        elif args.operation == "rhythm-longrun-verify":
            output={"verified":verify_long_rhythm(
                _load(args.record),
                _load(args.settings) if args.settings else None)}
        elif args.operation == "rhythm-longrun-continue":
            output=continue_long_rhythm(
                _load(args.record),_load(args.actions),
                _load(args.settings) if args.settings else None)
        elif args.operation == "rhythm-audio":
            if not args.trusted_local_operator:
                raise SystemEditorError("offline WAV materialization requires explicit local operator approval")
            settings=make_editor_document("rhythm",
                _load(args.settings) if args.settings else None)["settings"]
            if args.scene:
                scene=validate_advanced_scene(_load(args.scene),settings)
                if scene["editor"]!="rhythm" or scene["seed"]!=args.seed:
                    raise SystemEditorError("rhythm audio source/seed identity mismatched")
                layout=scene["layout"]
            else:
                layout=original_rhythm_chart(settings,args.seed)
            audio=render_original_beat_wav(layout,settings,from_ms=args.from_ms,
                                             duration_ms=args.duration_ms)
            destination=Path(args.output)
            if not destination.parent.is_dir() or destination.parent.is_symlink():
                raise SystemEditorError("WAV must be authored into existing ordinary local folder")
            with destination.open("xb") as soundfile:
                soundfile.write(audio)
            output=original_audio_receipt(layout,settings,from_ms=args.from_ms,
                                           duration_ms=args.duration_ms)
            output["output_path"]=str(destination)
        elif args.operation == "roguelike-marathon":
            output=replay_long_roguelike(
                _load(args.settings) if args.settings else None,
                _load(args.actions),seed=args.seed,
                scene=_load(args.scene) if args.scene else None,
                checkpoint_interval=args.checkpoint_interval)
        elif args.operation == "roguelike-marathon-verify":
            output={"verified":verify_long_roguelike(
                _load(args.record),_load(args.settings) if args.settings else None)}
        elif args.operation == "roguelike-marathon-continue":
            output=continue_long_roguelike(
                _load(args.record),_load(args.actions),
                _load(args.settings) if args.settings else None)
        elif args.operation == "godot-export":
            receipt=_load(args.session)
            settings=_load(args.settings) if args.settings else None
            renderer=(render_platformer_godot_package if receipt.get("editor")=="platformer"
                      else render_deck_godot_package if receipt.get("editor")=="deck_battler"
                      else render_shooter_godot_package if receipt.get("editor")=="shooter"
                      else render_tactics_godot_package if receipt.get("editor")=="tactics"
                      else render_defense_godot_package if receipt.get("editor")=="tower_defense"
                      else render_racing_godot_package if receipt.get("editor")=="racing"
                      else render_survival_godot_package if receipt.get("editor")=="survival"
                      else render_farming_godot_package if receipt.get("editor")=="farming"
                      else render_factory_godot_package if receipt.get("editor")=="factory"
                      else render_colony_godot_package if receipt.get("editor")=="colony"
                      else render_economy_godot_package if receipt.get("editor")=="economy"
                      else render_dialogue_godot_package if receipt.get("editor")=="dialogue"
                      else render_advanced_godot_package)
            artifact=renderer(receipt,settings,authorized=args.trusted_local_operator)
            destination=write_advanced_godot_package(
                artifact,args.output,authorized=args.trusted_local_operator)
            output={**artifact.manifest,"local_output_path":str(destination)}
        elif args.operation == "save":
            output = export_advanced_savegame(_load(args.session),
                _load(args.settings) if args.settings else None)
        elif args.operation == "load-save":
            output = import_advanced_savegame(_load(args.savegame))
        elif args.operation == "continue-save":
            output = continue_advanced_savegame(
                _load(args.savegame),_load(args.actions))
        elif args.operation == "verify-play":
            output = {"verified":verify_advanced_session(
                _load(args.session), _load(args.settings) if args.settings else None)}
        elif args.operation in ("template", "preview", "play"):
            settings = _load(args.settings) if args.settings else None
            if args.operation == "template":
                output = json.loads(editor_source(args.editor, settings))
            else:
                actions = _load(args.actions) if args.actions else []
                if args.operation == "play":
                    output = run_advanced_session(
                        args.editor, settings, actions, seed=args.seed,
                        scene=_load(args.scene) if args.scene else None)
                else:
                    output = preview_editor(args.editor, settings, actions or None)
        else:
            raise SystemEditorError("unknown editor command")
        print(json.dumps(output, sort_keys=True, ensure_ascii=True,
                         separators=(",", ":"), allow_nan=False))
        return 0
    except (SystemEditorError, WorkspaceError, PermissionError,
            OSError, UnicodeError, ValueError) as exc:
        print("system editor rejected: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
