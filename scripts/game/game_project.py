"""Standalone legal-first, cross-era game project authoring CLI.

Usage (repo root):
  python scripts/game/game_project.py --catalog
  python scripts/game/game_project.py --demo-project demo.json --targets nes-famicom,playstation-5
  python scripts/game/game_project.py --verify-capsule demo.json
  python scripts/game/game_project.py --plan target-requests.json
  python scripts/game/game_project.py --compose project-input.json --output new.json

No SDK/BIOS/firmware/ROM downloads, subprocesses, external assets,
model inference or training data are used.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat
import sys
from typing import Any, Sequence

from skeleton.ai.runtime.game_platform_catalog import (
    GamePlatformError, catalog_summary, plan_game_targets,
)
from skeleton.ai.runtime.game_rights import GameRightsError, SCHEMA as RIGHTS_SCHEMA
from skeleton.ai.runtime.game_project_capsule import (
    GameCapsuleError, make_game_capsule, verify_game_capsule,
)
from skeleton.ai.runtime.gameplay_capabilities import (
    GameplayError, compile_level, generate_level,
)
from skeleton.ai.runtime.game_play_session import (
    GamePlaySessionError, start_play_session, resume_play_session,
    verify_play_session, render_play_session, render_play_frame,
    fork_play_session, compare_play_sessions, render_play_comparison_frame,
    inspect_play_trace,
)
from skeleton.ai.runtime.game_play_bundle import (
    GamePlayBundleError, pack_play_bundle, verify_play_bundle,
    resume_play_bundle, fork_play_bundle,
)
from skeleton.ai.runtime.game_play_terminal import run_terminal_play
from skeleton.ai.runtime.game_input_profile import validate_terminal_input_profile
from skeleton.ai.runtime.game_play_challenge import (
    GameChallengeError, pack_play_score, verify_play_score,
    rank_play_scores, verify_play_board,
)
from skeleton.ai.runtime.game_play_quest import (
    GameQuestError, pack_quest_overlay, verify_quest_overlay,
)

MAX_INPUT_BYTES = 96 * 1024
MAX_RESULT_BYTES = 160 * 1024


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    found: dict[str, Any] = {}
    for key, value in items:
        if key in found:
            raise GameCapsuleError("duplicate game project JSON property")
        found[key] = value
    return found


def _nonfinite(_: str) -> None:
    raise GameCapsuleError("nonfinite game project numbers are inadmissible")


def _read_json(path: Path, *, max_bytes: int = MAX_INPUT_BYTES) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise GameCapsuleError("game input must be an existing regular local file")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > max_bytes:
            raise GameCapsuleError("game project input exceeded local file budget")
        data = stream.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise GameCapsuleError("game project input exceeded local file budget")
    try:
        value = json.loads(
            data.decode("utf-8", "strict"),
            object_pairs_hook=_pairs, parse_constant=_nonfinite,
        )
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise GameCapsuleError("game project JSON is malformed") from exc
    if not isinstance(value, dict):
        raise GameCapsuleError("game project JSON must be an object")
    return value


def _write_new(path: Path, result: dict[str, Any]) -> str:
    raw = (
        json.dumps(
            result, sort_keys=True, separators=(",", ":"),
            ensure_ascii=True, allow_nan=False,
        ) + "\n"
    ).encode("ascii")
    if len(raw) > MAX_RESULT_BYTES:
        raise GameCapsuleError("game project output exceeds 160-KiB cap")
    target = path.expanduser().absolute()
    if target.exists() or target.is_symlink() or not target.parent.is_dir():
        raise GameCapsuleError("project output must be a new file in an existing directory")
    fd = os.open(
        target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    return str(target)


def _demo(seed: int, target_ids: list[str], jurisdiction: str,
          *, width: int = 12, height: int = 9) -> dict[str, Any]:
    generated = generate_level({
        "seed": seed, "width": width, "height": height, "wall_percent": 30,
    })
    level = compile_level({"tiles": generated["tiles"]})
    rights = {
        "schema_version": RIGHTS_SCHEMA,
        "project_id": f"original-demo-{seed}",
        "title": "Original procedural Skeleton game prototype",
        "rights_contact": "local-operator-unverified",
        "assets": [{
            "asset_id": "tilemap",
            "sha256": level["tile_digest"],
            "source_kind": "original",
            "licensor": "local-operator-unverified",
            "license_reference": "original-procedural-generation-v1",
            "allowed_uses": ["embed", "modify", "distribute"],
            "contains_third_party_content": False,
            "contains_trademarks": False,
            "contains_technological_protection": False,
        }],
        "source_game_reference": None,
        "sdk_authorization": None,
    }
    return make_game_capsule(
        source_tiles=generated["tiles"], rights_manifest=rights,
        target_ids=target_ids, required_features=["tile2d", "input"],
        action="original_game", jurisdiction=jurisdiction,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Author legally reviewed game project specifications across eras. No ROM/SDK output.",
    )
    operations = parser.add_mutually_exclusive_group(required=True)
    operations.add_argument("--play-capsule", type=Path,
                            help="execute offline controller frames against a verified original capsule")
    operations.add_argument("--resume-play-session", type=Path,
                            help="verify and append frames to a source-bound saved session")
    operations.add_argument("--verify-play-session", type=Path,
                            help="replay a saved session against its original capsule")
    operations.add_argument("--render-play-session", type=Path,
                            help="show verified offline game state as an ASCII grid")
    operations.add_argument("--terminal-play-capsule", type=Path,
                            help="play an original capsule with accessible turn-by-turn keyboard controls")
    operations.add_argument("--terminal-resume-session", type=Path,
                            help="reopen a verified save and continue offline terminal play")
    operations.add_argument("--inspect-play-frame", type=Path,
                            help="replay and render a verified saved frame without changing it")
    operations.add_argument("--fork-play-session", type=Path,
                            help="create an independent save with alternate inputs at a verified frame")
    operations.add_argument("--compare-play-sessions", type=Path,
                            help="compare two independently verified alternate game histories")
    operations.add_argument("--render-play-comparison", type=Path,
                            help="ASCII overlay of two verified histories at one shared frame")
    operations.add_argument("--inspect-play-trace", type=Path,
                            help="inspect bounded replay-verified simulation frames")
    operations.add_argument("--export-play-bundle", type=Path,
                            help="package a verified original capsule and save for offline transfer")
    operations.add_argument("--verify-play-bundle", type=Path,
                            help="reopen and verify a self-contained offline game bundle")
    operations.add_argument("--resume-play-bundle", type=Path,
                            help="append controller frames to a verified portable bundle")
    operations.add_argument("--fork-play-bundle", type=Path,
                            help="create a portable alternate timeline from a verified bundle")
    operations.add_argument("--score-play-session", type=Path,
                            help="score a real source-bound game save against local challenge rules")
    operations.add_argument("--verify-play-score", type=Path,
                            help="replay and verify a portable local challenge score")
    operations.add_argument("--rank-play-scores", action="store_true",
                            help="rank up to eight verified local challenge scores")
    operations.add_argument("--verify-play-board", type=Path,
                            help="replay and verify every entry of an offline challenge board")
    operations.add_argument("--play-quest-overlay", type=Path,
                            help="replay a game save with authored pickups, crafting and quests")
    operations.add_argument("--verify-quest-overlay", type=Path,
                            help="verify and reopen a source-bound offline quest save")
    operations.add_argument("--catalog", action="store_true",
                            help="catalog targets, not fictional native build support")
    operations.add_argument("--plan", type=Path,
                            help="JSON file: target_ids, required_features, optional sdk_authorizations")
    operations.add_argument("--compose", type=Path,
                            help="JSON project: source_tiles, rights_manifest, action, jurisdiction, targets, edits")
    operations.add_argument("--verify-capsule", type=Path,
                            help="verify portable project and recalculate scene digests")
    operations.add_argument("--demo-project", type=Path,
                            help="write a new small original portable game capsule")
    parser.add_argument("--terminal-input-profile", type=Path,
                        help="strict local JSON keymap for accessible offline terminal controls")
    parser.add_argument("--terminal-max-frames", type=int,
                        help="terminal frames this invocation (1-64, default 32)")
    parser.add_argument("--trace-start", type=int,
                        help="inclusive one-based first frame of a verified trace window")
    parser.add_argument("--trace-end", type=int,
                        help="inclusive one-based final frame of a verified trace window")
    parser.add_argument("--at-frame", type=int,
                        help="zero-based replay seek/fork frame; zero is the original spawn")
    parser.add_argument("--controls-file", type=Path,
                        help="JSON object containing a bounded controls array")
    parser.add_argument("--session-capsule", type=Path,
                        help="original capsule for session resume/verification")
    parser.add_argument("--other-session", type=Path,
                        help="second saved history for --compare-play-sessions")
    parser.add_argument("--save-session", type=Path,
                        help="write a new exclusive offline session JSON file")
    parser.add_argument("--bundle-output", type=Path,
                        help="exclusive new output for a portable play bundle")
    parser.add_argument("--challenge-policy", type=Path,
                        help="strict JSON scoring rules for --score-play-session")
    parser.add_argument("--score-output", type=Path,
                        help="exclusive new score receipt output")
    parser.add_argument("--score-input", type=Path, action="append",
                        help="repeat for each verified score to rank (maximum eight)")
    parser.add_argument("--board-output", type=Path,
                        help="exclusive new offline challenge board output")
    parser.add_argument("--quest-manifest", type=Path,
                        help="source-bound authored collectibles, recipes and quests")
    parser.add_argument("--quest-actions", type=Path,
                        help="per-frame craft and claim decisions for verified gameplay")
    parser.add_argument("--quest-output", type=Path,
                        help="exclusive new quest overlay save")
    parser.add_argument("--output", type=Path,
                        help="exclusive new file for --compose")
    parser.add_argument("--seed", type=int, default=1729,
                        help="bounded seed for original procedural demo only")
    parser.add_argument("--width", type=int, default=12,
                        help="original game map width 5-32; 5-8 for CHIP-8")
    parser.add_argument("--height", type=int, default=9,
                        help="original game map height 5-32; 5-8 for CHIP-8")
    parser.add_argument("--targets", default="nes-famicom,game-boy,playstation-5,windows-11",
                        help="comma-separated era targets for demo only")
    parser.add_argument("--jurisdiction", default="NO",
                        help="legal review region for original demo; not legal clearance")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    terminal = (args.terminal_play_capsule is not None
                or args.terminal_resume_session is not None)
    playing = any(value is not None for value in (
        args.play_capsule, args.resume_play_session,
        args.verify_play_session, args.render_play_session,
        args.inspect_play_frame, args.fork_play_session,
        args.compare_play_sessions, args.render_play_comparison,
        args.inspect_play_trace,
        args.terminal_play_capsule, args.terminal_resume_session,
        args.score_play_session, args.verify_play_score, args.verify_play_board,
        args.play_quest_overlay, args.verify_quest_overlay,
    )) or args.rank_play_scores
    bundling = any(value is not None for value in (
        args.export_play_bundle, args.verify_play_bundle, args.resume_play_bundle,
        args.fork_play_bundle,
    ))
    seeking = any(value is not None for value in (
        args.inspect_play_frame, args.fork_play_session, args.fork_play_bundle,
        args.render_play_comparison,
    ))
    comparing = args.compare_play_sessions is not None or args.render_play_comparison is not None
    if (args.other_session is not None) != comparing:
        print("--other-session is required only for session comparison", file=sys.stderr)
        return 2
    tracing = args.inspect_play_trace is not None
    if (args.trace_start is not None or args.trace_end is not None) != tracing:
        print("--trace-start and --trace-end require trace inspection", file=sys.stderr)
        return 2
    if tracing and (args.trace_start is None or args.trace_end is None):
        print("trace inspection requires both frame bounds", file=sys.stderr)
        return 2
    if (seeking != (args.at_frame is not None)):
        print("--at-frame is required only for timeline inspection or forks", file=sys.stderr)
        return 2
    scoring = args.score_play_session is not None
    ranking = args.rank_play_scores
    if ((args.challenge_policy is not None) != scoring
            or (args.score_output is not None) != scoring):
        print("challenge policy and score output require --score-play-session",
              file=sys.stderr)
        return 2
    if (bool(args.score_input) != ranking
            or (args.board_output is not None) != ranking):
        print("score inputs and board output require --rank-play-scores",
              file=sys.stderr)
        return 2
    questing = args.play_quest_overlay is not None
    if any((value is not None) != questing for value in (
        args.quest_manifest, args.quest_actions, args.quest_output,
    )):
        print("quest manifest, actions and output require --play-quest-overlay",
              file=sys.stderr)
        return 2
    if args.terminal_input_profile is not None and not terminal:
        print("--terminal-input-profile requires terminal play", file=sys.stderr)
        return 2
    if (args.terminal_max_frames is not None and not terminal):
        print("--terminal-max-frames requires a terminal play operation", file=sys.stderr)
        return 2
    if (args.terminal_max_frames is not None
            and not 1 <= args.terminal_max_frames <= 64):
        print("terminal frame budget must be between 1 and 64", file=sys.stderr)
        return 2
    if not playing and not bundling and any(value is not None for value in (
        args.controls_file, args.session_capsule, args.save_session, args.bundle_output,
    )):
        print("play-session flags require a play-session operation", file=sys.stderr)
        return 2
    if playing and args.bundle_output is not None:
        print("bundle output requires a bundle operation", file=sys.stderr)
        return 2
    if bundling:
        needs_actions = (args.resume_play_bundle is not None
                         or args.fork_play_bundle is not None)
        needs_source = args.export_play_bundle is not None
        needs_output = args.verify_play_bundle is None
        if (needs_actions != (args.controls_file is not None)
                or needs_source != (args.session_capsule is not None)
                or needs_output != (args.bundle_output is not None)
                or args.save_session is not None):
            print("play-bundle source, controls and output arguments mismatch", file=sys.stderr)
            return 2
    if playing:
        needs_actions = any(value is not None for value in (
            args.play_capsule, args.resume_play_session, args.fork_play_session,
        ))
        needs_output = needs_actions or terminal
        needs_source = (args.play_capsule is None
                        and args.terminal_play_capsule is None)
        if (needs_actions != (args.controls_file is not None)
                or needs_output != (args.save_session is not None)
                or needs_source != (args.session_capsule is not None)):
            print("play-session source, controls and output arguments mismatch", file=sys.stderr)
            return 2
    if args.output is not None and args.compose is None:
        print("--output is supported only for --compose", file=sys.stderr)
        return 2
    if args.compose is not None and args.output is None:
        print("--compose requires --output for a durable new project", file=sys.stderr)
        return 2
    if (args.width != 12 or args.height != 9) and args.demo_project is None:
        print("--width and --height are only for --demo-project", file=sys.stderr)
        return 2
    if args.seed != 1729 and args.demo_project is None:
        print("--seed is only for --demo-project", file=sys.stderr)
        return 2
    if args.targets != "nes-famicom,game-boy,playstation-5,windows-11" and args.demo_project is None:
        print("--targets is only for --demo-project", file=sys.stderr)
        return 2
    try:
        if bundling:
            if args.verify_play_bundle is not None:
                bundle = _read_json(args.verify_play_bundle, max_bytes=MAX_RESULT_BYTES)
                report = verify_play_bundle(bundle)
            elif args.export_play_bundle is not None:
                capsule = _read_json(args.session_capsule)
                session = _read_json(args.export_play_bundle)
                bundle = pack_play_bundle(capsule, session)
                output = _write_new(args.bundle_output, bundle)
                report = {**verify_play_bundle(bundle), "output_path": output}
            else:
                bundle = _read_json(
                    args.resume_play_bundle or args.fork_play_bundle,
                    max_bytes=MAX_RESULT_BYTES,
                )
                actions = _read_json(args.controls_file)
                if set(actions) != {"controls"}:
                    raise GamePlayBundleError("play controls require exactly controls")
                if args.fork_play_bundle is not None:
                    updated = fork_play_bundle(bundle, args.at_frame, actions["controls"])
                else:
                    updated = resume_play_bundle(bundle, actions["controls"])
                output = _write_new(args.bundle_output, updated)
                report = {**verify_play_bundle(updated), "output_path": output}
                if args.fork_play_bundle is not None:
                    report["fork_frame"] = args.at_frame
                    report["forked_from_bundle_sha256"] = bundle["bundle_sha256"]
        elif playing:
            capsule = _read_json(
                args.play_capsule or args.terminal_play_capsule or args.session_capsule,
            )
            if args.play_quest_overlay is not None:
                manifest = _read_json(args.quest_manifest)
                decisions = _read_json(args.quest_actions)
                if set(decisions) != {"actions"}:
                    raise GameQuestError("quest decisions require exactly actions")
                session = _read_json(args.play_quest_overlay)
                overlay = pack_quest_overlay(
                    capsule, session, manifest, decisions["actions"],
                )
                receipt = verify_quest_overlay(capsule, overlay)
                report = {
                    **receipt, "output_path": _write_new(args.quest_output, overlay),
                }
            elif args.verify_quest_overlay is not None:
                overlay = _read_json(args.verify_quest_overlay, max_bytes=MAX_RESULT_BYTES)
                report = verify_quest_overlay(capsule, overlay)
            elif args.score_play_session is not None:
                policy = _read_json(args.challenge_policy, max_bytes=4096)
                saved = _read_json(args.score_play_session)
                score = pack_play_score(capsule, saved, policy)
                receipt = verify_play_score(capsule, score)
                report = {
                    **receipt, "output_path": _write_new(args.score_output, score),
                }
            elif args.verify_play_score is not None:
                score = _read_json(args.verify_play_score, max_bytes=MAX_RESULT_BYTES)
                report = verify_play_score(capsule, score)
            elif args.rank_play_scores:
                scores = [
                    _read_json(candidate, max_bytes=MAX_RESULT_BYTES)
                    for candidate in args.score_input
                ]
                board = rank_play_scores(capsule, scores)
                receipt = verify_play_board(capsule, board)
                report = {
                    **receipt, "output_path": _write_new(args.board_output, board),
                }
            elif args.verify_play_board is not None:
                board = _read_json(args.verify_play_board, max_bytes=MAX_RESULT_BYTES)
                report = verify_play_board(capsule, board)
            elif terminal:
                previous = (
                    _read_json(args.terminal_resume_session)
                    if args.terminal_resume_session is not None else None
                )
                input_profile = (
                    _read_json(args.terminal_input_profile, max_bytes=4096)
                    if args.terminal_input_profile is not None else None
                )
                validate_terminal_input_profile(input_profile)
                terminal_result = run_terminal_play(
                    capsule, previous, sys.stdin, sys.stderr,
                    max_frames=args.terminal_max_frames or 32,
                    input_profile=input_profile,
                )
                session = terminal_result["session"]
                output_path = _write_new(args.save_session, session)
                report = {
                    **{key: value for key, value in terminal_result.items()
                       if key != "session"},
                    "output_path": output_path,
                    "rendered_grid": render_play_session(capsule, session)["grid"],
                }
            elif args.inspect_play_trace is not None:
                report = inspect_play_trace(
                    capsule, _read_json(args.inspect_play_trace),
                    args.trace_start, args.trace_end,
                )
            elif args.render_play_comparison is not None:
                report = render_play_comparison_frame(
                    capsule, _read_json(args.render_play_comparison),
                    _read_json(args.other_session), args.at_frame,
                )
            elif args.compare_play_sessions is not None:
                report = compare_play_sessions(
                    capsule, _read_json(args.compare_play_sessions),
                    _read_json(args.other_session),
                )
            elif args.verify_play_session is not None:
                report = verify_play_session(capsule, _read_json(args.verify_play_session))
            elif args.render_play_session is not None:
                report = render_play_session(capsule, _read_json(args.render_play_session))
            elif args.inspect_play_frame is not None:
                report = render_play_frame(
                    capsule, _read_json(args.inspect_play_frame), args.at_frame,
                )
            else:
                actions = _read_json(args.controls_file)
                if set(actions) != {"controls"}:
                    raise GamePlaySessionError("play controls require exactly controls")
                parent_session = None
                if args.play_capsule is not None:
                    session = start_play_session(capsule, actions["controls"])
                elif args.fork_play_session is not None:
                    parent_session = _read_json(args.fork_play_session)
                    session = fork_play_session(
                        capsule, parent_session, args.at_frame, actions["controls"],
                    )
                else:
                    session = resume_play_session(
                        capsule, _read_json(args.resume_play_session), actions["controls"],
                    )
                output_path = _write_new(args.save_session, session)
                report = {
                    "schema_version": "skeleton.game.play_session.write.v1",
                    "session_sha256": session["session_sha256"],
                    "capsule_sha256": session["capsule_sha256"],
                    "frame_count": session["frame_count"],
                    "victory_frame": session["victory_frame"],
                    "native_export_created": False,
                    "output_path": output_path,
                    "rendered_grid": render_play_session(capsule, session)["grid"],
                }
                if parent_session is not None:
                    report["fork_frame"] = args.at_frame
                    report["forked_from_session_sha256"] = parent_session["session_sha256"]
        elif args.catalog:
            report = catalog_summary()
        elif args.plan:
            body = _read_json(args.plan)
            if set(body) - {"target_ids", "required_features", "sdk_authorizations"}:
                raise GamePlatformError("target planning inputs have extra fields")
            report = plan_game_targets(
                target_ids=body.get("target_ids"),
                required_features=body.get("required_features"),
                sdk_authorizations=body.get("sdk_authorizations"),
            )
        elif args.compose:
            body = _read_json(args.compose)
            if set(body) - {
                "source_tiles", "rights_manifest", "target_ids",
                "required_features", "action", "jurisdiction", "edits",
                "sdk_authorizations",
            }:
                raise GameCapsuleError("game project input contains unknown fields")
            project = make_game_capsule(
                source_tiles=body.get("source_tiles"),
                rights_manifest=body.get("rights_manifest"),
                target_ids=body.get("target_ids"),
                required_features=body.get("required_features"),
                action=body.get("action"),
                jurisdiction=body.get("jurisdiction"),
                edits=body.get("edits"),
                sdk_authorizations=body.get("sdk_authorizations"),
            )
            report = {
                **verify_game_capsule(project),
                "output_path": _write_new(args.output, project) if args.output else None,
                "output_type": "portable_original_game_project_json",
            }
        elif args.demo_project:
            selected = args.targets.split(",")
            project = _demo(args.seed, selected, args.jurisdiction,
                            width=args.width, height=args.height)
            checked = verify_game_capsule(project)
            report = {
                **checked, "output_path": _write_new(args.demo_project, project),
                "requested_target_count": len(selected),
                "source_rights_self_attested": True,
                "no_native_console_binary_created": True,
            }
        else:
            report = verify_game_capsule(_read_json(args.verify_capsule))
        print(json.dumps(report, sort_keys=True, ensure_ascii=True))
        return 0
    except (GameQuestError, GameChallengeError, GamePlayBundleError, GamePlaySessionError, GameCapsuleError, GamePlatformError, GameRightsError,
            GameplayError, ValueError, TypeError, KeyError, OSError) as exc:
        print(
            "cross-era game project rejected: " + type(exc).__name__ + ": " + str(exc),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
