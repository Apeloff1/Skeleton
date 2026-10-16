"""Measured scene/quest production workboard and Dragon replay research intake.

No game-frame, model-weight, independent-review or release claims are inferred
from a completed deterministic Director simulation.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from typing import Any

BOARD_SCHEMA = "skeleton.jeeves.director_production_board.v1"
RESEARCH_SCHEMA = "skeleton.dragon.director_replay_candidate.v1"
MAX_SOURCE_BYTES = 16 * 1024 * 1024


def _digest(value: object) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=True, allow_nan=False).encode()).hexdigest()


def _load_world(root: Path, source: str):
    from skeleton.developer.jeeves_game_quality import _read
    from skeleton.developer.game_cli import _load
    from skeleton.ai.game_builder.quest_scene_forge import compile_director_blueprint
    document, identity = _read(root, source, MAX_SOURCE_BYTES)
    if (set(document) != {"schema", "director_world", "author_review_acknowledged"}
            or document.get("schema") != "skeleton.jeeves.director_campaign_source.v1"
            or document.get("author_review_acknowledged") is not True):
        raise ValueError("Director board requires explicit reviewed campaign source")
    world = compile_director_blueprint(document["director_world"], human_reviewed=True)
    project = _load(root)["name"].lower().replace("-", "_")
    if world.project_id != project:
        raise ValueError("Director campaign does not belong to this game workspace")
    return world, identity


def _runtime_signal_atlas(root: Path, *, source: str, world_digest: str) -> dict[str, Any]:
    """Read-only local source evidence; failures remain diagnostics, never P0 signoff."""
    from skeleton.developer.jeeves_game_director_atlas import verify
    target = root / "build" / "director_atlases" / (world_digest[:20] + "-live-v6")
    if not target.exists() and not target.is_symlink():
        return {"present": False, "source_verified": False}
    try:
        checked = verify(root, source=source)
        return {"present": True, "source_verified": checked["source_manifest_verified"],
                "native_live_quest_ui_source_verified": True,
                "generated_original_scene_media_hashes_verified": True,
                "godot_engine_executed": False}
    except (OSError, ValueError, KeyError) as exc:
        return {"present": True, "source_verified": False, "error": str(exc)}


def _runtime_signal_sessions(root: Path, *, world_digest: str) -> dict[str, Any]:
    """Count fully replay-verified, exact-world sessions without mutating evidence."""
    from skeleton.developer.jeeves_game_director_session import inspect
    folder = root / ".jeeves" / "director_sessions"
    if folder.is_symlink() or (folder.exists() and not folder.is_dir()):
        return {"verified_sessions": 0, "invalid_sessions": 1, "warning": "unsafe session inventory"}
    if not folder.exists():
        return {"verified_sessions": 0, "invalid_sessions": 0}
    names = sorted(folder.iterdir(), key=lambda p: p.name)
    if len(names) > 32:
        return {"verified_sessions": 0, "invalid_sessions": 0,
                "warning": "specialized session audit required above 32 entries"}
    verified, invalid, steps = 0, 0, 0
    for node in names:
        if node.is_symlink() or not node.is_dir():
            invalid += 1
            continue
        try:
            report = inspect(root, session=node.name)
            if report["world_sha256"] == world_digest:
                verified += 1
                steps += report["sequence"]
        except (OSError, ValueError, KeyError, TypeError):
            invalid += 1
    return {"verified_sessions": verified, "invalid_sessions": invalid,
            "replayed_interactive_actions": steps}


def _runtime_signal_bindings(root: Path, *, source: str) -> dict[str, Any]:
    from skeleton.developer.jeeves_game_director_bindings import check
    import re
    base = root / "design"
    if base.is_symlink() or not base.is_dir():
        return {"verified_contracts": 0, "invalid_contracts": 1}
    paths = list(base.glob("director_bindings_*.json"))
    if len(paths) > 32:
        return {"verified_contracts": 0, "invalid_contracts": 0,
                "warning": "specialized binding audit required above 32 files"}
    good, bad = 0, 0
    for node in paths:
        digest = node.name[len("director_bindings_"):-len(".json")]
        if not re.fullmatch(r"[0-9a-f]{64}", digest) or node.is_symlink():
            bad += 1
            continue
        try:
            if check(root, source=source, digest=digest)["binding_source_verified"]:
                good += 1
        except (OSError, ValueError, TypeError, KeyError):
            bad += 1
    return {"verified_contracts": good, "invalid_contracts": bad}


def _runtime_signal_dragon_policy(root: Path, *, world_digest: str
                                  ) -> dict[str, Any]:
    """Re-fit local Dragon micro-model evidence; never qualify transformer weights."""
    import re
    from skeleton.developer.jeeves_game_dragon_policy import _load_checkpoint, fit
    base = root / ".jeeves"
    folder = base / "dragon_policy_checkpoints"
    if (base.is_symlink() or folder.is_symlink()
            or (folder.exists() and not folder.is_dir())):
        return {"replay_verified_policies": 0, "invalid_policies": 1,
                "warning": "unsafe policy checkpoint location"}
    if not folder.exists():
        return {"replay_verified_policies": 0, "invalid_policies": 0}
    nodes = list(folder.iterdir())
    if len(nodes) > 16:
        return {"replay_verified_policies": 0, "invalid_policies": 0,
                "warning": "specialized Dragon checkpoint audit required above 16 files"}
    valid, invalid, held_out = 0, 0, []
    for node in nodes:
        digest = node.name.removesuffix(".json")
        if (node.is_symlink() or not node.is_file()
                or not re.fullmatch(r"[0-9a-f]{64}\Z", digest)):
            invalid += 1
            continue
        try:
            model = _load_checkpoint(root, digest)
            if model["world_sha256"] != world_digest:
                continue
            samples = [x["session"] for x in model["training_session_receipts"]]
            samples.append(model["held_out_session_receipt"]["session"])
            if fit(root, sessions=",".join(samples)) != model:
                invalid += 1
                continue
            valid += 1
            held_out.append({
                "model_sha256": digest,
                "trained_actions": model["train_action_count"],
                "heldout_covered_actions": model["heldout_context_coverage_count"],
                "heldout_top1_accuracy": model["heldout_top1_accuracy"],
            })
        except (OSError, ValueError, KeyError, TypeError):
            invalid += 1
    return {"replay_verified_policies": valid, "invalid_policies": invalid,
            "empirical_policy_checks": held_out,
            "production_transformer_training_verified": False}


def _labyrinth_signal(root: Path, *, source: str) -> dict[str, Any]:
    """Surface topology risks as evidence, never conflate with artistic signoff."""
    from skeleton.developer.jeeves_game_director_labyrinth import topology
    report = topology(root, source=source)
    return {
        "all_scenes_accessible": report["all_scenes_accessible_from_start"],
        "strongly_connected": report["fully_strongly_connected"],
        "one_way_exit_count": len(report["one_way_links"]),
        "cannot_return_to_start_count": len(report["cannot_return_to_start"]),
        "unreachable_quest_stage_count": len(report["quest_placement_gaps"]),
        "scene_count": report["scene_count"],
        "artistic_path_quality_approved": False,
    }


def _dynamic_world_signal(world: Any) -> dict[str, Any]:
    """Surface factual authored world systems separately from native game claims."""
    if world.dynamics is None:
        return {
            "enabled": False, "compiled_and_type_checked": False,
            "native_transport_animation_executed": False,
        }
    from skeleton.developer.jeeves_game_director_dynamic_audit import analyze
    report = analyze(world)
    return {
        "enabled": True,
        "compiled_and_type_checked": True,
        "faction_count": report["faction_count"],
        "walking_gate_count": report["walking_gate_count"],
        "transport_count": report["transport_count"],
        "world_influence_count": report["authored_influence_count"],
        "initial_permission_risks": report["structural_risks"][:50],
        "initial_permission_risk_total": report["risk_count"],
        "state_space_exhaustively_verified": False,
        "real_native_transport_playthrough_verified": False,
        "assurance_sha256": report["assurance_sha256"],
    }


def _society_signal(world: Any) -> dict[str, Any]:
    """Social simulation facts; no false approval of cinematic acting or AI."""
    if world.dynamics is None or world.dynamics.society is None:
        return {
            "enabled": False,
            "NPC_personality_or_language_model_trained": False,
        }
    from skeleton.developer.jeeves_game_director_society_audit import analyze
    report = analyze(world)
    return {
        "enabled": True,
        "typed_source_compiled": True,
        "NPC_count": report["NPC_count"],
        "merchant_count": report["shop_count"],
        "goods_count": report["tradeable_item_count"],
        "NPC_dialogue_choices": sum(
            len(person.dialogue)
            for person in world.dynamics.society.residents
        ),
        "authored_social_gates": len(report["conditional_society_links"]),
        "initial_social_actions": report["actual_initial_NPC_market_actions"][:40],
        "structural_review_item_count": report["structural_review_item_count"],
        "structural_review_item_sample": report["structural_review_items"][:30],
        "assurance_sha256": report["assurance_sha256"],
        "native_NPC_walk_cycle_verified": False,
        "literary_character_voice_human_approved": False,
        "NPC_language_model_trained": False,
    }


def board(root: Path, *, source: str, routes: int = 3,
          dragon_digest: str | None = None) -> dict[str, Any]:
    from skeleton.ai.game_builder.quest_campaign_completion import compare_campaign_branches
    from skeleton.developer.jeeves_game_quality import _read
    from skeleton.developer.game_cli import _read_forge
    if type(routes) is not int or not 2 <= routes <= 8:
        raise ValueError("Director board needs 2..8 replayed campaign branches")
    world, source_sha = _load_world(root, source)
    learning = None
    if dragon_digest is not None:
        from skeleton.developer.jeeves_game_dragon import load_handoff
        learning = load_handoff(root, dragon_digest)
        if learning["project"].lower().replace("-", "_") != world.project_id:
            raise ValueError("Dragon handoff belongs to another game project")
    result = compare_campaign_branches(world, routes=routes)
    if not result["ok"] or not result["all_routes_completed"]:
        raise ValueError("campaign replay cannot support the Director production board")
    seen = set()
    for report in result["route_reports"]:
        for item in report["results"]:
            seen.add((item["quest"], item["stage"]))
    scenes = [
        {
            "scene": item.key, "region": item.region,
            "cast": list(item.cast), "props": list(item.props),
            "affordances": len(item.affordances),
            "cutscene_timelines": len(item.cutscenes),
            "links": list(item.links), "logic_admitted": True,
            "rendered_scene_verified": False, "interactive_engine_tested": False,
        }
        for item in world.scenes
    ]
    stages = [
        {
            "quest": quest.key, "stage": stage.key, "scene_ids": list(stage.scene_ids),
            "solution_methods": len(stage.solutions),
            "optional_objectives": len(stage.optional),
            "director_replay_verified": (quest.key, stage.key) in seen,
            "native_engine_played": False,
        }
        for quest in world.quests for stage in quest.stages
    ]
    dragon_work = []
    if learning is not None:
        dragon_work = [
            {
                "mechanic": spec["mechanic"],
                "objective": spec["objective"],
                "system_response": spec["system_response"],
                "acceptance": spec["validation"],
                "implemented_in_native_engine": False,
                "player_review_pending": True,
            }
            for spec in learning["prototype"]["mechanics"]
        ]
    engine = {"manifest_verified": False, "source_sha256": None,
              "interactive_playtest_verified": False}
    try:
        _, files, receipt = _read_forge(root)
        engine["manifest_verified"] = bool(files and receipt["sha256"])
        engine["source_sha256"] = receipt["sha256"]
    except (OSError, ValueError, KeyError):
        pass
    from skeleton.developer.jeeves_game_quality import _read
    if _read(root, source, MAX_SOURCE_BYTES)[1] != source_sha:
        raise ValueError("Director source changed while computing production board")
    output = {
        "schema": BOARD_SCHEMA, "project": world.project_id,
        "source": source, "source_sha256": source_sha,
        "director_world_sha256": world.digest,
        "dragon_handoff_sha256": dragon_digest,
        "logic_campaign": {
            "routes": result["route_count"],
            "all_routes_completed": result["all_routes_completed"],
            "branch_outcomes_materially_distinct": result["branch_outcomes_materially_distinct"],
            "divergent_stages": result["divergent_quest_stages"],
            "states": [
                row["final_director_state_sha256"] for row in result["route_reports"]
            ],
            "action_counts": [row["action_count"] for row in result["route_reports"]],
            "replay_receipts": [
                row["replay_receipt_sha256"] for row in result["route_reports"]
            ],
            "all_stages_replayed": all(s["director_replay_verified"] for s in stages),
        },
        "scene_workorders": scenes, "quest_stage_workorders": stages,
        "dragon_mechanic_workorders": dragon_work,
        "gameforge_engine": engine,
        "new_runtime_development_evidence": {
            "labyrinth_topology": _labyrinth_signal(root, source=source),
            "dynamic_living_world": _dynamic_world_signal(world),
            "NPC_society_and_economy": _society_signal(world),
            "interactive_director_sessions": _runtime_signal_sessions(
                root, world_digest=world.digest),
            "godot_scene_atlas": _runtime_signal_atlas(
                root, source=source, world_digest=world.digest),
            "engine_event_bindings": _runtime_signal_bindings(
                root, source=source),
            "dragon_empirical_policy": _runtime_signal_dragon_policy(
                root, world_digest=world.digest),
            "native_gameplay_certified_by_sources": False,
        },
        "remaining_milestones": [
            {"id": "GAME-SCENES", "required": "Render and inspect every scene and asset", "verified": False},
            {"id": "GAME-INTERACTION", "required": "Wire simulated quest actions into a playable engine", "verified": False},
            {"id": "GAME-PATHS", "required": "Perform installed real-player end-to-end multi-ending playthrough", "verified": False},
            {"id": "GAME-CANON", "required": "Independent continuity and literary direction review", "verified": False},
            {"id": "GAME-DRAGON", "required": "Review real feedback and demonstrate checkpoint weight improvement", "verified": False},
            {"id": "GAME-RELEASE", "required": "License audit, packaging, first installation and recovery", "verified": False},
        ],
        "source_only": True,
        "independent_game_completion_verified": False,
    }
    output["board_sha256"] = _digest(output)
    return {"ok": True, "action": "director-board", **output}


def prepare_dragon_research(root: Path, *, source: str, routes: int = 3,
                            dragon_digest: str | None = None,
                            approve: str | None = None) -> dict[str, Any]:
    """Build an evidence-linked replay lesson; no fake preference or weight update."""
    from skeleton.developer.jeeves_game_authoring import _create_only
    from skeleton.developer.jeeves_game_quality import _read
    result = board(root, source=source, routes=routes, dragon_digest=dragon_digest)
    receipt = result["board_sha256"]
    features = result["logic_campaign"]
    payload = {
        "schema": RESEARCH_SCHEMA, "project": result["project"],
        "source": source, "source_sha256": result["source_sha256"],
        "board_sha256": receipt,
        "director_world_sha256": result["director_world_sha256"],
        "dragon_handoff_sha256": dragon_digest,
        "route_count": features["routes"],
        "executed_action_counts": features["action_counts"],
        "verified_replay_receipts": features["replay_receipts"],
        "stage_outcome_divergence": features["divergent_stages"],
        "questions_for_future_real_gameplay": [
            "Do actual player choices produce the same consequences as these Director transitions?",
            "Do scene assets and audio communicate the intended gameplay feedback?",
            "Do real navigation, save/load and accessibility audits reproduce this campaign?",
        ],
        "recorded_player_preference": None,
        "captured_human_gameplay": False,
        "independent_research_review": False,
        "model_weights_modified": False,
        "native_game_playthrough": False,
    }
    digest = _digest(payload)
    preview = {
        "ok": True, "action": "director-prepare-training",
        "candidate_sha256": digest, "candidate": payload,
        "persisted": False, "training_performed": False,
    }
    if approve is None:
        return preview
    if approve != digest:
        raise ValueError("--approve must match the reviewed Dragon replay candidate digest")
    directory = root / ".jeeves"
    folder = directory / "dragon_replay_candidates"
    if directory.is_symlink() or folder.is_symlink() or (
        directory.exists() and not directory.is_dir()
    ) or (folder.exists() and not folder.is_dir()):
        raise ValueError("unsafe Dragon replay candidate location")
    if _read(root, source, MAX_SOURCE_BYTES)[1] != payload["source_sha256"]:
        raise ValueError("Director campaign source changed during Dragon feedback creation")
    destination = folder / (digest + ".json")
    _create_only(destination, (json.dumps(payload, sort_keys=True, indent=2,
                                          ensure_ascii=True, allow_nan=False) + "\n").encode())
    preview["persisted"] = True
    preview["path"] = str(destination)
    return preview
