"""Jeeves game-development workbench over the existing local GameForge workspace.

This is a deterministic, evidence-grounded CLI adapter to canonical Jeeves
BuilderBrain and Forge verification; it does not impersonate trained inference.
Recommendations are proposals, never implicit filesystem mutations.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

SCHEMA = "skeleton.jeeves.game_workbench.v1"
MAX_NOTES_BYTES = 256 * 1024


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=True, default=str).encode("ascii")).hexdigest()


def _context(root: Path) -> tuple[dict[str, str], dict[str, Any]]:
    from skeleton.developer.game_cli import _load
    cfg = _load(root)
    from skeleton.forge.eras import list_eras
    from skeleton.forge.archetypes import default_library
    if cfg["era"] not in set(list_eras()):
        raise ValueError("unsupported configured era")
    if cfg["archetype"] not in {"auto", "vision", *default_library().names()}:
        raise ValueError("unsupported configured archetype")
    from skeleton.forge.eras import compile_era
    pack = compile_era(cfg["era"])
    return cfg, pack


def _plan(root: Path) -> dict[str, Any]:
    cfg, pack = _context(root)
    from skeleton.context.tensor import ContextTensor
    from skeleton.jeeves.builder import BuilderBrain
    tensor = ContextTensor.from_era(cfg["era"])
    # Intentionally uses no external model, checkpoint, or fabricated oracle.
    plan = BuilderBrain().plan(pack, tensor=tensor).to_dict()
    return {"schema": SCHEMA, "action": "plan", "project": str(root),
            "vision": cfg["vision"], "era": cfg["era"], "archetype": cfg["archetype"],
            "plan": plan, "authorship": "deterministic-local-jeeves-builder",
            "model_inference": False, "checkpoint_verified": False,
            "plan_sha256": _digest(plan)}


def _audit(root: Path) -> dict[str, Any]:
    """Cross-check product input, actual files, and real evidence without inventing passes."""
    from skeleton.developer.game_cli import _read_forge, _check_assets, GameCLIError
    cfg, _ = _context(root)
    checks: list[dict[str, Any]] = []
    def record(name: str, ok: bool, detail: str, *, category: str = "static") -> None:
        checks.append({"name": name, "ok": ok, "detail": detail, "category": category})
    record("workspace_manifest", True, f"{cfg['name']} ({cfg['era']})")
    try:
        _, files, receipt = _read_forge(root)
        record("emitted_source_integrity", True,
               f"{len(files)} source files; sha256 {receipt['sha256']}")
    except (GameCLIError, OSError, ValueError) as exc:
        receipt = None
        record("emitted_source_integrity", False, str(exc))
    try:
        assets = _check_assets(root)
        record("asset_inventory", True, f"{assets['count']} tracked assets")
    except (GameCLIError, OSError, ValueError) as exc:
        assets = None
        record("asset_inventory", False, str(exc))
    from skeleton.forge.playtest import resolve_binary
    binary, source, verified = resolve_binary()
    record("godot_binary", bool(binary), f"source={source}; artifact_verified={verified}",
           category="runtime")
    # A binary existing is NOT proof that this emitted project can boot.
    record("headless_playthrough", False, "not executed by this read-only audit",
           category="unverified")
    record("release_export", False, "native export/signing not performed",
           category="unverified")
    failures = [c["name"] for c in checks if not c["ok"] and c["category"] != "unverified"]
    return {"schema": SCHEMA, "action": "audit", "project": str(root),
            "ok": not failures, "ready_for_source_review": receipt is not None,
            "production_qualified": False, "checks": checks,
            "blocking": failures, "assets": {"count": assets["count"]} if assets else None,
            "source_sha256": receipt["sha256"] if receipt else None}


def _recommendations(plan: dict[str, Any], audit: dict[str, Any]) -> list[dict[str, str]]:
    failed = {item["name"] for item in audit["checks"] if not item["ok"]}
    out: list[dict[str, str]] = []
    def add(priority: str, goal: str, command: str, why: str) -> None:
        out.append({"priority": priority, "goal": goal, "command": command, "reason": why})
    if "emitted_source_integrity" in failed:
        add("P0", "Generate or repair emitted game source",
            "python -m skeleton dev game build --project .",
            "No verified canonical Godot source receipt exists")
    if "asset_inventory" in failed:
        add("P0", "Repair local assets directory", "python -m skeleton dev game assets --project .",
            "Asset inventory is missing, unsafe or unreadable")
    if "godot_binary" in failed:
        add("P1", "Provision and qualify Godot toolchain",
            "python -m skeleton dev game doctor --project . --require-godot",
            "A dynamic boot cannot be verified without Godot")
    else:
        add("P1", "Execute a real headless boot",
            "python -m skeleton dev game playtest --project .",
            "A readable source manifest is not evidence of runtime playability")
    add("P1", "Review gameplay pacing and balance",
        "python -m skeleton walk --era " + plan["era"] + " --mode thermal --json",
        "A generated plan must face reproducible gameplay simulation")
    add("P2", "Review story and continuity in design notes",
        "python -m skeleton dev game jeeves context --project .",
        "Narrative continuity requires authored evidence, not inferred completion")
    add("P2", "Review verified source release material",
        "python -m skeleton dev game package --project . --dry-run",
        "Packaging remains a separate operator-approved action")
    return out


def _notes(root: Path) -> list[dict[str, str]]:
    base = root / "design"
    if base.is_symlink() or not base.is_dir():
        raise ValueError("design directory missing or symlinked")
    result: list[dict[str, str]] = []
    for node in sorted(base.rglob("*")):
        if node.is_symlink():
            raise ValueError("symlinks in design material are not allowed")
        if node.is_dir():
            continue
        if node.suffix.lower() not in {".md", ".txt", ".json"}:
            continue
        if len(result) >= 128 or node.stat().st_size > MAX_NOTES_BYTES:
            raise ValueError("design note count or size exceeds bounds")
        try:
            content = node.read_text(encoding="utf-8")
        except UnicodeError as exc:
            raise ValueError("design notes must be UTF-8") from exc
        result.append({"path": node.relative_to(root).as_posix(),
                       "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
                       "excerpt": content[:240]})
    return result


def run_jeeves_game_cli(argv: list[str], root: Path) -> dict[str, Any]:
    """Game-authoring proposals require real model I/O and explicit local acceptance."""
    parser = argparse.ArgumentParser(prog="skeleton dev game jeeves")
    parser.add_argument("action", choices=("plan", "audit", "next", "context", "handoff",
                                            "propose", "review", "apply", "queue", "benchmark", "benchmark-matrix", "asset-gate",
                                            "fidelity-plan", "fidelity-matrix", "display-plan", "upscale", "upscale-verify", "render-reference", "production-init",
                                            "production-status", "production-cycle", "production-training",
                                            "dragon-observe-start", "dragon-observe-sync", "dragon-observe-status",
                                            "dragon-observe-cycle", "dragon-observe-action", "dragon-observe-lessons", "dragon-observe-revoke",
                                                   "direction-audit", "direction-revision", "direction-benchmark", "direction-shots", "direction-gameplay", "direction-campaign", "direction-campaign-reopen", "p0-acceptance",
                                            "upscale-world", "upscale-stage", "upscale-environment", "upscale-clutter",
                                            "upscale-foliage", "upscale-animation", "upscale-shadow",
                                            "upscale-parallax", "upscale-music", "asset-inventory",
                                            "upscale-review", "vividness-review", "queue-upscaled-training",
                                            "camera-plan", "camera-render",
                                            "direction-audit", "direction-workorder", "production-gap-matrix",
                                            "dragon-review", "dragon-portfolio", "dragon-ingest", "dragon-plan", "dragon-adopt",
                                            "director-draft", "director-revise", "director-examine", "director-promote",
                                            "director-board", "director-prepare-training",
                                            "director-session-begin", "director-session-status", "director-session-step",
                                            "director-session-compare", "director-session-fork", "director-session-trace", "director-serve", "director-atlas-export", "director-atlas-verify",
                                            "dragon-session-lesson", "director-bindings", "director-bindings-publish", "director-bindings-check", "dragon-lab", "dragon-policy-preview", "dragon-policy-train",
                                            "dragon-policy-predict", "director-coverage", "director-godot-smoke", "director-loopback-e2e", "director-native-http-e2e", "director-route", "director-topology",
                                            "director-causality", "director-story-contrast", "dragon-navigation-study", "director-dynamics-design", "director-dynamics-publish",
                                            "director-dynamics-audit", "dragon-world-study", "dragon-world-contrast", "director-dynamics-playthrough", "director-society-design", "director-society-publish",
                                             "director-society-audit", "dragon-society-study", "dragon-society-contrast", "director-society-stress", "director-society-acceptance"))
    parser.add_argument("--kind")
    parser.add_argument("--brief")
    parser.add_argument("--include-notes", action="store_true")
    parser.add_argument("--digest")
    parser.add_argument("--approve")
    parser.add_argument("--console")
    parser.add_argument("--genre")
    parser.add_argument("--period")
    parser.add_argument("--profile")
    parser.add_argument("--evidence")
    parser.add_argument("--target")
    parser.add_argument("--source")
    parser.add_argument("--direction-source")
    parser.add_argument("--dragon-digest")
    parser.add_argument("--seed", type=int)
    parser.add_argument("--regions")
    parser.add_argument("--revision")
    parser.add_argument("--quest-types")
    parser.add_argument("--stages", type=int)
    parser.add_argument("--goal")
    parser.add_argument("--routes", type=int)
    parser.add_argument("--session")
    parser.add_argument("--at", type=int)
    parser.add_argument("--tail", type=int)
    parser.add_argument("--destination")
    parser.add_argument("--route-profile", choices=("fastest", "scenic", "quiet", "novel", "quest"))
    parser.add_argument("--alternatives", type=int)
    parser.add_argument("--intensity", type=int)
    parser.add_argument("--include-optional", action="store_true")
    parser.add_argument("--sessions")
    parser.add_argument("--port", type=int)
    parser.add_argument("--timeout", type=float)
    parser.add_argument("--other-session")
    parser.add_argument("--choice")
    parser.add_argument("--output")
    parser.add_argument("--mode", choices=("nearest", "scale2x", "remaster", "ambience", "cinematic"))
    parser.add_argument("--factor", type=int)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--passes", type=int)
    parser.add_argument("--gate")
    parser.add_argument("--page", type=int)
    parser.add_argument("--page-size", type=int)
    parser.add_argument("--repair-generated", action="store_true")
    parser.add_argument("--consent", action="store_true")
    parser.add_argument("--actor")
    parser.add_argument("--phase")
    parser.add_argument("--event")
    parser.add_argument("--outcome")
    parser.add_argument("--pattern", choices=("wind", "breathe", "bob", "shimmer", "water"))
    parser.add_argument("--frames", type=int)
    parser.add_argument("--frame-height", type=int)
    parser.add_argument("--richness", type=int)
    parser.add_argument("--focus", choices=("world", "environment", "foliage", "clutter", "shadow"))
    parser.add_argument("--pan", type=int)
    parser.add_argument("--distance", type=int)
    parser.add_argument("--ambience")
    parser.add_argument("--depth", choices=("2d", "2_5d", "2_9d", "3d"))
    parser.add_argument("--yaw", type=float)
    parser.add_argument("--pitch", type=float)
    parser.add_argument("--parallax-planes", type=int)
    for dimension in ("native-width", "native-height", "screen-width",
                      "screen-height", "pixel-aspect-num", "pixel-aspect-den"):
        parser.add_argument("--" + dimension, type=int)
    args = parser.parse_args(argv)
    try:
        if args.action.startswith("dragon-observe-"):
            from skeleton.developer import jeeves_dragon_observer as witness
            observer_options = {
                "dragon-observe-start": {"consent"},
                "dragon-observe-sync": {"page_size"},
                "dragon-observe-status": set(),
                "dragon-observe-cycle": {"passes", "gate", "repair_generated"},
                "dragon-observe-action": {"actor", "phase", "event", "outcome", "evidence"},
                "dragon-observe-lessons": {"page", "page_size"},
                "dragon-observe-revoke": set(),
            }
            allowed = observer_options[args.action] | {"action"}
            for key, value in vars(args).items():
                if key not in allowed and value is not None and value is not False:
                    raise ValueError("unrelated observer option --" + key.replace("_", "-"))
            if args.action == "dragon-observe-start":
                return witness.start(root, consent=args.consent)
            if args.action == "dragon-observe-sync":
                return witness.sync(root, limit=args.page_size if args.page_size is not None else 256)
            if args.action == "dragon-observe-status":
                return witness.status(root)
            if args.action == "dragon-observe-cycle":
                return witness.cycle(
                    root, passes=args.passes if args.passes is not None else 1,
                    gate=args.gate, repair_generated=args.repair_generated,
                )
            if args.action == "dragon-observe-action":
                return witness.record_action(
                    root, actor=args.actor, phase=args.phase, action=args.event,
                    outcome=args.outcome, evidence_sha256=args.evidence,
                )
            if args.action == "dragon-observe-lessons":
                return witness.lessons(
                    root, page=args.page if args.page is not None else 0,
                    page_size=args.page_size if args.page_size is not None else 64,
                )
            return witness.revoke(root)
        live_actions = {
            "director-session-begin": {"action", "source", "session"},
            "director-session-status": {"action", "session"},
            "director-session-step": {"action", "session", "choice"},
            "director-session-compare": {"action", "session", "other_session"},
            "director-session-fork": {"action", "session", "other_session", "at", "approve"},
            "director-session-trace": {"action", "session", "tail"},
            "director-serve": {"action", "session", "port", "digest"},
            "director-atlas-export": {"action", "source", "dry_run"},
            "director-atlas-verify": {"action", "source"},
            "dragon-session-lesson": {"action", "session", "approve"},
            "director-bindings": {"action", "source"},
            "director-bindings-publish": {"action", "source", "approve"},
            "director-bindings-check": {"action", "source", "digest"},
            "dragon-lab": {"action", "sessions", "approve"},
            "dragon-policy-preview": {"action", "sessions"},
            "dragon-policy-train": {"action", "sessions", "approve"},
            "dragon-policy-predict": {"action", "session", "digest"},
            "director-coverage": {"action", "source", "routes"},
            "director-godot-smoke": {"action", "source", "timeout"},
            "director-loopback-e2e": {"action", "source", "routes"},
            "director-native-http-e2e": {"action", "source", "timeout"},
            "director-route": {"action", "session", "destination", "route_profile", "alternatives"},
            "director-topology": {"action", "source"},
            "director-causality": {"action", "session", "page", "page_size"},
            "director-story-contrast": {"action", "session", "other_session"},
            "dragon-navigation-study": {"action", "session", "approve"},
            "director-dynamics-design": {"action", "source", "intensity"},
            "director-dynamics-publish": {"action", "source", "intensity", "approve"},
            "director-dynamics-audit": {"action", "source"},
            "director-dynamics-playthrough": {"action", "source", "routes", "include_optional"},
            "dragon-world-study": {"action", "session", "approve"},
            "dragon-world-contrast": {"action", "session", "other_session"},
            "director-society-design": {"action", "source", "intensity"},
            "director-society-publish": {"action", "source", "intensity", "approve"},
            "director-society-audit": {"action", "source"},
            "director-society-stress": {"action", "source", "routes", "intensity"},
            "director-society-acceptance": {"action", "source"},
            "dragon-society-study": {"action", "session", "approve"},
            "dragon-society-contrast": {"action", "session", "other_session"},
        }
        if args.action in live_actions:
            for key, value in vars(args).items():
                if key not in live_actions[args.action] and value is not None and value is not False:
                    raise ValueError("unrelated Director runtime option --" + key.replace("_", "-"))
            if args.action == "director-society-acceptance":
                from skeleton.developer.jeeves_game_director_society_acceptance import prove
                if not args.source:
                    raise ValueError("NPC acceptance requires --source")
                return prove(root, source=args.source)
            if args.action == "director-society-stress":
                from skeleton.developer.jeeves_game_director_society_stress import stress
                if not args.source:
                    raise ValueError("NPC stress requires --source")
                return stress(root, source=args.source,
                              routes=args.routes if args.routes is not None else 4,
                              intensity=args.intensity if args.intensity is not None else 3)
            if args.action in {"director-society-design",
                               "director-society-publish", "director-society-audit"}:
                if not args.source:
                    raise ValueError("original NPC society requires --source")
                if args.action == "director-society-audit":
                    from skeleton.developer.jeeves_game_director_society_audit import audit
                    return audit(root, source=args.source)
                from skeleton.developer.jeeves_game_director_society_author import preview, publish
                level = args.intensity if args.intensity is not None else 3
                if args.action == "director-society-design":
                    return preview(root, source=args.source, intensity=level)
                return publish(root, source=args.source, intensity=level,
                               approved_sha256=args.approve)
            if args.action in {"dragon-society-study", "dragon-society-contrast"}:
                from skeleton.developer.jeeves_game_dragon_society import queue, compare
                if not args.session:
                    raise ValueError("Dragon NPC study requires --session")
                if args.action == "dragon-society-contrast":
                    if not args.other_session:
                        raise ValueError("Dragon society comparison requires --other-session")
                    return compare(root, first=args.session, second=args.other_session)
                return queue(root, session=args.session, approved_sha256=args.approve)
            if args.action == "director-dynamics-playthrough":
                from skeleton.developer.jeeves_game_director_dynamic_playthrough import prove
                if not args.source:
                    raise ValueError("living campaign proof requires --source")
                return prove(root, source=args.source,
                             routes=args.routes if args.routes is not None else 3,
                             optional=args.include_optional)
            if args.action in {"dragon-world-study", "dragon-world-contrast"}:
                from skeleton.developer.jeeves_game_dragon_world import queue, compare
                if not args.session:
                    raise ValueError("Dragon world research requires --session")
                if args.action == "dragon-world-contrast":
                    if not args.other_session:
                        raise ValueError("Dragon world contrast requires --other-session")
                    return compare(root, first=args.session, second=args.other_session)
                return queue(root, session=args.session, approved_sha256=args.approve)
            if args.action in {"director-dynamics-design",
                               "director-dynamics-publish", "director-dynamics-audit"}:
                if not args.source:
                    raise ValueError("dynamic-world authoring requires --source")
                if args.action == "director-dynamics-audit":
                    from skeleton.developer.jeeves_game_director_dynamic_audit import audit
                    return audit(root, source=args.source)
                from skeleton.developer.jeeves_game_director_dynamic_author import (
                    preview, publish,
                )
                complexity = args.intensity if args.intensity is not None else 3
                if args.action == "director-dynamics-design":
                    return preview(root, source=args.source, intensity=complexity)
                return publish(root, source=args.source, intensity=complexity,
                               approved_sha256=args.approve)
            if args.action == "dragon-navigation-study":
                from skeleton.developer.jeeves_game_dragon_navigation import queue
                if not args.session:
                    raise ValueError("Dragon navigation review requires --session")
                return queue(root, session=args.session, approved_digest=args.approve)
            if args.action in {"director-route", "director-topology"}:
                from skeleton.developer.jeeves_game_director_labyrinth import plan, topology
                if args.action == "director-topology":
                    if not args.source:
                        raise ValueError("director-topology requires --source")
                    return topology(root, source=args.source)
                if not args.session:
                    raise ValueError("director-route requires --session")
                return plan(root, session=args.session, destination=args.destination,
                            profile=args.route_profile or "fastest",
                            alternatives=args.alternatives if args.alternatives is not None else 3)
            if args.action in {"director-causality", "director-story-contrast"}:
                from skeleton.developer.jeeves_game_director_causality import audit, contrast
                if not args.session:
                    raise ValueError("causal study requires --session")
                if args.action == "director-story-contrast":
                    if not args.other_session:
                        raise ValueError("story contrast needs --other-session")
                    return contrast(root, first=args.session, second=args.other_session)
                return audit(root, session=args.session,
                             page=args.page if args.page is not None else 1,
                             page_size=args.page_size if args.page_size is not None else 100)
            if args.action == "director-serve":
                from skeleton.developer.jeeves_game_director_bridge import serve
                if not args.session:
                    raise ValueError("director-serve requires --session")
                return serve(root, session=args.session,
                             port=args.port if args.port is not None else 8765,
                             policy_digest=args.digest)
            if args.action in {"dragon-policy-preview", "dragon-policy-train",
                               "dragon-policy-predict"}:
                from skeleton.developer.jeeves_game_dragon_policy import preview, train, predict
                if args.action == "dragon-policy-predict":
                    if not args.session or not args.digest:
                        raise ValueError("policy prediction needs --session and --digest")
                    return predict(root, session=args.session, digest=args.digest)
                if not args.sessions:
                    raise ValueError("Dragon policy fitting needs --sessions a,b,c")
                if args.action == "dragon-policy-preview":
                    return preview(root, sessions=args.sessions)
                return train(root, sessions=args.sessions, approved_digest=args.approve)
            if args.action == "dragon-lab":
                from skeleton.developer.jeeves_game_dragon_lab import queue
                if not args.sessions:
                    raise ValueError("Dragon comparative lab requires --sessions a,b,...")
                return queue(root, sessions=args.sessions, approved_sha256=args.approve)
            if args.action == "director-native-http-e2e":
                from skeleton.developer.jeeves_game_director_native_e2e import accept
                if not args.source:
                    raise ValueError("director-native-http-e2e requires --source")
                return accept(root, source=args.source,
                              timeout=args.timeout if args.timeout is not None else 90.0)
            if args.action == "director-loopback-e2e":
                from skeleton.developer.jeeves_game_director_e2e import run
                if not args.source:
                    raise ValueError("director-loopback-e2e requires --source")
                return run(root, source=args.source,
                           routes=args.routes if args.routes is not None else 2)
            if args.action == "director-godot-smoke":
                from skeleton.developer.jeeves_game_director_godot_smoke import smoke
                if not args.source:
                    raise ValueError("director-godot-smoke requires --source")
                return smoke(root, source=args.source,
                             timeout=args.timeout if args.timeout is not None else 90.0)
            if args.action == "director-coverage":
                from skeleton.developer.jeeves_game_director_coverage import coverage
                if not args.source:
                    raise ValueError("director-coverage requires --source")
                return coverage(root, source=args.source,
                                routes=args.routes if args.routes is not None else 3)
            if args.action in {"director-session-fork", "director-session-trace"}:
                from skeleton.developer.jeeves_game_director_branch import fork, trace
                if not args.session:
                    raise ValueError("Director history requires --session")
                if args.action == "director-session-trace":
                    return trace(root, session=args.session, tail=(
                        args.tail if args.tail is not None else 64))
                if args.at is None or not args.other_session:
                    raise ValueError("Director fork requires --at and --other-session")
                return fork(root, session=args.session, new_session=args.other_session,
                            at=args.at, approved_head=args.approve)
            if args.action.startswith("director-session-"):
                from skeleton.developer.jeeves_game_director_session import begin, inspect, choose, compare
                if not args.session:
                    raise ValueError("interactive Director session requires --session")
                if args.action == "director-session-begin":
                    if not args.source:
                        raise ValueError("new Director session needs --source")
                    return begin(root, source=args.source, session=args.session)
                if args.action == "director-session-status":
                    return inspect(root, session=args.session)
                if args.action == "director-session-step":
                    if not args.choice:
                        raise ValueError("Director move needs --choice kind:key")
                    return choose(root, session=args.session, choice=args.choice)
                if not args.other_session:
                    raise ValueError("compare needs --other-session")
                return compare(root, first=args.session, second=args.other_session)
            if args.action in {"director-atlas-export", "director-atlas-verify"}:
                from skeleton.developer.jeeves_game_director_atlas import export, verify
                if not args.source:
                    raise ValueError("Godot scene atlas requires --source")
                if args.action == "director-atlas-export":
                    return export(root, source=args.source, dry_run=args.dry_run)
                return verify(root, source=args.source)
            if args.action in {"director-bindings", "director-bindings-publish",
                               "director-bindings-check"}:
                from skeleton.developer.jeeves_game_director_bindings import preview, publish, check
                if not args.source:
                    raise ValueError("Director bindings require --source")
                if args.action == "director-bindings":
                    return preview(root, source=args.source)
                if args.action == "director-bindings-publish":
                    return publish(root, source=args.source, approved_digest=args.approve)
                if not args.digest:
                    raise ValueError("binding check needs --digest")
                return check(root, source=args.source, digest=args.digest)
            from skeleton.developer.jeeves_game_dragon_session import enqueue
            if not args.session:
                raise ValueError("Dragon session lesson requires --session")
            return enqueue(root, session=args.session, approved_digest=args.approve)
        if any(value is not None for value in (args.session, args.sessions, args.other_session, args.choice, args.port, args.timeout, args.at, args.tail, args.destination, args.route_profile, args.alternatives, args.intensity)):
            raise ValueError("runtime options require a director-session or dragon-session action")
        director_actions = {"director-draft", "director-revise", "director-examine", "director-promote",
                            "director-board", "director-prepare-training"}
        if args.action in director_actions:
            allowed = {
                "director-draft": {"action", "seed", "regions", "quest_types", "stages", "goal", "dragon_digest"},
                "director-revise": {"action", "source", "revision"},
                "director-examine": {"action", "source", "routes"},
                "director-promote": {"action", "source", "routes", "approve"},
                "director-board": {"action", "source", "routes", "dragon_digest"},
                "director-prepare-training": {"action", "source", "routes", "dragon_digest", "approve"},
            }[args.action]
            for key, value in vars(args).items():
                if key not in allowed and value is not None and value is not False:
                    raise ValueError("unrelated Director production option --" + key.replace("_", "-"))
            if args.action == "director-draft":
                from skeleton.developer.jeeves_game_director_factory import draft
                if args.seed is None:
                    raise ValueError("director-draft requires --seed")
                return draft(root, seed=args.seed, regions=args.regions,
                             quest_types=args.quest_types,
                             stages=args.stages if args.stages is not None else 3,
                             goal=args.goal, dragon_digest=args.dragon_digest)
            if not args.source:
                raise ValueError("Director production commands require --source")
            if args.action == "director-revise":
                from skeleton.developer.jeeves_game_director_revision import revise
                if not args.revision:
                    raise ValueError("director-revise requires --revision design/<file>.json")
                return revise(root, source=args.source, revision=args.revision)
            if args.action in {"director-examine", "director-promote"}:
                from skeleton.developer.jeeves_game_director_factory import examine, promote
                if args.action == "director-examine":
                    return examine(root, source=args.source,
                                   routes=args.routes if args.routes is not None else 3)
                return promote(root, source=args.source, approved_digest=args.approve,
                               routes=args.routes if args.routes is not None else 3)
            from skeleton.developer.jeeves_game_production_board import board, prepare_dragon_research
            if args.action == "director-board":
                return board(root, source=args.source,
                             routes=args.routes if args.routes is not None else 3,
                             dragon_digest=args.dragon_digest)
            return prepare_dragon_research(
                root, source=args.source,
                routes=args.routes if args.routes is not None else 3,
                dragon_digest=args.dragon_digest, approve=args.approve)
        if any(value is not None for value in (
                args.seed, args.regions, args.revision, args.quest_types, args.stages, args.goal, args.routes)):
            raise ValueError("Director forge options require a director-* action")
        if args.dragon_digest is not None and args.action != "propose":
            raise ValueError("--dragon-digest only supports proposal authoring")
        if args.action in {"dragon-review", "dragon-portfolio", "dragon-ingest", "dragon-plan", "dragon-adopt"}:
            allowed = ({"action", "source", "approve"} if args.action == "dragon-ingest"
                       else {"action", "source", "genre", "target", "approve"}
                       if args.action == "dragon-adopt"
                       else {"action", "source", "genre", "target"} if args.action == "dragon-plan"
                       else {"action", "source"})
            for key, value in vars(args).items():
                if key not in allowed and value is not None and value is not False:
                    raise ValueError("unrelated Dragon option --" + key.replace("_", "-"))
            if not args.source:
                raise ValueError("Dragon observation source requires --source design/<file>.json")
            from skeleton.developer.jeeves_game_dragon import review, portfolio, ingest, plan, adopt
            if args.action == "dragon-review":
                return review(root, source=args.source)
            if args.action == "dragon-portfolio":
                return portfolio(root, source=args.source)
            if args.action == "dragon-ingest":
                return ingest(root, source=args.source, approved_sha256=args.approve)
            if not args.genre or not args.target:
                raise ValueError("Dragon game forge needs --genre and --target")
            if args.action == "dragon-plan":
                return plan(root, source=args.source, genre=args.genre, target=args.target)
            return adopt(root, source=args.source, genre=args.genre, target=args.target,
                         approved_sha256=args.approve)
        from skeleton.developer.jeeves_game_world_cli import ACTIONS, dispatch
        if args.action in ACTIONS:
            output = dispatch(args, root)
            output["ok"] = bool(output.get("ok", True))
            return output
        if args.action in ("direction-audit", "direction-workorder", "production-gap-matrix"):
            allowed = {"action", "source", "passes"} if args.action != "production-gap-matrix" else {"action"}
            for key, value in vars(args).items():
                if key not in allowed and value is not None and value is not False:
                    raise ValueError("unrelated director option --" + key.replace("_", "-"))
            if args.action == "production-gap-matrix":
                from skeleton.developer.jeeves_game_production_gaps import gaps
                return gaps(root)
            from skeleton.developer.jeeves_game_quality import _read
            from skeleton.developer.jeeves_game_direction import audit, workorder, SCHEMA as DIRECTION_SCHEMA
            from skeleton.developer.jeeves_game_direction_cli import SCHEMA as LEGACY_DIRECTION_SCHEMA, direction
            source = args.source or "design/direction_manifest.json"
            passes = args.passes if args.passes is not None else 1
            if type(passes) is not int or not 1 <= passes <= 8:
                raise ValueError("director scrutiny supports 1..8 passes per invocation")
            dossier, _ = _read(root, source, 16 * 1024 * 1024)
            if dossier.get("schema") == LEGACY_DIRECTION_SCHEMA:
                return direction(
                    root, action="direction-audit" if args.action == "direction-audit"
                    else "direction-revision", source=source, passes=passes)
            if dossier.get("schema") != DIRECTION_SCHEMA:
                raise ValueError("unsupported story direction source schema")
            result = None
            identity = None
            for _ in range(passes):
                current = audit(root, source=source) if args.action == "direction-audit" else workorder(root, source=source)
                observed = current.get("manifest_sha256", current.get("source_sha256"))
                if identity is not None and observed != identity:
                    raise ValueError("narrative source changed during multi-pass scrutiny")
                identity = observed
                result = current
            result["source_scrutiny_passes"] = passes
            result["independent_review_performed_by_replays"] = False
            return result
        world_args = (args.pattern, args.frames, args.frame_height, args.richness,
                      args.focus, args.pan, args.distance, args.ambience,
                      args.depth, args.yaw, args.pitch, args.parallax_planes)
        if any(x is not None for x in world_args):
            raise ValueError("multidomain upscale options require an upscale studio action")
        display_args = (args.native_width, args.native_height, args.screen_width,
                        args.screen_height, args.pixel_aspect_num, args.pixel_aspect_den)
        quality_args = (args.console, args.genre, args.period, args.profile, args.evidence)
        if args.direction_source is not None and args.action != "propose":
            raise ValueError("--direction-source only supports proposal authoring")
        render_args = (args.target, args.source, args.output, args.mode, args.factor,
                       args.dry_run, args.passes, args.gate, args.repair_generated,
                       args.page, args.page_size,
                       *display_args)
        other_content = (args.kind, args.brief, args.digest, args.approve,
                         args.include_notes, args.profile, args.evidence)
        if args.action == "direction-benchmark":
            if not args.source:
                raise ValueError("direction-benchmark requires --source design/story_reference_cohorts.json")
            if any((args.kind, args.brief, args.include_notes, args.digest, args.approve,
                    *quality_args, args.target, args.output, args.mode, args.factor,
                    args.dry_run, args.passes, args.gate, args.repair_generated,
                    args.page, args.page_size, *display_args)):
                raise ValueError("direction-benchmark accepts --source only")
            from skeleton.developer.jeeves_game_direction_cli import benchmark
            output = benchmark(root, source=args.source)
        elif args.action == "direction-campaign":
            if not args.source:
                raise ValueError("direction-campaign requires --source design/director_campaign_source.json")
            if any((args.kind, args.brief, args.include_notes, args.digest, args.approve,
                    *quality_args, args.target, args.mode, args.factor,
                    args.dry_run, args.gate, args.repair_generated, args.page,
                    args.page_size, *display_args)):
                raise ValueError("direction-campaign accepts --source, --passes and optional --output save prefix")
            from skeleton.developer.jeeves_game_direction_cli import campaign
            output = campaign(root, source=args.source,
                              routes=args.passes if args.passes is not None else 2,
                              save_prefix=args.output)
        elif args.action == "direction-campaign-reopen":
            if not args.source or not args.output or any((
                    args.kind, args.brief, args.include_notes, args.digest, args.approve,
                    *quality_args, args.target, args.mode, args.factor,
                    args.dry_run, args.passes, args.gate, args.repair_generated,
                    args.page, args.page_size, *display_args)):
                raise ValueError("direction-campaign-reopen requires --source and --output save identity only")
            from skeleton.developer.jeeves_game_direction_cli import reopen_campaign
            output = reopen_campaign(root, source=args.source, save_name=args.output)
        elif args.action == "p0-acceptance":
            if any((args.source, args.passes, args.kind, args.brief, args.include_notes,
                    args.digest, args.approve, *quality_args, args.target, args.output,
                    args.mode, args.factor, args.dry_run, args.gate,
                    args.repair_generated, args.page, args.page_size, *display_args)):
                raise ValueError("p0-acceptance accepts --project only")
            from skeleton.developer.jeeves_game_p0_acceptance import assess_p0
            output = assess_p0(root)
        elif args.action == "direction-gameplay":
            if not args.source:
                raise ValueError("direction-gameplay needs --source design/story_gameplay_dossier.json")
            if any((args.kind, args.brief, args.include_notes, args.digest, args.approve,
                    *quality_args, args.target, args.output, args.mode, args.factor,
                    args.dry_run, args.gate, args.repair_generated, args.page,
                    args.page_size, *display_args)):
                raise ValueError("direction-gameplay accepts --source and --passes only")
            from skeleton.developer.jeeves_game_direction_cli import gameplay
            output = gameplay(root, source=args.source,
                              passes=args.passes if args.passes is not None else 3)
        elif args.action == "direction-shots":
            if not args.source:
                raise ValueError("direction-shots needs --source design/story_direction_packet.json")
            if any((args.kind, args.brief, args.include_notes, args.digest, args.approve,
                    *quality_args, args.target, args.output, args.mode, args.factor,
                    args.dry_run, args.gate, args.repair_generated, args.page,
                    args.page_size, *display_args)):
                raise ValueError("direction-shots accepts --source and --passes only")
            from skeleton.developer.jeeves_game_direction_cli import cinematic
            output = cinematic(root, source=args.source,
                               passes=args.passes if args.passes is not None else 3)
        elif args.action in {"direction-audit", "direction-revision"}:
            if not args.source:
                raise ValueError("direction-audit/revision require --source design/story_direction_packet.json")
            if any((args.kind, args.brief, args.include_notes, args.digest, args.approve,
                    *quality_args, args.target, args.output, args.mode, args.factor,
                    args.dry_run, args.gate, args.repair_generated, args.page,
                    args.page_size, *display_args)):
                raise ValueError("direction review accepts --source and --passes only")
            from skeleton.developer.jeeves_game_direction_cli import direction
            output = direction(root, action=args.action, source=args.source,
                               passes=args.passes if args.passes is not None else 3)
        elif args.action in {"production-init", "production-status", "production-cycle",
                           "production-training"}:
            from skeleton.developer.jeeves_game_production import init, status, cycle, training_candidates
            if args.action == "production-init":
                if not args.target or not args.genre or not args.period or any((
                    *other_content, args.console, args.source, args.output, args.mode,
                    args.factor, args.dry_run, args.passes, args.gate, args.repair_generated,
                    args.page, args.page_size, *display_args
                )):
                    raise ValueError("production-init requires --target --genre --period only")
                output = init(root, target=args.target, genre=args.genre, period=args.period)
            elif args.action == "production-status":
                if any((*other_content, *quality_args, *render_args)):
                    raise ValueError("production-status accepts --project only")
                output = status(root)
            elif args.action == "production-training":
                if any((*other_content, *quality_args, args.target, args.source,
                        args.output, args.mode, args.factor, args.dry_run, args.passes,
                        args.gate, args.repair_generated, *display_args)):
                    raise ValueError("production-training accepts --page and --page-size only")
                output = training_candidates(
                    root, page=args.page if args.page is not None else 0,
                    page_size=args.page_size if args.page_size is not None else 64)
            else:
                if any((*other_content, *quality_args, args.target, args.source, args.output,
                        args.mode, args.factor, args.dry_run, args.page, args.page_size,
                        *display_args)):
                    raise ValueError("production-cycle accepts --passes and optional --gate only")
                output = cycle(root, passes=args.passes if args.passes is not None else 1, gate=args.gate,
                               repair_generated=args.repair_generated)
        elif args.action == "render-reference":
            if not args.target or not args.source or not args.output:
                raise ValueError("render-reference requires --target --source --output")
            if any((*other_content, *quality_args, args.mode, args.factor, args.passes,
                    args.gate, args.repair_generated, args.page, args.page_size,
                    *display_args)):
                raise ValueError("render-reference accepts --target, --source, --output and --dry-run only")
            from skeleton.developer.jeeves_game_render import render_reference
            output = render_reference(
                root, source=args.source, output=args.output,
                target=args.target, dry_run=args.dry_run)
        elif args.action in {"fidelity-plan", "fidelity-matrix", "display-plan", "upscale", "upscale-verify"}:
            from skeleton.developer.jeeves_game_upscale import fidelity_plan, fidelity_matrix, display_plan, upscale, verify_upscale
            if args.action == "fidelity-matrix":
                if any((*other_content, *quality_args, *render_args)):
                    raise ValueError("fidelity-matrix accepts --project only")
                output = fidelity_matrix()
            else:
                if not args.target or any((*other_content, *quality_args,
                                           args.gate, args.repair_generated, args.page,
                                           args.page_size)) or (
                    args.passes is not None and args.action != "upscale-verify"
                ):
                    raise ValueError("fidelity commands require --target without unrelated options")
                if args.action == "fidelity-plan":
                    if any((args.source, args.output, args.mode, args.factor, args.dry_run,
                            *display_args)):
                        raise ValueError("fidelity-plan accepts --target only")
                    output = fidelity_plan(args.target)
                elif args.action == "display-plan":
                    if any((args.source, args.output, args.mode, args.factor, args.dry_run)):
                        raise ValueError("display-plan does not emit any render file")
                    if any(x is None for x in display_args[:4]):
                        raise ValueError("display-plan requires native and screen width/height")
                    output = display_plan(
                        target=args.target, native_width=args.native_width,
                        native_height=args.native_height, screen_width=args.screen_width,
                        screen_height=args.screen_height,
                        pixel_aspect_num=args.pixel_aspect_num if args.pixel_aspect_num is not None else 1,
                        pixel_aspect_den=args.pixel_aspect_den if args.pixel_aspect_den is not None else 1,
                    )
                else:
                    if any(display_args):
                        raise ValueError("upscale accepts source/output rather than display geometry")
                    if not args.source or not args.output:
                        raise ValueError("upscale requires --source --output under assets/")
                    if args.action == "upscale-verify":
                        if args.dry_run:
                            raise ValueError("upscale-verify is read-only and does not need --dry-run")
                        output = verify_upscale(root, source=args.source, output=args.output,
                                                target=args.target, mode=args.mode or "nearest",
                                                factor=args.factor if args.factor is not None else 2,
                                                passes=args.passes if args.passes is not None else 3)
                    else:
                        output = upscale(root, source=args.source, output=args.output,
                                         target=args.target, mode=args.mode or "nearest",
                                         factor=args.factor if args.factor is not None else 2,
                                         dry_run=args.dry_run)
        elif args.action == "benchmark-matrix":
            if any((args.kind, args.brief, args.digest, args.approve, args.include_notes,
                    args.console, args.genre, args.period, args.evidence, *render_args)):
                raise ValueError("benchmark-matrix accepts --profile only")
            from skeleton.developer.jeeves_game_quality import benchmark_matrix
            output = benchmark_matrix(root, profile=args.profile or "design/market_benchmarks.json")
        elif args.action in {"benchmark", "asset-gate"}:
            if any(render_args):
                raise ValueError("quality evidence checks do not use production/fidelity options")
            if not all((args.console, args.genre, args.period)):
                raise ValueError("benchmark needs --console, --genre, --period")
            if any((args.kind, args.brief, args.digest, args.approve, args.include_notes)):
                raise ValueError("unsupported game quality gate option")
            from skeleton.developer.jeeves_game_quality import rank_cohort, gate_render_asset
            if args.action == "benchmark":
                if args.evidence:
                    raise ValueError("benchmark does not use --evidence")
                output = rank_cohort(root, console=args.console, genre=args.genre,
                                     period=args.period,
                                     profile=args.profile or "design/market_benchmarks.json")
                output["action"] = "benchmark"
                output["ok"] = output["eligible_for_inspiration"]
            else:
                if not args.evidence:
                    raise ValueError("asset-gate requires --evidence")
                output = gate_render_asset(
                    root, console=args.console, genre=args.genre, period=args.period,
                    profile=args.profile or "design/market_benchmarks.json",
                    evidence=args.evidence,
                )
        elif args.action in {"propose", "review", "apply", "queue"}:
            if any(render_args):
                raise ValueError("model draft actions do not use production/fidelity options")
            from skeleton.developer.jeeves_game_authoring import propose, review, apply, queue
            if args.action == "queue":
                if any((args.kind, args.brief, args.digest, args.approve, args.include_notes,
                        *quality_args, *render_args)):
                    raise ValueError("queue takes no proposal selection options")
                output = queue(root)
            elif args.action == "propose":
                if args.kind is None or args.brief is None or args.digest or args.approve or args.evidence:
                    raise ValueError("propose requires --kind and --brief; cannot include digest/approval/evidence")
                output = propose(
                    root, kind=args.kind, brief=args.brief, include_notes=args.include_notes,
                    console=args.console, genre=args.genre, period=args.period,
                    profile=args.profile or "design/market_benchmarks.json",
                    direction_source=args.direction_source, dragon_digest=args.dragon_digest,
                )
            elif args.action == "review":
                if not args.digest or any((args.kind, args.brief, args.approve, args.include_notes,
                                           *quality_args, *render_args)):
                    raise ValueError("review requires --digest only")
                output = review(root, args.digest)
            else:
                if not args.digest or not args.approve or any((args.kind, args.brief,
                                                               args.include_notes, *quality_args, *render_args)):
                    raise ValueError("apply requires --digest and --approve only")
                output = apply(root, digest=args.digest, approved_digest=args.approve)
        elif args.action == "plan":
            if any((args.kind, args.brief, args.digest, args.approve, args.include_notes,
                    *quality_args, *render_args)):
                raise ValueError("unused Jeeves options")
            output = _plan(root)
        elif args.action == "audit":
            if any((args.kind, args.brief, args.digest, args.approve, args.include_notes,
                    *quality_args, *render_args)):
                raise ValueError("unused Jeeves options")
            output = _audit(root)
        elif args.action == "context":
            if any((args.kind, args.brief, args.digest, args.approve, args.include_notes,
                    *quality_args, *render_args)):
                raise ValueError("unused Jeeves options")
            cfg, _ = _context(root)
            notes = _notes(root)
            output = {"schema": SCHEMA, "action": "context", "project": str(root),
                      "vision": cfg["vision"], "era": cfg["era"], "notes": notes,
                      "notes_sha256": _digest([{k: v for k, v in n.items() if k != "excerpt"}
                                               for n in notes])}
        else:
            if any((args.kind, args.brief, args.digest, args.approve, args.include_notes,
                    *quality_args, *render_args)):
                raise ValueError("unused Jeeves options")
            planned, audited = _plan(root), _audit(root)
            recs = _recommendations(planned["plan"], audited)
            output = {"schema": SCHEMA, "action": args.action, "project": str(root),
                      "plan_sha256": planned["plan_sha256"],
                      "recommendations": recs,
                      "blocking": audited["blocking"], "production_qualified": False}
            if args.action == "handoff":
                ctx = _notes(root)
                output["project_vision"] = planned["vision"]
                output["era"] = planned["era"]
                output["design_notes"] = [{k: v for k, v in n.items() if k != "excerpt"} for n in ctx]
                output["source_sha256"] = audited["source_sha256"]
                output["plan"] = planned["plan"]
                output["checks"] = audited["checks"]
        output["ok"] = bool(output.get("ok", True))
        return output
    except (OSError, ValueError) as exc:
        return {"schema": SCHEMA, "action": args.action, "ok": False,
                "project": str(root), "error": str(exc)}
