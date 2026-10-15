"""Explicit local operator for the same Jeeves game-policy learning owners.

Files are private checkpoint/export artifacts, not application authority or
production promotion receipts. No web service or provider credentials are used.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import stat
import sys
import tempfile
from pathlib import Path
from typing import Any

MAX_POLICY_BYTES = 32 * 1024 * 1024
CHECKPOINT_SCHEMA = "skeleton.game.local_parallel_checkpoint.v1"


def _read(path: Path, maximum: int) -> bytes:
    if type(maximum) is not int or maximum < 1:
        raise ValueError("Input byte bound must be positive")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    with os.fdopen(os.open(path, flags), "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size > maximum:
            raise ValueError("Input must be a bounded regular file")
        chunks, size = [], 0
        while size <= maximum:
            chunk = stream.read(min(65536, maximum + 1 - size))
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
        if size > maximum:
            raise ValueError("Input changed beyond its byte limit")
        after = os.fstat(stream.fileno())
        final = os.stat(path, follow_symlinks=False)
        identity = lambda value: (
            value.st_dev,
            value.st_ino,
            value.st_size,
            value.st_mtime_ns,
            value.st_ctime_ns,
        )
        if (
            not stat.S_ISREG(final.st_mode)
            or identity(before) != identity(after)
            or identity(after) != identity(final)
        ):
            raise ValueError("Input identity changed while it was read")
        return b"".join(chunks)


def _json_read(path: Path) -> dict[str, Any]:
    value = json.loads(_read(path, MAX_POLICY_BYTES))
    if not isinstance(value, dict):
        raise TypeError("Checkpoint/project must be a JSON object")
    return value


def _write(path: Path, payload: bytes, *, replace: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink() or path.exists() and not stat.S_ISREG(path.stat().st_mode):
        raise ValueError("Output must be a regular file and cannot be a symbolic link")
    if path.exists() and not replace:
        raise FileExistsError(
            "Output exists; use an explicit resume/fork or replacement option"
        )
    descriptor, temporary = tempfile.mkstemp(prefix=".game-learning-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        if replace:
            os.replace(temporary, path)
        else:
            os.link(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _write_json(path: Path, value: Any, *, replace: bool) -> None:
    payload = (
        json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n"
    ).encode()
    if len(payload) > MAX_POLICY_BYTES:
        raise ValueError("Checkpoint output exceeds its byte budget")
    _write(path, payload, replace=replace)


def _factory(args):
    from .game_learning_parallel import GameEnvironmentRequest

    rom = None
    tree = None
    lineage = {
        "operator": "explicit_local_cli",
        "target": args.target,
        "source_authority": "explicit local operator source choice; no application rights receipt",
    }
    if args.rom:
        from .game_rom_runtime import MAX_ROM_BYTES

        rom = _read(args.rom, MAX_ROM_BYTES)
        lineage["rom_digest"] = hashlib.sha256(rom).hexdigest()
    if args.project:
        project = _json_read(args.project)
        raw = project.get("files", project.get("tree", project))
        if isinstance(raw, list):
            raw = {item["path"]: item["content"] for item in raw}
        if not isinstance(raw, dict):
            raise ValueError("Project input must contain a bounded file mapping")
        tree = raw
        lineage["project_digest"] = hashlib.sha256(
            json.dumps(tree, sort_keys=True).encode()
        ).hexdigest()
    if rom is not None and tree is not None:
        raise ValueError("Select one explicit ROM or project execution source")
    dialect = None
    if tree is not None and "engine/manifest.json" in tree:
        manifest = json.loads(tree["engine/manifest.json"])
        if not isinstance(manifest, dict):
            raise ValueError("Project engine manifest must be an object")
        dialect = manifest.get("gameplay_dialect")
    native = args.core is not None or args.target.startswith("emulator:")
    core_id, registry_digest = None, None
    if native:
        from .game_emulator_catalog import GameEmulatorRegistry

        if rom is None or tree is not None:
            raise ValueError(
                "Installed-core local play requires --rom; large/multifile media use the streamed studio loader"
            )
        registry = GameEmulatorRegistry.from_environment()
        approved = registry.resolve(args.target)
        if args.core is not None and approved.core_id != args.core:
            approved = registry.resolve_core(args.core)
            if args.target.removeprefix("emulator:") not in approved.target_ids:
                raise ValueError(
                    "Requested installed core is not approved for this console"
                )
        core_id, registry_digest = approved.core_id, registry.registry_digest
        lineage.update(core_id=core_id, registry_digest=registry_digest)
    request = GameEnvironmentRequest(
        target_id=args.target,
        max_steps=args.episode_steps,
        tree=tree,
        rom_source=rom,
        cycles_per_step=args.cycles_per_step,
        kind="libretro" if native else "builtin",
        core_id=core_id,
        registry_digest=registry_digest,
        filename=args.rom.name if args.rom else "game.bin",
        frames_per_step=args.frames_per_step,
        gameplay_dialect=dialect,
    )
    factory = request.build
    # Return the serializable request alongside its ordinary environment factory.
    return factory, lineage, request


def _checkpoint(value):
    if value.get("schema_version") != CHECKPOINT_SCHEMA:
        return value, None
    if set(value) != {"schema_version", "policy", "parallel_state"} or not isinstance(
        value["policy"], dict
    ):
        raise ValueError("Local parallel checkpoint envelope is invalid")
    return value["policy"], value["parallel_state"]


def _train(args) -> dict[str, Any]:
    from .game_learning import GameLearningConfig, GamePolicyLearner
    from .game_learning_demonstrations import close_environment

    factory, lineage, environment_request = _factory(args)
    probe = factory()
    try:
        spec = probe.spec
    finally:
        close_environment(probe)
    if args.resume and args.fork_parent:
        raise ValueError("Choose exact resume or an explicit parent-policy fork")
    config = GameLearningConfig(
        seed=args.seed, max_updates=args.max_updates, max_episodes=args.max_episodes
    )
    pending_batch = None
    if args.resume:
        snapshot, pending_batch = _checkpoint(_json_read(args.policy_file))
        learner = GamePolicyLearner.from_snapshot(
            snapshot,
            expected_spec=spec,
            expected_config=config,
            expected_source_lineage=lineage,
        )
        if learner.policy_id != args.policy_id:
            raise ValueError(
                "Resume must retain the original configured policy identity"
            )
    elif args.fork_parent:
        learner = GamePolicyLearner.fork(
            _checkpoint(_json_read(args.fork_parent))[0],
            newpolicy_id=args.policy_id,
            newsource_lineage=lineage,
            config=config,
            expected_spec=spec,
        )
    else:
        if args.policy_file.exists():
            raise FileExistsError("Policy output exists; select resume or a new file")
        learner = GamePolicyLearner(
            spec, config, policy_id=args.policy_id, source_lineage=lineage
        )
    output_created = args.resume
    stop = False

    def cancelled():
        return stop

    parallel = (
        args.workers > 1
        or environment_request.kind == "libretro"
        or pending_batch is not None
    )

    def checkpoint(snapshot, trace, batch_state=None):
        nonlocal output_created
        if args.trace_directory and trace is not None:
            name = hashlib.sha256(trace["episode_id"].encode()).hexdigest() + ".json"
            destination = args.trace_directory / name
            if destination.exists():
                if _json_read(destination) != trace:
                    raise ValueError(
                        "Existing episode trace differs from the admitted episode"
                    )
            else:
                _write_json(destination, trace, replace=False)
        # The policy file is the commit point; no fallible audit write follows it.
        payload = (
            {
                "schema_version": CHECKPOINT_SCHEMA,
                "policy": snapshot,
                "parallel_state": batch_state,
            }
            if parallel
            else snapshot
        )
        _write_json(args.policy_file, payload, replace=output_created)
        output_created = True

    try:
        if parallel:
            from .game_learning_parallel import ParallelGamePolicyTrainer

            result = ParallelGamePolicyTrainer(
                learner, environment_request, actors=args.workers
            ).train(
                episodes=args.episodes,
                resume_state=pending_batch,
                on_checkpoint=checkpoint,
                cancel=cancelled,
            )
        else:
            result = learner.train(
                factory,
                episodes=args.episodes,
                on_checkpoint=checkpoint,
                cancel=cancelled,
            )
    except KeyboardInterrupt:
        stop = True
        return {
            "status": "interrupted",
            "message": "Only complete checkpointed episodes are preserved.",
            "policy_file": str(args.policy_file),
        }
    return {
        "status": "candidate_trained",
        "algorithm": "frozen_batch_local_actor_q_v1"
        if parallel
        else "tabular_q_learning_v1",
        "workers": args.workers if parallel else 1,
        "updates": result.updates,
        "committed_episodes": result.snapshot["committed_episodes"],
        "policy_digest": result.snapshot["snapshot_digest"],
        "policy_file": str(args.policy_file),
        "production_promotion": False,
    }


def _evaluate(args) -> dict[str, Any]:
    from .game_learning import GamePolicyLearner
    from .game_learning_demonstrations import close_environment

    factory, _, _ = _factory(args)
    probe = factory()
    try:
        spec = probe.spec
    finally:
        close_environment(probe)
    learner = GamePolicyLearner.from_snapshot(
        _checkpoint(_json_read(args.policy_file))[0], expected_spec=spec
    )
    baseline = (
        None if args.baseline is None else _checkpoint(_json_read(args.baseline))[0]
    )
    result = learner.evaluate(
        factory, heldout_seeds=args.heldout_seed, baseline_snapshot=baseline
    ).as_dict()
    _write_json(args.evidence_file, result, replace=args.force)
    return {
        "status": "candidate_measured",
        "evaluation_digest": result["evaluation_digest"],
        "evidence_file": str(args.evidence_file),
        "production_promotion": False,
    }


def _native(args) -> dict[str, Any]:
    from .game_rom_generation import build_original_dmg_game

    result = build_original_dmg_game(seed=args.seed, title=args.title)
    rom = base64.b64decode(result["rom_base64"], validate=True)
    _write(args.output, rom, replace=args.force)
    _write_json(
        args.output.with_suffix(args.output.suffix + ".json"),
        result["manifest"],
        replace=args.force,
    )
    return {
        "status": "original_rom_built",
        "rom_digest": result["rom_digest"],
        "rom_bytes": result["rom_bytes"],
        "output": str(args.output),
        "hardware_compatibility_verified": False,
    }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    commands.add_parser(
        "catalog", help="Print actual target/source/execution readiness"
    )
    native = commands.add_parser(
        "build-dmg", help="Build an original seeded maze cartridge"
    )
    native.add_argument("--seed", type=int, default=0)
    native.add_argument("--title", default="Signal Garden")
    native.add_argument("--output", type=Path, required=True)
    native.add_argument("--force", action="store_true")
    for name in ("train", "evaluate"):
        command = commands.add_parser(name)
        command.add_argument("--target", required=True)
        command.add_argument("--rom", type=Path)
        command.add_argument("--project", type=Path)
        command.add_argument("--episode-steps", type=int, default=256)
        command.add_argument("--cycles-per-step", type=int, default=1824)
        command.add_argument(
            "--core", help="Explicit approved installed libretro core identity"
        )
        command.add_argument("--frames-per-step", type=int, default=1)
        command.add_argument("--policy-file", type=Path, required=True)
        if name == "train":
            command.add_argument("--episodes", type=int, default=16)
            command.add_argument("--max-episodes", type=int, default=1024, help="Policy horizon, 1–8192 episodes; larger work uses explicit checkpoints")
            command.add_argument("--seed", type=int, default=0)
            command.add_argument("--max-updates", type=int, default=65536)
            command.add_argument("--policy-id", default="local-game-policy")
            command.add_argument("--resume", action="store_true")
            command.add_argument("--fork-parent", type=Path)
            command.add_argument("--trace-directory", type=Path)
            command.add_argument("--workers", type=int, default=1, choices=range(1, 9))
        else:
            command.add_argument(
                "--heldout-seed", type=int, action="append", required=True
            )
            command.add_argument("--baseline", type=Path)
            command.add_argument("--evidence-file", type=Path, required=True)
            command.add_argument("--force", action="store_true")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "catalog":
            from .game_console_catalog import execution_inventory

            result = execution_inventory()
        elif args.command == "train":
            result = _train(args)
        elif args.command == "evaluate":
            result = _evaluate(args)
        else:
            result = _native(args)
        print(json.dumps(result, sort_keys=True, allow_nan=False))
        return 0
    except (ValueError, TypeError, OSError, KeyError) as exc:
        print(
            json.dumps({"status": "rejected", "message": str(exc)[:1000]}),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
