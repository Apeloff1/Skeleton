"""Bounded paginated executable checks for each registered original-game engine.

This is a real runner, not a list of green checks. Every registered action
can be visited in independent pages, using the source-authoritative engine
and replay-verification protocol. Rejections in the initial state are recorded
as rejections, NOT mislabeled successful gameplay. Native renderer/device,
copyright and neural generalization tests are outside these probes.
"""

from __future__ import annotations

import argparse
import base64
import json
from hashlib import sha256

from skeleton.ai.game_builder.advanced_gameplay_runtime import ACTION_HELP, ENGINES
from skeleton.ai.game_builder.system_editors import (
    SystemEditorError,
    make_editor_document,
)

from .game_studio_environment import (
    StudioEnvironmentError,
    StudioGameEnvironment,
    make_studio_source,
    parse_studio_source,
)
from .game_studio_scenario_lab import test_manifest

SCHEMA = "skeleton.game_builder.engine_diagnostics.v1"
MAX_ACTIONS_PER_PAGE = 64


class EngineDiagnosticsError(ValueError):
    """Invalid engine probe bounds or nondeterministic original-game execution."""


def _digest(value):
    return sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False, ensure_ascii=True).encode()
    ).hexdigest()


def engine_action_diagnostics(editor: str, *, offset: int = 0, limit: int = 32, seed: int = 0) -> dict:
    if (
        editor not in ENGINES
        or type(offset) is not int
        or offset < 0
        or (type(limit) is not int or not 1 <= limit <= MAX_ACTIONS_PER_PAGE)
        or type(seed) is not int
        or not 0 <= seed <= 2**31 - 1
    ):
        raise EngineDiagnosticsError("registered engine and bounded probe page required")
    actions = tuple(ACTION_HELP[editor])
    if offset >= len(actions):
        raise EngineDiagnosticsError("action page begins beyond the engine registry")
    probes = []
    for action in actions[offset : offset + limit]:
        source = make_studio_source(editor, actions=(action,))
        first = StudioGameEnvironment(source, max_steps=2)
        replay = StudioGameEnvironment(source, max_steps=2)
        try:
            first.reset(seed)
            _ = replay.reset(seed)
            if first.snapshot() != replay.snapshot():
                raise EngineDiagnosticsError("same-seed initial engine state diverged")
            result = first.step(action)
            second = replay.step(action)
            if first.snapshot() != replay.snapshot() or (
                result.transition_digest != second.transition_digest
            ):
                raise EngineDiagnosticsError("registered control did not replay deterministically")
            snapshot = first.snapshot()
            independent = StudioGameEnvironment(source, max_steps=2)
            try:
                restored = independent.restore(snapshot)
                if restored != dict(result.observation) or independent.snapshot() != snapshot:
                    raise EngineDiagnosticsError("independent control snapshot replay diverged")
            finally:
                independent.close()
            accepted = result.info["evidence"]["accepted"] is True
            probes.append(
                {
                    "action": action,
                    "source_digest": first.source_digest,
                    "accepted_in_initial_state": accepted,
                    "rejected_in_initial_state": not accepted,
                    "reward": round(result.reward, 6),
                    "replay_verified": True,
                    "end_state_digest": snapshot["digest"],
                    "error_type": result.info["evidence"].get("error_type"),
                    "native_hardware_certified": False,
                }
            )
        finally:
            first.close()
            replay.close()
    covered = offset + len(probes)
    report = {
        "schema_version": SCHEMA,
        "engine": editor,
        "source": "actual_original_reference_runtime",
        "start": offset,
        "count": len(probes),
        "registered_action_count": len(actions),
        "next_offset": covered if covered < len(actions) else None,
        "action_protocol_passes": len(probes),
        "accepted_initial_actions": sum(x["accepted_in_initial_state"] for x in probes),
        "rejected_initial_actions": sum(x["rejected_in_initial_state"] for x in probes),
        "page_action_coverage_complete": covered == len(actions) and offset == 0,
        "full_engine_quality_certified": False,
        "matrix": test_manifest(editor)["digest"],
        "action_probes": probes,
    }
    return {**report, "digest": _digest(report)}


def run_engine_contract_diagnostics(editor: str, *, seed: int = 7) -> dict:
    """Actual metadata, invalid source admission and replay checks."""
    if editor not in ENGINES or type(seed) is not int or not 0 <= seed <= 2**31 - 1:
        raise EngineDiagnosticsError("registered editor and stable source seed required")
    source = make_studio_source(editor)
    normalized = parse_studio_source(source)
    if normalized != source:
        raise EngineDiagnosticsError("normalized source unexpectedly differs")
    rejection = False
    try:
        make_editor_document(editor, {"__unregistered_exec_code__": "deny"})
    except SystemEditorError:
        rejection = True
    if not rejection:
        raise EngineDiagnosticsError("undeclared user engine knob was not rejected")
    corrupt = dict(source)
    corrupt["editor"] = "foreign_runtime"
    foreign_rejection = False
    try:
        parse_studio_source(corrupt)
    except StudioEnvironmentError:
        foreign_rejection = True
    if not foreign_rejection:
        raise EngineDiagnosticsError("source identity could be substituted")
    first = StudioGameEnvironment(source, max_steps=2)
    replay = StudioGameEnvironment(source, max_steps=2)
    try:
        first_obs = dict(first.reset(seed))
        second_obs = dict(replay.reset(seed))
        if first_obs != second_obs or first.snapshot() != replay.snapshot():
            raise EngineDiagnosticsError("game initial source is not deterministic")
        snap = first.snapshot()
        restored = replay.restore(snap)
        if restored != first_obs or replay.snapshot() != snap:
            raise EngineDiagnosticsError("source-bound snapshot restore failed")
        frame = first.preview()
        if (
            not isinstance(frame, dict)
            or not frame.get("session_digest")
            or frame.get("source_session_digest") != frame["session_digest"]
            or frame.get("native_hardware_verified") is not False
            or frame.get("real_game_world_framebuffer") is not False
        ):
            raise EngineDiagnosticsError("simulation lied about actual game frame or source")
        if frame.get("render_kind") == "original_reference_scene_projection":
            if frame.get("pixel_frame_available") is not True or not isinstance(frame.get("data_uri"), str):
                raise EngineDiagnosticsError("original reference scene is unavailable")
            uri = frame["data_uri"]
            prefix = "data:image/png;base64,"
            if not uri.startswith(prefix) or len(uri) > 65536:
                raise EngineDiagnosticsError("original reference scene exceeds bounded PNG transport")
            png = base64.b64decode(uri[len(prefix) :], validate=True)
            if sha256(png).hexdigest() != frame.get("png_digest"):
                raise EngineDiagnosticsError("original reference scene PNG digest differs")
            from .game_console_assets import decode_png

            width, height, _ = decode_png(png)
            if (width, height) != (frame.get("width"), frame.get("height")):
                raise EngineDiagnosticsError("original reference scene dimensions differ")
        elif (
            frame.get("render_kind") != "reference_state_telemetry_raster"
            or frame.get("pixel_frame_available") is not False
        ):
            raise EngineDiagnosticsError("reference preview must identify its actual renderer")
        # The invalid command must be stopped by allowlist, never dispatched
        # to an external system or added as an accepted game action.
        denied = False
        try:
            first.step("__untrusted_ai_script__")
        except StudioEnvironmentError:
            denied = True
        if not denied:
            raise EngineDiagnosticsError("runtime executed an undeclared AI command")
        if first.snapshot() != snap:
            raise EngineDiagnosticsError("denied source command mutated world state")
    finally:
        first.close()
        replay.close()
    result = {
        "schema_version": "skeleton.game_builder.engine_contract_probe.v1",
        "engine": editor,
        "seed": seed,
        "source_validation": True,
        "undeclared_fields_rejected": rejection,
        "foreign_engine_rejected": foreign_rejection,
        "same_seed_replay": True,
        "snapshot_reexecution": True,
        "foreign_game_control_rejected": True,
        "native_game_frames_claimed": False,
        "neural_weights_trained": False,
        "full_engine_state_exhausted": False,
    }
    return {**result, "digest": _digest(result)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", choices=ENGINES, required=True)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--limit", type=int, default=32)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args(argv)
    contract = run_engine_contract_diagnostics(args.engine, seed=args.seed)
    actions = engine_action_diagnostics(
        args.engine,
        offset=args.offset,
        limit=args.limit,
        seed=args.seed,
    )
    print(
        json.dumps(
            {"contract": contract, "actions": actions},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
